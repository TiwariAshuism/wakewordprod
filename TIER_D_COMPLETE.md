# Tier D — Completion Status (Model / Research Track)

_Verified 2026-07-07. Host gates green: `python tools/lint_deps.py core` → **OK**; host test
suite → **50 tests, 0 failed** (the pre-existing 45 + 5 new `StreamingWindow` tests, built with
the documented `-DAURA_USE_MICROGTEST` command including `core/runtime/tests/streaming_window_test.cpp`)._

Legend: **DONE (host)** = built + measured on this Windows/MinGW box, no device/toolchain
excuse. **DATA-GATED** = code is done, the remaining claim needs a corpus we don't have.
**DEVICE-GATED** = needs a physical Android device / MCU to verify.

## Status table

| ID | Item | Host-verifiable part | Status | Data/Device-gated remainder | Artifacts |
|----|------|----------------------|--------|-----------------------------|-----------|
| **D1** | INT8 quantization + QAT ablation (ADR-004) | QAT vs PTQ INT8 controlled ablation on the speaker-independent held-out set; report regenerated from the **saved ONNX** (cheap re-eval, no retrain) using the corrected honest F1-band verdict | **DONE (host)** | — (nothing gated; QAT-on-device latency falls under D3/D5) | `tools/heym_qat.py`, `tools/heym_qat_regen_report.py`, `.data/heym_dscnn_qat_fp32.onnx`, `.data/heym_dscnn_ptq_int8.onnx`, `.data/heym_dscnn_qat_int8.onnx`, `benchmarks/dashboards/heym_qat_report.md`, `tools/quantize_kws.py`, `benchmarks/dashboards/quant_report.md` |
| **D2a** | Streaming redundancy measurement (py) | Analytic MACs + wall-clock always-on stream over shipped `heym.onnx` + `aura_frontend.py` | **DONE (host)** | — | `tools/streaming_bench.py`, `benchmarks/dashboards/streaming_bench.md` |
| **D2b** | Streaming feature-window accumulator (cpp) | Header-only O(1) double-mirror ring window + 5 unit tests (FIFO order, zero pre-roll, naive-reference cross-check, constant-work witness, reset) | **DONE (host)** | — | `core/runtime/StreamingWindow.h`, `core/runtime/tests/streaming_window_test.cpp` |
| **D2c** | Streaming-native *inference* (the full feature) | — | **DEVICE-GATED (not started)** | A causal/stateful model + a stateful `IInferenceBackend` + detector rework, then on-device latency/power validation. Only the measurement + host scaffold above shipped. | (design only) |
| **D3** | Real "hey m" model | Speaker-independent train/eval pipeline; DS-CNN head-to-head winner (58.6 KB, ~98% per-clip recall); INT8 ~38 KB (regenerated to match current float model); FA-reduction round (broad-negative mining + Stage-2 cascade ON) → 0 FA in the measurable corpus | **DONE (host) / DATA+DEVICE-GATED** | ≤0.05 FA/hr needs a **20+ hr licensed negative corpus** (16-min corpus resolves only ~4/hr); FRR/latency/CPU/RAM/battery need a **device + Silero VAD** (host harness uses EnergyVad); corpus is **en-IN-dominant — en-US/GB/AU absent** | `tools/heym_data.py`, `tools/heym_train.py`, `tools/heym_eval.py`, `tools/quant_heym_int8.py`, `HEYM_RESULTS.md`, `HEYM_FA_REDUCTION.md`, `benchmarks/dashboards/heym_report.md`, `apps/android/src/main/assets/models/heym.onnx`, `.../heym_int8.onnx`, `.../heym_stage2.onnx` |
| **D4** | Multilingual / accent robustness | Sarvam-TTS bootstrap: 28 clips (mr/bn/hi-Hinglish/ml/ta/te), idempotent generator, retrain with **no regression** on real en-IN speakers | **DONE (host, bootstrap only) / DATA-GATED** | 28 clips is a seed not a fix; mr/bn gain **unmeasurable without real per-language test data**; **en-US/GB/AU need a Western TTS or real speakers** (Sarvam is India-only). Real robustness needs MSWC/Common Voice/FLEURS or collection. | `tools/sarvam_tts_gen.py`, `MULTILINGUAL_PLAN.md` |
| **D5** | Second-tier inference backends (ADR-002) | TFLite + ExecuTorch conversion toolchains **installed on cp313**; both artifacts produced and verified to load + run vs float ONNX | **DONE (host)** | On-**MCU**/on-device runtime execution (`TfliteMicroBackend` static-arena path; MCU flashing) still **DEVICE-GATED** | `apps/android/src/main/assets/models/heym.tflite` (35 KB), `.../heym.pte` (66 KB), `core/runtime/TfliteMicroBackend.{h,cpp}`, `tools/convert_to_tflite.md`, `benchmarks/dashboards/d5_backends.md` |

## D1 — corrected verdict (regenerated from saved ONNX, no retrain)

The original run wrote the report with an earlier verdict rule while it was still mid-flight;
`tools/heym_qat_regen_report.py` re-scored the three already-exported ONNX models on the same
speaker-independent held-out set (`heym_feat2.npz`, 483 clips: 369 pos / 114 neg) and rewrote
the report with the honest F1-band ranking now in `heym_qat.py`.

| model | hey-m recall | per-clip FAR | F1 | size (KB) |
|---|---|---|---|---|
| fp32 (reference) | 0.973 | 0.307 | 0.941 | 58.6 |
| **plain-PTQ-INT8** | 0.976 | 0.307 | **0.942** | 38.1 |
| QAT-INT8 | 0.883 | 0.351 | 0.887 | 38.1 |

**Verdict: plain-PTQ-INT8 wins (higher F1, Δ = +0.055 over QAT — a material gap, not a tie).**
On this ~14 K-param model PTQ INT8 is already near-lossless; the QAT fine-tune actually cost
recall (0.976 → 0.883). ADR-004's "QAT for shipped models" mandate is satisfied as a *measured
ablation*: it was run, and PTQ is retained because it measurably wins here.

## D2 — headline measurement

Always-on windowed schedule (100-frame / 1000 ms window re-scored every 10 frames / 100 ms) does
**10× redundant conv compute**: one full inference = **3.656 MMACs**; windowed = **36.558 MMACs/s**
vs streaming-ideal **3.656 MMACs/s** → **90.0 % always-on compute reduction** available to a
streaming-native model. The C++ `StreamingWindow` is the O(1)-push state such a model would carry
(constant two-row copy per push, verified independent of window size).

## Brutally-honest bottom line

- **D1** — done (QAT ablation measured; PTQ retained on merit).
- **D2** — host measurement + C++ scaffold done; a **production causal streaming model + on-device
  validation remain** (D2c).
- **D3** — model engineering done; **FA/hr ≤ 0.05 and on-device FRR/latency/CPU/RAM/battery need a
  20+ hr corpus + a device**; corpus is en-IN-dominant.
- **D4** — bootstrap only; **real multilingual robustness needs real per-language train+test data**
  and en-US/GB/AU coverage.
- **D5** — both `.tflite` and `.pte` produced and host-verified (toolchains were *not* blocked on
  cp313 as feared); **on-MCU execution is still device-gated**.
