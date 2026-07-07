#!/usr/bin/env python3
"""INT8 quantization for the AURA Stage-1 KWS model (ADR-004 / committee I1, I8).

Produces an INT8 model from the shipped float ONNX and measures the accuracy / size /
latency delta on real Speech Commands test clips through the on-device front-end. Two
paths, so the QAT-vs-PTQ ablation the committee wants is measurable:

  (default) PTQ  — onnxruntime static post-training quantization (calibrated on real
                   training-feature windows). Fast; the ADR-004 "prototyping" baseline.
  --compare-qat  — additionally reports the accuracy of a QAT-trained model if
                   tools/train_kws_model.py was run with --qat (kws_dscnn_qat.onnx).

ADR-004 mandates QAT for *shipped* models (PTQ only for prototyping). This tool measures
both so the decision is data-driven.
"""
import argparse
import json
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import aura_frontend as fe
import sc_dataset

ASSET = os.path.join(HERE, "..", "apps", "android", "src", "main", "assets", "models")
DATA = os.path.join(HERE, "..", ".data")


class FeatureCalibrationReader:
    """Feeds representative [1,100,40] windows (from the cached training features) to the
    static quantizer for activation-range calibration."""
    def __init__(self, input_name, n=256):
        d = np.load(os.path.join(DATA, "aura_feat_aug.npz"))
        X = d["Xtr"]
        idx = np.random.RandomState(0).choice(len(X), size=min(n, len(X)), replace=False)
        self.samples = [X[i][None].astype(np.float32) for i in idx]
        self.input_name = input_name
        self.i = 0

    def get_next(self):
        if self.i >= len(self.samples):
            return None
        s = self.samples[self.i]
        self.i += 1
        return {self.input_name: s}


def softmax_marvin(sess, in_name, x, mi):
    f = fe.features(x, apply_dsp_chain=True, frames=fe.WINDOW_FRAMES)[None].astype(np.float32)
    z = sess.run(None, {in_name: f})[0][0]
    z = z - z.max()
    e = np.exp(z)
    return float((e / e.sum())[mi])


def eval_model(path, root, mi, per, threshold):
    import onnxruntime as ort
    sess = ort.InferenceSession(path, providers=["CPUExecutionProvider"])
    in_name = sess.get_inputs()[0].name
    tp = fp = nm = no = 0
    for x, label in sc_dataset.iter_clips(root, "testing", shuffle_seed=1):
        if nm >= per and no >= per:
            break
        p = softmax_marvin(sess, in_name, x, mi)
        if label == "marvin":
            if nm < per:
                nm += 1; tp += (p >= threshold)
        else:
            if no < per:
                no += 1; fp += (p >= threshold)
    # latency
    dummy = np.zeros((1, fe.WINDOW_FRAMES, fe.N_MELS), np.float32)
    for _ in range(5):
        sess.run(None, {in_name: dummy})
    lat = []
    for _ in range(200):
        t = time.perf_counter(); sess.run(None, {in_name: dummy}); lat.append((time.perf_counter()-t)*1000)
    return tp / max(nm, 1), fp / max(no, 1), float(np.percentile(lat, 50)), os.path.getsize(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=DATA)
    ap.add_argument("--per", type=int, default=150)
    ap.add_argument("--threshold", type=float, default=0.5)
    ap.add_argument("--compare-qat", action="store_true")
    args = ap.parse_args()

    from onnxruntime.quantization import quantize_static, CalibrationDataReader, QuantType, QuantFormat
    import onnxruntime as ort

    labels = json.load(open(os.path.join(ASSET, "labels.json")))
    mi = labels["marvin_index"]
    fp32 = os.path.join(ASSET, "kws_marvin.onnx")
    int8 = os.path.join(ASSET, "kws_marvin_int8.onnx")
    root = sc_dataset.find_root(args.data_dir)

    in_name = ort.InferenceSession(fp32, providers=["CPUExecutionProvider"]).get_inputs()[0].name

    class Reader(CalibrationDataReader):
        def __init__(s):
            s.r = FeatureCalibrationReader(in_name)
        def get_next(s):
            return s.r.get_next()

    print("running static PTQ (INT8, per-channel, QDQ)...")
    quantize_static(fp32, int8, Reader(), quant_format=QuantFormat.QDQ,
                    per_channel=True, weight_type=QuantType.QInt8, activation_type=QuantType.QInt8)

    print("evaluating float vs int8 on real test clips...")
    ftp, ffp, flat, fsz = eval_model(fp32, root, mi, args.per, args.threshold)
    itp, ifp, ilat, isz = eval_model(int8, root, mi, args.per, args.threshold)

    print("\n=== INT8 quantization (ADR-004) ===")
    print(f"{'model':<10} {'marvinTP':>9} {'FP':>6} {'lat_ms':>7} {'size_kb':>8}")
    print(f"{'float32':<10} {ftp:>9.3f} {ffp:>6.3f} {flat:>7.3f} {fsz/1024:>8.1f}")
    print(f"{'int8-PTQ':<10} {itp:>9.3f} {ifp:>6.3f} {ilat:>7.3f} {isz/1024:>8.1f}")
    print(f"size reduction: {100*(1-isz/fsz):.0f}%   TP delta: {itp-ftp:+.3f}")

    rows = [("float32", ftp, ffp, flat, fsz), ("int8-PTQ", itp, ifp, ilat, isz)]
    if args.compare_qat:
        qat = os.path.join(ASSET, "kws_dscnn_qat.onnx")
        if os.path.exists(qat):
            qtp, qfp, qlat, qsz = eval_model(qat, root, mi, args.per, args.threshold)
            print(f"{'qat(float)':<10} {qtp:>9.3f} {qfp:>6.3f} {qlat:>7.3f} {qsz/1024:>8.1f}")
            rows.append(("qat", qtp, qfp, qlat, qsz))
        else:
            print("(--compare-qat: run train_kws_model.py --arch dscnn --qat first)")

    with open(os.path.join(HERE, "..", "benchmarks", "dashboards", "quant_report.md"),
              "w", encoding="utf-8") as f:
        f.write("# INT8 Quantization Report (ADR-004)\n\n")
        f.write("Static PTQ (per-channel QDQ INT8) of the shipped DS-CNN, calibrated on real "
                "training-feature windows. Measured on held-out Speech Commands @0.5.\n\n")
        f.write("| model | marvin TP | FP | host lat (ms) | size (KB) |\n|---|---|---|---|---|\n")
        for name, tp, fp, lat, sz in rows:
            f.write(f"| {name} | {tp:.3f} | {fp:.3f} | {lat:.3f} | {sz/1024:.1f} |\n")
        f.write(f"\n**INT8 size reduction ~{100*(1-isz/fsz):.0f}%**, TP delta {itp-ftp:+.3f}. "
                "ADR-004 mandates **QAT for shipped models** (PTQ shown here as the prototyping "
                "baseline / ablation); run `train_kws_model.py --qat` for the QAT path. "
                "Placeholder model — not the AURA-trained model.\n")
    print(f"\nwrote benchmarks/dashboards/quant_report.md; INT8 model -> {int8}")


if __name__ == "__main__":
    main()
