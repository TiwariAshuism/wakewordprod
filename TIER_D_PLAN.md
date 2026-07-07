# Tier D — Phased Implementation Plan (model / research track)

How the model track goes from the current **placeholder** (Speech-Commands "marvin", DS-CNN,
INT8) to a **production, AURA-trained** model — split into phases, each marking **what I build**
vs **⟵ what you must provide** (decisions, data, legal, compute, hardware). The blockers are not
code; they are data + decisions + hardware. This plan makes them explicit and ordered.

Current state (updated 2026-07-07): the placeholder is superseded — a **real "hey m" dataset was
placed** and a **real model trained** on it. Done: `tools/heym_{data,train,eval}.py` pipeline
(speaker-independent), **DS-CNN winner** (58.6 KB, 98% per-clip recall), **INT8 (38 KB)**, an
**FA-reduction round** (broad-negative mining + Stage-2 cascade → FA ~1193/hr → 0 in the measurable
corpus, confusable-fire 33%→~3%), a **Sarvam-TTS multilingual bootstrap** (`tools/sarvam_tts_gen.py`,
28 clips, no regression), the INT8 PTQ tool, and the device-guarded TFLite Micro backend. See
`HEYM_RESULTS.md`, `HEYM_FA_REDUCTION.md`, `MULTILINGUAL_PLAN.md`, `SPEAKER_VERIFICATION_PLAN.md`.

---

## ✅ Decisions RECEIVED (2026-07-07) — these unblocked the first real-model pass

1. **Wake word:** **"hey m"**.
2. **Platform:** **Android-only** for V1.
3. **Target metrics (hard / stretch):** FA ≤ 0.05/hr (0.01) · FR ≤ 5% (2%) · latency < 100 ms (60) ·
   size < 500 KB (200) · RAM < 20 MB (10) · CPU < 5% (2) · battery < 10 mAh/hr (5) · startup < 1 s
   (500 ms) · streaming frame 20–30 ms (10–20). All treated as hard requirements.
4. **Accents/languages:** V1 = Indian/American/British/Australian English; V2 = +Hindi, +Hinglish;
   V3 = +Tamil/Telugu/Marathi/Bengali English.
5. **Speaker verification:** in scope, **planned under Tier C** (`SPEAKER_VERIFICATION_PLAN.md`).
6. **Budget:** using existing data + synthetic generation where possible (Sarvam TTS, ~40-credit cap).

### ⟵ Still needed from you (the remaining critical-path gates)
- **20+ hour licensed negative corpus** (media/ambient) — to *verify* FA/hr ≤ 0.05 (unmeasurable in 16 min).
- **A real Android device + APK build** — for latency/CPU/RAM/battery/startup + true FRR with **Silero VAD**.
- **en-US / en-GB / en-AU** positive data — real speakers or a Western TTS (Sarvam is India-only).
- **Legal** — dataset-licensing review, DPDP/CCPA consent for collected voice data.

---

## Phase D-1 — QAT + deployment numerics *(engineering; ~days)*
Finish ADR-004: quantization-aware training so the *shipped* model is trained in INT8 numerics.
- **I build:** `--qat` path in `train_kws_model.py` (fuse → prepare_qat → train → convert),
  QAT-vs-PTQ ablation table, INT8 export. (PTQ is already lossless on the placeholder, so this
  is the process/insurance ADR-004 mandates and validates the pipeline before real data.)
- **⟵ You provide:** decision #3 (target metrics) so we know the accuracy/size envelope. Nothing else.
- **Deliverable:** measured QAT-INT8 model + ablation; unblocks "INT8 by construction" for D-3.

## Phase D-2 — Streaming-native inference *(engineering; ~1–2 wks)*
Replace the fixed 1 s re-window with a causal streaming model + stateful runtime (lower latency,
far less always-on compute → the power win).
- **I build:** a stateful `IInferenceBackend` (per-layer state cache), a causal streaming model
  (ring-buffer conv, Rybakov-style), detector integration, and a host prototype quantifying the
  compute reduction.
- **⟵ You provide:** a **real device** to confirm the latency/power win (host numbers aren't
  device-representative — DEVICE_RUNBOOK.md). Decision #3's latency/power budgets.
- **Deliverable:** streaming model + measured MACs/frame reduction; on-device latency (needs your device).

## Phase D-3a — Data pipeline & corpus *(PARTIAL — dataset placed; corpus scale-out still yours)*
- **✅ Built:** `tools/heym_{data,train,eval}.py` — speaker-independent loader/split, augmentation +
  **hard-negative mining** (broad Speech-Commands + ambient + augmented confusables), streaming-detector
  eval mirror. A real **`dataset/hey_m/`** was placed (2095 pos / 1430 neg, 20+ speakers, en-IN-dominant
  with hi/ta/te/kn/ml tags).
