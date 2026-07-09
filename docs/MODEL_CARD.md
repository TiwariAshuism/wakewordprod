# Model Card — "hey m" Wake Word (DS-CNN → CNN cascade)

This card documents the **real "hey m" wake-word model** trained on AURA-collected
`dataset/hey_m` data (not the earlier "marvin" placeholder). It is an honest engineering
record: what was measured on-host, and what is explicitly not yet verified.

## Overview
- **Task:** streaming keyword spotting — detect the wake word **"hey m"**.
- **Architecture:** a **two-stage cascade**.
  - **Stage-1 (always-on):** DS-CNN (depthwise-separable CNN), **14,338 params**,
    **58.6 KB** float / **38.0 KB** INT8. Head-to-head winner vs the Stage-2 CNN on the
    size-first selection rule (smaller and higher speaker-independent recall).
  - **Stage-2 (verifier, gated):** an independent CNN, **31,778 params**, **126 KB**, that must
    also agree before a detection fires. It exists to suppress false accepts / confusable fires.
- **Format:** ONNX, input `input` `[1, 100, 40]` (100 log-Mel frames × 40 mels), output `[1, 2]`
  logits (target class = index 1). Per-mel normalization is folded into the graph.
- **Combined footprint:** Stage-1 58.6 KB (38.0 KB INT8); Stage-1+Stage-2 **184.6 KB** — well
  under the < 500 KB size gate.

## Shipped files
- Stage-1 float: `apps/android/src/main/assets/models/heym.onnx`
- Stage-1 INT8: `apps/android/src/main/assets/models/heym_int8.onnx`
- Stage-2 verifier: `apps/android/src/main/assets/models/heym_stage2.onnx`

`heym.onnx` is a byte-identical copy of `.data/heym_dscnn.onnx`; `heym_stage2.onnx` of
`.data/heym_cnn.onnx`.

## INT8 quantization
- **Method:** onnxruntime **static PTQ**, `QuantFormat.QDQ`, **per-channel**, QInt8 weights +
  QInt8 activations, via `tools/quant_heym_int8.py` (verified — prints sizes and runs an INT8
  forward pass).
- **Calibration:** 300 windows from `.data/heym_feat2.npz['Xtr']` (the expanded 17,566-window
  train set).

  > **Terminology collision (flagged — `docs/design/aura_calibration_report.md` §2, `docs/design/adr/ADR-Calibration.md`):**
  > "calibration" here means **quantization calibration** — the PTQ activation-range calibration set
  > that determines INT8 clipping ranges/scale factors. It is **unrelated** to **confidence
  > calibration** (Platt/temperature scaling of the output score, measured by ECE/MCE), which is the
  > subject of ADR-Calibration. Always say which one is meant.
- **Result:** 58.6 KB → **38.0 KB (35.1% smaller)**; INT8 forward pass confirmed, output `[1, 2]`.
- **Fidelity (host, 483 held-out test windows):** float vs INT8 **argmax agreement 99.8%**;
  target recall 0.9756 → 0.9729; accuracy 0.9151 → 0.9130. Quantization is near-lossless here.

## Front-end contract (frozen — `docs/design/aura_sas.md` §19b)
16 kHz mono → DSP (AGC → AEC(no-op) → NS) → 400/160 Hann STFT, 512-pt, 40 **HTK** mel
[20, 8000] Hz, natural-log. Verified numpy == C++ (`tools/verify_frontend_alignment.py`).
Training and on-device inference use the identical front-end.

## Training
- **Data:** `dataset/hey_m` (see `DATASET_CARD.md`) — AURA-collected "hey m" positives + hard
  negatives, plus a broadened negative pool (Speech-Commands words, ambient/noise, and 2×
  augmented copies of the hard confusables). Expanded train set: **17.4k windows (≈6.9k pos /
  10.5k neg)**. Class weights softened (sqrt) so abundant negatives don't bias toward firing.
- **Split:** **speaker-independent** — speakers `ritu`, `rohan`, `vijay` are held out for
  evaluation, so all metrics below reflect **unseen voices** (`tools/heym_data.py`).
- **Tooling:** `tools/heym_train.py`, `tools/heym_data.py`, `tools/heym_eval.py`.

## Metrics — MEASURED (host, speaker-independent)
Held-out set: 369 held-out-speaker positive clips; 15.6-min negative corpus.

| Arch | Params | Speaker-indep F1 | Recall | Size |
|---|---|---|---|---|
| **DS-CNN (Stage-1, winner)** | 14,338 | 0.94 | **~0.976–0.978** | 58.6 KB / 38.0 KB INT8 |
| CNN (Stage-2) | 31,778 | 0.929 | 0.976 | 126 KB |

- **Speaker-independent recall ≈ 97–98%** (per-clip 0.976–0.978; streaming-detectable ~97% by
  direct diagnostic). Corresponding **true false-reject rate ≈ 3%** — clears the ≤ 5% gate. The
  higher 48–72% FRRs seen in the raw sweep are an operating-point-selection artifact (the sweep
  picking over-strict FA=0 points), **not** a model limitation.
- **False-accept reduction (the headline result):** with the Stage-2 cascade, FA/hr went from
  **~1193/hr** (dense-confusable corpus, Stage-1 pre-cascade) to **0.000 in the ~16-min
  measurable corpus** (Stage-1-only was 7.3/hr; the cascade is what drives it to 0).
- **Confusable false-fire (adversarial stress):** **33% → ~0.9–3.5%** (≈3%) with the cascade.
- **Size gate:** MET (58.6 KB / 184.6 KB cascade < 500 KB).

## Honest caveats — NOT yet verified
- **FA/hr is not verified at the 0.05 resolution.** `FA/hr = 0.000` was measured on only a
  **~16-minute** corpus, which bounds the rate at roughly **< 4/hr**, *not* < 0.05/hr. Proving
  ≤ 0.05/hr (1 false accept per 20 hours) requires a **20+ hour licensed real negative corpus**
  (media/TV/podcast). "0.000" is a strong signal, not proof of the hard gate.
- **Data is en-IN-dominant.** Live tags: en-IN 1430/331 (train/test) dwarf hi/ta/te/kn/ml-IN;
  **en-US, en-GB, en-AU are absent**. Cross-accent robustness for the V1 English accents is
  unmeasured. Mitigation (multilingual data expansion) is planned but not yet implemented.
- **All device-bound metrics are unmeasured on this host:** on-device latency, CPU, RAM,
  battery, cold startup, streaming frame period. The host figure of ~0.107 ms/forward-pass is
  wall-clock for one pass and is **not** the device-latency requirement. Measure per
  `DEVICE_RUNBOOK.md`.
- **Streaming FRR was measured with the host harness's crude energy VAD;** the device build uses
  Silero VAD (better gating). Real streaming FRR must be measured on-device.
- **Speaker verification is spec'd, not shipped** (ADR-005).

## Intended use / limitations
- **Intended:** V1 en-IN-first "hey m" wake word on Android, Stage-1 always-on with the Stage-2
  cascade for false-accept suppression.
- **Do not** make a public ≤ 0.05 FA/hr claim, a cross-accent (en-US/GB/AU) claim, or any
  device latency/power claim from this card until the corresponding gaps above are closed.

### References
- `DATASET_CARD.md`, `DEVICE_RUNBOOK.md`.
