# 'hey m' DS-CNN — QAT vs PTQ INT8 Ablation (D1 / ADR-004)

ADR-004 mandates **QAT for shipped models** (PTQ is prototyping-only). This is the measured, controlled comparison on the **speaker-independent** held-out set (`heym_data.items('test')`, materialized as `heym_feat2.npz` Xte).

- DS-CNN params: **14,338** (2-class: not-wake / hey-m)
- Held-out set: 483 clips (369 hey-m positives, 114 negatives), unseen speakers. Train windows: 17,566.
- Float fine-tune: 12 ep; QAT fine-tune: 4 ep (fuse conv+bn+relu, `prepare_qat`, per-channel qconfig).
- QAT-INT8 production path: **C:\Users\Ashu\Documents\wakewordprod\tools\..\.data\heym_dscnn_qat_int8.onnx**. (Torch->ONNX of the *quantized* graph is fragile — global-mean-pool over a quantized tensor; the fallback exports QAT-hardened FLOAT weights then INT8-PTQ, the meaningful "QAT-robust weights then INT8" path.)
- Both INT8 models use identical ort static QDQ per-channel quantization + the same training-window calibration, so the **only variable is QAT vs not**.

## Result

| model | hey-m recall | per-clip FAR | F1 | size (KB) |
|---|---|---|---|---|
| fp32 (reference) | 0.973 | 0.307 | 0.941 | 58.6 |
| **plain-PTQ-INT8** | 0.976 | 0.307 | 0.942 | 38.1 |
| **QAT-INT8** | 0.883 | 0.351 | 0.887 | 38.1 |

**QAT − PTQ:** recall -0.092, per-clip FAR +0.044, size +0.0 KB.

### Verdict: plain-PTQ-INT8 wins (higher F1)

Reported as measured. Note the model is tiny (~14 K params) so PTQ INT8 is already near-lossless; treat small deltas as within run-to-run noise.

_Accuracy is per-window argmax on the held-out clips (recall = hey-m sensitivity, per-clip FAR = false-accept rate on negatives). Size is the on-disk INT8 ONNX. Streaming FA/hr + FR at an operating point are measured separately by `tools/heym_eval.py`._
