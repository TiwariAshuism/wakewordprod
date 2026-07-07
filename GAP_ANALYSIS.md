# AURA — Gap Analysis vs `product/` Spec

What the `product/` docs require vs. what the v0/v1 vertical slice actually implements.
Sourced from all 10 `product/` files (SAS §3/§17/§18/§19, Stage-8/9, addendum, the
final gap analysis, phase-1 audit, production-architecture review, expert-panel review,
research report, investment-committee report).

**Read this correctly — there are two kinds of "missing":**
- **(A) Architecture/engineering vs the Stage-7 SAS** — *mostly implemented*, because the
  SAS turned the review findings into ADRs the slice was built against.
- **(B) The real model + production-readiness + legal/compliance** — *mostly absent*,
  largely because the kickoff explicitly scoped a single-platform vertical slice with a
  placeholder model. The bulk of what the reviews flag as "blocking for production" lives
  here.

Items already disclosed in `REPORT.md`/`REPORT_v1.md` are marked ✓flagged. Items **not
previously surfaced** in those reports are marked ★NEW — those are the real answer to
"what else is missing."

---

## A. Architecture findings — STATUS (12 arch-review findings + 5 panel gaps)

| Finding (review) | Status in slice |
|---|---|
| F1 Platform Abstraction Layer (`IPlatform`) | **BUILT** (`core/platform` + Android impl) |
| F2 Buffer ownership / backpressure (SPSC ring, move-not-copy, drop policy) | **BUILT** (`core/common/ring_buffer.h`, `core/audio`) |
| F3 Heterogeneous/hot-plug mic + **resampler** (polyphase/windowed-sinc) | **MISSING** ★NEW — fixed 16 kHz; only Oboe's built-in SRC; no core resampler, no hot-plug recovery |
| F4 Model lifecycle: `mmap` load + **`swapModel()`** double-buffered hot-swap | **PARTIAL** ✓flagged — mmap load done; hot-swap/`swapModel`/eviction absent |
| F5 Cross-language binding **codegen** (UniFFI/cbindgen) | **PARTIAL** ✓flagged — hand-written JNI; no `sdk/idl` codegen |
| F6 Build system decision (CMake vs Bazel) | **BUILT** (CMake) |
| F7 Lock hierarchy + **lock-order verification tool** (Clang TSA / lockdep-style) | **PARTIAL** ★NEW — hierarchy documented in SAS §6; no-alloc guard exists but **no lock-order checker implemented** |
| F8 Device provisioning / trust-anchor / attestation | **MISSING** ✓flagged (security skipped) |
| F9 Local-discovery protocol (mDNS/BLE) | **MISSING** ✓flagged (discovery skipped) |
| F10 Cascade causal tracing / correlation ID | **BUILT** (`CorrelationId`, minted at VadTriggered) |
| F11 Golden-fixture / deterministic replay | **BUILT** (`tests/golden`) |
| F12 `IInferenceBackend` plugin interface | **BUILT** (ONNX impl; TFLite/ExecuTorch not built) |
| Panel A Multi-device arbitration (ESP-style) | **MISSING** ✓flagged |
| Panel B Three-stage analog/ultra-low-power MCU cascade | **MISSING** ✓flagged (power/MCU skipped) |
| Panel C Priority-inheritance mutexes (firmware) | **PARTIAL** ★NEW — scheduler sets RT priority; no enforced PI-mutex policy/checker |
| Panel D Apple Neural Engine export conventions | N/A (iOS out of scope) |
| Panel E Linux ALSA/PipeWire/PulseAudio ADR | N/A (Linux out of scope) |

**Takeaway:** the slice satisfies most Critical/High *architecture* findings. The
architecture gaps that remain are the skipped modules plus three finer items not called
out before: **a real resampler, a lock-order verification tool, and model hot-swap.**

---

## B. Absent modules / features — ✓already flagged (kickoff scope)

`core/telemetry`, `core/security`, `core/ota`, `core/power` (module), `core/discovery`,
`core/speaker`; Stage-2 verifier; speaker verification/enrollment; hot-swap/OTA/rollback;
remote config / feature flags; multi-device arbitration; telemetry upload / metrics (§13);
full `ILogger`/structured logging; provisioning; multi-wake-word; SDK codegen; all
non-Android platforms. These were explicit kickoff constraints — not re-litigated here.

