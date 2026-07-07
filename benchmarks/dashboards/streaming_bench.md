# Streaming-Native Inference: Redundancy Measurement (D2)

Model: `heym.onnx` (input `[1,100,40]`, output `[1,2]`, 9 conv layers, depthwise-separable). Front-end: `tools/aura_frontend.py` (numpy == on-device C++).

Always-on schedule under test: `Stage1Detector` re-scores a **100-frame (1000 ms) window every stage1HopFrames = 10 frames (100 ms)**, i.e. 10 full-window inferences per second, forever.

## 1. Redundant compute (analytic MACs)

One full `[1,100,40]` inference = **3.656 MMACs**.

| layer | op | out shape | MACs |
|---|---|---|---|
| `stem/stem.0/Conv` | Conv | [1, 32, 20, 50] | 288.0 k |
| `net/net.0/dw/dw.0/Conv` | Conv | [1, 32, 20, 50] | 288.0 k |
| `net/net.0/pw/pw.0/Conv` | Conv | [1, 32, 20, 50] | 1.024 M |
| `net/net.1/dw/dw.0/Conv` | Conv | [1, 32, 10, 25] | 72.0 k |
| `net/net.1/pw/pw.0/Conv` | Conv | [1, 64, 10, 25] | 512.0 k |
| `net/net.2/dw/dw.0/Conv` | Conv | [1, 64, 10, 25] | 144.0 k |
| `net/net.2/pw/pw.0/Conv` | Conv | [1, 64, 10, 25] | 1.024 M |
| `net/net.3/dw/dw.0/Conv` | Conv | [1, 64, 5, 13] | 37.4 k |
| `net/net.3/pw/pw.0/Conv` | Conv | [1, 64, 5, 13] | 266.2 k |
| `head/Gemm` | Gemm | [1, 2] | 128 |
| **total** | | | **3.656 M** |

| schedule | inferences/s | **MACs/s** | note |
|---|---|---|---|
| windowed (shipped) | 10 | **36.558 M** | full window every 10 frames |
| streaming (idealized) | 100 (per-frame) | **3.656 M** | each frame's conv footprint computed once |

**Redundancy factor = 10.0x** (= window/hop = 100/10). Under the windowed schedule every 10 ms frame is pushed through the conv stack ~10 times before it leaves the window.

**Achievable always-on-compute reduction: 90%** of convolutional MAC/s (36.558 MMACs/s -> 3.656 MMACs/s).

## 2. Wall-clock throughput (HOST, measured)

Continuous **60 s** stream (5998 frames) through the real front-end, 590 windowed inferences:

- per-inference latency: p50 **0.102 ms**, p95 0.123 ms, mean 0.097 ms
- total inference wall-time for 60s of audio: **58 ms** (real-time factor 0.10% of audio duration)
- real-time budget per hop: 100 ms; headroom ~984x on this host
- **streaming-equivalent estimate: ~6 ms** total (10x less inference wall-time for the same 60s of audio)

> Absolute ms are x86 + onnxruntime desktop and are NOT device-representative. The redundancy factor and MAC ratio are schedule/architecture properties and transfer to device; on a phone this ~10x is the difference between the DSP/NPU waking for one window per hop vs a small per-frame increment, which is the dominant term in always-on wake-word power.

## 3. Power implication

Always-on inference energy is ~proportional to MAC/s at a fixed operating point. Cutting convolutional MAC/s by **90% (10x)** cuts the detector's compute-energy share by the same factor. Wake-word detection is one of the few blocks running 24/7 on a sleeping device, so this compute is on the always-on power budget rather than amortized against active use - the reduction is meaningful for standby battery life.

## 4. Honest remaining step: a causal streaming architecture

The 10x above is the *idealized* bound; it is NOT free with the current model. `heym.onnx` ends in a **global `ReduceMean` over the full [5x13] time-frequency map** (global-window pooling: present) followed by the classifier head. That global pool makes the output a function of the *entire* window, so the network as trained is fundamentally windowed - you cannot emit a correct per-frame posterior by only computing the newest columns.

To realize the win, the remaining step is a **mathematically streaming (causal) model**:

- replace global-window pooling with a **causal temporal aggregator** (causal/streaming convolutions, a ring-buffered receptive field, or an RNN/state so each new frame updates a running state instead of re-pooling the whole window);
- keep strided/downsampling convs **causal** (left-padding only) so no layer needs future frames;
- **retrain** for the streaming objective (per-frame targets) and re-verify FA/hr and FRR - a streaming model is a different model, not a repack of this one;
- export a stateful ONNX (carry the conv/RNN state across calls) so the runtime does the small per-frame increment measured as the idealized schedule above.

This measurement quantifies the prize (10x / 90% always-on conv compute) and localizes the blocker (the global `ReduceMean`); the causal redesign + retrain is the follow-on engineering task.

---

# D2 realized: trained streaming model (`StreamingKWS`)

