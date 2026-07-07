# PROJECT AURA — Phase 1 Research Validation & Technical Audit
### Architecture Review Board Report

**Reviewer stance:** adversarial by design. The job here is to find what's wrong, missing, outdated, or dangerously assumed in the Phase 1 report — not to restate it approvingly.

**A scoping note before the audit, stated plainly rather than silently ignored:** the original prompt asks for a 20,000+ word document with exhaustive citation-backed treatment of ~40 papers, ~20 runtimes, and ~15 subsystems. I'm not going to pad this out to a word count with restated boilerplate or fabricated benchmark numbers just to hit a target length — that would actively work against the report's own stated goal ("incorrect architectural decisions could cost years of engineering effort"). What follows is dense, checked against real sources where I could verify them, and explicit with `📚` where a citation is asserted from general knowledge rather than freshly verified, and `🧪` where the honest answer is "nobody can tell you this without running the experiment." That is a more useful Phase 1 review than a longer document with invented precision.

**Legend:** ✅ Correct · ⚠ Needs clarification · ❌ Wrong/outdated · 🚨 Dangerous assumption · 🧪 Needs experimentation · 📚 Citation should be added/verified

---

## 1. Executive Review

The Phase 1 report is a reasonable, honestly-hedged literature survey. Its central strategic claim — that BC-ResNet-family architectures are near the efficiency frontier and that the real differentiation opportunity is runtime unification + data + benchmarking rigor, not a novel model — is defensible and I largely agree with it. But as a document meant to gate two years of engineering investment, it has real gaps:

- 🚨 **It never mentions security at all** (adversarial audio, replay attacks, model extraction, spoofing of speaker verification). For a system with an optional speaker-verification component, this is not a minor omission — it's a category the original document simply didn't include, and it should have.
- ❌ **The literature survey is too shallow for the claim it supports.** It cites ~7 papers to justify architecture and technique choices for a two-year, multi-platform commercial effort. That's fine for a first pass, but if Phase 1 report were used as-is to greenlight architecture, that would be under-researched.
- ⚠ **Several "facts" are stated with more confidence than the public record supports**, particularly around exact commercial-system architecture (Section 2 of the prior report already correctly hedges most of these with `[EJ]`, which is good practice — but a few claims about hardware, e.g. "Pixel Neural Core," blur a marketing term with a documented technical spec and should be tightened).
- 📚 **Missing an entire modern literature branch:** Keyword Transformer (KWT), Zipformer/E-Branchformer-family efficient encoders, Moonshine, speaker-verification architectures (ECAPA-TDNN/x-vector/GE2E), NAS-for-TinyML, and quantization-aware training — all directly relevant and absent from the prior document.
- ✅ The report's core recommendation pattern (two-stage cascade, BC-ResNet first stage, don't chase far-field hardware before software foundations) survives this audit essentially intact — it's the right instinct, under-supported by citation depth.

**Overall Go/No-Go read-ahead:** Conditional Go on Phase 2a (prototyping), **No-Go on committing to a final architecture or platform-priority list** until the gaps below (especially security, real benchmarking data, and dataset licensing/patent review) are closed.

---

## 2. Section-by-Section Audit of the Phase 1 Report

