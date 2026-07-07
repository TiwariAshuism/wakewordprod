# PROJECT AURA — Investment Committee Report
### Architecture Decision Records, Risk Matrix, and Go/No-Go Recommendation

**How this document relates to the prior two:** this is a synthesis and decision document, not a third literature review. It draws on `aura_research_report.md` (Phase 1 survey) and `aura_phase1_audit.md` (adversarial audit) and does not re-litigate content already covered there except where this pass found something those two got wrong or incomplete. New verified findings from this pass are marked **NEW**. Per your instructions: no invented numbers, no fabricated benchmarks. Every claim below is tagged **Verified**, **General Knowledge**, **Engineering Judgement**, **Hypothesis**, or **Needs Experimentation** — used exactly as you defined them, not blurred.

**One correction to the prior two documents, found during this pass:** both earlier documents used the term **"PCAN."** The correct, real, citable technique is **PCEN (Per-Channel Energy Normalization)** — Wang, Getreuer, Hughes, Lyon, Saurous, "Trainable Frontend for Robust and Far-Field Keyword Spotting," ICASSP 2017 (arXiv:1607.05666). PCEN replaces static log/root compression with a trainable, differentiable automatic-gain-control-based dynamic compression, implementable as neural network layers and jointly optimized with the KWS acoustic model. **Verified.** This should be corrected wherever "PCAN" appears in the earlier documents — a small thing, but exactly the kind of error a real review board is supposed to catch, and neither prior pass caught it.

---

## 1. Executive Summary

AURA is technically feasible as scoped, but the project as currently defined has more scope risk than research risk. The core wake-word detection problem (single/few-word, offline, streaming, INT8, low-power) is well-trodden ground with strong published reference points (BC-ResNet, MatchboxNet, DS-CNN) and mature reference DSP/runtime components (Silero VAD, WebRTC APM, CMSIS-DSP/CMSIS-NN, ONNX Runtime, TFLite Micro). The harder problems are not research problems — they are **scope management** (11+ platforms, 5+ language bindings), **data acquisition** (no public dataset solves multilingual volume parity), and **unresolved security/legal posture** (speaker-verification anti-spoofing, dataset licensing, patent freedom-to-operate). None of these harder problems are things this review, or any literature review, can resolve — they require decisions, legal review, and experiments, which is why the recommendation below is conditional, not a flat yes/no.

---

## 2. Architecture Decision Records (ADRs)

### ADR-001: First-stage always-on model family
- **Decision:** Prototype BC-ResNet (Kim et al., Interspeech 2021) and MatchboxNet (Majumdar & Ginsburg, Interspeech 2020) head-to-head on an AURA-owned dataset before committing.
- **Status:** Proposed, not final.
- **Rationale:** Both are **Verified** as real, published, small-footprint architectures with strong reported results on Speech Commands; neither has been benchmarked on AURA's actual target data, so picking one now would be **Engineering Judgement** dressed up as a decision. **Needs Experimentation** before final commitment.
- **Alternatives considered:** DS-CNN (older, still reasonable, less parameter-efficient per published comparisons — General Knowledge); Keyword Transformer (Berg et al. 2021 — real, Verified, but attention-based KWS quantization tooling is less mature, so higher engineering risk for a first-stage always-on model specifically).

### ADR-002: Cross-platform inference runtime
- **Decision:** ONNX Runtime (+ XNNPACK/NNAPI/CoreML execution providers) as the primary mobile/desktop core; TensorFlow Lite Micro for ESP32/Cortex-M; evaluate ExecuTorch as a parallel candidate given its demonstrated Silero VAD export path.
- **Status:** Proposed.
- **Rationale:** ONNX Runtime's multi-EP cross-platform coverage is **General Knowledge** / widely documented; TFLite Micro's MCU maturity advantage over ONNX Runtime's MCU story is **General Knowledge** as of current tooling, not a permanent fact — this should be re-checked at the start of Phase 2a, not assumed to remain true for two years.
- **Risk:** maintaining two separate runtime code paths (ONNX Runtime + TFLite Micro) across 11 platforms is itself a maintenance-burden risk flagged in the prior audit (§15 of `aura_phase1_audit.md`) and not resolved by this ADR — it's a deliberate trade-off, not a free win.

