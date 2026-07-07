#!/usr/bin/env python3
"""Host proxy for on-device Step 3: run the exported real KWS model against real Speech
Commands test clips through the EXACT on-device front-end, and report a DET-style
threshold sweep (marvin TP vs other-word/silence FP). Optionally evaluates on
augmented (noisy/reverb) clips to show robustness.

Not the live-mic on-device test (that needs a device, DEVICE_RUNBOOK.md Step 3) — but it
verifies the real model + real front-end genuinely discriminate "marvin".

Usage: python tools/verify_kws_host.py [--onnx PATH] [--per 300] [--noisy]
"""
import argparse
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import aura_frontend as fe
import aura_augment as aug
import sc_dataset

ASSET = os.path.join(os.path.dirname(__file__), "..", "apps", "android", "src", "main",
                     "assets", "models")
THRESHOLDS = (0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9)


def softmax_marvin(z, idx):
    z = z - z.max()
    e = np.exp(z)
    return float((e / e.sum())[idx])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--onnx", default=os.path.join(ASSET, "kws_marvin.onnx"))
    ap.add_argument("--labels", default=os.path.join(ASSET, "labels.json"))
    ap.add_argument("--data-dir", default=os.path.join(os.path.dirname(__file__), "..", ".data"))
    ap.add_argument("--per", type=int, default=300)
    ap.add_argument("--noisy", action="store_true", help="augment test clips (robustness)")
    args = ap.parse_args()

    import onnxruntime as ort
    labels = json.load(open(args.labels))
    mi = labels["marvin_index"]
    sess = ort.InferenceSession(args.onnx, providers=["CPUExecutionProvider"])
    in_name = sess.get_inputs()[0].name
    root = sc_dataset.find_root(args.data_dir)
    noises = aug.load_background_noise(root) if args.noisy else []

    def prob(x):
        feat = fe.features(x, apply_dsp_chain=True, frames=fe.WINDOW_FRAMES)[None].astype(np.float32)
        return softmax_marvin(sess.run(None, {in_name: feat})[0][0], mi)

    marvin_p, other_p = [], []
    n_marv = n_oth = 0
    rng_seed = 0
    for x, label in sc_dataset.iter_clips(root, "testing", shuffle_seed=1):
        if n_marv >= args.per and n_oth >= args.per:
            break
        is_m = label == "marvin"
        if is_m and n_marv >= args.per:
            continue
        if not is_m and n_oth >= args.per:
            continue
        if args.noisy:
            rng_seed += 1
            x = aug.augment(x, noises, np.random.RandomState(rng_seed))
        p = prob(x)
        if is_m:
            marvin_p.append(p); n_marv += 1
        else:
            other_p.append(p); n_oth += 1
    # silence FP (VAD gates this on-device; sanity check)
    srng = np.random.RandomState(0)
    sil_p = [prob(aug.silence_clip(noises, srng) if noises else srng.randn(16000) * 0.001)
             for _ in range(100)]

    marvin_p = np.array(marvin_p); other_p = np.array(other_p); sil_p = np.array(sil_p)
    print(f"model={os.path.basename(args.onnx)} arch={labels.get('arch','?')} "
          f"marvin_index={mi} eval={'NOISY' if args.noisy else 'CLEAN'} "
          f"(marvin={len(marvin_p)} other={len(other_p)})")
    print(f"{'thr':>5} {'marvin_TP':>10} {'other_FP':>9} {'silence_FP':>11}")
    for t in THRESHOLDS:
        tp = float((marvin_p >= t).mean()) if len(marvin_p) else 0.0
        fp = float((other_p >= t).mean()) if len(other_p) else 0.0
        sp = float((sil_p >= t).mean()) if len(sil_p) else 0.0
        print(f"{t:>5.1f} {tp:>10.3f} {fp:>9.3f} {sp:>11.3f}")


if __name__ == "__main__":
    main()
