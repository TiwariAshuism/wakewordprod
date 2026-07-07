"""Regenerate the D1 QAT-vs-PTQ ablation report from the SAVED ONNX artifacts.

Cheap re-eval, no retraining. The original run wrote the report with an earlier
verdict rule; this re-scores the three already-exported ONNX models on the same
speaker-independent held-out set and rewrites benchmarks/dashboards/heym_qat_report.md
using the current honest F1-band ranking in tools/heym_qat.py.

Inputs (must already exist, produced by `python tools/heym_qat.py`):
  .data/heym_dscnn_qat_fp32.onnx   (fp32 reference)
  .data/heym_dscnn_ptq_int8.onnx   (plain PTQ INT8)
  .data/heym_dscnn_qat_int8.onnx   (QAT-hardened weights -> INT8)
  .data/heym_feat2.npz             (Xte/yte speaker-independent held-out)
"""
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import heym_qat as Q  # reuse eval_onnx / write_report / load_features / kws_models


class _Args:
    # Only the fields write_report reads. These match the run that produced the
    # saved artifacts (heym_qat.py defaults).
    float_epochs = 12
    qat_epochs = 4


def main():
    fp32_onnx = os.path.join(Q.DATA, "heym_dscnn_qat_fp32.onnx")
    ptq_onnx = os.path.join(Q.DATA, "heym_dscnn_ptq_int8.onnx")
    qat_onnx = os.path.join(Q.DATA, "heym_dscnn_qat_int8.onnx")
    for p in (fp32_onnx, ptq_onnx, qat_onnx):
        if not os.path.exists(p):
            raise SystemExit(f"missing artifact: {p} (run tools/heym_qat.py first)")

    Xtr, ytr, Xte, yte = Q.load_features()
    params = 14338  # DS-CNN 2-class param count (kws_models.build_model('dscnn'))
    try:
        import kws_models
        m = kws_models.build_model("dscnn",
                                   Xtr.reshape(-1, Q.MELS).mean(0),
                                   Xtr.reshape(-1, Q.MELS).std(0) + 1e-5,
                                   Q.NUM_CLASSES)
        params = kws_models.param_count(m)
    except Exception:
        pass

    m_fp32 = Q.eval_onnx(fp32_onnx, Xte, yte)
    m_ptq = Q.eval_onnx(ptq_onnx, Xte, yte)
    m_qat = Q.eval_onnx(qat_onnx, Xte, yte)
    for name, mm in (("fp32", m_fp32), ("ptq-int8", m_ptq), ("qat-int8", m_qat)):
        print(f"  {name:<10} recall={mm['recall']:.3f} FAR={mm['far']:.3f} "
              f"F1={mm['f1']:.3f} size={mm['size_kb']:.1f}KB")

    # --- current honest ranking (identical rule to heym_qat.main) ---
    d_f1 = m_qat["f1"] - m_ptq["f1"]
    d_rec = m_qat["recall"] - m_ptq["recall"]
    d_far = m_qat["far"] - m_ptq["far"]
    if abs(d_f1) < 0.01:
        if d_rec > 0.005 or d_far < -0.005 or d_rec < -0.005 or d_far > 0.005:
            verdict = "TIE / operating-point tradeoff (QAT does not beat PTQ on F1)"
        else:
            verdict = "TIE (QAT ties PTQ on this tiny model)"
    elif d_f1 > 0:
        verdict = "QAT-INT8 wins (higher F1)"
    else:
        verdict = "plain-PTQ-INT8 wins (higher F1)"

    Q.write_report(params, m_fp32, m_ptq, m_qat, qat_onnx, verdict,
                   _Args(), len(Xtr), len(Xte), int(yte.sum()), int((yte == 0).sum()))
    print(f"\nVERDICT: {verdict}")
    print(f"wrote {os.path.join(Q.DASH, 'heym_qat_report.md')} (regenerated from saved ONNX, no retrain)")


if __name__ == "__main__":
    main()