---

## C. ★NEW gaps surfaced by the product docs (not in prior reports)

### C1. Legal / compliance — **BLOCKING for production, entirely absent from our work**
- **India DPDP Act 2023 + DPDP Rules 2025** compliance *by design* for telemetry/enrollment/
  voice-embedding data (breach rule has **no materiality threshold**; full effect 13 May 2027).
- **CCPA** (California) in the same review scope.
- **Dataset-licensing legal review** — ESC-50 (CC-BY-**NC**, not commercial), AudioSet/YouTube
  redistribution, VoxCeleb research-only terms — **before** any data pipeline is finalized.
- **Patent freedom-to-operate scan** (Alexa/Siri/Google cascade + personalization patents)
  **before** committing the architecture.
  *(SAS §19 lists ADR-Legal-DPDP + ADR-Patent-FTO as Deferred, but our build reports never
  surfaced these as gaps. They are hard Phase-2 gates.)*

### C2. Model + quantization (research/committee, binding ADRs)
- **QAT (quantization-aware training) → INT8 is mandatory for the shipped model** (ADR-004:
  "PTQ only for prototyping, never for shipped models"). Our placeholder is float32, no QAT. ★
  **Still open** (robustness sprint deferred it — Tier-3 #9).
- **ADR-001 head-to-head**: first-stage must be chosen by **BC-ResNet vs MatchboxNet on
  AURA-owned data**. **PARTIALLY ADDRESSED (robustness sprint):** a CNN/BC-ResNet/DS-CNN
  head-to-head is now built (`tools/kws_models.py` + `select_best_model.py`) and DS-CNN was
  selected — but still on **public Speech Commands**, not AURA-owned data, and MatchboxNet
  proper is approximated by DS-CNN. Methodology done; data/arch still placeholder.
- **Two-stage cascade** (small always-on → larger verifier) and **streaming-native inference**
  (per-layer state buffers) — placeholder is single-stage fixed-window. ✓partly flagged
  (streaming = robustness Tier-3 #10, not built).

### C3. Benchmark harness + metrics — `benchmarks/harness` + `dashboards` are **absent** ★NEW
None of these are measured or even wired: **FA/hour** (on real media/TV/podcast negatives,
not Speech Commands), **FRR@fixed-FA/hr**, **ROC/DET curves**, **latency <100 ms on-device**,
**CPU <5%**, **RAM <20 MB**, **battery mAh/hr**, **thermal throttling**, **24-hour & 7-day
soak**, **model cold/warm load time**, **memory-leak detection** (Valgrind/ASan desktop,
heap-tracking embedded). Phase-1 audit §18 makes measured FA/hr + latency on real hardware a
**hard No-Go gate** for any architecture/platform claim.

### C4. CI/CD + MLOps — **none exists** (`.github` absent) ★NEW
No CI pipeline, no **model registry / experiment tracking / reproducible training**, no
**SBOM generation** (ONNX Runtime, Silero, etc.), no **model cards / dataset cards**, no
**drift detection / canary / shadow deployment**. SAS §15/§18 and the gap analysis require these.

### C5. Test categories missing ★NEW (only unit + golden exist)
`tests/fuzz` (malformed audio / model files / OTA packages), `tests/stress` (soak drivers),
integration tests, and hardware-in-loop are all absent (dirs not created).

### C6. DSP — production reference libs not integrated ★NEW/partly-flagged
Audit Priority-Fix #2 names concrete libs to build from: **WebRTC APM (AEC/AGC/NS)**,
**RNNoise**, **CMSIS-DSP**, **KissFFT**. Our DSP is placeholder (custom AGC, minimal NS,
**AEC = no-op**, custom radix-2 FFT instead of KissFFT). Silero VAD ✓ (we did integrate that).

### C7. Runtime / Android EP ★NEW
**"XNNPACK CPU fallback must always be present"** (NNAPI quality varies by OEM) — our
`OnnxRuntimeBackend` configures **no execution providers** (default CPU only). NNAPI/XNNPACK
EP selection is unwired.

### C8. Data / training pipeline (research report §7–8) — **PARTIALLY ADDRESSED (robustness sprint)**
**Now done** (`tools/aura_augment.py` + `train_kws_model.py` + `verify_kws_host.py`): waveform
augmentation (synthetic-RIR reverb, background-noise mixing at an **SNR curriculum**,
**SpecAugment**, speed ±15%, gain/time-shift), **hard-negative `_unknown_` + `_silence_`
class**, and **DET-curve threshold calibration**. **Still open:** TTS synthetic positives
(Piper/Coqui/XTTS), focal loss, codec/clipping sim, MUSAN/AudioSet-scale noise, proper
curriculum scheduling, ASR-mined hard negatives — and all of it on **AURA-owned data**, not
public Speech Commands.

### C9. Personalization + anti-spoofing / security attacks — absent
Speaker verification (**ECAPA-TDNN**, AAM-softmax/VoxCeleb) + **ASVspoof anti-spoofing gate**
(ADR-005: do not market SV as security without it). Also unevaluated: replay, voice-cloning,
**DolphinAttack ultrasonic**, model extraction, adversarial audio. ✓partly flagged (speaker skipped).

### C10. Multilingual / accent — absent
**MSWC** (multilingual spoken words), Common Voice + FLEURS, **accent volume-parity**. Our
"marvin" is a single US-English word. ✓partly flagged.

### C11. Embedded MCU tier (no hardware here, but stated as hard requirements) ★NEW
INT8 + **static allocation / no heap in hot path** (non-negotiable); **DMA-driven capture**;
**watchdog + brownout** as firmware requirements; **flash-wear-aware OTA rollback**; the
three-stage analog wake-on-sound gate (Panel B). Out of scope (Android-only) but flagged.

### C12. Missing ADRs the docs say should exist ★NEW
iOS audio API (AVAudioEngine), embedded RTOS (FreeRTOS), threading/concurrency (before Phase-2a
firmware), few-shot custom-wake-word approach, **Jetson runtime** (in platform list, never got a
runtime rec), Linux ALSA/PipeWire. (Android/Oboe + several others already exist in SAS §19.)

---

## D. Hard production Go/No-Go gates (phase-1 audit §18, verbatim conditions)

**No public architecture/platform commitment until:** (a) AURA's **own measured FA/hr and
latency on real target hardware** exist; (b) **legal review** of dataset licensing + patent
landscape is complete; (c) **security review** decides whether speaker verification is marketed
as security vs. personalization. None of (a)/(b)/(c) is satisfied.

---

## E. Bottom line

- The **architecture** the slice implements is faithful to the SAS and covers most Critical/High
  review findings. Remaining architecture gaps: **resampler, lock-order verification tool,
  model hot-swap**, plus the deliberately-skipped modules.
- The genuinely **new, previously-unsurfaced** gaps worth tracking now: **legal/compliance
  (DPDP/CCPA/licensing/patent FTO)**, the **benchmark harness + all metrics** (`benchmarks/harness`
  is empty), **CI/CD + MLOps** (no CI), **fuzz/soak testing**, **QAT/INT8**, and the
  **Android XNNPACK-fallback** EP config.
- Everything in the **research/model track** (real BC-ResNet cascade, data pipeline, anti-spoofing,
  multilingual, personalization) remains a placeholder — expected, but it is what stands between
  this slice and a shippable product, and per §18 gates it blocks any accuracy/latency claim.

**Update — algorithm robustness sprint (see `ROBUSTNESS_IMPROVEMENTS.md` + `model_comparison.md`):**
partially closed the *algorithm* side of C2/C8 — waveform augmentation + SNR curriculum +
SpecAugment, hard-negative/silence classes, a CNN/BC-ResNet/DS-CNN head-to-head (DS-CNN won),
posterior smoothing, and DET-curve threshold calibration. Measured: clean TP 47.7%→77.4% at
0% FP, ~70–77% under noise. **Unchanged:** it's still the Speech-Commands placeholder (not
AURA-owned data), and this did **not** touch the production gaps — legal/compliance, benchmark
harness + metrics, CI/MLOps, fuzz/soak, QAT/INT8, XNNPACK EP, resampler, lock-order tool,
hot-swap — which remain the real blockers.