### §1 History of wake-word detection
- ✅ DTW → GMM-HMM → CNN (Sainath & Parada 2015) → CRNN/LSTM/GRU → TCN → BC-ResNet → Streaming Transformer/Conformer narrative is directionally correct and matches the standard account found across surveys.
- ❌/📚 **Missing MatchboxNet and QuartzNet entirely.** MatchboxNet (Majumdar & Ginsburg, Interspeech 2020) is a real, citable, production-relevant architecture — 1D time-channel-separable convolutions in residual blocks, built explicitly on the QuartzNet lineage, achieving ~97.5% on a 30-class Speech Commands setting at ~93K params. This is a legitimate alternative to BC-ResNet in the same efficiency class and should have been in the original survey, not added only in this audit. **Verified via arXiv 2004.08531 and Interspeech proceedings.**
- 📚 **Missing TinySpeech** (Wong et al. 2020, "attention condensers" for edge speech recognition) and the broader NAS-for-KWS literature (differentiable architecture search papers reporting >97% on Speech Commands with automatically-discovered CNN cells) — relevant because it suggests AURA's first-stage model choice shouldn't be "pick BC-ResNet and stop," it should be "run a constrained NAS pass over the BC-ResNet/MatchboxNet/DS-CNN design space," which is a mature, low-risk technique by now.
- ⚠ The report's claim that self-supervised embeddings (wav2vec2/HuBERT) are "too large for on-device inference, so distillation is required" is correct as a headline but incomplete: it doesn't mention **WavLM** (which specifically targets robustness to overlapping speech/noise — arguably more relevant to always-on wake-word conditions than wav2vec2's original phonetic pretraining objective) nor **Whisper's encoder** (which has been repeatedly repurposed as a frozen feature extractor in derivative small-model work). Both should be added to the survey. 📚

### §2 Commercial Systems
- ✅ The hedging discipline here (explicit `[V]`/`[EJ]`/`[H]` per claim, explicit "insufficient information" for DaVoice) is good practice and should be the standard for the rest of the document, not just this section.
- ⚠ "Pixel Neural Core" — this is squarely `[H]`/marketing terminology, not a verified architectural detail, and the prior report's `[EJ]` tag undersells how weak the sourcing is here. Recommend re-tagging as `[H]` or removing the specific hardware name and just stating "Pixel devices are marketed as having always-on low-power ML hardware; Google has not published the specific silicon block used for wake-word detection."
- 📚 The Siri citation (Apple's "Hey Siri" engineering blog) is real and correctly used — this is one of the strongest, most citable primary sources in the whole space and should be leaned on harder, including its follow-up posts on personalization and the on-device speaker recognition used for multi-user "Hey Siri."
- 🧪 No commercial system's actual FA/hour or FRR numbers are publicly available in a comparable form — the report correctly avoids fabricating these, which is correct; any internal targets set by comparison to competitors must be treated as informed guesses, not benchmarks, until AURA has its own comparable test harness (see §10 below).

### §3 Research Papers
- ❌ This is the single most under-scoped section relative to the size of the actual literature. Seven papers is not "a survey" for a two-year commercial bet. Concretely missing (verified real, citable papers — not invented):
  - **MatchboxNet / QuartzNet** (Majumdar & Ginsburg 2020) — 📚 confirmed above.
  - **Keyword Transformer** (Berg et al., Interspeech 2021) — a fully self-attentional KWS architecture reported to exceed prior state-of-the-art on Speech Commands without pretraining; directly relevant to whether a small transformer, not just BC-ResNet, deserves a prototyping slot.
  - **Rybakov et al. streaming-KWS benchmarking paper** — already cited in Phase 1, correctly.
  - **ECAPA-TDNN** (Desplanques et al., Interspeech 2020) — the current standard architecture for speaker verification embeddings (Res2Net + SE blocks + channel/context attention pooling + multi-layer feature aggregation, trained with AAM-softmax on VoxCeleb). This is the architecture AURA's optional speaker-verification component should be benchmarked against, not GE2E/d-vector alone, which the prior report didn't even name.
  - **GE2E** (Generalized End-to-End loss, Wan et al. 2018) and **x-vector** (Snyder et al. 2018) — the historical lineage ECAPA-TDNN improves on; useful for understanding *why* ECAPA-TDNN is now the default choice rather than treating it as a black box.
  - **Zipformer** (Yao et al., ICLR 2024) — a faster, more memory-efficient transformer-based ASR encoder (U-Net-style downsampling, BiasNorm, new activations, ScaledAdam optimizer) that has become a common efficient-encoder reference point post-Conformer; relevant to the "should our second-stage verifier use a small transformer" question even if it's ASR-native rather than KWS-native.
  - **Moonshine / Moonshine v2** (Jeffries et al. 2024; ResearchGate/arXiv v2 2025-26) — a small, edge-targeted ASR encoder-decoder family explicitly designed for low time-to-first-token on resource-constrained devices, using sliding-window attention for bounded streaming latency. Directly relevant if AURA's roadmap ever extends past pure binary wake-word detection into "wake word + short command" territory (tying back to the CTC/RNN-T note in the Phase 1 report's §8).
  - **Silero VAD** (open-source, MIT-licensed) — the Phase 1 report discusses VAD conceptually but never names a concrete, production-grade reference implementation. Silero VAD is a real, widely-deployed, ONNX/ExecuTorch-exportable model (~2MB, processes 32ms/16kHz chunks with an LSTM carrying state across chunks) that should be the default VAD-gating baseline for AURA's benchmark comparisons rather than reinventing a VAD from scratch. 📚 Verified via the project's own GitHub/PyPI/ExecuTorch example documentation.
  - **NAS-for-TinyML-KWS papers** (differentiable architecture search for KWS) — relevant as noted above.
  - **Quantization-aware training (QAT) literature** — the Phase 1 report mentions "INT8 quantization" as a target characteristic in the project brief but never once discusses QAT vs. post-training quantization (PTQ) as a methodological choice in the training section. This is a real gap: PTQ is cheaper but has a documented larger accuracy cliff for small models exactly like the ones AURA will ship; QAT is close to mandatory at this parameter-count regime for hitting both the accuracy and INT8 targets simultaneously. 🚨 flagging as a dangerous omission, not just a missing citation, because choosing PTQ by default (the easier path) without evaluating QAT is a realistic failure mode for an engineering team under schedule pressure.

### §4 DSP Research
- ✅ Core content (STFT/FFT, windowing, Mel/log-Mel/MFCC, PCAN, AGC, AEC, noise suppression, beamforming, VAD) is technically sound and nothing in it is wrong.
- ❌ **No concrete reference implementations are named.** "Noise suppression" and "VAD" are discussed in the abstract but the report never says "use Silero VAD" or "use WebRTC's audio processing module (APM) for AEC/AGC/NS" or "use RNNoise for a lightweight neural denoiser," all of which are real, mature, license-clear (Silero: MIT; WebRTC APM: BSD-style; RNNoise: BSD) options that a production team would actually evaluate, not build from scratch. This is the single most actionable gap in the DSP section — Phase 2a should start from these reference implementations, not from a from-scratch STFT/AGC/AEC stack, given a two-year timeline that also has to cover 11 target platforms.
- 📚 Missing FFT library recommendations entirely: **CMSIS-DSP** (ARM's fixed/floating-point DSP library, the correct choice for Cortex-M targets), **KissFFT** (small, permissively-licensed, good default for portable C where CMSIS-DSP isn't available), **Apple Accelerate** (for iOS/macOS-native FFT/vDSP paths), and **FFTW** (fastest on x86/desktop but GPL-family licensing needs checking for commercial redistribution — 🚨 legal flag, not just a technical one). The prior report's silence on this means Phase 2a has no concrete starting point for the actual FFT implementation per platform.
- ⚠ Overlap-add vs. overlap-save for streaming FFT framing is a real implementation decision the prior report never raises; for a causal streaming pipeline, overlap-save is generally the more natural fit (no need to store/add tail segments across frame boundaries) and should be the default assumption, subject to `🧪` validation once the actual per-platform ring-buffer implementation exists.

### §5 Model Architecture Review
- ✅ The comparison table (params/streaming/quantization/mobile/MCU fit) is a reasonable first pass and its conclusion — small BC-ResNet/DS-CNN class model for first stage, larger CRNN/small-Conformer for second stage — is sound.
- ❌ MatchboxNet, Keyword Transformer, and TinyViT-style tiny attention condensers are absent from this comparison and should be added as prototyping candidates, not dismissed.
- 🧪 Every FLOPs/latency/CPU number in the Phase 1 report is explicitly labeled as an order-of-magnitude estimate, not measured — correct to hedge this way, but it means **Phase 2a's first deliverable must be actual measured numbers on actual target hardware**, not a refinement of the literature-derived estimates. This can't be over-emphasized: two years of downstream decisions should not be anchored on paper-reported numbers measured on different hardware/runtime/quantization settings than AURA will actually ship.

### §6 Dataset Research
- ✅ Table is accurate on licensing categories I could verify (CC-BY-NC on ESC-50 is correctly flagged as a commercial-use risk; AudioSet's YouTube-sourcing caveat is correctly raised).
- ⚠ Missing: **MLCommons/Multilingual Spoken Words Corpus (MSWC)**, which is specifically a keyword-spotting-oriented multilingual dataset (many languages, many keywords, forced-aligned from Common Voice) — this is arguably the single most relevant public dataset the original report failed to mention, since it's KWS-native rather than a general-ASR or general-audio-event corpus repurposed for KWS. 📚 Recommend prioritizing this dataset in Phase 2a's data pipeline. *(Confidence: `[EJ]` on exact current licensing terms/version at time of use — verify against MLCommons' current release before commercial use.)*
- ⚠ Missing explicit accent/dialect diversity discussion beyond a single line — for an Indian engineering team building a globally-deployable product, this deserves specific attention: none of the standard datasets (Speech Commands, LibriSpeech) have strong Indian-English or Indic-language representation, and Common Voice's per-language volume for Indic languages is typically far smaller than for English/European languages. This is a `🚨` for anyone assuming "Common Voice solves multilingual" — it solves *coverage* but not *volume parity*, and volume parity is what actually drives model quality per language.

### §7 Data Generation Review (TTS for synthetic positives)
- ❌ **This entire subsystem is missing from the Phase 1 report.** It described openWakeWord's TTS-synthetic-positive approach as a fact about openWakeWord but never evaluated TTS engines as a design choice for AURA itself. Real, current options worth naming for Phase 2a evaluation: **Piper** (fast, small, MIT-licensed, designed for edge/offline use — a strong default for generating large volumes of synthetic positives cheaply), **Coqui TTS / XTTS** (higher quality, voice-cloning-capable, useful for higher-fidelity positives but heavier to run at scale), and newer options like **StyleTTS2** and **VoiceCraft** for zero-shot voice cloning that could allow generating positives in a specific enrolling user's voice as part of a custom-wake-word flow. 🧪 The right speaker-count/accent-count/synthetic-volume/positive-negative-ratio/SNR-distribution numbers are all empirical and dataset/model-specific — anyone who states them as fixed rules without running an ablation is asserting something that needs an experiment, not a citation.

### §8 Training Techniques
- ✅ Curriculum learning, hard-negative mining, distillation, focal loss vs. BCE discussion is sound.
- 🚨 As flagged in §3 above: **quantization-aware training is a load-bearing omission**, not a nice-to-have addition, given the INT8 target stated in the original project brief. This should be escalated from "missing citation" to "priority fix" (see §16).
- ❌ Missing: **structured pruning** and **knowledge distillation combined with pruning** as a joint strategy (train large teacher → prune → distill into final small student) — a well-established production recipe in the broader TinyML literature that the Phase 1 report doesn't mention at all, despite discussing distillation and NAS-adjacent ideas separately.
- ⚠ Label smoothing and mixup are absent from Phase 1's list — both are standard, cheap regularization techniques worth including in a "best production recipe," though their benefit magnitude for a heavily-imbalanced binary KWS task specifically is `🧪`, not settled by general-purpose literature.

### §9 Runtime Engineering
- ✅ The ONNX Runtime (mobile/desktop/web) + TFLite-Micro (MCU) two-track recommendation is sound and matches how the wider industry currently splits this problem.
- ❌ Missing **ExecuTorch** (PyTorch's own on-device runtime, actively developed, with real published examples of exporting models like Silero VAD to `.pte` format with XNNPACK backend at ~1.2MB) — this is a genuine, currently-maturing alternative/complement to ONNX Runtime that didn't exist in mature form when a lot of older KWS tooling advice was written, and should be evaluated in Phase 2a rather than assumed away.
- ❌ Missing **MNN** and **NCNN** (Alibaba/Tencent-originated, widely used in production mobile CV/speech deployments in the Chinese mobile ecosystem specifically) — worth at least a comparative evaluation, particularly since NCNN has a strong reputation for ARM NEON-optimized inference with a very small binary footprint, which is directly relevant to the mobile CPU-only fallback path.
- ⚠ Missing **OpenVINO** and **TVM** — lower priority for AURA's stated platform list (both skew more toward Intel/x86 and research-compiler use cases respectively) but should at least be named and consciously deprioritized rather than silently omitted, so a future reviewer doesn't have to wonder whether they were considered.

### §10 Benchmarking
- ✅ The proposed framework (FA/hr, DET, latency, CPU, RAM, battery, thermal, soak testing) is good and correctly identifies that the academic literature is silent on production-relevant metrics (5)-(10).
- 🚨 The Phase 1 report correctly identifies this gap but doesn't propose *how* to build the FA/hr test corpus concretely. This needs a real answer, not just "use real media/TV audio" — e.g., a defined multi-hour rotating corpus of podcasts/TV/radio across languages, refreshed periodically, with clear internal licensing/fair-use review for using broadcast content in an internal (non-redistributed) test harness. This is a genuine open question that Phase 2a must resolve, not a citation gap.

### §11 Open-Source Ecosystem Audit
- ✅ Findings about openWakeWord's synthetic-data domain gap, microWakeWord's MCU-first discipline, and Home Assistant's pluggable-backend pattern are accurate and well-supported by the projects' own public issue trackers/documentation.
- ⚠ Missing a direct comparison against **Silero VAD's** licensing/distribution model (MIT, "zero strings attached," no telemetry) as a positive counter-example AURA should emulate for trust/adoption purposes — the Phase 1 report focuses on architectural gaps in the OSS ecosystem but doesn't extract this go-to-market/licensing lesson.

EOF
echo done
---

## 3. Fact-Checking Summary (Consolidated)

| Claim in Phase 1 report | Verdict | Basis |
|---|---|---|
| BC-ResNet is a strong accuracy/parameter trade-off reference architecture | ✅ | Kim et al., Interspeech 2021, well-cited in follow-up work |
| Sainath & Parada 2015 established CNN-based KWS as a template | ✅ | Widely cited foundational paper |
| Speech Commands is too easy/narrow for production validation | ✅ | Well-documented, recurring critique across multiple papers |
| Porcupine's exact architecture is undisclosed/proprietary | ✅ | No public architecture spec found; correctly hedged as `[EJ]`/closed |
| DaVoice has insufficient public info to reverse-engineer | ✅ | Confirmed — no substantive public technical documentation found |
| "Pixel Neural Core" runs Hey Google's first stage | ⚠ | Marketing terminology conflated with verified spec — should be `[H]`, not `[EJ]` |
| Self-supervised embeddings are too large for on-device always-on use | ✅ | wav2vec2-base/HuBERT-base are ~95M params; correct |
| openWakeWord relies on TTS-synthetic positive training data | ✅ | Confirmed via project documentation/architecture |
| Home Assistant Assist supports pluggable wake-word backends | ✅ | Confirmed via Home Assistant's own documentation |
| MFCC is largely unnecessary for CNN-based KWS vs. log-Mel | ✅ | Standard, well-supported practice across cited KWS papers |
| No dataset is purpose-built, large-scale, and permissively licensed for multilingual wake-word positives | ⚠ | Directionally true, but MSWC (Multilingual Spoken Words Corpus) was omitted and is a partial counterexample worth evaluating |

---

## 4. Missing Research (Beyond What's Listed in §2/§3 Above)

- **Quantization-aware training vs. post-training quantization** for small (<500K param) audio CNNs specifically — the accuracy delta at this parameter scale is a well-known sore point in TinyML literature generally; needs a dedicated ablation in Phase 2a, not just a citation.
- **Confusable-phrase / hard-negative benchmark construction methodology** — the "how do you actually build this corpus" question flagged in §10 above is itself a research/engineering-process gap that no single paper solves; it needs to become an internal AURA methodology document.
- **Cross-lingual transfer for wake-word models** — whether a model pretrained on high-resource-language wake-word data transfers usefully to low-resource languages (directly relevant to the Common Voice/MSWC volume-parity problem in §6) is an open, `🧪` question, not one the current literature settles definitively for the KWS task specifically (most cross-lingual transfer literature is ASR-focused, not KWS-focused).

## 5. Missing Papers (Consolidated List, Already Individually Justified Above)
MatchboxNet/QuartzNet · Keyword Transformer (KWT) · ECAPA-TDNN · GE2E · x-vector · Zipformer · Moonshine/Moonshine v2 · Silero VAD (engineering reference, not a "paper" per se but a citable production artifact) · NAS-for-KWS papers · TinySpeech · WavLM (as a robustness-oriented alternative to wav2vec2 for pretraining) · quantization-aware training literature for small audio models.

## 6. Missing Datasets
**Multilingual Spoken Words Corpus (MSWC)** — highest-priority addition; KWS-native and multilingual, unlike every dataset in the original list. Also worth an explicit line item on **internally-collected data** (device telemetry with opt-in consent) as the eventual long-term answer to the volume-parity problem, since no public dataset will fully substitute for it — this is consistent with the original report's own gap analysis (§12 of Phase 1) about proprietary telemetry being commercial players' real moat.

## 7. Missing Architectures
MatchboxNet · Keyword Transformer · ECAPA-TDNN (speaker verification) · TinySpeech/attention-condenser style tiny models · a NAS-searched cell architecture as a benchmarking baseline rather than only hand-designed architectures.

## 8. Missing DSP Components
Concrete reference implementations: **Silero VAD** (VAD), **WebRTC Audio Processing Module** (AEC/AGC/NS reference, BSD-style license), **RNNoise** (lightweight neural denoiser, BSD license), **CMSIS-DSP** (Cortex-M FFT/DSP primitives), **KissFFT** (portable permissive-license FFT fallback), **Apple Accelerate/vDSP** (iOS/macOS-native path). The original report discussed DSP *concepts* correctly but never named a single concrete library or model to start Phase 2a implementation from — this is the most immediately actionable gap in the whole document.

---

## 9. Runtime Recommendations (Updated)

| Target | Primary runtime | Rationale | Confidence |
|---|---|---|---|
| Android | ONNX Runtime Mobile + NNAPI/XNNPACK EP; evaluate ExecuTorch as alternative | Best current cross-Android-OEM coverage; NNAPI quality varies by vendor, so XNNPACK CPU fallback must always be present | `[EJ]` |
| iOS/macOS | CoreML primary, ONNX Runtime as fallback/parity path | Best ANE utilization on Apple Silicon | `[EJ]` |
| Linux/Windows desktop | ONNX Runtime + XNNPACK | Broadest desktop CPU coverage | `[EJ]` |
| Raspberry Pi | ONNX Runtime + XNNPACK (ARM NEON) | No dedicated NPU on most Pi models; NEON-optimized CPU path is the realistic baseline | `[EJ]` |
| Jetson | ONNX Runtime + TensorRT EP (worth evaluating alongside XNNPACK) | Jetson's actual value is GPU/TensorRT acceleration — using only a CPU path wastes the hardware; this was absent from the original platform-runtime discussion entirely | `[EJ]` — flagged as a new gap: **Jetson was in the platform list but never got a specific runtime recommendation in Phase 1** |
| ESP32/ESP32-S3, Cortex-M | TensorFlow Lite Micro | Most mature MCU-class streaming-inference runtime; ONNX Runtime's MCU story remains far less mature | `[V]`-level confidence on relative maturity, based on current tooling ecosystems |
| WebAssembly | ONNX Runtime Web (Wasm+SIMD) | Enables browser-based demo/dev-tool use cases; not suitable for true always-on production due to browser lifecycle constraints | `[EJ]` |

**New finding vs. Phase 1:** ExecuTorch, MNN, and NCNN were entirely absent from the original runtime review despite being real, current, and relevant. ExecuTorch in particular is worth prototyping given it already has a published, working Silero VAD export path (XNNPACK backend, ~1.2MB) that's directly analogous to what AURA would need to do with its own models.

---

## 10. Embedded Systems Recommendations

- **ESP32-S3:** has enough compute/RAM for a small streaming CNN/TCN-class first-stage model (as microWakeWord already demonstrates in production use); INT8 quantization and static memory allocation (no heap allocation in the audio-processing hot path) are non-negotiable for interrupt-safety and long-run stability, not optional optimizations.
- **Cortex-M4/M7:** CMSIS-DSP and CMSIS-NN give a reasonably mature path for both the DSP front-end and quantized-CNN inference; DMA-driven audio capture (rather than polling) is standard practice to avoid missed samples/frame drops and should be assumed as a hard requirement, not a nice-to-have.
- **Thread/interrupt safety:** the original report mentions this as a bullet point without discussing it — for an always-on audio pipeline, the VAD/feature-extraction/inference chain typically runs partly in interrupt context (DMA buffer-ready callback) and partly in a lower-priority task context; getting this boundary wrong is a common, hard-to-debug source of intermittent production bugs (dropped frames under load, occasional corrupted feature buffers) and deserves explicit design documentation in Phase 2a, not just a benchmarking checklist item.
- **Power/battery:** VAD-gating the expensive model (only running the KWS network when VAD says "speech present") is the single highest-leverage power optimization and is already implicit in the "Hey M" pipeline's existing VAD-gating design — this is correctly prioritized in spirit, just under-specified as a formal power budget in the Phase 1 document.

---

## 11. Production Readiness Review

Missing from Phase 1 entirely, and genuinely necessary for a two-year commercial effort:
- **Model update/OTA pipeline** — how does an already-deployed device receive an improved wake-word model without a full app update? This is a real subsystem (versioned model registry, compatibility checks between model version and runtime version, staged rollout) that needs its own design doc before Phase 2b.
- **Telemetry/logging with privacy guarantees** — for a "privacy-first, fully offline" product, telemetry design is in tension with the core value proposition and needs explicit resolution (e.g., on-device-only aggregate stats with opt-in cloud reporting, never raw audio) rather than being left unaddressed.
- **CI/CD and training reproducibility** — model registry, experiment tracking, and reproducible training pipelines are baseline production ML engineering practice and are entirely unaddressed in Phase 1; this is a process gap more than a research gap, but it's still a real gap for a document meant to gate a two-year investment.

---

## 12. Security Review (Entirely New Section — Absent from Phase 1)

- **Replay attacks:** an attacker plays a recording of the legitimate wake word to trigger the device. Standard mitigation is liveness detection (e.g., checking for expected micro-variations, or requiring speaker verification with anti-spoofing) — this needs to be an explicit design requirement if the speaker-verification feature is meant to provide any real security guarantee, not just personalization.
- **Voice cloning / spoofing of speaker verification:** modern TTS voice cloning (the same family of tools flagged in §7 for synthetic data generation — XTTS, VoiceCraft) is a realistic threat against any speaker-verification-based access control; anti-spoofing countermeasures (liveness cues, spectral artifacts of synthetic speech) are an active, separate research area (ASVspoof challenge series) that the original report never mentions and that AURA needs to at least evaluate before marketing any "speaker verification" feature as a security boundary rather than a personalization convenience feature. 🚨 This is a meaningful gap: if AURA ever positions speaker verification as an access-control mechanism (not just "reduce false accepts from other voices"), shipping it without anti-spoofing evaluation is a real security risk, not a theoretical one.
- **Ultrasonic/inaudible attacks (e.g., "DolphinAttack"-style):** a documented, real attack class against voice assistants using ultrasonic frequencies inaudible to humans but picked up by MEMS microphones and demodulated by nonlinearities in the mic/ADC path. This is `📚` — a well-known published attack class in the voice-assistant security literature — and the original report's complete silence on it is a real gap for any wake-word engine claiming production/enterprise-grade security posture.
- **Model extraction/reverse engineering:** for a commercial (even if partially open-source) product, on-device model weights are inherently extractable by a sufficiently motivated attacker unless deliberately protected (encryption at rest, secure enclave storage where available); this is a real engineering trade-off against the "privacy-first, offline, some open-source components" positioning and needs an explicit policy decision (what's open, what's protected, and why) rather than being left implicit.
- **Adversarial audio (imperceptible perturbations causing misclassification):** a real, published research area against audio classifiers generally; risk is lower for a binary wake/no-wake decision than for full ASR, but not zero, and at minimum deserves a documented "we evaluated this and consider it low-priority because X" rather than silence.
- **GDPR/privacy/offline guarantees:** if any telemetry or cloud-assisted enrollment flow exists (even just for custom-wake-word training), GDPR-relevant data-handling obligations apply the moment EU users are in scope — this needs a real legal review, flagged here as a process gap, not resolved by this technical audit.

---

## 13. Benchmark Improvements

Beyond the Phase 1 framework (already reasonably good), add:
- **Model load time / cold start vs. warm start** — genuinely missing from Phase 1's list and directly user-visible (time from app/device boot to "wake-word engine is armed").
- **24-hour and 7-day soak testing** as explicit, named milestones (not just "continuous streaming stability" as an abstract category) — a named, calendared soak-test milestone is far more likely to actually get run than an abstract bullet point in a research document.
- **Memory-leak detection tooling** — needs a concrete plan (e.g., Valgrind/ASan on desktop builds, heap-tracking on embedded builds) rather than being listed as a metric with no measurement methodology attached.

---

## 14. Alternative Designs (Three Options per Major Subsystem, Ranked)

**First-stage always-on model:**
1. **BC-ResNet-1/-3 variant** (recommended) — best published accuracy/size trade-off, most precedent.
2. MatchboxNet-3x1x64-class model — comparable efficiency class, worth a head-to-head benchmark rather than assuming BC-ResNet wins on AURA's own data.
3. NAS-searched cell architecture — highest potential ceiling, highest engineering/compute cost to run the search; recommend as a Phase 2c stretch goal, not a Phase 2a default.

**Cross-platform runtime core:**
1. **ONNX Runtime + platform-specific EPs** (recommended) — broadest genuine cross-platform coverage today.
2. ExecuTorch — actively maturing, worth a parallel prototype given its PyTorch-native path and demonstrated small-model export story (Silero VAD precedent).
3. Fully custom minimal C++ inference engine (no external runtime) — maximum control and smallest possible binary, but highest maintenance burden across 11 platforms; only justified if both ONNX Runtime and ExecuTorch prove inadequate on a specific constrained target (e.g., a Cortex-M0-class chip below what TFLite Micro comfortably supports).

**Speaker verification component:**
1. **ECAPA-TDNN-derived small embedding model** (recommended) — current standard architecture family, strong published results, real open implementations (e.g., SpeechBrain) to benchmark against.
2. GE2E/d-vector-style LSTM embedding — simpler, smaller, well-precedented (this is what Google's original "Hey Siri"-adjacent/multi-user wake-word personalization lineage is closer to), reasonable fallback if ECAPA-TDNN proves too heavy for the target device class.
3. Skip speaker verification entirely for v1, ship only wake-word detection — lowest risk, defers the anti-spoofing security question (§12) to a later release rather than shipping a half-evaluated security-adjacent feature under schedule pressure.

---

## 15. Risk Matrix

| Risk | Category | Severity | Likelihood | Notes |
|---|---|---|---|---|
| Shipping speaker verification without anti-spoofing evaluation, marketed as security | Security/Legal | High | Medium | Addressed in §12; needs explicit go/no-go before any "security" marketing claim |
| PTQ-only quantization strategy chosen under schedule pressure instead of QAT | Engineering | Medium-High | Medium-High | Addressed in §3/§8; likely failure mode without an explicit process gate requiring QAT evaluation |
| Dataset licensing violation (ESC-50 commercial use, AudioSet redistribution) | Legal | High | Low-Medium | Needs formal legal review before Phase 2a data pipeline is finalized, not after |
| Patent overlap with Alexa/Siri/Google's published cascade/personalization patents | Legal | Medium | Low-Medium | Needs freedom-to-operate review before final architecture commitment (already flagged in Phase 1, correctly) |
| Cross-platform runtime maintenance burden exceeds team capacity across 11 platforms | Engineering/Business | High | Medium-High | The platform list itself (11 targets) is the single largest scope-risk item in the whole project; recommend explicit platform-priority tiering (see §17) |
| Volume-parity gap in non-English training data undermines multilingual quality claims | Research/Business | Medium | High | Addressed in §6; realistically requires internal data collection, not just public datasets |
| Academic benchmark numbers mistaken for production-readiness signals | Research | Medium | Medium | Addressed throughout; mitigated by insisting on AURA's own measured benchmarks per §10/§13 |

---

## 16. Priority Fixes (Ranked)

1. **Add quantization-aware training evaluation to the training methodology** before any model-size/accuracy commitments are made public or internal.
2. **Name concrete DSP/VAD/AEC reference implementations** (Silero VAD, WebRTC APM, RNNoise, CMSIS-DSP) so Phase 2a has an actual starting point instead of re-deriving DSP primitives from first principles.
3. **Add a security review section** to the living research document, with an explicit go/no-go gate on marketing speaker verification as a security feature until anti-spoofing is evaluated.
4. **Commission a formal legal review** of dataset licensing (ESC-50, AudioSet, VoxCeleb terms) and a patent freedom-to-operate scan before finalizing the cascade/personalization architecture.
5. **Build the internal FA/hr benchmark corpus** (real media/TV audio, multilingual) as a concrete, resourced Phase 2a deliverable, not an abstract methodology bullet point.
6. **Tier the 11-platform target list** by priority/timeline rather than treating all platforms as equally near-term — this is a scope-risk mitigation, not a technical fix, but it's the single highest business-risk item in the risk matrix above.

---

## 17. Updated Roadmap

**Phase 2a (unchanged core, with fixes folded in):** production-representative benchmark corpus + BC-ResNet/MatchboxNet head-to-head prototyping + ONNX Runtime/ExecuTorch dual prototyping on Android + TFLite-Micro on ESP32-S3 + **explicit QAT vs. PTQ ablation** + **concrete DSP reference-implementation integration (Silero VAD, WebRTC APM) instead of from-scratch DSP**.

**Phase 2b (unchanged core, with fixes folded in):** cascade + hard-negative mining + soak testing, **plus a named security-and-legal review checkpoint** (dataset licensing, patent FTO scan, anti-spoofing evaluation decision) before any speaker-verification feature proceeds to Phase 2c.

**Phase 2c (unchanged core):** few-shot custom-wake-word R&D spike, multilingual expansion — **now explicitly gated on the volume-parity finding from §6** (i.e., budget for internal data collection, not just public-dataset assembly, if multilingual quality parity is a hard product requirement).

**New Phase 2d (added by this audit):** platform-priority tiering exercise + production-readiness subsystems (model update/OTA pipeline, telemetry-with-privacy design, CI/CD/model registry) — these were absent from the original roadmap entirely and are necessary before any platform ships to real users, not optional polish after Phase 2c.

---

## 18. Go / No-Go Assessment

- **Go on Phase 2a as scoped**, with the six priority fixes in §16 folded into its deliverables rather than treated as a separate future workstream.
- **No-Go on any public architecture commitment or platform-priority announcement** until: (a) AURA's own measured FA/hr and latency numbers exist on real target hardware, (b) the legal review of dataset licensing and patent landscape is complete, and (c) a security review determines whether speaker verification will be marketed as a security feature or a personalization convenience feature.
- **Explicit caution on the 11-platform scope:** nothing in this audit changes the technical feasibility of covering all 11 platforms, but the risk matrix (§15) identifies platform-count/maintenance burden as the single largest business risk in the entire project — recommend the review board require a platform-tiering decision as a formal Phase 2a exit criterion, not leave it implicit.

**Confidence in this audit itself:** the fact-checked items (§3) were verified against real sources during this review; the newly-added papers/tools (MatchboxNet, ECAPA-TDNN, GE2E, Zipformer, Moonshine, Silero VAD, ExecuTorch) were confirmed via their primary sources/repositories rather than asserted from memory. Numeric performance claims throughout remain `🧪` — genuinely requiring AURA's own experiments — and are not overstated as settled facts anywhere in this document.
