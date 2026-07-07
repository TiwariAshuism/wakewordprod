# 'hey m' Requirements Evaluation — CASCADE (stage1+stage2)

Speaker-independent. Realistic negative corpus 10.9 min (ambient + broad speech + sparse confusables). Positives: 369; confusable-stress clips: 114.

| metric | hard target | measured | met |
|---|---|---|---|
| FA/hr (realistic) | <= 0.05 | 5.492 | NO |
| False Reject | <= 5% | 50.1% | NO |
| Confusable false-fire (stress) | (report) | 6.1% | — |
| Model size | < 500 KB | 184.6 KB | YES |
| Host latency (not device) | <100 ms | 0.324 ms | (host) |

**Operating point:** M=3, stage1_thr=0.5, stage2_thr=0.95 — no point meets both FA & FR (best-effort shown).

## Sweep (top by lowest FA/hr)

| M | s1_thr | s2_thr | FA/hr | FRR | confusable-fire |
|---|---|---|---|---|---|
| 3 | 0.5 | 0.95 | 5.492 | 0.501 | 0.061 |
| 3 | 0.6 | 0.95 | 5.492 | 0.501 | 0.061 |
| 3 | 0.7 | 0.95 | 5.492 | 0.507 | 0.061 |
| 3 | 0.8 | 0.95 | 5.492 | 0.507 | 0.061 |
| 3 | 0.9 | 0.95 | 5.492 | 0.545 | 0.061 |
| 3 | 0.95 | 0.95 | 5.492 | 0.640 | 0.009 |
| 2 | 0.95 | 0.95 | 10.984 | 0.469 | 0.035 |
| 3 | 0.95 | 0.5 | 10.984 | 0.550 | 0.026 |
| 3 | 0.95 | 0.6 | 10.984 | 0.550 | 0.026 |
| 3 | 0.95 | 0.7 | 10.984 | 0.550 | 0.026 |
| 3 | 0.95 | 0.8 | 10.984 | 0.553 | 0.026 |
| 3 | 0.95 | 0.9 | 10.984 | 0.575 | 0.009 |

_FA/hr on realistic ambient+speech (audit methodology); confusable-fire is the adversarial stress metric reported separately. en-IN-dominant data; en-US/GB/AU absent._
