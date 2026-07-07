# AURA — Algorithm Robustness Backlog (model / DSP / detection)

Scope: **algorithms only** — the model, feature front-end, DSP, VAD, and detection
logic. OTA / security / infra excluded per request. Ranked by robustness-ROI, tailored
to the *current* v1 placeholder (not a generic list). "Now?" = doable in this host env
today (torch + Speech Commands + the aligned front-end already in place).

**Current baseline (what we're improving from):** tiny 3-conv CNN, trained on clean
Speech Commands "marvin", **no augmentation**, bouncy training (val_acc swung 0.33–0.64,
no LR schedule, early-stopped on nothing), flat `_unknown_` bucket, **single-window**
fire at fixed softmax ≥ 0.6, float32. Host metrics: marvin TP 47.7% / FP 0.0% @0.6.

## Sprint status (algorithm-only, host-verified) — RESULTS

**Measured outcome** (host DET sweep, held-out Speech Commands; full table in
`model_comparison.md`). Winner **DS-CNN, 15K params, F1 0.921**:

| operating point | v1 baseline (clean) | v2 dscnn (clean) | v2 dscnn (NOISY) |
|---|---|---|---|
| marvin TP @ 0.6 | 47.7% | **77.4%** | **70.3%** |
| marvin TP @ 0.5 | 55.9% | **83.1%** | **77.4%** |
| non-marvin FP @ 0.5 | 0.7% | 0.0% | 0.3% |

**+30 points** clean TP at 0% false-accept, and **~70–77% recall retained under
noise/reverb/speed** (baseline was never noise-tested). Default `stage1Threshold` moved
0.6 → **0.5** (chosen from this curve). 25/25 host tests green; front-end numpy==C++
alignment preserved; lint OK.

**DONE this sprint:**
- ✅ **#1 augmentation** — `tools/aura_augment.py` (noise @ SNR curriculum, synthetic-RIR
  reverb, speed ±15%, gain, time-shift + online SpecAugment).
- ✅ **#2 posterior smoothing** — `core/detect/Stage1Detector` M-of-N consecutive positive
  windows (`DetectConfig.stage1ConsecutiveWindows=3`); robust to VAD flicker; +2 unit tests.
- ✅ **#3 stabilized training** — cosine LR+warmup, label smoothing, early-stop on marvin-F1
  (monotonic vs the old 0.33↔0.64 bounce).
- ✅ **#4 hard-negative `_unknown_` + dedicated `_silence_` class** (13 classes).
- ✅ **#5 architecture head-to-head** — CNN 32K / BC-ResNet 8K / DS-CNN 15K
  (`tools/kws_models.py`); `tools/select_best_model.py` exported **dscnn** as the winner.
- ✅ **#6 DET threshold sweep** — `tools/verify_kws_host.py` (clean + `--noisy`).

**Deferred (Tier-2/3, noted not built this sprint):** #7 PCEN, #8 deeper VAD tuning,
#9 INT8/QAT, #10 streaming-native, #11 multilingual. Still the Speech-Commands
**placeholder** (now augmented + selected), not the AURA-trained model.

---

## Tier 1 — highest ROI, all doable now on host

### 1. Data augmentation (the single biggest robustness lever — research §7) — ✅ DONE
- **Now?** Yes. `tools/train_kws_model.py` currently trains on *clean* clips only.
- **Add:** background-noise mixing (use the dataset's own `_background_noise_` + optionally
  MUSAN) at an **SNR curriculum** (start clean → down to ~0–5 dB); **RIR/reverb**
  convolution for far-field; **SpecAugment** (time+freq masking on the log-Mel); **speed
  perturbation ±10–20%**; **gain/volume jitter**; random **time-shift** within the window.
- **Why robust:** the model currently only knows clean, centered, close-mic speech. Real
  mics are noisy/reverberant/variable-level; augmentation is what closes that gap. Expect
  the largest jump in noisy-condition recall and the biggest drop in real-world false-fires.
- **Careful:** augment *positives* heavily (marvin is the rare class); mix noise into
  negatives too so the model doesn't learn "noise ⇒ not-marvin."

### 2. Posterior smoothing / multi-window decision in `core/detect` (cheap, high impact) — ✅ DONE
- **Now?** Yes — pure C++ logic in `Stage1Detector.cpp`, no retrain needed.
- **Change:** instead of firing on a *single* window ≥ threshold, smooth the per-window
  marvin posterior (moving average / require **M-of-N consecutive** windows over threshold),
  the classic Chen-et-al. KWS posterior-handling. Keep the refractory.
- **Why robust:** a single spurious high-confidence window (transient noise) currently can
  fire; requiring a short run of agreeing windows sharply cuts false accepts while barely
  hurting recall (a real "marvin" produces many windows). Directly improves FA behavior
  independent of the model.

### 3. Stabilize + lengthen training (fixes the bouncy 0.33–0.64 swing) — ✅ DONE
- **Now?** Yes.
- **Add:** cosine LR schedule + warmup; more epochs (30–50) with **early-stop on marvin-F1**
  (not loss); **label smoothing** (~0.1); optionally **mixup**; track/checkpoint best-F1.
- **Why robust:** current training ends on whatever epoch 14 happened to be. A schedule +
  best-checkpoint selection alone should lift marvin F1 well above 0.65 and make results
  reproducible rather than lucky.

