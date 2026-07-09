# 'hey m' Requirements Evaluation — CASCADE (stage1+stage2)

Speaker-independent. Realistic negative corpus 6.7 min (ambient + broad speech + sparse confusables). Positives: 0; confusable-stress clips: 0.

| metric | hard target | measured | met |
|---|---|---|---|
| FA/hr (realistic) | <= 0.05 | 0.000 | YES |
| False Reject | <= 5% | 0.0% | YES |
| Confusable false-fire (stress) | (report) | 0.0% | — |
| Model size | < 500 KB | 184.6 KB | YES |
| Host latency (not device) | <100 ms | 0.263 ms | (host) |

**Operating point:** M=1, stage1_thr=0.5, stage2_thr=0.5 — meets FA & FR.

## Sweep (top by lowest FA/hr)

| M | s1_thr | s2_thr | FA/hr | FRR | confusable-fire |
|---|---|---|---|---|---|
| 1 | 0.5 | 0.5 | 0.000 | 0.000 | 0.000 |
| 1 | 0.5 | 0.6 | 0.000 | 0.000 | 0.000 |
| 1 | 0.5 | 0.7 | 0.000 | 0.000 | 0.000 |
| 1 | 0.5 | 0.8 | 0.000 | 0.000 | 0.000 |
| 1 | 0.5 | 0.9 | 0.000 | 0.000 | 0.000 |
| 1 | 0.5 | 0.95 | 0.000 | 0.000 | 0.000 |
| 1 | 0.6 | 0.5 | 0.000 | 0.000 | 0.000 |
| 1 | 0.6 | 0.6 | 0.000 | 0.000 | 0.000 |
| 1 | 0.6 | 0.7 | 0.000 | 0.000 | 0.000 |
| 1 | 0.6 | 0.8 | 0.000 | 0.000 | 0.000 |
| 1 | 0.6 | 0.9 | 0.000 | 0.000 | 0.000 |
| 1 | 0.6 | 0.95 | 0.000 | 0.000 | 0.000 |

## Stage-1 calibration quality (per-clip ECE/MCE)

Measured on 0 positive + 0 negative held-out test clips (single-window stage-1 posteriors). Calibration applied: **platt** from `apps/android/src/main/assets/models/labels.json`.

| ECE (10-bin) | MCE | Brier | AUROC |
|---|---|---|---|
| 0.0000 | 0.0000 | nan | nan |

_FA/hr on realistic ambient+speech (audit methodology); confusable-fire is the adversarial stress metric reported separately. en-IN-dominant data; en-US/GB/AU absent._