### ADR-003: Feature front-end
- **Decision:** log-Mel as the default input representation; evaluate PCEN (corrected term, see above) as a robustness upgrade for far-field/noisy conditions specifically, not as a default replacement.
- **Status:** Proposed.
- **Rationale:** log-Mel-as-default is **General Knowledge**, standard across nearly all cited KWS literature. PCEN's benefit is specifically demonstrated for **far-field** and loudness-variable conditions (Wang et al. 2017 — **Verified**); for close-talk mobile/wearable use it may add complexity without proportional benefit — **Needs Experimentation** on AURA's actual target device classes before deciding whether PCEN is default-on, opt-in per device class, or dropped.

### ADR-004: Quantization strategy
- **Decision:** Adopt Quantization-Aware Training (QAT) as the default path for the shipped first-stage model; use Post-Training Quantization (PTQ) only for rapid prototyping/ablation iterations, not for shipped models.
- **Status:** Proposed — this is the single most important correction from the prior audit (`aura_phase1_audit.md` §3/§8/§16) and is elevated to a formal ADR here because it was a **dangerous omission**, not a minor gap.
- **Rationale:** It is **General Knowledge** in the TinyML/quantization literature that small (<1M parameter) models are more sensitive to the accuracy loss from naive PTQ than larger models, and that QAT closes most of this gap. The exact accuracy delta for AURA's specific architecture is **Needs Experimentation** — this ADR commits to the QAT-by-default *process*, not to a specific claimed accuracy number.

### ADR-005: Speaker verification component
- **Decision:** Prototype ECAPA-TDNN-derived embeddings (Desplanques et al., Interspeech 2020 — **Verified** as the current standard architecture family for speaker verification, using Res2Net+SE blocks, channel/context attention pooling, multi-layer feature aggregation, typically trained with AAM-softmax/AM-softmax on VoxCeleb). Do **not** market this feature as a security/access-control mechanism until an explicit anti-spoofing evaluation against the ASVspoof benchmark methodology is complete.
- **Status:** Proposed, with an explicit gate.
- **Rationale:** ASVspoof is **Verified** as the standard, long-running (since 2015) academic challenge series for anti-spoofing countermeasures against exactly this kind of attack (replay, synthetic speech/voice cloning, voice conversion); AAM-softmax/one-class-softmax variants are **Verified** as standard loss functions in this literature. Shipping speaker verification without this evaluation and calling it "security" would be **the single highest security risk item in this entire project** — this was correctly flagged as 🚨 in the prior audit and is being formalized here as a hard gate, not a suggestion.

