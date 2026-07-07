# D2 — Streaming-Native Inference: Implemented, Trained, Measured, Host-Verified

Status: **`[~]` — model + C++ detector done and host-verified; only on-device wiring/validation remains.**

D2 replaces the always-on **windowed** detector (re-run a full `[1,100,40]` DS-CNN inference
every hop = ~10× redundant conv compute) with a **causal streaming** path that consumes ONE
log-Mel frame at a time and emits a wake posterior per frame — no window re-scan. This document
records what was built, how it was verified on the host, the trained accuracy, the measured
compute reduction, and — honestly — what still requires a device.

---

## 1. The causal streaming model (`StreamingKWS`)

`tools/streaming_model.py` :: `StreamingKWS`:

- input projection `Conv1d(40→48, k1)`,
- **6 stacked depthwise-separable dilated causal conv blocks**, dilations `1, 2, 4, 8, 16, 32`,
  each left-padded only (no future frames), ring-buffered, BN + ReLU, **residual**,
- `1×1` classifier head → per-frame logits,
- clip score = **temporal max-pool** over the per-frame positive logit.

**Causal receptive field = 127 frames (1.27 s)** — this *is* the streaming replacement for the
fixed 100-frame (1.0 s) window. Parameters: **17,906**.

### Streaming step == full forward (exact, self-tested)

The load-bearing correctness property: the frame-by-frame `step()` path (each call advances
per-layer ring-buffer state by exactly one frame) must be **mathematically identical** to the
full-clip `forward_frames()` path — otherwise streaming would be an approximation, not a
substitute.

```
$ python tools/streaming_model.py
receptive_field=127 frames  params=17906
max |forward_frames - step| = 2.46e-07  -> EQUIVALENT
```

`max|Δ| = 2.5e-7` (float round-off only). So the per-frame streaming increment is an **exact**
substitute for windowed scoring, not a lossy one. **This self-test still passes** as of this
verification pass.

---

## 2. Trained accuracy vs the windowed model

Trained by `tools/streaming_train.py` — same cache (`.data/heym_feat2.npz`), same
**speaker-independent** split (test speakers `vijay / ritu / rohan` never seen in training),
same recipe as `heym_train.py` (cosine LR + 3-epoch warmup, sqrt class weights, label smoothing
0.05, online SpecAugment, 25 epochs). Each 100-frame window is one clip; `forward()` max-pools
per-frame logits to the clip logit. Exported to `.data/heym_streaming.onnx` and verified running
under onnxruntime.

Held-out speaker-independent set, N=483 (369 pos / 114 neg):

| metric      | **STREAMING** (`heym_streaming.onnx`) | **WINDOWED DS-CNN** (`heym_dscnn.onnx`) |
|-------------|:-------------------------------------:|:---------------------------------------:|
| recall      | 0.9214                                | **0.9756**                              |
| per-clip FAR| 0.3070                                | **0.2807**                              |
| F1          | 0.9140                                | **0.9461**                              |
| params      | 17,906                                | 14,338                                  |
| size (KB)   | 83.5                                  | 58.6                                    |

**Honest read: the streaming model is modestly WORSE on detection accuracy, not better.** On the
same unseen speakers it gives up ~5.4 pts recall, ~2.6 pts per-clip FAR, ~3.2 pts F1, and it is
larger (17.9k vs 14.3k params). Both models were trained/evaluated identically — this is an
apples-to-apples gap, and it is real. The D2 value proposition is **not** accuracy; it is
(a) genuine streaming capability (exact per-frame inference, no window re-scan) and (b) the
always-on compute reduction below. The small negative set (114 clips) makes per-clip FAR coarse
(~0.9 pts/clip); closing the accuracy gap (wider channels, more negatives, tuned operating point)
is available follow-on work and does not change the compute argument.

---

## 3. Measured compute reduction (MMACs/s: windowed vs streaming)

Always-on schedule: the windowed `Stage1Detector` re-scores a 100-frame window every
`stage1HopFrames = 10` frames → 10 full DS-CNN inferences/s (3.656 MMACs each). The streaming
model instead pays a small **per-frame** conv cost (each conv emits one output column; the
ring-buffer supplies causal context) at the 100 fps frame rate.

Per-frame streaming cost (from layer shapes in `streaming_train.py`):

| layer            | op                          | MACs/frame |
|------------------|-----------------------------|-----------:|
| `inproj`         | Conv1d(40→48, k1)           | 1,920      |
| `blocks.0..5.dw` | Conv1d(48→48, k3, dw) ×6    | 864        |
| `blocks.0..5.pw` | Conv1d(48→48, k1) ×6        | 13,824     |
| `head`           | Conv1d(48→2, k1)            | 96         |
| **total**        |                             | **16,704** |

