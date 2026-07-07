#!/usr/bin/env python3
"""Train one AURA KWS architecture with augmentation + stabilized training (robustness
sprint). Head-to-head driver: run once per --arch {cnn,bcresnet,dscnn}; then
tools/select_best_model.py picks the winner and exports it as the shipped model.

Front-end = tools/aura_frontend.py (numpy == on-device C++, verified). Augmentation
(tools/aura_augment.py) is waveform-domain BEFORE features(), plus online SpecAugment, so
the on-device front-end is untouched. 13 classes: 11 words (marvin first) + _unknown_ +
_silence_. marvin_index = 0.

Outputs (per arch): .data/kws_<arch>.onnx + .data/kws_<arch>_metrics.json.
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
import kws_models

TARGET_WORDS = ["marvin", "yes", "no", "up", "down", "left", "right", "on", "off", "stop", "go"]
LABELS = TARGET_WORDS + ["_unknown_", "_silence_"]
MARVIN_INDEX = 0
NUM_CLASSES = len(LABELS)  # 13
SILENCE_IDX = LABELS.index("_silence_")

DATA = os.path.join(os.path.dirname(__file__), "..", ".data")


def sweep(prob_marvin, y, thresholds=(0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9)):
    """Per-clip marvin TP rate + non-marvin FP rate at each threshold."""
    out = {}
    pos = y == MARVIN_INDEX
    neg = ~pos
    for t in thresholds:
        fired = prob_marvin >= t
        tp = float((fired & pos).sum()) / max(int(pos.sum()), 1)
        fp = float((fired & neg).sum()) / max(int(neg.sum()), 1)
        out[f"{t:.1f}"] = {"tp": round(tp, 4), "fp": round(fp, 4)}
    return out


def build_dataset(root, subset, label_index, limit, unknown_ratio, aug_variants, seed, noises):
    """Return X [N,100,40], y [N]. subset 'training' gets aug variants; others clean only."""
    rng = np.random.RandomState(seed)
    counts = {i: 0 for i in range(NUM_CLASSES)}
    unknown_cap = limit * unknown_ratio
    unk = LABELS.index("_unknown_")
    X, y = [], []
    is_train = subset == "training"

    def all_filled():  # classes 0..unk are filled from clips; _silence_ is generated separately
        return all(counts[c] >= (unknown_cap if c == unk else limit) for c in range(unk + 1))

    for x, label in sc_dataset.iter_clips(root, subset, shuffle_seed=seed):
        if all_filled():
            break
        cls = label_index.get(label, unk)
        cap = unknown_cap if cls == unk else limit
        if counts[cls] >= cap:
            continue
        X.append(fe.features(x, apply_dsp_chain=True, frames=fe.WINDOW_FRAMES))
        y.append(cls)
        counts[cls] += 1
        if is_train:
            k = aug_variants + (2 if cls == MARVIN_INDEX else 0)  # augment marvin more
            for _ in range(k):
                xa = aug.augment(x, noises, rng)
                X.append(fe.features(xa, apply_dsp_chain=True, frames=fe.WINDOW_FRAMES))
                y.append(cls)
    # synthetic _silence_ class from background noise
    n_sil = limit if is_train else max(1, limit // 4)
    for _ in range(n_sil):
        s = aug.silence_clip(noises, rng, length=fe.SR)
        X.append(fe.features(s, apply_dsp_chain=True, frames=fe.WINDOW_FRAMES))
        y.append(SILENCE_IDX)
    counts[SILENCE_IDX] += n_sil
    return np.asarray(X, dtype=np.float32), np.asarray(y, dtype=np.int64), counts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arch", default="cnn", choices=["cnn", "bcresnet", "dscnn"])
    ap.add_argument("--data-dir", default=DATA)
    ap.add_argument("--epochs", type=int, default=30)
    ap.add_argument("--limit-per-class", type=int, default=1200)
    ap.add_argument("--unknown-ratio", type=int, default=2)
    ap.add_argument("--aug-variants", type=int, default=2)
    ap.add_argument("--batch", type=int, default=128)
    ap.add_argument("--patience", type=int, default=8)
    args = ap.parse_args()

    import torch
    import torch.nn as nn
    torch.manual_seed(0)
    np.random.seed(0)

    root = sc_dataset.find_root(args.data_dir)
    label_index = {w: i for i, w in enumerate(TARGET_WORDS)}

    # Arch-independent augmented feature cache (built once, reused across archs).
    cache = os.path.join(args.data_dir, "aura_feat_aug.npz")
    if os.path.exists(cache):
        print(f"loading cached augmented features: {cache}")
        d = np.load(cache)
        Xtr, ytr, Xte, yte, Xte_noisy = d["Xtr"], d["ytr"], d["Xte"], d["yte"], d["Xte_noisy"]
    else:
        noises = aug.load_background_noise(root)
        print(f"loaded {len(noises)} background-noise clips; extracting augmented features...")
        Xtr, ytr, tr_c = build_dataset(root, "training", label_index, args.limit_per_class,
                                       args.unknown_ratio, args.aug_variants, 0, noises)
        Xte, yte, _ = build_dataset(root, "testing", label_index, args.limit_per_class // 3,
                                    args.unknown_ratio, 0, 1, noises)
        # noisy test = one augmentation pass over the same testing clips (robustness eval)
        Xn, yn = [], []
        unk = LABELS.index("_unknown_")
        cap = {i: 0 for i in range(NUM_CLASSES)}
        te_limit = args.limit_per_class // 3

        def noisy_filled():
            return all(cap[c] >= (te_limit * args.unknown_ratio if c == unk else te_limit)
                       for c in range(unk + 1))

        for x, label in sc_dataset.iter_clips(root, "testing", shuffle_seed=1):
            if noisy_filled():
                break
            cls = label_index.get(label, unk)
            lim = te_limit * (args.unknown_ratio if cls == unk else 1)
            if cap[cls] >= lim:
                continue
            Xn.append(fe.features(aug.augment(x, noises, np.random.RandomState(1000 + cap[cls])),
                                  apply_dsp_chain=True))
            yn.append(cls)
            cap[cls] += 1
        Xte_noisy = np.asarray(Xn, dtype=np.float32)
        yte_noisy = np.asarray(yn, dtype=np.int64)
        print("train per-class:", {LABELS[k]: v for k, v in tr_c.items()})
        np.savez_compressed(cache, Xtr=Xtr, ytr=ytr, Xte=Xte, yte=yte,
                            Xte_noisy=Xte_noisy, yte_noisy=yte_noisy)
        d = np.load(cache)
    yte_noisy = d["yte_noisy"] if "yte_noisy" in d else yte
    print(f"features: train={Xtr.shape} clean-test={Xte.shape} noisy-test={Xte_noisy.shape}")

    mean = Xtr.reshape(-1, fe.N_MELS).mean(0)
    std = Xtr.reshape(-1, fe.N_MELS).std(0) + 1e-5

    model = kws_models.build_model(args.arch, mean, std, NUM_CLASSES)
    print(f"arch={args.arch} params={kws_models.param_count(model)}")

    counts = np.bincount(ytr, minlength=NUM_CLASSES).astype(np.float32)
    weights = (counts.sum() / (NUM_CLASSES * np.maximum(counts, 1))).astype(np.float32)
    crit = nn.CrossEntropyLoss(weight=torch.tensor(weights), label_smoothing=0.1)
    opt = torch.optim.Adam(model.parameters(), lr=2e-3, weight_decay=1e-4)
    warmup, total = 3, args.epochs
    def lr_at(ep):
        if ep < warmup:
            return (ep + 1) / warmup
        import math
        return 0.5 * (1 + math.cos(math.pi * (ep - warmup) / max(1, total - warmup)))
    sched = torch.optim.lr_scheduler.LambdaLR(opt, lr_at)

    Xtr_t, ytr_t = torch.tensor(Xtr), torch.tensor(ytr)
    Xte_t, yte_t = torch.tensor(Xte), torch.tensor(yte)

    def marvin_f1(logits, yt):
        pred = logits.argmax(1)
        mi = MARVIN_INDEX
        tp = ((pred == mi) & (yt == mi)).sum().item()
        fp = ((pred == mi) & (yt != mi)).sum().item()
        fn = ((pred != mi) & (yt == mi)).sum().item()
        p = tp / (tp + fp) if tp + fp else 0.0
        r = tp / (tp + fn) if tp + fn else 0.0
        return (2 * p * r / (p + r) if p + r else 0.0), (pred == yt).float().mean().item()

    best_f1, best_state, bad = -1.0, None, 0
    rng = np.random.RandomState(0)
    n = len(Xtr_t)
    for ep in range(args.epochs):
        model.train()
        perm = torch.randperm(n)
        tot = 0.0
        for s in range(0, n, args.batch):
            idx = perm[s:s + args.batch]
            xb = Xtr[idx.numpy()]
            xb = np.stack([aug.spec_augment(f, rng) for f in xb])  # online SpecAugment
            xb_t = torch.tensor(xb)
            opt.zero_grad()
            loss = crit(model(xb_t), ytr_t[idx])
            loss.backward()
            opt.step()
            tot += loss.item() * len(idx)
        sched.step()
        model.eval()
        with torch.no_grad():
            f1, acc = marvin_f1(model(Xte_t), yte_t)
        print(f"epoch {ep+1:2d}/{args.epochs} loss={tot/n:.4f} val_acc={acc:.3f} marvin_f1={f1:.3f}")
        if f1 > best_f1:
            best_f1, best_state, bad = f1, {k: v.clone() for k, v in model.state_dict().items()}, 0
        else:
            bad += 1
            if bad >= args.patience:
                print(f"early stop at epoch {ep+1} (best marvin_f1={best_f1:.3f})")
                break
    if best_state:
        model.load_state_dict(best_state)

    # Evaluate best on clean + noisy test.
    model.eval()
    with torch.no_grad():
        clean_logits = model(Xte_t).numpy()
        noisy_logits = model(torch.tensor(Xte_noisy)).numpy()
    def softmax_marvin(z):
        z = z - z.max(1, keepdims=True)
        e = np.exp(z)
        return (e / e.sum(1, keepdims=True))[:, MARVIN_INDEX]
    clean_sweep = sweep(softmax_marvin(clean_logits), yte)
    noisy_sweep = sweep(softmax_marvin(noisy_logits), yte_noisy)
    f1_clean, acc_clean = marvin_f1(torch.tensor(clean_logits), yte_t)

    onnx_path = os.path.join(args.data_dir, f"kws_{args.arch}.onnx")
    dummy = torch.zeros(1, fe.WINDOW_FRAMES, fe.N_MELS)
    try:
        torch.onnx.export(model, dummy, onnx_path, input_names=["input"],
                          output_names=["output"], opset_version=13, dynamo=False)
    except TypeError:
        torch.onnx.export(model, dummy, onnx_path, input_names=["input"],
                          output_names=["output"], opset_version=13)

    metrics = {
        "arch": args.arch, "params": kws_models.param_count(model),
        "num_classes": NUM_CLASSES, "marvin_index": MARVIN_INDEX, "labels": LABELS,
        "val_acc_clean": round(acc_clean, 4), "marvin_f1_clean": round(f1_clean, 4),
        "clean_sweep": clean_sweep, "noisy_sweep": noisy_sweep,
        "onnx": os.path.basename(onnx_path),
    }
    with open(os.path.join(args.data_dir, f"kws_{args.arch}_metrics.json"), "w") as f:
        json.dump(metrics, f, indent=2)
    print(f"\n[{args.arch}] params={metrics['params']} f1_clean={f1_clean:.3f} "
          f"clean@0.5={clean_sweep['0.5']} noisy@0.5={noisy_sweep['0.5']}")
    print(f"exported {onnx_path}")


if __name__ == "__main__":
    main()