The causal redesign from §4 is now built, trained, and measured. `tools/streaming_model.py` :: `StreamingKWS` is a purpose-built streaming KWS net (input projection → 6 stacked **depthwise-separable dilated causal** conv blocks, dilations `1,2,4,8,16,32`, each ring-buffered and residual → 1x1 classifier head → **temporal max-pool** over per-frame logits for the clip score). Causal receptive field = **127 frames** (1.27 s), which replaces the 100-frame window.

**Correctness is self-tested** (`python tools/streaming_model.py`): the frame-by-frame `step()` path reproduces the full-clip `forward_frames()` path to `max|Δ| = 2.5e-7` (EQUIVALENT). So the per-frame streaming increment is a mathematically exact substitute for windowed scoring — not an approximation.

Trained with `tools/streaming_train.py`: same cache (`.data/heym_feat2.npz`, speaker-independent split — test speakers `vijay/ritu/rohan` never seen in training), same recipe as `heym_train.py` (cosine LR + 3-epoch warmup, sqrt class weights, label smoothing 0.05, online SpecAugment, 25 epochs). Each 100-frame window is one clip; `forward()` max-pools per-frame logits to the clip logit. Exported to `.data/heym_streaming.onnx` (`forward`, `[1,100,40] -> [1,2]`, verified running under onnxruntime).

## 5. Accuracy — streaming vs windowed (speaker-independent held-out, N=483: 369 pos / 114 neg)

| metric | **STREAMING** (`heym_streaming.onnx`) | **WINDOWED DS-CNN** (`heym_dscnn.onnx`) |
|---|---|---|
| recall | 0.9214 | **0.9756** |
| per-clip FAR | 0.3070 | **0.2807** |
| F1 | 0.9140 | **0.9461** |
| params | 17,906 | 14,338 |
| size (KB) | 83.5 | 58.6 |

**Honest read: the streaming model is modestly WORSE on accuracy, not better.** On the same unseen speakers it gives up ~5.4 pts recall (0.921 vs 0.976), ~2.6 pts per-clip FAR (0.307 vs 0.281), and ~3.2 pts F1 (0.914 vs 0.946), and it is larger (17.9k vs 14.3k params, 83.5 vs 58.6 KB). Accuracy is *comparable* but not at parity — the DS-CNN remains the better detector on this metric. The D2 value proposition is **not** accuracy; it is (a) genuine streaming capability (exact per-frame inference, no window re-scan) and (b) the always-on compute reduction below. Both models are trained/evaluated identically, so this is an apples-to-apples gap, and the gap is real.

Note the small dataset (114 negative clips) makes per-clip FAR coarse (each clip ≈ 0.9 pts); the accuracy verdict is directional. Closing the gap (wider channels, more negatives, tuned operating point) is available follow-on work — it does not change the compute argument.

## 6. Compute win — analytic MMACs/s (this is the D2 payoff)

The streaming model pays a small **per-FRAME** conv cost (each conv emits one output column, ring-buffer supplies the causal context) run at the 100 fps frame rate — versus the windowed schedule re-running a full DS-CNN inference every hop=10 frames.

Per-frame MACs (streaming `step()`, computed from layer shapes in `streaming_train.py`):

| layer | op | MACs/frame |
|---|---|---|
| `inproj` | Conv1d(40→48, k1) | 1,920 |
| `blocks.0..5.dw` | Conv1d(48→48, k3, depthwise) ×6 | 6 × 144 = 864 |
| `blocks.0..5.pw` | Conv1d(48→48, k1) ×6 | 6 × 2,304 = 13,824 |
| `head` | Conv1d(48→2, k1) | 96 |
| **total** | | **16,704 MACs/frame** |

| schedule | rate | **MMACs/s** | note |
|---|---|---|---|
| windowed (shipped DS-CNN) | 10 inferences/s | **36.560** | full 3.656 MMAC window every hop=10 frames |
| streaming (`StreamingKWS`) | 100 frames/s | **1.6704** | 16,704 MACs/frame × 100 fps |

**Compute reduction = 21.89x** (36.56 → 1.67 MMACs/s), i.e. a **95.4% cut** in always-on convolutional MAC/s.

This beats the idealized 10x / 90% bound from §1 because that bound assumed the *DS-CNN's own* per-frame conv footprint (3.656 MMACs/s); the purpose-built streaming net has a smaller per-frame footprint (1.67 MMACs/s), so it wins on two counts at once — no window redundancy **and** a lighter per-frame op. Since always-on wake-word energy is ~proportional to MAC/s at a fixed operating point, this is a ~22x cut in the detector's standby compute-energy share.

## 7. D2 verdict

- **Streaming capability: delivered and proven exact** (`step()` == `forward_frames()`, 2.5e-7).
- **Compute: 21.89x fewer always-on MMACs/s** (36.56 → 1.67), the headline win.
- **Accuracy: comparable but honestly ~3 pts F1 / ~5 pts recall WORSE** than the windowed DS-CNN on the same speaker-independent set. It is not a free upgrade in detection quality; it is a large compute reduction at a small, real accuracy cost.

Reproduce: `python tools/streaming_model.py` (self-test) then `python tools/streaming_train.py` (train + export + this comparison). Metrics dumped to `.data/heym_streaming_metrics.json`.
