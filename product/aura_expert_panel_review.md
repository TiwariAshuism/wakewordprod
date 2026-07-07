# PROJECT AURA — Expert Panel Review
### Distinguished Engineer / Principal Scientist / Dissertation Committee Pass

Reviewed against all five prior documents in full. Per instructions, only items that are completely absent, materially significant to a FAANG-caliber wake-word team, and backed by real, checked references are reported. Everything else: **Coverage Complete.**

---

## Streaming ASR
Coverage Complete.

## Wake-word detection (core)
Coverage Complete — architecture, cascade, papers (including 2024–2026 additions), and localization losses (HEiMDaL) are already covered.

## Wake-word detection — Multi-device household arbitration

**Genuinely missing.** No document in the set addresses what happens when **more than one AURA-equipped device** is within earshot of the same utterance. This is a distinct problem from "multiple wake words" (which all five documents treat as multiple *keywords* on one device).

1. **Why it matters:** in any multi-device home/office deployment (explicitly a plausible AURA scenario given the product's cross-platform, embeddable positioning), two or more devices will hear the same wake word simultaneously and, without arbitration, will both trigger — a directly user-visible failure mode, not a subtle one.
2. **Why previous documents missed it:** all five documents treat "wake-word detection" as a single-device signal-processing/ML problem; none frame it as a multi-device coordination problem, which sits at the boundary of the ML/DSP scope and a distributed-systems scope explicitly named in this review's search domains but not previously exercised against this specific case.
3. **References:** Amazon's **Echo Spatial Perception (ESP)** is the publicly documented, named precedent — originally on-device proximity/confidence comparison between Echo units, later moved to a cloud-arbitrated implementation (per Amazon's own public product announcements). **Verified** (real, named, publicly documented feature with a multi-year public track record, including well-documented failure modes worth learning from — e.g., publicly reported cases of the wrong device responding after Amazon's cloud migration, which is itself a useful cautionary data point about centralizing arbitration logic).
4. **Affects architecture:** yes — requires either (a) a local device-to-device signal-confidence exchange protocol (offline-friendly, consistent with AURA's privacy-first positioning) or (b) a lightweight local-network coordination service, as a **new subsystem** not present in any current design. Given AURA's "fully offline" requirement is a differentiator against Alexa/Google specifically, a **local, non-cloud arbitration mechanism** would itself be a competitive differentiator versus Amazon's cloud-centralized ESP — worth calling out explicitly as a positioning opportunity, not just a gap to fill defensively.
5. **Should become an ADR:** yes.
6. **Requires experimentation:** yes — confidence-score comparison thresholds and the local coordination protocol's latency budget are both **Needs Experimentation**.
7. **Estimated complexity:** Medium-High (new networked subsystem, though scoped only for local-network operation to preserve the offline positioning).
8. **Priority:** **High** — directly product-visible if AURA is ever deployed as more than one unit in the same space, which is a realistic and common deployment pattern for a smart-speaker-adjacent product.

---

## TinyML — MCU power states and the always-on assumption

**Genuinely missing, and architecturally significant.** All five documents describe a **two-stage cascade** (always-on low-power first stage → higher-power verifier) as the standing recommendation, including for ESP32/Cortex-M targets. None of the five documents examine whether the first-stage model itself is cheap enough to run **continuously while the MCU is in its lowest power states**, as opposed to merely being smaller than the second stage.

1. **Why it matters:** for genuinely coin-cell/battery-longevity-class embedded deployments (a plausible AURA target given the ESP32/Cortex-M platform list and CoBuild Labs' hardware focus), even a small BC-ResNet/DS-CNN-class first-stage model running continuously on an active CPU core draws meaningfully more power than the MCU's deep-sleep state. Production ultra-low-power voice-trigger designs (documented in Espressif's and Silicon Labs' own application notes on "analog wake-on-sound front ends") commonly use a **third, sub-digital stage**: a simple analog or ultra-low-power always-on comparator/energy-threshold circuit that wakes the MCU from deep sleep only on gross acoustic activity, before the digital first-stage KWS model ever runs. Without this, the "always-on first-stage model" as currently scoped implicitly assumes the MCU stays in an active (not deep-sleep) power state continuously, which may be incompatible with the battery-life targets implied by "battery efficient" in the original project brief.
2. **Why previous documents missed it:** the cascade discussion throughout the document set focuses on **model size** as the proxy for power cost, and separately discusses sleep modes/watchdog/brownout as generic embedded hygiene items (`aura_final_gap_analysis.md` §8) — but the two were never connected into the specific question of whether the first-stage *model* is compatible with the MCU's lowest power state, or whether a third, pre-digital gating stage is required.
3. **References:** this pattern (analog/ultra-low-power front-end gating a digital KWS pipeline) is standard, documented production practice in the TinyML/ultra-low-power voice-trigger space (Espressif and Silicon Labs application notes on wake-on-sound analog front ends; general pattern also discussed in the TinyML Foundation's own community materials on always-on sensing architectures). **General Knowledge** — this is established production engineering practice, not a single citable paper, and is flagged accordingly rather than attributed to a specific paper that doesn't exist.
4. **Affects architecture:** yes — potentially requires a **three-stage** (analog/ultra-low-power gate → digital first-stage model → verifier) cascade for the most power-constrained MCU targets specifically, which is a different pipeline shape than the two-stage cascade repeated throughout all five documents for the mobile/desktop tiers.
5. **Should become an ADR:** yes — scoped specifically to the MCU/Cortex-M/ESP32 tier, not the mobile/desktop runtime ADRs already recorded.
6. **Requires experimentation:** yes — actual power draw of the digital first-stage model in AURA's chosen active-vs-sleep MCU states is **Needs Experimentation** on real target silicon.
7. **Estimated complexity:** Medium (mostly a hardware reference-design decision plus a firmware state-machine addition, not new ML research).
8. **Priority:** **Critical** for any coin-cell/ultra-low-power product configuration; **Low** if AURA's MCU tier assumes mains or larger-battery power budgets — the priority is genuinely conditional on a product decision not yet made in any prior document, which is itself worth surfacing.

---

## Embedded DSP / ARM DSP-NPU / Firmware Engineering — Priority Inversion

**Genuinely missing.** "Priority inversion" was explicitly named in this review's own search-domain list and in earlier prompts' embedded-systems topic lists, but no prior document addresses it, despite the real-time audio pipeline's mixed-priority-task structure (interrupt-context DMA capture, task-context inference, lower-priority OTA/logging/telemetry) being discussed extensively elsewhere (`aura_phase1_audit.md` §10, `aura_final_gap_analysis.md` §17's threading-model ADR).

1. **Why it matters:** priority inversion occurs when a low-priority task holds a resource (e.g., a mutex protecting a shared buffer or logging subsystem) needed by a high-priority task, and an unrelated medium-priority task preempts the low-priority holder — indefinitely blocking the high-priority task. In an always-on audio pipeline, if the audio-capture or first-stage-inference task shares any resource with a lower-priority OTA/telemetry task without priority-inheritance protection, this can cause **audio frame drops or missed wake-word detections** under specific, hard-to-reproduce timing conditions — exactly the kind of intermittent field bug that is expensive to diagnose post-ship.
2. **Why previous documents missed it:** the threading/ISR-safety discussion in the document set (correctly) identifies that a design is needed, and even proposes a lock-free ring buffer for the ISR-to-task handoff (`aura_final_gap_analysis.md` §17) — but lock-free ring buffers solve the ISR-to-task handoff specifically, not the broader question of any *other* shared resource (e.g., a shared logging buffer, a shared model-weights-swap lock during OTA hot-reload) between tasks of different priority, which is where priority inversion actually manifests.
3. **References:** the canonical, widely-taught real-world case is the **Mars Pathfinder priority-inversion bug** (1997, publicly documented by JPL/Glenn Reeves in a widely-cited postmortem), resolved via **priority inheritance**; FreeRTOS (already the recommended RTOS per `aura_final_gap_analysis.md` §8) has **built-in priority-inheritance mutex support** specifically for this reason. **Verified** (both the historical incident and FreeRTOS's mutex implementation are well-documented, primary-source-backed facts).
4. **Affects architecture:** yes, at the firmware level — every shared resource crossing task-priority boundaries (not just the DMA/ISR handoff already covered) needs an explicit priority-inheritance-mutex policy.
5. **Should become an ADR:** yes — extend the already-recommended threading-model ADR (`aura_final_gap_analysis.md` §17) to explicitly mandate priority-inheritance mutexes (not plain mutexes) for any cross-priority shared resource, rather than leaving this as an implicit detail under the existing ADR title.
6. **Requires experimentation:** partially — the design principle itself is settled (Needs Experimentation only for verifying no priority-inversion window remains, via stress testing under real scheduling load).
7. **Estimated complexity:** Low (FreeRTOS provides this primitive natively; the work is applying it consistently, not building it).
8. **Priority:** **High** — cheap to fix now as a stated firmware policy, expensive to diagnose later as a field bug if omitted.

---

## Apple CoreAudio / ARM DSP-NPU — Apple Neural Engine architecture-specific model constraints

**Genuinely missing.** CoreML is recommended throughout the document set (`aura_investment_committee_report.md` §2 ADR-002, `aura_phase1_audit.md` §9) as the iOS/macOS runtime, but no document addresses the fact that **CoreML models are not automatically ANE-efficient** — the Apple Neural Engine has specific, publicly documented architectural preferences that materially affect latency/power if ignored.

1. **Why it matters:** Apple's own published guidance shows that a naively-exported transformer-style model (directly relevant to AURA's second-stage verifier, which multiple prior documents flag as a candidate for a small Conformer/transformer architecture) can run substantially slower and less power-efficiently on ANE than one restructured to follow ANE-friendly patterns (e.g., preferring `Conv2d` 1×1 over `Linear`/dense layers, splitting softmax computation across attention heads for better cache residency) — Apple's own published case study reports large latency and peak-memory improvements from these specific restructurings on a reference transformer model. **This directly affects whether AURA's chosen second-stage architecture (§ADR-002/ADR-001 in the investment committee report) will actually get ANE acceleration on iOS/macOS, or silently fall back to CPU/GPU execution at a real power/latency cost the current documents haven't accounted for.**
2. **Why previous documents missed it:** CoreML was treated as a black-box runtime target ("use CoreML on Apple platforms") rather than examined for its specific graph-level constraints — the distinction between "CoreML-compatible" and "ANE-efficient" was never raised.
3. **References:** Apple Machine Learning Research, **"Deploying Transformers on the Apple Neural Engine"** (June 2022, WWDC22, with accompanying open-sourced reference PyTorch→CoreML implementation) — reports the Hugging Face DistilBERT reference case study achieving substantially lower latency and peak memory after ANE-specific restructuring, at power draw as low as 0.07W, **per Apple's own published figures** (General Knowledge — Apple's own reported numbers, not independently re-benchmarked by this review). A 2024 follow-up, **"Deploying Attention-Based Vision Transformers to Apple Neural Engine,"** extends the same principles to vision transformers and is a secondary confirming reference. **Verified** that both articles exist and describe these specific optimization principles.
4. **Affects architecture:** yes, specifically for ADR-001 (first/second-stage model architecture choice) as it applies to the iOS/macOS runtime target — if a transformer-family second-stage model is chosen, it should be built using Apple's published ANE-friendly reference patterns from the outset, not adapted after the fact.
5. **Should become an ADR:** yes — a new ADR specifically for "ANE-compatible model export conventions," distinct from the existing general CoreML runtime ADR.
6. **Requires experimentation:** yes — actual ANE vs. CPU/GPU fallback behavior for AURA's specific model once built is **Needs Experimentation** (Apple does not guarantee ANE placement even for compliant graphs; the `coremltools` compute-unit profiler is the correct tool to verify this, per Apple's own documentation).
7. **Estimated complexity:** Low-Medium (mostly a model-export convention to follow, using Apple's own open-sourced reference implementation as a starting point rather than building from scratch).
8. **Priority:** **Medium-High** — only matters once a transformer-family second-stage verifier is actually chosen (per the still-open ADR-001 experimentation), but should be known *before* that experimentation happens so the iOS/macOS benchmark numbers aren't misleading.

---

## Linux ALSA/PipeWire/PulseAudio

**Genuinely missing.** The document set added explicit audio-capture-API ADRs for Android (Oboe, `aura_final_gap_analysis.md` §6) and iOS (AVAudioEngine, §7) — but **never addressed the equivalent decision for Linux/Raspberry Pi**, despite both being explicit target platforms throughout all five documents.

1. **Why it matters:** modern Linux distributions have moved from **PulseAudio** to **PipeWire** as the default userspace audio server on most current desktop/Raspberry Pi OS releases, sitting above the kernel-level **ALSA** layer; an always-on, low-latency capture pipeline needs an explicit choice among direct-ALSA (lowest latency, least portable across distro audio-server configurations), PipeWire (current default on most modern distros, unifies the audio-server landscape that used to be split between PulseAudio and JACK), or PulseAudio-compatibility-mode (for older/embedded Linux images that haven't migrated). Getting this wrong risks exactly the kind of per-distro fragmentation already flagged as a risk for Android/NNAPI (`aura_investment_committee_report.md` §4) but for Linux specifically, which no document currently addresses.
2. **Why previous documents missed it:** the Linux/Raspberry Pi platform entries in the runtime tables (`aura_phase1_audit.md` §9, `aura_addendum_v4.md` §2) address **inference runtime** (ONNX Runtime + XNNPACK) but never the **audio capture layer**, mirroring the exact gap that was caught and fixed for Android/iOS in `aura_final_gap_analysis.md` but not extended to Linux at the time.
3. **References:** general knowledge of the current Linux audio ecosystem state (PipeWire's adoption as the default on most major distributions' current releases, sitting above ALSA, with PulseAudio/JACK compatibility layers) — **General Knowledge**, not a single citable paper, consistent with how this document set has labeled comparable ecosystem-state claims elsewhere.
4. **Affects architecture:** yes — a concrete new ADR, directly analogous to the Android/iOS ones already recorded.
5. **Should become an ADR:** yes.
6. **Requires experimentation:** yes — actual achievable latency via direct ALSA vs. PipeWire on the specific Raspberry Pi OS image AURA targets is **Needs Experimentation**.
7. **Estimated complexity:** Low-Medium (well-trodden ground for any Linux audio application; the gap is that no decision was recorded, not that the decision is hard).
8. **Priority:** **Medium** — same category and urgency as the Android/iOS audio-API ADRs already recorded; should be closed for consistency before Phase 2a Linux/Pi prototyping begins.

---

## Qualcomm Hexagon DSP / ARM NPU
Coverage Complete for the runtime/EP-level treatment already given (QNN named in `aura_phase1_audit.md` §9); no further architecturally-significant gap at the level of detail this review is scoped to (deeper Hexagon HVX/HMX programming-model detail would be implementation detail, not an architectural omission, per this review's own filtering criteria).

## Android Audio HAL / AudioFlinger
Coverage Complete — already addressed in `aura_final_gap_analysis.md` §6 (Oboe/AAudio/OpenSL ES/AudioFlinger/FastMixer).

## Beamforming, Echo cancellation, Speech enhancement, VAD, Speaker verification, Anti-spoofing, Self-supervised speech, Efficient Transformers, NAS, Continual Learning, Few-shot Learning, Federated Learning, On-device adaptation, Quantization, Pruning, Distillation, Compilation (TVM/MLIR/IREE), ONNX Runtime, ExecuTorch, TensorFlow Lite, CMSIS-NN/DSP, Ethos-U, Edge TPU, MLOps, Benchmark methodology, Dataset methodology, Security, Privacy, OTA, Supply-chain security, Regulatory compliance, Production monitoring, Reliability engineering, Mobile engineering (beyond the audio-API gaps above)

**Coverage Complete** for all of the above at the architectural-decision level this review is scoped to. (Note: MLIR and IREE specifically were considered — TVM is already covered as the compiler-stack option in `aura_phase1_audit.md` §9/`aura_addendum_v4.md` §2, and MLIR/IREE would only be a materially distinct architectural option, not an implementation detail, if TVM proved inadequate; absent that finding, adding them now would not change any current recommendation and is therefore excluded per this review's own filtering rule #9.)

---

## Final Verdict

Coverage is **not** effectively complete — five specific, materially significant gaps were identified above (multi-device arbitration, MCU power-state/cascade-shape interaction, priority inversion, ANE-specific model export constraints, Linux audio-API choice), each meeting all of this review's stated criteria: real production/academic precedent, not implicitly covered, and each capable of changing an architecture decision, an ADR, or an experimentation plan. Of these, **two are Critical/High priority and product-shape-affecting** (MCU cascade architecture for power-constrained targets; multi-device arbitration as both a gap and a potential differentiator), and the remaining three are concrete, boundedly-scoped fixes (priority-inheritance mutex policy; ANE export convention; Linux audio-API ADR) that close out the same category of gap already fixed for Android/iOS. No further search across the listed domains produced findings meeting the full bar set by this review's rule #9 — remaining topics not named above are implementation detail within already-recorded architectural decisions, not omissions from them.
