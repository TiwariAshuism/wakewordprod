# PROJECT AURA — Addendum (Version 4)
### Append-Only Completion Pass

This document adds ONLY content not already present in `aura_research_report.md`, `aura_phase1_audit.md`, or `aura_investment_committee_report.md`. It does not restate, summarize, or re-decide anything already covered there. Where a requested topic turned out to already be adequately covered in a prior document, that is noted briefly and skipped rather than padded.

**Labeling convention (unchanged from prior documents):** Verified / General Knowledge / Engineering Judgement / Needs Experimentation / Hypothesis.

---

## 1. Modern Research Papers (New Additions Only)

**WavLM** (Chen et al., Microsoft, 2021/2022) — self-supervised speech pretraining, extends HuBERT-style masked prediction with an explicit denoising objective (trained on a mix of clean and simulated noisy/overlapping-speech audio, not just clean speech). **Innovation:** because the pretraining objective itself includes noise/overlap robustness, WavLM's representations transfer better to noise-robust downstream tasks (speaker verification, speaker diarization, and by extension potentially noisy-condition KWS) than wav2vec2/HuBERT, which pretrain on cleaner data. **Strengths:** best-in-class transfer for noise-robustness-sensitive downstream tasks among the self-supervised family, per Microsoft's own published SUPERB-benchmark results. **Weaknesses:** same deployment problem as wav2vec2/HuBERT — base models are tens of millions of parameters, unusable directly on an always-on embedded budget. **Relevance to AURA:** stronger candidate than wav2vec2/HuBERT specifically *if* AURA pursues the few-shot custom-wake-word-from-real-audio R&D spike (already flagged as highest-research-risk item in `aura_phase1_audit.md` §13, item 7) — a WavLM-derived teacher for distillation is a better-motivated choice than the previously-named wav2vec2/HuBERT, precisely because the deployment condition (always-on, real-world noise) matches WavLM's pretraining objective more closely. **Verdict: prototype only as part of that already-flagged R&D spike, not as a new standalone workstream.** Confidence: General Knowledge (Microsoft's own publication and benchmark claims, not independently re-verified numerically in this review).

**Zipformer / Moonshine / Moonshine v2** — already covered with citations in `aura_phase1_audit.md` §3 and §5. Not repeated here. One addition: Moonshine v2's **sliding-window self-attention for bounded streaming latency** (as opposed to full-attention, which forces "encode-the-whole-utterance-first" latency) is the specific mechanism worth naming if AURA ever prototypes a transformer-based second-stage verifier — bounded-window attention, not full attention, is the relevant pattern to copy. This mechanistic detail was not previously spelled out. Confidence: Verified (per the paper's own abstract/description).

**TinySpeech** — already cited in `aura_phase1_audit.md` §3 (Wong et al. 2020, "attention condensers"). Not repeated.

**NAS-based TinyML KWS** — already flagged in `aura_phase1_audit.md` §3/§4/§14. One concrete addition not previously named: **AutoKWS** (Zhang et al., ICASSP 2021) — differentiable architecture search specifically for keyword spotting (as opposed to the more generic NAS-for-KWS papers already cited). Confidence: Verified (real ICASSP 2021 paper).

