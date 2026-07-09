#!/usr/bin/env python3
"""Evaluate a 'hey m' model (optionally as a Stage-1 + Stage-2 CASCADE) against the hard
requirements via the streaming-detector mirror.

Reports TWO honest false-accept numbers (not conflated):
  - **FA/hr** on a *realistic* negative corpus (ambient noise + broad speech, with
    confusables at realistic low frequency) — the audit's FA/hr methodology.
  - **Confusable false-fire rate** on the held-out hard-negative confusables (the
    adversarial stress metric — "hey man / hey ma / hey am" etc.).
Plus FR on held-out-speaker positives, size, host latency. Sweeps threshold x M and, for
the cascade, stage1 x stage2 thresholds, to find an operating point meeting FA <= 0.05/hr
AND FR <= 5%. Writes benchmarks/dashboards/heym_report.md."""
import argparse
import json
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.join(HERE, "..", "benchmarks", "harness")]
import aura_frontend as fe
import aura_augment as aug
import heym_data
import calibrate as cal  # calibration apply + ECE/MCE helpers
from bench_kws import EnergyGate

DATA = os.path.join(HERE, "..", ".data")
DASH = os.path.join(HERE, "..", "benchmarks", "dashboards")
HOP = fe.HOP
TARGET = 1


def marv_scores(mel, sess, in_name, hop_pts, window=100, calibration=None, stage="stage1"):
    """Target-class posterior per hop window. If `calibration` (a labels.json calibration
    block) is given, apply Platt sigmoid(a*z+b) or temperature softmax(z/T); else plain softmax."""
    out = np.zeros(len(hop_pts), np.float32)
    for i, t in enumerate(hop_pts):
        z = sess.run(None, {in_name: mel[t - window:t][None].astype(np.float32)})[0][0]
        if calibration is not None:
            out[i] = cal.apply_calibration(z, calibration, stage, TARGET)
        else:
            z = z - z.max(); e = np.exp(z); out[i] = (e / e.sum())[TARGET]
    return out


def stream_prep(audio, sess1, in1, sess2, in2, window=100, hop=10, calibration=None):
    dsp = fe.apply_dsp(audio); mel = fe.log_mel(dsp)
    T = len(mel)
    gate = EnergyGate(); go = np.zeros(max(T, 1), bool)
    for t in range(T):
        go[t] = gate.frame(dsp[t * HOP:t * HOP + HOP])
    hp = list(range(window, T + 1, hop))
    if not hp:
        return None
    s1 = marv_scores(mel, sess1, in1, hp, calibration=calibration, stage="stage1")
    s2 = (marv_scores(mel, sess2, in2, hp, calibration=calibration, stage="stage2")
          if sess2 else np.ones(len(hp), np.float32))
    return hp, s1, s2, go


def decide(prep, thr1, thr2, M=3, hop=10, refr=100):
    if prep is None:
        return 0
    hp, s1, s2, go = prep
    consec = r = dets = 0
    for i, t in enumerate(hp):
        if r > 0:
            r -= hop
        if not go[t - 1] or r > 0:
            continue
        if s1[i] >= thr1 and s2[i] >= thr2:
            consec += 1
            if consec >= M:
                consec = 0; r = refr; dets += 1
        else:
            consec = 0
    return dets


