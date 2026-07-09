#!/usr/bin/env python3
"""Easy wake-word EVALUATION entry point.

    python evaluate.py                 # uses ./config.yaml + models/ from train.py
    python evaluate.py --config my.yaml

Loads the trained Stage-1 (+ optional Stage-2) from output_dir and scores the held-out
(speaker-independent) split with the STREAMING-DETECTOR MIRROR (tools/aura_frontend.py DSP +
log-Mel, sliding 100-frame window, M-consecutive-hit decision with a refractory) to report:
  * FA/hr  — false accepts per hour on the held-out negative corpus
  * FRR    — false-reject rate on held-out positives
  * ECE/MCE (10-bin), Brier, AUROC — per-clip calibration quality (tools/calibrate.py)
Prints a summary and writes benchmarks/dashboards/<wake_word>_eval.md.
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.join(HERE, "tools")
DASH = os.path.join(HERE, "benchmarks", "dashboards")

WINDOW = 100   # frames (aura_frontend.WINDOW_FRAMES)
HOP = 10       # hop windows between scored positions
REFR = 100     # refractory frames after a detection


# --------------------------------------------------------------------- streaming mirror
def _energy_go(dsp, T, hop_pts_len, fe):
    """Simple per-frame RMS energy gate mirroring the on-device gate intent."""
    import numpy as np
    go = np.zeros(max(T, 1), bool)
    for t in range(T):
        blk = dsp[t * fe.HOP:t * fe.HOP + fe.HOP]
        go[t] = blk.size > 0 and float(np.sqrt(np.mean(blk * blk))) > 1e-3
    return go


def _window_scores(mel, sess, in_name, hop_pts, calibration, stage, target, cal, fe):
    import numpy as np
    out = np.zeros(len(hop_pts), np.float32)
    for i, t in enumerate(hop_pts):
        z = sess.run(None, {in_name: mel[t - WINDOW:t][None].astype(np.float32)})[0][0]
        out[i] = cal.apply_calibration(z, calibration, stage, target)
    return out


def _stream_prep(audio, sess1, in1, sess2, in2, calibration, target, cal, fe):
    import numpy as np
    dsp = fe.apply_dsp(audio); mel = fe.log_mel(dsp)
    T = len(mel)
    hp = list(range(WINDOW, T + 1, HOP))
    if not hp:
        return None
    s1 = _window_scores(mel, sess1, in1, hp, calibration, "stage1", target, cal, fe)
    s2 = (_window_scores(mel, sess2, in2, hp, calibration, "stage2", target, cal, fe)
          if sess2 else np.ones(len(hp), np.float32))
    go = _energy_go(dsp, T, len(hp), fe)
    return hp, s1, s2, go


def _decide(prep, thr1, thr2, M):
    if prep is None:
        return 0
    hp, s1, s2, go = prep
    consec = r = dets = 0
    for i, t in enumerate(hp):
        if r > 0:
            r -= HOP
        if not go[t - 1] or r > 0:
            continue
        if s1[i] >= thr1 and s2[i] >= thr2:
            consec += 1
            if consec >= M:
                consec = 0; r = REFR; dets += 1
        else:
            consec = 0
    return dets


# --------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(
        description="Evaluate a trained wake-word model (streaming FA/hr, FRR, calibration).")
    ap.add_argument("--config", default=os.path.join(HERE, "config.yaml"),
                    help="path to config.yaml (default: ./config.yaml)")
    args = ap.parse_args()

    if not os.path.exists(args.config):
        sys.exit(f"config not found: {args.config}")
    sys.path.insert(0, HERE)
    from train import load_config
    cfg = load_config(args.config)
    wake_word = cfg.get("wake_word", "hey_aura")
    dataset_dir = os.path.join(HERE, cfg.get("dataset_dir", f"datasets/{wake_word}"))
    output_dir = os.path.join(HERE, cfg.get("output_dir", "models"))

    labels_path = os.path.join(output_dir, "labels.json")
    if not os.path.exists(labels_path):
        sys.exit(f"labels.json not found in {output_dir} — run `python train.py` first.")
    if not os.path.isdir(dataset_dir):
        sys.exit(f"dataset_dir not found: {dataset_dir}")

    sys.path.insert(0, TOOLS)
    import numpy as np
    import onnxruntime as ort
    import aura_frontend as fe
    import aura_data
    import calibrate as cal

    with open(labels_path) as f:
        labels = json.load(f)
    target = int(labels.get("target_index", 1))
    calibration = labels.get("calibration") or {"method": "none", "stage1": {}, "stage2": {}}

    s1_path = os.path.join(output_dir, (labels.get("stage1") or {}).get("onnx", f"{wake_word}.onnx"))
    s1 = ort.InferenceSession(s1_path, providers=["CPUExecutionProvider"]); i1 = s1.get_inputs()[0].name
    s2 = i2 = None
    if labels.get("stage2"):
        s2_path = os.path.join(output_dir, labels["stage2"]["onnx"])
        if os.path.exists(s2_path):
            s2 = ort.InferenceSession(s2_path, providers=["CPUExecutionProvider"])
            i2 = s2.get_inputs()[0].name

    print(f"wake_word={wake_word}  stage1={os.path.basename(s1_path)}  "
          f"cascade={'yes' if s2 else 'no'}  calibration={calibration.get('method')}")

    # ---- held-out positives (FRR) and negatives (FA corpus) ----
    pos_preps, neg_clips = [], []
    for path, label, spk, acc in aura_data.items("test", dataset_dir=dataset_dir, wake_word=wake_word):
        x = aura_data.read_wav(path)
        if label == 1:
            padded = np.concatenate([np.zeros(int(0.5 * fe.SR)), x, np.zeros(int(0.7 * fe.SR))])
            pos_preps.append(_stream_prep(padded, s1, i1, s2, i2, calibration, target, cal, fe))
        else:
            neg_clips.append(x)
    if not pos_preps:
        sys.exit("no held-out positive clips — need more speakers for a speaker-independent split.")

    # negative corpus = all held-out negatives concatenated with 0.3 s gaps
    if neg_clips:
        parts = []
        for c in neg_clips:
            parts.append(c); parts.append(np.zeros(int(0.3 * fe.SR)))
        neg_audio = np.concatenate(parts)
    else:
        neg_audio = np.zeros(fe.SR)
    neg_hours = len(neg_audio) / fe.SR / 3600.0
    neg_prep = _stream_prep(neg_audio, s1, i1, s2, i2, calibration, target, cal, fe)

    # ---- threshold x M sweep -> operating point (FA<=0.05/hr AND FRR<=5%) ----
    ths = [0.5, 0.6, 0.7, 0.8, 0.9, 0.95]
    rows, best = [], None
    for M in (1, 2, 3):
        for t1 in ths:
            for t2 in (ths if s2 else [0.0]):
                fa = _decide(neg_prep, t1, t2, M)
                fa_hr = fa / max(neg_hours, 1e-9)
                frr = sum(1 for p in pos_preps if _decide(p, t1, t2, M) == 0) / len(pos_preps)
                rows.append((M, t1, t2, fa_hr, frr))
                if fa_hr <= 0.05 and frr <= 0.05 and (best is None or frr < best[4]):
                    best = (M, t1, t2, fa_hr, frr)
    op = best or min(rows, key=lambda r: r[3] + r[4])

    # ---- per-clip ECE/MCE/Brier/AUROC (calibrated stage-1 posteriors) ----
    ece_p, ece_y = [], []
    for path, label, spk, acc in aura_data.items("test", dataset_dir=dataset_dir, wake_word=wake_word):
        z = s1.run(None, {i1: fe.features(aura_data.read_wav(path), apply_dsp_chain=True,
                                          frames=fe.WINDOW_FRAMES)[None].astype(np.float32)})[0][0]
        ece_p.append(cal.apply_calibration(z, calibration, "stage1", target)); ece_y.append(int(label))
    ece_p = np.asarray(ece_p, np.float64); ece_y = np.asarray(ece_y, np.int64)
    ece_val, mce_val, _ = cal.ece_mce(ece_p, ece_y)
    brier_val = cal.brier(ece_p, ece_y); auroc_val = cal.auroc(ece_p, ece_y)

    size_kb = os.path.getsize(s1_path) / 1024 + (os.path.getsize(s2_path) / 1024 if s2 else 0)

    # ---- console summary ----
    print(f"held-out: {len(pos_preps)} positives | negative corpus {neg_hours * 60:.1f} min "
          f"({int(ece_y.sum())} pos / {int((ece_y == 0).sum())} neg clips)")
    print(f"operating point: M={op[0]} stage1_thr={op[1]}" + (f" stage2_thr={op[2]}" if s2 else ""))
    print(f"  FA/hr={op[3]:.3f} ({'OK' if op[3] <= 0.05 else 'high'})  "
          f"FRR={op[4] * 100:.1f}% ({'OK' if op[4] <= 0.05 else 'high'})")
    print(f"  ECE={ece_val:.4f} MCE={mce_val:.4f} Brier={brier_val:.4f} AUROC={auroc_val:.4f}")
    print(f"  model size={size_kb:.1f} KB")

    # ---- dashboard ----
    os.makedirs(DASH, exist_ok=True)
    report = os.path.join(DASH, f"{wake_word}_eval.md")
    with open(report, "w", encoding="utf-8") as f:
        f.write(f"# '{wake_word}' Evaluation" + (" — CASCADE (stage1+stage2)" if s2 else "") + "\n\n")
        f.write(f"Speaker-independent held-out split. Positives: {len(pos_preps)}; "
                f"negative corpus: {neg_hours * 60:.1f} min. Streaming-detector mirror "
                f"(win {WINDOW}, hop {HOP}, refractory {REFR}).\n\n")
        f.write("| metric | target | measured | met |\n|---|---|---|---|\n")
        f.write(f"| FA/hr | <= 0.05 | {op[3]:.3f} | {'YES' if op[3] <= 0.05 else 'NO'} |\n")
        f.write(f"| False Reject | <= 5% | {op[4] * 100:.1f}% | {'YES' if op[4] <= 0.05 else 'NO'} |\n")
        f.write(f"| Model size | < 500 KB | {size_kb:.1f} KB | {'YES' if size_kb < 500 else 'NO'} |\n\n")
        f.write(f"**Operating point:** M={op[0]}, stage1_thr={op[1]}"
                + (f", stage2_thr={op[2]}" if s2 else "")
                + (" — meets FA & FR." if best else " — no point meets both (best-effort shown).") + "\n\n")
        f.write("## Calibration quality (per-clip stage-1 posteriors)\n\n")
        f.write(f"Calibration applied: **{calibration.get('method', 'none')}**. "
                f"Measured on {int(ece_y.sum())} positive + {int((ece_y == 0).sum())} negative held-out clips.\n\n")
        f.write("| ECE (10-bin) | MCE | Brier | AUROC |\n|---|---|---|---|\n")
        f.write(f"| {ece_val:.4f} | {mce_val:.4f} | {brier_val:.4f} | {auroc_val:.4f} |\n\n")
        f.write("## Sweep (lowest FA/hr first)\n\n| M | s1_thr | s2_thr | FA/hr | FRR |\n|---|---|---|---|---|\n")
        for r in sorted(rows, key=lambda r: r[3])[:12]:
            f.write(f"| {r[0]} | {r[1]} | {r[2]} | {r[3]:.3f} | {r[4]:.3f} |\n")
    print(f"\nwrote {report}")


if __name__ == "__main__":
    main()
