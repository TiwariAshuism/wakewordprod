# INT8 Quantization Report (ADR-004)

Static PTQ (per-channel QDQ INT8) of the shipped DS-CNN, calibrated on real training-feature windows. Measured on held-out Speech Commands @0.5.

| model | marvin TP | FP | host lat (ms) | size (KB) |
|---|---|---|---|---|
| float32 | 0.833 | 0.000 | 0.096 | 61.4 |
| int8-PTQ | 0.858 | 0.000 | 0.124 | 38.7 |

**INT8 size reduction ~37%**, TP delta +0.025. ADR-004 mandates **QAT for shipped models** (PTQ shown here as the prototyping baseline / ablation); run `train_kws_model.py --qat` for the QAT path. Placeholder model — not the AURA-trained model.