### ADR-006: Platform scope and sequencing
- **Decision:** Explicitly tier the 11+ platform list rather than treat all as simultaneous v1 targets. Recommended tiering (Engineering Judgement, not yet validated with the team's actual capacity/timeline): Tier 1 (Android, Linux/C++ core, ESP32-S3) → Tier 2 (iOS, Raspberry Pi, Windows/macOS) → Tier 3 (Jetson, Cortex-M variants beyond ESP32, WebAssembly, Flutter/React Native bindings as wrappers around the Tier 1/2 native core).
- **Status:** Proposed — **this decision cannot be finalized by a research/audit process; it depends on team size, hiring plan, and business priorities that are outside the scope of any technical document.**
- **Rationale:** the prior audit's risk matrix correctly identified platform count as the single largest business-risk item; a research report cannot resolve a staffing/prioritization decision, only flag that it needs to be made explicitly rather than left implicit.

---

## 3. Decision Matrix

| Decision axis | Option A | Option B | Option C | Recommended | Confidence |
|---|---|---|---|---|---|
| First-stage model | BC-ResNet | MatchboxNet | Keyword Transformer | A or B, resolved by experiment | Needs Experimentation |
| Runtime (mobile/desktop) | ONNX Runtime | ExecuTorch | Custom C++ engine | A, with B evaluated in parallel | Engineering Judgement |
| Runtime (MCU) | TFLite Micro | ONNX Runtime (embedded) | Custom bare-metal | A | General Knowledge (current tooling maturity) |
| Quantization | QAT | PTQ | Mixed (PTQ prototyping, QAT shipping) | C, defaulting to QAT for ship builds | General Knowledge + Needs Experimentation for exact deltas |
| Speaker verification arch | ECAPA-TDNN | GE2E/d-vector | Skip for v1 | A for prototyping; C is the lower-risk ship decision pending ADR-005's gate | Verified (architecture exists) / Hypothesis (whether it clears the security gate in time) |
| Far-field strategy | Multi-mic beamforming hardware | Software-only noise robustness (PCEN, augmentation) | Defer far-field entirely to v2 | C for v1, per both prior documents' sequencing recommendation | Engineering Judgement |

---

## 4. Risk Matrix (Consolidated and Re-Verified)

This restates the prior audit's risk matrix (`aura_phase1_audit.md` §15) with confidence levels re-tagged per this document's stricter labeling requirement, plus one **NEW** item found in this pass.

| Risk | Severity | Likelihood | Confidence in risk assessment itself |
|---|---|---|---|
| Speaker verification shipped without anti-spoofing evaluation, marketed as security | High | Medium | General Knowledge (ASVspoof literature is mature and well-established) |
| PTQ-only quantization chosen under schedule pressure | Medium-High | Medium-High | General Knowledge |
| Dataset licensing violation (ESC-50 NC license, AudioSet redistribution terms) | High | Low-Medium | General Knowledge on license terms; Engineering Judgement on actual violation likelihood |
| Patent overlap with Alexa/Siri/Google cascade/personalization patents | Medium | Low-Medium | Hypothesis — **no patent database search was actually performed in this review**; this remains an assertion that a real freedom-to-operate search is needed, not a finding that overlap exists |
| Platform-count maintenance burden exceeds capacity | High | Medium-High | Engineering Judgement |
| Multilingual volume-parity gap | Medium | High | General Knowledge (documented in Common Voice's own per-language volume statistics) |
| **NEW: Terminology/detail errors propagating uncorrected across review passes** (e.g., "PCAN" vs. "PCEN") | Low (individually) / Medium (in aggregate, if it signals insufficiently-verified content elsewhere) | Confirmed occurred once | This is a process risk about the review methodology itself, not just the technology — worth naming because a review board reading three passes of "AI-generated literature review" should not assume later passes are error-free just because they used stricter labeling; every technical claim in all three documents should still get one final human expert pass before being used for actual engineering decisions |

---

## 5. Priority Fixes

1. Correct "PCAN" → "PCEN" throughout the document set (trivial, but do it).
2. Formalize ADR-004 (QAT-by-default) and ADR-005 (speaker-verification security gate) as binding engineering process requirements, not optional recommendations.
3. Commission an actual patent freedom-to-operate search (this review did not perform one — see Risk Matrix note above) before finalizing the cascade/personalization architecture.
4. Commission actual dataset-licensing legal review before Phase 2a data pipeline construction begins.
5. Make the platform-tiering decision (ADR-006) explicit and owned by a business/eng-leadership decision-maker, not left as an implicit "we'll do all 11 eventually."

---

## 6. Go / No-Go Recommendation

**Conditional Go on Phase 2a prototyping** (model architecture head-to-head, runtime prototyping, QAT ablation) — this is low-risk, well-precedented engineering work.

**No-Go on:**
- Any public claim about accuracy, FA/hour, latency, or battery life until measured on AURA's own hardware (**Needs Experimentation** — nothing in any of the three documents produced so far constitutes a measured AURA benchmark).
- Marketing speaker verification as a security feature (**blocked on ADR-005's anti-spoofing evaluation**).
- Finalizing the platform priority list without an explicit business decision (**ADR-006 is not a technical decision this review can make**).
- Committing to specific dataset licensing without legal review (**Priority Fix #4**).

---

## 7. Phase 2 Roadmap (Delta from Prior Audit's §17)

No material change from `aura_phase1_audit.md` §17 — that roadmap (2a: benchmarking + prototyping; 2b: cascade + security/legal checkpoint; 2c: gated multilingual/few-shot R&D; 2d: production-readiness plumbing) remains the recommendation. This document adds only: **ADR-004 and ADR-005 should be treated as Phase 2a exit criteria**, not Phase 2b nice-to-haves — i.e., Phase 2a is not "done" until there's a QAT-vs-PTQ measured comparison and a documented anti-spoofing evaluation plan (not necessarily completed evaluation, but at minimum a plan and literature-informed threat model), on AURA's own hardware/data.

---

## 8. Research Backlog

- Freedom-to-operate patent search (Priority Fix #3).
- QAT vs. PTQ ablation on AURA's actual first-stage model candidates (**Needs Experimentation**).
- BC-ResNet vs. MatchboxNet vs. Keyword Transformer head-to-head on AURA's own data (**Needs Experimentation**).
- PCEN vs. log-Mel-only ablation across close-talk vs. far-field device classes (**Needs Experimentation**).
- ASVspoof-methodology anti-spoofing evaluation for the ECAPA-TDNN speaker-verification prototype (**Needs Experimentation**).
- Cross-lingual transfer experiment: does a model trained predominantly on high-resource-language data transfer usefully to a low-resource target language, or does AURA need per-language data at parity volume? (**Needs Experimentation** — literature on this specific question for KWS, as opposed to general ASR, is thin; flagged as a genuine open research question, not just an engineering task.)

## 9. Engineering Backlog

- ONNX Runtime + XNNPACK/NNAPI/CoreML integration on Android/iOS/desktop.
- TFLite Micro integration on ESP32-S3.
- Silero VAD integration as the VAD-gating baseline (real, MIT-licensed, ONNX/ExecuTorch-exportable — Verified).
- WebRTC APM or RNNoise integration for AEC/noise-suppression baseline.
- CMSIS-DSP/CMSIS-NN integration for Cortex-M targets.
- Model registry + experiment tracking infrastructure (absent from all prior documents' scope until the production-readiness section of the audit — still not started).
- OTA model update pipeline design.

## 10. Experiments Required Before Shipping

- Measured FA/hour on a real, internally-built media/TV/podcast audio corpus (not Speech Commands).
- Measured latency, CPU%, RAM, and battery drain on actual target device hardware per platform tier.
- 24-hour and 7-day continuous soak tests per platform tier.
- Anti-spoofing evaluation for speaker verification, if that feature proceeds past prototyping.

## 11. Things Nobody Knows Yet
- Whether AURA's specific architecture choice (once benchmarked) will actually beat openWakeWord/be competitive with Porcupine on FA/hour and FRR — **no one can know this without running the experiment**, and no public information (including this review) can substitute for it.
- Whether the platform-count scope (11+) is achievable within a two-year timeline with the team's actual size — this is a staffing/planning question, not a research question, and this document explicitly declines to guess at it.
- Whether cross-lingual transfer will be "good enough" or will require full per-language data collection — flagged above as a genuine open research question.

## 12. What Requires Real Hardware Testing
Everything in §10 above, plus: NNAPI delegate behavior (known to vary meaningfully by Android OEM/SoC — this is **General Knowledge**, a well-documented pain point in the Android ML developer community, but the *specific* devices AURA will support need their own testing matrix, which doesn't exist yet); thermal throttling behavior under sustained always-on inference load on each target device class; DMA/interrupt-safety behavior on the actual ESP32-S3/Cortex-M reference hardware once real firmware exists.

## 13. Production Checklist (Carried Forward, Unchanged in Substance from Prior Audit §11)
Model update/OTA pipeline · privacy-preserving telemetry design · CI/CD and reproducible training · model registry · benchmark dashboard · platform-tiering decision documented and owned.

## 14. Open Questions
- Is speaker verification a v1 feature at all, given the anti-spoofing gate (ADR-005)? This document recommends deferring it to v2 unless the anti-spoofing evaluation can realistically complete within the Phase 2a/2b timeline — but that's a scheduling call for the team, not something this review can decide unilaterally.
- What is the actual patent risk? Unknown until Priority Fix #3 is done — this document does not know the answer and says so rather than guessing.
- What is the real team size/timeline behind the "two year" estimate? Unknown to this review, and the platform-tiering/roadmap recommendations above are contingent on it.

## 15. Final Verdict

**Conditional Go on Phase 2a. No-Go on any public commitment (architecture, platform list, accuracy/performance claims, or security positioning) until the specific gates above are met.** The underlying technology is not the bottleneck here — the published literature and available open-source/reference components (BC-ResNet/MatchboxNet, Silero VAD, ONNX Runtime/TFLite Micro, ECAPA-TDNN, ASVspoof methodology) give AURA a legitimate, well-precedented path to a competitive product. The actual project risk is concentrated in scope management (11+ platforms), unresolved legal/security gates that no literature review can close (they require actual legal counsel and actual security evaluation), and the discipline to run real experiments on real hardware before making claims — none of which is a reason to stop the project, but all of which are reasons not to treat any research document, including this one, as a substitute for that work.