- **⟵ Still yours (critical path):**
  - **20+ hr licensed negative corpus** (media/ambient) for a *measurable* FA/hr (the audit's §10 req).
  - **en-US/GB/AU** positives + more speakers per accent; real per-language **test** splits for V2/V3.
  - **Legal:** dataset-licensing review + DPDP/CCPA consent; **storage + experiment tracking**.
- **Deliverable:** a versioned, licensed corpus at scale. Placed data got us a first pass; scale is yours.

## Phase D-3b — Train & evaluate the real model *(FIRST PASS DONE)*
- **✅ Done:** DS-CNN/CNN/BC-ResNet head-to-head on the placed data → **DS-CNN winner** (58.6 KB, 98%
  per-clip / ~97% streaming recall, position-robust), **INT8 38 KB**. **FA-reduction round**: broad-negative
  mining + softened weights + **Stage-2 cascade** → FA ~1193/hr → **0 in the measurable corpus**,
  confusable-fire 33%→~3%. Honest reports: `HEYM_RESULTS.md`, `HEYM_FA_REDUCTION.md`, `heym_report.md`.
- **⟵ To CLAIM the gate:** the 20+ hr corpus (verify ≤0.05 FA/hr) + on-device eval (Silero VAD +
  latency/CPU/RAM/battery). These are measurement/data gates, not model defects.
- **Deliverable:** ✅ a real "hey m" model meeting recall + size; ⏳ a *verified* FA/hr + on-device numbers.

## Phase D-4 — Multilingual / accent expansion *(BOOTSTRAP DONE; scale-out pending)*
- **✅ Done:** `tools/sarvam_tts_gen.py` (Sarvam TTS, idempotent, budget-prioritized) → **28 synthetic
  clips** (Marathi/Bengali/Hindi-Hinglish/Malayalam/Tamil/Telugu); retrained with **no regression**.
- **Limits / ⟵ still yours:** 28 clips is a seed, not robustness; mr/bn gain **unmeasurable** without real
  per-language **test** data; **en-US/GB/AU need a Western TTS or real speakers** (Sarvam is India-only);
  real volume via **MSWC / Common Voice / FLEURS** or collection + a per-language **volume-parity budget**.
- **Deliverable:** ⏳ locale-tiered models with per-locale FA/hr / FRR on *real* test data.

## Phase D-5 — Device runtime backends *(engineering + your hardware; ~1–2 wks each)*
- **I build:** finish the **TFLite Micro** path (produce INT8 `.tflite` per `convert_to_tflite.md`,
  wire `TfliteMicroBackend` into the ESP-IDF/Cortex-M build), evaluate **ExecuTorch** as an
  alternative, per-device numerics validation.
- **⟵ You provide:** **target MCU dev boards** (ESP32-S3, a Cortex-M board), a **TensorFlow-capable
  build/CI** (absent in the current image), and ideally a **device farm + power rig** for HIL and
  battery benchmarks.
- **Deliverable:** the model running on the MCU tier with measured RAM/power.

---

## Dependency order & who unblocks what

```
D-1 (QAT) ─┐                      [me]
D-2 (streaming) ─┐                [me] + your device to measure
                 ├─► D-3b (train real) ─► D-4 (multilingual) ─► D-5 (MCU deploy)
D-3a (DATA + LEGAL + BUDGET) ─────┘   ⟵ YOU: the critical path
```

- I can start **D-1 and D-2 immediately** (pure engineering) while you work D-3a.
- **D-3b/D-4/D-5 are all gated on D-3a**, which is gated on **your** decisions #1–#6 + data + legal + budget.
- Nothing past D-2 can produce *claimable* numbers until the AURA corpus exists (committee No-Go gate).

## Your action checklist (updated — what's left)

- [x] Decisions #1–#6 (wake word, platform, metrics, accents, SV, budget) — **received**
- [x] Placed a real dataset (`dataset/hey_m/`) — **first real-model pass ran on it**
- [x] Multilingual bootstrap via Sarvam TTS — **done (seed)**
- [ ] **20+ hr licensed negative corpus** — to *verify* FA/hr ≤ 0.05 (the current blocker on that gate)
- [ ] **A real Android device** (+ let me build the APK) — for latency/CPU/RAM/battery + Silero-VAD FRR
- [ ] **en-US / en-GB / en-AU** positives — real speakers or a Western TTS (Sarvam can't)
- [ ] Real **per-language test** splits (mr/bn/…) so multilingual gains are measurable
- [ ] **Legal** — dataset-licensing review + DPDP/CCPA consent
- [ ] (later) MCU boards + TF/CI for **D-5**

**What I can do next without you:** **D-2 (streaming-native inference)** — the largest unbuilt
engineering piece, directly serving your latency/CPU/battery targets. Everything with *claimable*
FA/hr or on-device numbers waits on the corpus + a device above.
