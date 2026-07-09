# ADR-Calibration — Confidence calibration method and process for cascade / arbitration thresholds

- **Status:** **Proposed — Needs Experimentation** (not Accepted; requires prototyping + measurement on AURA's own cascade before promotion).
- **Owner:** ML/Runtime Architect (per the existing ownership matrix).
- **Grounding:** `docs/design/aura_calibration_report.md` — especially §8 (recommended ADR), §5.3 (audio-classifier benchmark), §6 (quantization × calibration), §7 (pipeline + process rules), §2 (terminology).
- **Related:** ADR-004 (QAT by default), multi-device arbitration design, OTA rollout rollback triggers, the benchmark harness (FA/hr, DET, latency).

---

## Context

Every prior AURA document treats the cascade "confidence score" as a single opaque number that thresholds gate against. Calibration is whether that number *means* what it claims. This is not a generic concern — it touches four already-committed AURA features (report §1):

1. **Cascade thresholds** (Stage-1 → Stage-2 → speaker verification) — the flagged follow-through on setting principled, comparable thresholds instead of ad-hoc per-model ones.
2. **Multi-device arbitration** — devices broadcast Stage-1 confidence and the highest-confidence device wins. If models are not calibrated *consistently against each other*, arbitration systematically favors the more overconfident device, not the one that heard the wake word most clearly. This is a correctness bug in an already-designed feature, not a hypothetical.
3. **OTA rollback triggers** — fixed FA/hr and FRR gates assume the score's meaning is stable across model versions; an uncalibrated swap can shift the implied operating point and fire a false "regression".
4. **Quantization (ADR-004, INT8)** — calibration and quantization interact counter-intuitively (see Sequencing dependency below).

## Decision

Adopt confidence calibration as a required, routinely-tracked step, and prototype candidate methods **in this order** (report §8). This ordering is deliberate — cheapest / most-appropriate-to-AURA's-decision-structure first, and explicitly **not** focal-loss-first:

1. **Platt scaling — primary candidate (binary decision).** A 2-parameter logistic fit (`a·z + b`). For AURA's binary wake / no-wake trigger decision specifically, this is a more natural fit than temperature scaling, which was designed for multi-class softmax (report §4.2). Cheap, does not touch shipped weights, no retraining.
2. **Temperature scaling — comparison point.** A single learned scalar `T` dividing the logits (report §4.1). The field's most common baseline, so it is the comparison to A/B Platt against — not assumed correct just because it dominates the (multi-class, image-heavy) general literature. Does not change argmax / accuracy.
3. **SNGP — training-time candidate, only if post-hoc proves insufficient.** Spectral-normalized Neural Gaussian Process. In the one directly-relevant audio-classifier study (Ye et al., arXiv:2206.13071, report §5.3) SNGP was **best on both ECE and OOD rejection across all three backbones at near-baseline compute cost** — the standout joint calibration+rejection result.

**Explicitly NOT focal-loss-first.** In that same study (report §5.3 / §8), focal loss improves ECE substantially but **degrades OOD rejection** (worst AUROC performer in two of three backbones). AURA's FA/hr metric *is* an OOD / negative-rejection problem, so adopting focal loss for calibration reasons alone — without re-measuring FA/hr, not just ECE — risks trading away exactly the property AURA needs. Focal loss is therefore not a first-choice calibration lever; if considered at all, it must come with an FA/hr re-check.

## Sequencing dependency (report §6)

**Calibration must be fit *after* QAT / quantization, not before.** PTQ acts like injected activation/logit noise; overconfident predictions are *more* robust to being flipped by that noise than well-calibrated (less-confident) ones, so a model deliberately made better-calibrated can become *more* fragile to accuracy loss under quantization. This does **not** argue against ADR-004's QAT-by-default — it strengthens it (QAT learns quantization robustness during training). The consequence for this ADR: **train (with QAT) → quantize → *then* fit Platt/temperature scaling on the final INT8 model's actual output distribution on held-out data.** Calibration is the last step in the pipeline. Calibrating the pre-quantization float model risks calibrating a version of the model that no longer exists once quantization is applied. (Engineering Judgement — Needs Experimentation to confirm on AURA's own models.)

## New validation requirement (report §7, rule 3)

**Cross-device calibration-consistency check for multi-device arbitration.** Per-device calibration quality is not sufficient: two individually well-calibrated models, calibrated on independently-composed sets (different accent / noise mix), can still disagree systematically — which silently breaks arbitration. This is a new, AURA-specific validation step **not covered by the general calibration literature** (which considers a single model in isolation) and **not present in the current benchmark-harness spec**. It must be added. Alongside it (report §7, rule 4), ECE / MCE / reliability-diagram generation should be added to the existing benchmark harness as standard per-version output.

## Process rules (report §7)

1. **Re-fit per model version — calibration is NOT portable.** `T` / Platt parameters from Stage-1 v1.2.0 do not transfer to v1.3.0 even with unchanged architecture. This becomes a required item in the model-promotion checklist, extending the existing FA/hr + latency gate.
2. **Calibration set ≠ FA/hr benchmark set.** Reusing the benchmark corpus overfits calibration to it and yields a falsely rosy ECE. Use a genuinely separate held-out split matched to the real deployment distribution.
3. **Watch for "negative calibration" (report §5.4).** Stacking an in-training method (label smoothing / focal loss) with a post-hoc pass (temperature scaling) can calibrate *worse* than either alone. If an in-training method is adopted, re-measure ECE with and without the post-hoc pass — do not assume stacking is strictly better.

## Terminology note — a collision to name explicitly (report §2)

"Calibration" means two unrelated things in this stack and **will** get confused in team conversation if not disambiguated:

- **Confidence calibration** (this ADR): does a model's output score reflect true correctness likelihood? Fixed via Platt / temperature scaling, measured by ECE / MCE / reliability diagrams.
- **Quantization (PTQ) calibration** (ADR-004 / INT8): the unrelated activation-range calibration — feeding a small "calibration dataset" through the model to determine INT8 clipping ranges / scale factors (e.g. TensorRT `IInt8EntropyCalibrator`; in AURA, the 300-window calibration set in `tools/quant_heym_int8.py`, per `docs/MODEL_CARD.md`).

From here on, docs and code must say **"confidence calibration"** vs **"quantization calibration"** explicitly. AURA's INT8 requirement already puts "the calibration set" in the room for the second meaning, so reusing the bare term across both is a realistic source of miscommunication.

## Consequences

- The cascade and multi-device arbitration compare genuinely comparable confidence scores.
- The model-promotion checklist and benchmark harness gain calibration re-fit + ECE/MCE emission and a cross-device consistency check.
- Everything above marked Engineering Judgement / Needs Experimentation must be validated on AURA's own cascade before this ADR moves to Accepted; the audio-classifier findings transfer from adjacent (ESC-50 / GTZAN) research and are not KWS-verified.

## References

- `docs/design/aura_calibration_report.md` §§1–8.
- Guo et al. 2017 (temperature scaling); Platt 1999 (Platt scaling); Ye et al. 2022 arXiv:2206.13071 (audio-classifier ECE/OOD comparison, SNGP vs focal loss); arXiv:2111.08163 (quantization × confidence dilemma).