def realistic_negative(max_seconds, seed=5):
    """Ambient + broad speech dominate; confusables sprinkled at realistic low frequency."""
    rng = np.random.RandomState(seed)
    parts = []
    sc = os.path.join(DATA, "SpeechCommands", "speech_commands_v0.02")
    if os.path.isdir(sc):
        import sc_dataset
        parts += aug.load_background_noise(sc)
        got = sum(len(p) for p in parts)
        for x, lab in sc_dataset.iter_clips(sc, "testing", shuffle_seed=seed):
            parts.append(x); parts.append(np.zeros(int(0.1 * fe.SR))); got += len(x)
            if got >= max_seconds * fe.SR:
                break
    # sprinkle a FEW held-out confusables (realistic: users rarely say near-words)
    conf = [heym_data.read_wav(p) for p, l, s, a in heym_data.items("test") if l == 0]
    rng.shuffle(conf)
    for c in conf[:15]:
        parts.append(c); parts.append(np.zeros(int(1.0 * fe.SR)))
    return np.concatenate(parts)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage1", default=os.path.join(DATA, "heym_dscnn.onnx"))
    ap.add_argument("--stage2", default="")   # optional verifier for the cascade
    ap.add_argument("--neg-seconds", type=int, default=900)
    ap.add_argument("--calibration", default="",
                    help="path to a labels.json with a 'calibration' block; applies it "
                         "(Platt sigmoid(a*z+b) or softmax(z/T)) so FA/hr + ECE use calibrated scores")
    args = ap.parse_args()
    import onnxruntime as ort
    s1 = ort.InferenceSession(args.stage1, providers=["CPUExecutionProvider"]); i1 = s1.get_inputs()[0].name
    s2 = i2 = None
    if args.stage2 and os.path.exists(args.stage2):
        s2 = ort.InferenceSession(args.stage2, providers=["CPUExecutionProvider"]); i2 = s2.get_inputs()[0].name

    calibration = None
    if args.calibration:
        calibration = cal.load_calibration(args.calibration)
        print(f"calibration: method={calibration.get('method')} from {args.calibration}")

    neg = realistic_negative(args.neg_seconds); neg_hours = len(neg) / fe.SR / 3600.0
    neg_prep = stream_prep(neg, s1, i1, s2, i2, calibration=calibration)
    print(f"realistic negative corpus: {neg_hours*60:.1f} min  cascade={'yes' if s2 else 'no'}")

    pos = []
    for p, l, sp, a in heym_data.items("test"):
        if l == 1:
            padded = np.concatenate([np.zeros(int(0.5*fe.SR)), heym_data.read_wav(p), np.zeros(int(0.7*fe.SR))])
            pos.append(stream_prep(padded, s1, i1, s2, i2, calibration=calibration))
    conf = []
    for p, l, sp, a in heym_data.items("test"):
        if l == 0:
            padded = np.concatenate([np.zeros(int(0.5*fe.SR)), heym_data.read_wav(p), np.zeros(int(0.7*fe.SR))])
            conf.append(stream_prep(padded, s1, i1, s2, i2, calibration=calibration))

    # ---- ECE / MCE (10-bin) on per-clip stage-1 posteriors (calibrated if --calibration) ----
    cal_block = calibration or {"method": "none"}
    ece_p, ece_y = [], []
    for p, l, sp, a in heym_data.items("test"):
        z = s1.run(None, {i1: fe.features(heym_data.read_wav(p), apply_dsp_chain=True)[None].astype(np.float32)})[0][0]
        ece_p.append(cal.apply_calibration(z, cal_block, "stage1", TARGET))
        ece_y.append(int(l))
    ece_p = np.asarray(ece_p, np.float64); ece_y = np.asarray(ece_y, np.int64)
    ece_val, mce_val, _ = cal.ece_mce(ece_p, ece_y)
    brier_val = cal.brier(ece_p, ece_y); auroc_val = cal.auroc(ece_p, ece_y)
    print(f"stage1 calibration quality (per-clip): ECE={ece_val:.4f} MCE={mce_val:.4f} "
          f"Brier={brier_val:.4f} AUROC={auroc_val:.4f} "
          f"(n_pos={int(ece_y.sum())}, n_neg={int((ece_y==0).sum())}, method={cal_block.get('method')})")

    ths = [0.5, 0.6, 0.7, 0.8, 0.9, 0.95]
    rows = []; best = None
    for M in (1, 2, 3):
        for t1 in ths:
            for t2 in (ths if s2 else [0.0]):
                fa = decide(neg_prep, t1, t2, M); fa_hr = fa / max(neg_hours, 1e-9)
                frr = sum(1 for p in pos if decide(p, t1, t2, M) == 0) / max(len(pos), 1)
                cff = sum(1 for c in conf if decide(c, t1, t2, M) > 0) / max(len(conf), 1)
                rows.append((M, t1, t2, fa_hr, frr, cff))
                if fa_hr <= 0.05 and frr <= 0.05 and (best is None or frr < best[4]):
                    best = (M, t1, t2, fa_hr, frr, cff)
    op = best or min(rows, key=lambda r: r[3] + r[4])  # else lowest FA+FR
    size_kb = os.path.getsize(args.stage1) / 1024 + (os.path.getsize(args.stage2)/1024 if s2 else 0)
    dummy = np.zeros((1, fe.WINDOW_FRAMES, fe.N_MELS), np.float32)
    for _ in range(5): s1.run(None, {i1: dummy})
    L = []
    for _ in range(200):
        tt = time.perf_counter(); s1.run(None, {i1: dummy});
        if s2: s2.run(None, {i2: dummy})
        L.append((time.perf_counter()-tt)*1000)
    lat = float(np.percentile(L, 50))

    os.makedirs(DASH, exist_ok=True)
    with open(os.path.join(DASH, "heym_report.md"), "w", encoding="utf-8") as f:
        f.write("# 'hey m' Requirements Evaluation" + (" — CASCADE (stage1+stage2)" if s2 else "") + "\n\n")
        f.write(f"Speaker-independent. Realistic negative corpus {neg_hours*60:.1f} min "
                f"(ambient + broad speech + sparse confusables). Positives: {len(pos)}; "
                f"confusable-stress clips: {len(conf)}.\n\n")
        f.write("| metric | hard target | measured | met |\n|---|---|---|---|\n")
        f.write(f"| FA/hr (realistic) | <= 0.05 | {op[3]:.3f} | {'YES' if op[3]<=0.05 else 'NO'} |\n")
        f.write(f"| False Reject | <= 5% | {op[4]*100:.1f}% | {'YES' if op[4]<=0.05 else 'NO'} |\n")
        f.write(f"| Confusable false-fire (stress) | (report) | {op[5]*100:.1f}% | — |\n")
        f.write(f"| Model size | < 500 KB | {size_kb:.1f} KB | {'YES' if size_kb<500 else 'NO'} |\n")
        f.write(f"| Host latency (not device) | <100 ms | {lat:.3f} ms | (host) |\n")
        f.write(f"\n**Operating point:** M={op[0]}, stage1_thr={op[1]}"
                + (f", stage2_thr={op[2]}" if s2 else "")
                + (" — meets FA & FR" if best else " — no point meets both FA & FR (best-effort shown)") + ".\n\n")
        f.write("## Sweep (top by lowest FA/hr)\n\n| M | s1_thr | s2_thr | FA/hr | FRR | confusable-fire |\n|---|---|---|---|---|---|\n")
        for r in sorted(rows, key=lambda r: r[3])[:12]:
            f.write(f"| {r[0]} | {r[1]} | {r[2]} | {r[3]:.3f} | {r[4]:.3f} | {r[5]:.3f} |\n")
        f.write("\n## Stage-1 calibration quality (per-clip ECE/MCE)\n\n")
        f.write(f"Measured on {int(ece_y.sum())} positive + {int((ece_y==0).sum())} negative "
                "held-out test clips (single-window stage-1 posteriors). Calibration applied: "
                f"**{cal_block.get('method', 'none')}**"
                + (f" from `{args.calibration}`" if args.calibration else "") + ".\n\n")
        f.write("| ECE (10-bin) | MCE | Brier | AUROC |\n|---|---|---|---|\n")
        f.write(f"| {ece_val:.4f} | {mce_val:.4f} | {brier_val:.4f} | {auroc_val:.4f} |\n\n")
        f.write("_FA/hr on realistic ambient+speech (audit methodology); confusable-fire is the "
                "adversarial stress metric reported separately. en-IN-dominant data; en-US/GB/AU absent._\n")
    print(f"OP M={op[0]} s1={op[1]} s2={op[2]} FA/hr={op[3]:.3f} FRR={op[4]:.3f} confFire={op[5]:.3f} "
          f"size={size_kb:.1f}KB -> {os.path.join(DASH,'heym_report.md')}")


if __name__ == "__main__":
    main()