### 4. Real hard-negative structure + a noise/silence class — ✅ DONE
- **Now?** Yes.
- **Change:** the `_unknown_` bucket is currently a flat sample of other words. Instead:
  (a) explicitly include **phonetically-confusable** words as hard negatives and upweight
  them; (b) add a dedicated **noise/silence class** trained on `_background_noise_` chunks.
- **Why robust:** teaches the model the *decision boundary* around "marvin" (e.g. "marvin"
  vs "marvel/margin/martin"-like sounds) and gives it an explicit non-speech target, so it
  false-fires less on noise and near-words. Complements #2.

---

## Tier 2 — strong ROI, moderate effort (host-doable)

### 5. Replace the generic CNN with a KWS-native architecture (ADR-001 direction) — ✅ DONE (dscnn won)
- **Now?** Yes.
- **Change:** swap the 3-conv-block net for **BC-ResNet** (broadcasted-residual, the research
  report's recommended family, ~10–200K params) or **DS-CNN / MatchboxNet**. Keep the same
  `[1,100,40] → [12]` I/O contract so nothing downstream changes.
- **Why robust:** these are designed for streaming KWS — better accuracy at the same tiny
  param budget, and BC-ResNet's frequency-broadcast structure is more noise/shift tolerant
  than a vanilla CNN. This is the model-arch commitment the committee wants (BC-ResNet vs
  MatchboxNet head-to-head).

### 6. Threshold calibration + pick the operating point from a curve (not a guess) — ✅ DONE (threshold 0.6→0.5)
- **Now?** Yes — extend `tools/verify_kws_host.py`.
- **Add:** temperature/Platt scaling so the softmax is calibrated; sweep threshold and pick
  `DetectConfig.stage1Threshold` from a **DET/ROC-style** curve at a target FA rate, instead
  of the hard-coded 0.6. Report TP@target-FA.
- **Why robust:** 0.6 is arbitrary; a calibrated, curve-chosen threshold gives a defensible
  precision/recall trade and adapts if the model changes. Pairs with #2 (smoothing shifts the
  operating point).

### 7. PCEN front-end option (far-field / loudness robustness — research §4.4, ADR-003)
- **Now?** Yes, but requires C++ + numpy parity work.
- **Change:** add **PCEN** (per-channel energy normalization) as a selectable alternative to
  log compression in `core/features/LogMelExtractor` (and mirror in `tools/aura_frontend.py`),
  then A/B it against log-Mel under noise/reverb augmentation.
- **Why robust:** PCEN normalizes channel loudness dynamically — more stable than static
  log-Mel across distance and gain, which is exactly the far-field failure mode. Keep log-Mel
  default; enable PCEN if the A/B shows a win (that's the ADR-003 decision).

### 8. VAD gating tuning (avoid clipping the word / stray triggers)
- **Now?** Partially (Silero is device-only; tune `VadConfig`).
- **Change:** tune Silero threshold + `minSpeechFrames`/`hangoverFrames` so the gate opens
  early enough not to truncate "marvin" and closes cleanly; ensure the detection window is
  well-aligned to the gated speech.
- **Why robust:** if VAD opens late/closes early it truncates the keyword → missed detections;
  if it's trigger-happy it wastes inference. Small tuning, measurable via the host replay.

---

## Tier 3 — larger effort / deployment-numerics (host-doable but heavier)

### 9. INT8 quantization — PTQ to measure, then QAT (ADR-004)
- **Now?** Yes (onnxruntime/torch quantization on host).
- **Change:** PTQ the exported model to INT8 and measure accuracy delta; then **QAT** for the
  shipped model. Verify the INT8 model still hits the host TP/FP.
- **Why robust:** on-device inference *is* INT8; training/evaluating in the deployment numerics
  removes the float↔int8 accuracy surprise and is the committee's binding requirement. Also
  smaller/faster (helps the always-on power budget).

### 10. Streaming-native inference (per-layer state, causal convs)
- **Now?** Partial — bigger change.
- **Change:** move from fixed 100-frame window re-inference every hop to a **streaming** model
  with cached per-layer state (ring-buffer causal convolution), so each new frame updates the
  posterior in O(1) instead of recomputing a 1 s window.
- **Why robust (+efficient):** lower latency, far less compute per frame (enables true always-on
  duty-cycling), and no window-boundary artifacts. This is the research report's streaming-KWS
  formalism; largest engineering lift here.

### 11. More / broader data + multilingual & accent parity
- **Now?** Partial (English Speech Commands only).
- **Change:** add **MSWC / Common Voice / FLEURS** and accent-balanced data; watch volume parity.
- **Why robust:** the placeholder is one US-English word from clean data; real robustness across
  accents/languages needs the broader corpus. Biggest data effort; mostly a real-model concern.

---

## First sprint — ✅ COMPLETED

Delivered `#1 augmentation` + `#3 stable training` + `#4 hard-neg/silence class` +
`#5 arch head-to-head` (in `tools/{aura_augment,train_kws_model,kws_models,select_best_model}.py`),
`#2 posterior smoothing` (`Stage1Detector.cpp`), and `#6 curve-based threshold`
(`verify_kws_host.py`). Result: **47.7% → 77.4% clean TP @0.6 at 0% FP**, and **~70–77% TP
under noise** (dscnn winner). Full numbers in `model_comparison.md`. Next candidates:
`#9 INT8/QAT` (deployment numerics) and `#10 streaming-native` (latency/power).