**Recent efficient streaming KWS (2023–2025), genuinely new since the prior three documents:**
- **Cioflan et al., "On-Device Domain Learning for Keyword Spotting on Low-Power Extreme Edge Embedded Systems"** (2024, arXiv:2403.10549) — proposes on-device domain adaptation for KWS models under <10KB of memory using ~100 labeled utterances, reporting accuracy gains from adapting an already-trained model to a new acoustic domain on-device. **Relevance to AURA:** directly relevant to the "custom wake word" and "adapts to a specific user's mic/room" product angles — this is a concrete, recent, citable precedent for on-device few-shot adaptation that is far cheaper than the "distill a large self-supervised teacher" approach discussed elsewhere, and should be evaluated as a lower-risk alternative path for personalization/custom-wake-word features, not only the heavier WavLM-distillation route. **Verdict: add to the research backlog as an alternative, lower-risk approach to the few-shot custom-wake-word problem.** Confidence: Verified (paper exists, on-device domain learning claim is as stated by the authors; the specific accuracy-gain figures are the authors' own reported results, not independently re-verified by this review — treat as General Knowledge, not as an AURA-applicable guarantee).
- **"Advances in Small-Footprint Keyword Spotting: A Comprehensive Review of Efficient Models and Algorithms"** (2025, arXiv:2506.11169) — a recent survey reviewing roughly 250 KWS papers published 2010–2025. **Relevance to AURA:** this survey itself is the single most efficient way for the AURA research team to close the remaining literature-review depth gap that all three prior documents' §3/history sections acknowledged but didn't fully close — recommend the team read this survey directly as a Phase 2a task rather than this document attempting to re-derive its contents secondhand. Confidence: Verified (paper exists with the stated scope); its internal claims are not independently re-verified here.
- **Hello Edge: Keyword Spotting on Microcontrollers** (Zhang, Suda, Lai, Chandra, 2018, arXiv:1711.07128) — this is an older (2018) but foundational MCU-specific KWS paper that, on review, should have been included in the original Phase 1 history section (`aura_research_report.md` §1) and was missed across all three prior passes. It systematically benchmarks DNN/CNN/RNN/CRNN/DS-CNN architectures specifically for microcontroller deployment constraints. **This is a genuine retroactive gap, flagged here rather than silently left uncorrected.** Confidence: Verified.

---

## 2. Runtime Ecosystem — Comparison Table (New: binary size / GPU / embedded-suitability dimensions not previously tabulated)

`aura_phase1_audit.md` §9 already named ExecuTorch, MNN, NCNN as gaps and OpenVINO/TVM as lower-priority. This table adds the specific comparison dimensions the current request asks for that were not previously tabulated together.

| Runtime | Typical binary size footprint | ARM/NEON optimization | GPU support | Embedded (MCU) suitability | Maintenance/community | Confidence |
|---|---|---|---|---|---|---|
| ONNX Runtime (Mobile) | Moderate (can be trimmed via custom ops build) | Via XNNPACK EP | Via CoreML/NNAPI/CUDA/DirectML EPs depending on platform | Weak — no first-class MCU story | Very active, Microsoft-backed | General Knowledge |
| TFLite Micro | Very small (designed for this) | Via CMSIS-NN kernels on ARM | None (not applicable at MCU scale) | Best-in-class for this use case | Active, Google-backed | General Knowledge |
| ExecuTorch | Small–moderate, actively being optimized (demonstrated ~1.2MB for Silero VAD export w/ XNNPACK, per its own repo example — Verified per prior audit) | Via XNNPACK backend | Emerging (Vulkan/Metal backends in active development per PyTorch's own roadmap communications) | Not yet MCU-class mature; mobile/edge-Linux focus | Newer, actively developed by PyTorch/Meta | General Knowledge, with the one specific figure Verified |
| NCNN | Very small, specifically optimized for minimal binary size | Strong — this is its core design focus (Tencent-originated, ARM NEON hand-tuned kernels) | Vulkan support exists | Not MCU-class, but excellent for ARM mobile/SBC (e.g., Raspberry Pi) | Active, large deployment base in Chinese mobile ecosystem apps | General Knowledge |
| MNN | Small–moderate | Strong ARM optimization (Alibaba-originated) | Vulkan/OpenCL/Metal support exists | Not MCU-class; mobile/edge focus | Active, growing (including recent MNN-LLM extensions per its own published work) | General Knowledge |
| OpenVINO | Larger (designed for Intel-class hardware, not minimal-footprint edge) | Not its focus — x86/Intel-optimized instead | Intel GPU/VPU support is its core value proposition | Poor fit — not designed for MCU or ARM-mobile-first deployment | Active, Intel-backed | General Knowledge |
| TVM | Variable (it's a compiler, not a fixed runtime — output size depends on what you compile) | Can target ARM via its code-generation backends, but requires more compiler-engineering investment than the alternatives above | Can target various GPU backends via its compiler infrastructure | Possible via microTVM, but with a steeper adoption/engineering curve than TFLite Micro | Active open-source (Apache TVM), but meaningfully higher integration complexity | General Knowledge |

**Recommendation (unchanged in substance from `aura_phase1_audit.md` §9, restated only to close the table):** ONNX Runtime + TFLite Micro remains the primary two-track recommendation; NCNN is worth a specific evaluation for the ARM-mobile/Raspberry Pi tier given its binary-size and NEON-optimization reputation; OpenVINO and TVM remain correctly deprioritized for AURA's stated platform list (Intel-centric and compiler-complexity reasons respectively) — this addendum does not change that recommendation, only substantiates it with the requested comparison dimensions.

---

## 3. DSP Production Stack — Pipeline Placement (New: where each component sits in AURA's actual signal chain)

This was requested as "describe where each fits into AURA's pipeline" — the prior documents named these components but did not lay out pipeline order. New content:

```
Microphone → [AGC] → [AEC (if device plays audio back)] → [Noise Suppression: RNNoise or WebRTC-APM NS] 
→ Framing/Windowing → STFT/FFT (CMSIS-DSP on MCU / KissFFT or Accelerate elsewhere) 
→ Log-Mel (+ optional PCEN, see aura_investment_committee_report.md ADR-003) 
→ [VAD gate: Silero VAD] → (only if VAD says "speech") → First-stage KWS model (CMSIS-NN on MCU / ONNX Runtime elsewhere) 
→ (if triggered) → Second-stage verifier model → (if triggered) → [Optional: speaker verification, ECAPA-TDNN-derived] → Wake event
```

Notes on placement, not previously stated:
- **AGC before AEC/NS, not after** — General Knowledge/Engineering Judgement: normalizing level first gives the downstream adaptive filters (AEC) and noise suppressor a more consistent input range to adapt against; doing AGC after noise suppression risks amplifying residual noise-suppression artifacts.
- **The VAD gate sits between feature extraction and the first-stage model**, not before feature extraction — because VAD itself typically needs a feature representation (Silero VAD operates on raw audio chunks directly per its own documentation, so in AURA's case the VAD and the log-Mel front-end can actually run in parallel off the same raw-audio ring buffer rather than strictly in series, which is a genuine pipeline-design choice not previously identified in any of the three prior documents. **Needs Experimentation** — parallel vs. serial VAD placement has real implications for latency and CPU scheduling that should be measured, not assumed.
- **WebRTC APM bundles AEC+AGC+NS+VAD as one module** — worth noting explicitly: a team could choose WebRTC APM as a single integrated component instead of separately integrating Silero VAD + RNNoise + a separate AGC/AEC implementation. This is a genuine build-vs-integrate decision not previously framed as a binary choice: **(a)** one integrated WebRTC-APM pipeline (simpler integration, less flexibility to swap individual components) vs. **(b)** best-of-breed separate components (Silero VAD + RNNoise + custom/CMSIS AGC-AEC — more flexibility, more integration work). **Needs Experimentation/Engineering Judgement** — no prior document posed this as an explicit fork in the road.

---

## 4. Dataset Strategy — Genuinely New Content

**Dataset balancing and accent balancing:** not previously discussed as a concrete methodology. New recommendation: rather than balancing purely by raw sample count per accent/language (which can overweight whichever group was easiest to collect), balance by **estimated phonetic coverage** — i.e., ensure the confusable-phrase hard-negative set (already prioritized in `aura_phase1_audit.md` §3.7/§8) has proportional representation across the accent groups AURA intends to support, since false-accept patterns are often accent-specific in ways raw sample-count balancing doesn't guarantee. This is **Engineering Judgement**, not a settled literature finding — flagged as a Needs Experimentation item for Phase 2a's data pipeline design.

**Synthetic data ratios:** the prior documents (`aura_research_report.md` §7 in the audit) correctly flagged that ideal positive/negative ratios and synthetic/real ratios are empirical, not literature-settled, and declined to invent numbers — that discipline is maintained here. No new numeric recommendation is added; this remains **Needs Experimentation**.

**MSWC (Multilingual Spoken Words Corpus):** already flagged as the highest-priority missing dataset in `aura_phase1_audit.md` §6. Not repeated. One addition: MSWC is specifically **forced-aligned from Common Voice**, which means its per-language volume and quality is directly downstream of Common Voice's own per-language volume disparities (already flagged in `aura_phase1_audit.md` §6) — i.e., MSWC does not independently solve the volume-parity problem, it inherits it. This dependency relationship was not previously made explicit. Confidence: General Knowledge (MSWC's own documented construction methodology).

---

## 5. Training Infrastructure Appendix (Entirely New — Not Previously Covered)

| Tool | Purpose | Why it matters for AURA specifically |
|---|---|---|
| **MLflow** | Experiment tracking, model registry, artifact logging | Open-source, self-hostable — fits the "privacy-first/offline-leaning" project ethos better than a SaaS-only alternative; gives a queryable history of which architecture/hyperparameter/dataset-version combination produced which measured FA/hr and FRR numbers, which is required infrastructure for the "our own measured benchmarks, not paper-reported numbers" discipline insisted on throughout `aura_phase1_audit.md` and `aura_investment_committee_report.md`. |
| **Weights & Biases (W&B)** | Experiment tracking, hyperparameter sweep management, collaborative dashboards | Stronger out-of-the-box visualization/collaboration UX than self-hosted MLflow; trade-off is a SaaS dependency (relevant if AURA's own data-handling policy wants to avoid sending training metrics/artifacts to a third-party service — a policy decision, not a technical one). |
| **DVC (Data Version Control)** | Dataset and pipeline versioning, git-friendly large-file/data tracking | Directly addresses "dataset versioning" (already named as a benchmark-harness requirement in `aura_investment_committee_report.md` §7/production checklist) by tying a specific model artifact to the exact dataset version/commit that produced it — necessary for reproducing a regression when a benchmark number changes. |
| **Model registry** (MLflow's built-in registry, or a custom equivalent) | Versioned model artifact storage with stage transitions (staging/production/archived) | This is the concrete mechanism underlying the "model registry" line item already flagged as missing in `aura_phase1_audit.md` §11 (Production Readiness Review) — that section named the gap; this table names the concrete tool options to fill it. |
| **CI/CD for ML** (e.g., GitHub Actions/GitLab CI triggering automated retraining-validation-benchmark pipelines) | Ensures every model change automatically re-runs the benchmark harness (see §7 below) before merge | Directly closes the "CI/CD" gap named in `aura_phase1_audit.md` §11 — the addition here is specifying that the CI pipeline's job is specifically to **re-run the FA/hr and FRR benchmark automatically**, not just run unit tests, since a silent accuracy regression is the most costly failure mode for a wake-word model specifically. |

**Why this whole category matters, stated once rather than repeated per tool:** every prior document insisted on "measure on your own hardware, don't trust paper-reported numbers" as a recurring discipline. That discipline is unenforceable without the infrastructure in this table — this appendix is the missing "how" behind that repeated "should," which is exactly why it was worth adding as new content rather than being a restatement.

---

## 6. OTA Model Update Architecture (Entirely New — Not Previously Designed)

Previously, "OTA model update pipeline" was named as a missing production feature (`aura_phase1_audit.md` §11, `aura_investment_committee_report.md` §13) but not designed. New design sketch:

- **Versioning:** semantic version per model artifact (e.g., `major.minor.patch`), where `major` changes signal an incompatible input/output contract change (e.g., different feature extraction requirements) and `minor`/`patch` signal accuracy/size improvements with a stable contract.
- **Compatibility:** each model artifact should declare the minimum runtime version it requires (e.g., "requires ONNX Runtime EP version X or TFLite Micro version Y") so a device with an outdated runtime doesn't silently load an incompatible model — this compatibility check should be a hard gate in the OTA client, not an assumption.
- **Checksum verification:** every downloaded model artifact must be hash-verified (e.g., SHA-256) against a manifest before being loaded, to catch corrupted downloads before they reach the inference engine — standard practice, but must be explicit given the always-on/production-critical nature of the wake-word model specifically (a corrupted model silently failing to trigger is a worse failure mode than a crashed app, since there's no user-visible error).
- **Signed models:** the manifest/checksum itself should be signed (not just the model file hashed) so a compromised CDN/update-server can't serve a valid-checksum-but-malicious model — this ties directly into the Security Appendix below (§8 of this addendum) rather than being a standalone item.
- **Staged rollout:** roll out new model versions to a small percentage of devices first, monitor aggregate (privacy-preserving, on-device-computed, opt-in) FA/FR proxy metrics, then expand — this requires the telemetry-with-privacy design already flagged as needed in `aura_phase1_audit.md` §11, and is the concrete reason that telemetry design is a blocking dependency for safe OTA rollout, not an independent nice-to-have.
- **Rollback:** the OTA client should retain the previous known-good model version on-device and be able to revert automatically if the new version fails a post-install sanity check (e.g., a quick synthetic self-test audio clip that should reliably trigger, run once after every model update) — this specific self-test-after-update mechanism is new content not previously proposed anywhere in the three prior documents.
- **Offline fallback:** given the "fully offline" product requirement, the device must remain fully functional on its last-downloaded model version indefinitely if it never receives an OTA update (e.g., no network access ever) — this should be a explicit, tested requirement (a device that has never once connected to any update server should still work correctly forever on its shipped model), not an implicit assumption.

---

## 7. Benchmark Harness Design (New — Prior Documents Specified *What* to Measure, Not *How* to Run It Automatically)

- **Hardware matrix:** a defined, named set of physical reference devices per platform tier (per the tiering in `aura_investment_committee_report.md` ADR-006) that benchmarks always run against — e.g., a specific Android phone model per price tier, a specific ESP32-S3 dev board, a specific Raspberry Pi model — checked into the benchmark configuration itself so "which device did this number come from" is never ambiguous.
- **Automated benchmarking / CI benchmark execution:** the FA/hr, FRR, latency, CPU, RAM measurements (already specified in `aura_phase1_audit.md` §13) should run automatically on every model-affecting change via the CI/CD pipeline named in §5 above, against physical or emulated reference hardware in a device farm — not run manually/ad hoc, which is how benchmark numbers silently go stale in most real projects.
- **Dataset versioning for benchmarks specifically:** the benchmark corpus itself (the internal FA/hr media/TV audio corpus specified in `aura_phase1_audit.md` §10/§13) needs its own DVC-tracked version, separate from the training dataset versioning, so that a benchmark-number change can be attributed to either (a) a model change or (b) a benchmark-corpus change — conflating these two is a realistic source of confusing, hard-to-debug "why did our FA/hr suddenly change" incidents.
- **Regression detection:** automated comparison against the previous release's benchmark numbers, with a defined threshold for what counts as a regression requiring human review before merge (e.g., "FA/hr increased by more than X%" — the specific threshold is **Needs Experimentation/team decision**, not something this document invents).
- **Benchmark dashboards:** a persistent, queryable view of benchmark history over time per platform/device — this can reuse the MLflow/W&B infrastructure from §5 rather than requiring a separate custom tool.

---

## 8. Security Appendix — New Topics Only (ASVspoof Already Covered, Not Repeated)

- **Secure Enclave (Apple) / Android Keystore (Android):** hardware-backed secure storage for cryptographic keys, relevant to AURA if (a) speaker-verification enrollment data (voice embeddings) needs to be stored with hardware-level protection rather than as a plain file, or (b) the OTA model-signing verification key (§6 above) needs to be protected from extraction even if the device's main OS/filesystem is compromised. **Recommendation:** store the OTA update-verification public key and, if speaker verification ships, the enrolled user's voice-embedding template, using Secure Enclave/Keystore-backed storage APIs rather than plain application storage, on platforms where this hardware exists (iOS/modern Android). This is General Knowledge (standard mobile security practice) newly applied to AURA's specific artifacts (model-signing keys, voice embeddings) rather than previously named as a security consideration at all.
- **Model encryption at rest:** distinct from model signing (§6, which verifies authenticity/integrity) — encryption protects confidentiality of the model weights themselves against extraction/reverse-engineering (already named as a risk category in `aura_phase1_audit.md` §12, but without a concrete mitigation). **New concrete recommendation:** if model confidentiality is a business requirement (e.g., the trained weights represent significant proprietary training-data investment per the "data is the moat" finding in `aura_research_report.md` §12), encrypt the model file at rest and decrypt only into protected memory at load time, with the decryption key itself protected via Secure Enclave/Keystore as above — full protection against a sufficiently motivated attacker with physical device access is not achievable on most consumer hardware, and this should be stated as a "raises the bar, does not make extraction impossible" mitigation, not a guarantee.
- **Replay protection for the OTA channel specifically** (distinct from replay attacks against the *microphone/wake-word* input, already covered under ASVspoof-adjacent content in `aura_investment_committee_report.md` ADR-005): the OTA update protocol itself should include a freshness mechanism (e.g., a monotonically increasing version counter enforced by the client, or a short-lived signed timestamp) so a captured-and-replayed old "valid" update package can't be used to downgrade a device to a known-vulnerable model version. This is a distinct threat from voice replay attacks and was not previously named anywhere in the three prior documents.
- **Secure OTA channel:** the update download itself should occur over TLS with certificate pinning where feasible, in addition to (not instead of) the model-signing verification in §6 — signing protects integrity/authenticity of the payload even if the channel is compromised, while TLS protects confidentiality of what's being fetched and reduces tampering-in-transit surface area; both are standard and both are needed, not a choice between them.

---

## 9. Patent Landscape Appendix (Concise, No Legal Analysis — Areas Requiring FTO Review Only)

Consistent with `aura_investment_committee_report.md`'s explicit statement that no actual patent search was performed in that document, this appendix only names **areas** where a Freedom-to-Operate search is needed — it draws no conclusions about infringement, novelty, or validity, and should not be read as legal guidance.

- **Multi-stage cascade wake-word detection** (low-power first-stage detector triggering a higher-power/higher-accuracy second-stage verifier) — publicly described as part of Amazon's, Google's, and Apple's own engineering blogs/patents per `aura_research_report.md` §2; area requires FTO review before AURA finalizes its own cascade implementation details.
- **Speaker-adaptive/personalized wake-word models** — publicly described by both Google and Apple per their own engineering blogs (`aura_research_report.md` §2.2/§2.3); area requires FTO review if AURA's speaker-verification/personalization feature (per `aura_investment_committee_report.md` ADR-005) proceeds past prototyping.
- **Few-shot/custom wake-word enrollment flows** — an active commercial area (Porcupine's own enrollment console is one public example of a product embodying this general idea, per `aura_research_report.md` §2.4); area requires FTO review before AURA finalizes its own custom-wake-word training/enrollment UX and underlying technical approach.
- **On-device domain adaptation for KWS** — newly relevant given the Cioflan et al. 2024 paper surfaced in §1 of this addendum; academic publication reduces (but does not eliminate) patent risk in this specific area, since some jurisdictions' patent systems still permit patenting of specific implementations of a publicly-described general technique; still worth including in the FTO scope precisely because this is a newly-identified area of interest for AURA, not because this review has found any specific conflicting patent.

**This section is a checklist of areas to search, not a risk assessment of any specific patent — that remains explicitly out of scope for this or any prior document, per the original instruction not to perform legal analysis.**

---

## 10. Long-Term Roadmap Extension — Phase 3, 4, 5 (New)

`aura_phase1_audit.md` §17 and `aura_investment_committee_report.md` §7 cover Phase 2a–2d. This extends beyond that horizon, explicitly labeled as **longer-range and more speculative** than the Phase 2 content — these are directional, not committed, and each carries its own Needs Experimentation/Hypothesis tags.

**Phase 3 — Personalization & Custom Wake Words at Scale:**
- Ship the on-device domain-adaptation approach (Cioflan et al.-style, §1 above) as the primary custom-wake-word mechanism, treating the heavier WavLM-distillation approach as a fallback R&D track rather than the primary path, given the lower resource footprint and existing academic precedent for the domain-adaptation approach. **Hypothesis** — this prioritization itself needs validation once both approaches are prototyped in Phase 2c.
- Multilingual expansion, explicitly sequenced after the volume-parity question (flagged repeatedly across all documents) is resolved via either licensed data acquisition or internal collection.

**Phase 4 — Federated Learning & Privacy-Preserving Improvement Loops:**
- Explore federated learning (on-device model improvement aggregated across a user population without raw audio ever leaving the device) as a mechanism to close the volume-parity/data-scarcity gap for lower-resource languages/accents without compromising the "privacy-first, offline" positioning that is central to AURA's differentiation (per `aura_research_report.md` §12/§13). **Hypothesis, high research risk** — federated learning for small audio classification models is a less mature, less commonly published combination than federated learning for the more commonly studied text/vision domains; this should be treated as a genuine research question requiring its own literature review at the time Phase 4 is actually approached, not assumed solvable based on federated learning's general reputation in other domains.
- MCU-only fully-offline deployment tier (no companion app/phone required at all) as a distinct product configuration, building on the ESP32-S3/Cortex-M work already scoped in Phase 2a.

**Phase 5 — Hardware Acceleration & Reference Designs:**
- Revisit the far-field/beamforming hardware co-design question (explicitly deferred past Phase 2 in `aura_research_report.md` §15's "explicit non-goal") once the software foundation is validated — this remains the correct sequencing decision from the original roadmap, restated here only to confirm it still applies at this extended time horizon rather than being silently dropped.
- Evaluate dedicated low-power ML accelerator silicon (the broader class of ultra-low-power CNN accelerators referenced in recent edge-KWS literature surfaced in §1 of this addendum) as a potential reference-hardware differentiator, in combination with CoBuild Labs' hardware development capability — **Hypothesis**, contingent on Phase 3/4 outcomes and business priorities that are outside this document's scope.

---

## Closing Note on This Addendum's Own Limits

This addendum, like the three documents before it, is a research-assistance artifact, not a substitute for the actual experiments, legal reviews, and hardware testing that every one of the four documents in this set has consistently flagged as still required. The single most important thing this whole four-document set has repeated, in different words, at every stage: **the technology is not the bottleneck; verified measurement, legal clearance, and disciplined scope management are.** Nothing in this addendum changes that conclusion — it closes literature and design gaps, not the underlying requirement to go run the experiments.
