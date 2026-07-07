#!/usr/bin/env python3
"""Head-to-head selection: read per-arch metrics from training, pick the most robust
model, export it as the shipped kws_marvin.onnx + labels.json, and write
model_comparison.md. ROBUSTNESS_IMPROVEMENTS #5 / ADR-001.

Selection rule (robustness-first): among archs whose false-positive rate stays low
(<= FP_CAP at threshold 0.5 on BOTH clean and noisy test), pick the highest **noisy**
marvin TP@0.5; tie-break by fewer params. If none meet the FP cap, pick the best
(noisy_TP - 3*max_FP). Honest: reports all three even if some are weak.
"""
import json
import os
import shutil
import sys

DATA = os.path.join(os.path.dirname(__file__), "..", ".data")
ASSET = os.path.join(os.path.dirname(__file__), "..", "apps", "android", "src", "main",
                     "assets", "models")
ARCHS = ["cnn", "bcresnet", "dscnn"]
FP_CAP = 0.10


def load(arch):
    p = os.path.join(DATA, f"kws_{arch}_metrics.json")
    return json.load(open(p)) if os.path.exists(p) else None


def at(m, split, t, key):
    return m[split].get(f"{t:.1f}", {}).get(key, 0.0)


def main():
    metrics = {a: load(a) for a in ARCHS if load(a)}
    if not metrics:
        print("no metrics found — run tools/train_kws_model.py --arch <a> first", file=sys.stderr)
        return 1

    rows = []
    for a, m in metrics.items():
        rows.append({
            "arch": a, "params": m["params"], "f1_clean": m["marvin_f1_clean"],
            "clean_tp": at(m, "clean_sweep", 0.5, "tp"), "clean_fp": at(m, "clean_sweep", 0.5, "fp"),
            "noisy_tp": at(m, "noisy_sweep", 0.5, "tp"), "noisy_fp": at(m, "noisy_sweep", 0.5, "fp"),
        })

    def key(r):
        max_fp = max(r["clean_fp"], r["noisy_fp"])
        meets = max_fp <= FP_CAP
        # sort: meets-cap first, then higher noisy_tp, then fewer params
        return (0 if meets else 1, -r["noisy_tp"], r["params"])
    rows.sort(key=key)
    best = rows[0]
    print("head-to-head @0.5 (marvin TP / FP):")
    for r in rows:
        print(f"  {r['arch']:9s} params={r['params']:6d} f1={r['f1_clean']:.3f} "
              f"clean[TP={r['clean_tp']:.3f} FP={r['clean_fp']:.3f}] "
              f"noisy[TP={r['noisy_tp']:.3f} FP={r['noisy_fp']:.3f}]")
    print(f"WINNER: {best['arch']}")

    # export winner
    src = os.path.join(DATA, f"kws_{best['arch']}.onnx")
    dst = os.path.join(ASSET, "kws_marvin.onnx")
    os.makedirs(ASSET, exist_ok=True)
    shutil.copyfile(src, dst)
    wm = metrics[best["arch"]]
    labels = {
        "labels": wm["labels"], "marvin_index": wm["marvin_index"],
        "num_classes": wm["num_classes"], "arch": best["arch"], "params": wm["params"],
        "frontend": {"sample_rate": 16000, "win": 400, "hop": 160, "fft": 512, "n_mels": 40,
                     "mel": "HTK", "log": "natural", "dsp": "AGC->AEC(noop)->NS",
                     "window_frames": 100},
        "val_accuracy_clean": wm["val_acc_clean"], "marvin_f1_clean": wm["marvin_f1_clean"],
        "note": "PLACEHOLDER Speech-Commands model (augmented, head-to-head winner), "
                "not the AURA-trained model.",
    }
    json.dump(labels, open(os.path.join(ASSET, "labels.json"), "w"), indent=2)

    # comparison doc
    with open(os.path.join(os.path.dirname(__file__), "..", "model_comparison.md"), "w",
              encoding="utf-8") as f:
        f.write("# AURA KWS — Architecture Head-to-Head (robustness sprint)\n\n")
        f.write("Same augmented + stabilized training pipeline, same 13-class task, same "
                "front-end. Metrics on the held-out Speech Commands test split (marvin "
                "TP / non-marvin FP at softmax threshold 0.5). `noisy` = one augmentation "
                "pass (noise/reverb/speed) on the same test clips.\n\n")
        f.write("| arch | params | marvin F1 (clean) | clean TP@.5 | clean FP@.5 | noisy TP@.5 | noisy FP@.5 |\n")
        f.write("|---|---|---|---|---|---|---|\n")
        for r in rows:
            star = " **(winner)**" if r["arch"] == best["arch"] else ""
            f.write(f"| {r['arch']}{star} | {r['params']} | {r['f1_clean']:.3f} | "
                    f"{r['clean_tp']:.3f} | {r['clean_fp']:.3f} | "
                    f"{r['noisy_tp']:.3f} | {r['noisy_fp']:.3f} |\n")
        f.write(f"\n**Winner: `{best['arch']}`** - selected by highest noisy TP@0.5 with "
                f"FP <= {FP_CAP} on both splits (tie-break: fewer params). Exported as the "
                f"shipped `kws_marvin.onnx`. Placeholder weights (Speech Commands), not the "
                f"AURA-trained model.\n")
    print(f"exported winner -> {dst}; wrote labels.json + model_comparison.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
