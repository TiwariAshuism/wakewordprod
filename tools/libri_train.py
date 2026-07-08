#!/usr/bin/env python3
"""Train the REAL-speech 'little' keyword model on dataset/libri_little (2-class: wake vs not-wake).

SPEAKER-independent: ~20% of DISTINCT LibriSpeech speakers are held out and NEVER seen in
training (see libri_data.py), so recall / per-clip FAR / F1 reflect UNSEEN REAL VOICES. Reuses
the AURA front-end, augmentation, and model zoo. Stage-1 = dscnn -> .data/libri.onnx,
Stage-2 = cnn -> .data/libri_stage2.onnx. Broad-speech negatives (Speech-Commands words +
_background_noise_ + ambient) are folded into the TRAIN negatives so the model isn't naive to
generic speech. Feature cache (.data/libri_feat.npz) is shared across both archs."""
import argparse
import json
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import aura_frontend as fe
import aura_augment as aug
import libri_data
import kws_models

DATA = os.path.join(os.path.dirname(__file__), "..", ".data")
NUM_CLASSES = 2  # 0 = not-wake, 1 = "little"


def _sc_root():
    p = os.path.join(DATA, "SpeechCommands", "speech_commands_v0.02")
    return p if os.path.isdir(p) else None


def build(split, noises, aug_variants, seed):
    rng = np.random.RandomState(seed)
    X, y = [], []
    for path, label, spk, word in libri_data.items(split):
        x = libri_data.read_wav(path)
        X.append(fe.features(x, apply_dsp_chain=True, frames=fe.WINDOW_FRAMES))
        y.append(label)
        if split == "train":
            # Augment both classes; hard negatives (confusable real words) most.
            k = aug_variants + (2 if label == 0 else 1)
            for _ in range(k):
                X.append(fe.features(aug.augment(x, noises, rng), apply_dsp_chain=True))
                y.append(label)

    # FA-reduction: broaden the negative distribution so the model learns "generic speech
    # and ambient are NOT the keyword". Train split only — the test set stays the held-out
    # SPEAKERS for an honest speaker-independent recall/FAR.
    if split == "train":
        sc = _sc_root()
        if sc:
            import sc_dataset
            n_sc = 0
            for xx, lab in sc_dataset.iter_clips(sc, "training", shuffle_seed=seed):
                X.append(fe.features(xx, apply_dsp_chain=True)); y.append(0)  # broad speech = negative
                if rng.random() < 0.5:  # + a noisy variant
                    X.append(fe.features(aug.augment(xx, noises, rng), apply_dsp_chain=True)); y.append(0)
                n_sc += 1
                if n_sc >= 2500:
                    break
        # ambient/noise negatives chopped into 1 s windows
        for nz in noises:
            for _ in range(30):
                off = rng.randint(0, max(1, len(nz) - fe.SR))
                seg = nz[off:off + fe.SR] * rng.uniform(0.3, 1.0)
                X.append(fe.features(seg, apply_dsp_chain=True)); y.append(0)
    return np.asarray(X, np.float32), np.asarray(y, np.int64)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arch", default="dscnn", choices=["cnn", "bcresnet", "dscnn"])
    ap.add_argument("--out", default=None, help="onnx basename override (default: stage naming)")
    ap.add_argument("--epochs", type=int, default=25)
    ap.add_argument("--aug-variants", type=int, default=2)
    ap.add_argument("--batch", type=int, default=128)
    args = ap.parse_args()
    import torch
    import torch.nn as nn
    torch.manual_seed(0); np.random.seed(0)

    noises = aug.load_background_noise(os.path.join(DATA, "SpeechCommands", "speech_commands_v0.02")) \
        if os.path.isdir(os.path.join(DATA, "SpeechCommands")) else []

    cache = os.path.join(DATA, "libri_feat.npz")  # arch-independent -> shared by both stages
    if os.path.exists(cache):
        d = np.load(cache); Xtr, ytr, Xte, yte = d["Xtr"], d["ytr"], d["Xte"], d["yte"]
    else:
        Xtr, ytr = build("train", noises, args.aug_variants, 0)
        Xte, yte = build("test", noises, 0, 1)
        np.savez_compressed(cache, Xtr=Xtr, ytr=ytr, Xte=Xte, yte=yte)
    print(f"[{args.arch}] train={Xtr.shape} test={Xte.shape} pos_tr={int(ytr.sum())} "
          f"neg_tr={int((ytr==0).sum())} pos_te={int(yte.sum())} neg_te={int((yte==0).sum())}")

    mean = Xtr.reshape(-1, fe.N_MELS).mean(0); std = Xtr.reshape(-1, fe.N_MELS).std(0) + 1e-5
    model = kws_models.build_model(args.arch, mean, std, NUM_CLASSES)
    params = kws_models.param_count(model)

    # Softened (sqrt) class weights: keep recall without over-weighting the positive class.
    counts = np.bincount(ytr, minlength=NUM_CLASSES).astype(np.float32)
    w = np.sqrt(counts.sum() / (NUM_CLASSES * np.maximum(counts, 1))).astype(np.float32)
    crit = nn.CrossEntropyLoss(weight=torch.tensor(w), label_smoothing=0.05)
    opt = torch.optim.Adam(model.parameters(), lr=2e-3, weight_decay=1e-4)
    warm, tot = 3, args.epochs
    sched = torch.optim.lr_scheduler.LambdaLR(
        opt, lambda e: (e + 1) / warm if e < warm else 0.5 * (1 + math.cos(math.pi * (e - warm) / max(1, tot - warm))))
    Xtr_t, ytr_t = torch.tensor(Xtr), torch.tensor(ytr)
    Xte_t, yte_t = torch.tensor(Xte), torch.tensor(yte)
    rng = np.random.RandomState(0)

    def metrics(logits):
        pred = logits.argmax(1)
        tp = int(((pred == 1) & (yte_t == 1)).sum()); fp = int(((pred == 1) & (yte_t == 0)).sum())
        fn = int(((pred == 0) & (yte_t == 1)).sum())
        rec = tp / max(tp + fn, 1); prec = tp / max(tp + fp, 1)
        f1 = 2 * prec * rec / max(prec + rec, 1e-9)
        far = fp / max(int((yte_t == 0).sum()), 1)  # per-clip false-accept rate on negatives
        return f1, rec, far

    def op_sweep(logits):
        """HONEST operating-point analysis on the held-out REAL speakers.
        Sweep the Stage-1 decision threshold on P(class=1) and report recall at
        fixed per-clip FAR budgets (1/2/5%), the best-F1 point, and raw argmax."""
        p = torch.softmax(logits, 1)[:, 1].numpy()
        yv = yte_t.numpy()
        pos = p[yv == 1]; neg = p[yv == 0]
        P = int((yv == 1).sum()); N = int((yv == 0).sum())
        cand = np.unique(np.concatenate([p, [0.0, 1.0 + 1e-6]]))
        rows = []  # (thr, recall, far, prec, f1)
        for t in cand:
            tp = int((pos >= t).sum()); fp = int((neg >= t).sum())
            rec = tp / max(P, 1); far = fp / max(N, 1)
            prec = tp / max(tp + fp, 1)
            f1 = 2 * prec * rec / max(prec + rec, 1e-9)
            rows.append((float(t), rec, far, prec, f1))

        def at_far(budget):
            # max recall achievable while keeping per-clip FAR <= budget
            ok = [r for r in rows if r[2] <= budget + 1e-12]
            best = max(ok, key=lambda r: (r[1], -r[2]))  # prefer recall, tie-break lower FAR
            return {"far_budget": budget, "thr": round(best[0], 4),
                    "recall": round(best[1], 4), "far": round(best[2], 4),
                    "precision": round(best[3], 4), "f1": round(best[4], 4)}

        bestf1 = max(rows, key=lambda r: r[4])
        # raw argmax == threshold 0.5 for a 2-class softmax head
        arg = min(rows, key=lambda r: abs(r[0] - 0.5))
        return {
            "P_pos_test": P, "N_neg_test": N,
            "far_grain": round(1.0 / max(N, 1), 4), "recall_grain": round(1.0 / max(P, 1), 4),
            "recall_at_far": {"1pct": at_far(0.01), "2pct": at_far(0.02), "5pct": at_far(0.05)},
            "best_f1": {"thr": round(bestf1[0], 4), "recall": round(bestf1[1], 4),
                        "far": round(bestf1[2], 4), "precision": round(bestf1[3], 4),
                        "f1": round(bestf1[4], 4)},
            "argmax": {"thr": 0.5, "recall": round(arg[1], 4), "far": round(arg[2], 4),
                       "precision": round(arg[3], 4), "f1": round(arg[4], 4)},
        }

    best_f1, best = -1, None
    n = len(Xtr_t)
    for ep in range(args.epochs):
        model.train(); perm = torch.randperm(n)
        for s in range(0, n, args.batch):
            idx = perm[s:s + args.batch]
            xb = np.stack([aug.spec_augment(f, rng) for f in Xtr[idx.numpy()]])
            opt.zero_grad(); loss = crit(model(torch.tensor(xb)), ytr_t[idx]); loss.backward(); opt.step()
        sched.step(); model.eval()
        with torch.no_grad():
            f1, rec, far = metrics(model(Xte_t))
        if f1 > best_f1:
            best_f1, best = f1, {k: v.clone() for k, v in model.state_dict().items()}
    if best: model.load_state_dict(best)
    model.eval()
    with torch.no_grad():
        te_logits = model(Xte_t)
        f1, rec, far = metrics(te_logits)
        op = op_sweep(te_logits)

    hs = sorted(libri_data.heldout_speakers(), key=lambda s: (len(s), s))
    base = args.out if args.out else ("libri" if args.arch == "dscnn" else "libri_stage2")
    onnx = os.path.join(DATA, f"{base}.onnx")
    try:
        torch.onnx.export(model, torch.zeros(1, fe.WINDOW_FRAMES, fe.N_MELS), onnx,
                          input_names=["input"], output_names=["output"], opset_version=13, dynamo=False)
    except TypeError:
        torch.onnx.export(model, torch.zeros(1, fe.WINDOW_FRAMES, fe.N_MELS), onnx,
                          input_names=["input"], output_names=["output"], opset_version=13)
    m = {"arch": args.arch, "params": params, "num_classes": 2, "target_class": 1,
         "keyword": "little", "eval": "speaker-independent",
         "speaker_indep_f1": round(f1, 4), "recall": round(rec, 4),
         "per_clip_far": round(far, 4), "size_kb": round(os.path.getsize(onnx) / 1024, 1),
         "n_train_clips": int(len(ytr)), "n_test_clips": int(len(yte)),
         "n_heldout_speakers": len(hs), "heldout_speakers": hs,
         "pos_te": int(yte.sum()), "neg_te": int((yte == 0).sum()),
         "epochs": args.epochs, "operating_points": op}
    json.dump(m, open(os.path.join(DATA, f"{base}_metrics.json"), "w"), indent=2)
    print(f"[{args.arch}] params={params} size={m['size_kb']}KB epochs={args.epochs}")
    print(f"  ARGMAX (thr=0.5)     recall={op['argmax']['recall']:.3f} "
          f"FAR={op['argmax']['far']:.3f} F1={op['argmax']['f1']:.3f}")
    print(f"  BEST-F1 (thr={op['best_f1']['thr']:.3f}) recall={op['best_f1']['recall']:.3f} "
          f"FAR={op['best_f1']['far']:.3f} F1={op['best_f1']['f1']:.3f}")
    for tag in ("1pct", "2pct", "5pct"):
        r = op["recall_at_far"][tag]
        print(f"  recall@FAR<={tag:>4}   recall={r['recall']:.3f} FAR={r['far']:.3f} "
              f"thr={r['thr']:.3f} prec={r['precision']:.3f}")
    print(f"  [held-out REAL speakers: {op['P_pos_test']} pos / {op['N_neg_test']} neg clips, "
          f"{len(hs)} speakers]  -> {onnx}")


if __name__ == "__main__":
    main()