| schedule                       | rate            | **MMACs/s** |
|--------------------------------|-----------------|------------:|
| windowed (shipped DS-CNN)      | 10 inferences/s | **36.560**  |
| streaming (`StreamingKWS`)     | 100 frames/s    | **1.6704**  |

**Compute reduction = 21.89× (36.56 → 1.67 MMACs/s) — a 95.4% cut in always-on convolutional
MAC/s.** This beats the earlier idealized 10×/90% bound (`streaming_bench.md` §1), which assumed
the DS-CNN's *own* per-frame footprint; the purpose-built streaming net wins on two counts at
once — no window redundancy **and** a lighter per-frame op. Since always-on wake-word energy is
~proportional to MAC/s at a fixed operating point, this is a ~22× cut in the detector's standby
compute-energy share.

Full analysis: `benchmarks/dashboards/streaming_bench.md` §5–§7.

---

## 4. C++ StreamingDetector + tests (host-verified)

The on-device decision logic is implemented as the per-frame counterpart of `Stage1Detector`:

- `core/detect/StreamingDetector.h` / `.cpp` — declares **`IStreamingScorer`** (abstract,
  stateful per-frame scorer: `scoreFrame(const float* mel, int n) -> float`; the host supplies a
  scripted fake, the device supplies the streaming ONNX model) and **`StreamingDetector`**, which
  applies the **same decision policy** as the windowed path — `stage1Threshold` gate +
  `stage1ConsecutiveWindows` M-of-N consecutive positive **frames** + `refractoryFrames` — with
  **no re-windowing**, one score per frame. The scorer is always advanced (even in refractory) so
  the stateful model never sees a gap. Hot path (`pushFrame`) is allocation-free under
  `ScopedNoAllocGuard`; the rare detection edge opens the documented `ScopedAllowAllocGuard`
  escape hatch, mirroring `Stage1Detector::confirm`. Row 6 deps only (core/config + core/common).
- `core/detect/tests/streaming_detector_test.cpp` — **6 tests**: fires on a sustained M-consecutive
  high run; requires M consecutive frames; no fire below threshold; refractory prevents double-fire;
  re-arms after refractory elapses; allocation-free hot path (under `ScopedNoAllocGuard`).

### Host suite result

Built with the documented host command (adding `core/detect/StreamingDetector.cpp` to the
explicit source list — the `core/*/tests/*.cpp` glob already picks up the new test):

```
[==========] 56 tests, 0 failed
```

**56 tests, 0 failed** = the 50-test baseline + the 6 new `StreamingDetect.*` tests, all green.
`python tools/lint_deps.py core` prints **OK** (row order, PAL isolation, no cycles).

> Fix applied during verification: the documented build line listed `Stage1Detector.cpp` but not
> the new `StreamingDetector.cpp`, so the link failed on undefined `StreamingDetector` symbols.
> Adding `core/detect/StreamingDetector.cpp` to the object list (as done for every other module
> `.cpp`) resolves it; no source change was needed and the pre-existing suite stays green.

---

## 5. What REMAINS (device-gated)

The model math, the compute win, and the C++ decision logic are done and host-verified. Two
pieces genuinely require hardware and are **not** claimed complete:

1. **A stateful streaming ONNX / backend wired for on-device execution.** Today the exported
   `heym_streaming.onnx` runs its *full* `forward` for training/accuracy comparison, and the C++
   `StreamingDetector` is driven on the host by a scripted `IStreamingScorer` fake. To realize the
   1.67 MMACs/s on device, the `step()` state (the per-block ring buffers) must be exported as a
   **stateful ONNX graph carrying state across calls** and wrapped behind a real
   `IStreamingScorer` that runs one streaming step per frame in the on-device runtime.
2. **On-device latency / power validation.** The 21.9× / 95.4% compute reduction is an
   analytic MAC/s property (architecture + schedule) and transfers to device in principle, but the
   actual standby latency and power/battery win must be **measured on the target Android/DSP/NPU**.
   No such device is available in this environment.

Everything else — causal architecture, exact streaming equivalence, trained accuracy, measured
compute reduction, and the C++ detector + tests — is implemented and verified on the host.

---

## Reproduce

```
python tools/lint_deps.py core                 # -> OK
python tools/streaming_model.py                # -> EQUIVALENT (step == forward, 2.5e-7)
python tools/streaming_train.py                # train + export + accuracy comparison
# host test build (add core/detect/StreamingDetector.cpp to the documented g++ line):
#   ... core/detect/Stage1Detector.cpp core/detect/StreamingDetector.cpp ...
#   -> [==========] 56 tests, 0 failed
```
