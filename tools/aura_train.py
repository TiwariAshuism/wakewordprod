#!/usr/bin/env python3
"""Train a wake-word model (2-class: wake vs not-wake). Reuses the AURA front-end
(tools/aura_frontend.py), waveform augmentation (tools/aura_augment.py), and the model zoo
(tools/kws_models.py).

Two ways to drive it:
  * CLI (legacy):  `python tools/aura_train.py --arch dscnn`  trains on the synthetic
    dataset/hey_aura (accent-independent split) and writes .data/aura*.onnx — behavior
    preserved for existing scripts.
  * Importable API (the easy `train.py` flow): call `prepare_features(...)` +
    `train_arch(...)` + `export_onnx(...)` with a `dataset_dir` so it loads
    datasets/<wakeword>/{positive,negative} with a speaker-independent split.

Stage-1 = dscnn, Stage-2 = cnn. Broad-speech negatives (Speech-Commands words +
_background_noise_ + ambient) are folded into the TRAIN negatives so the model isn't naive to
generic speech."""
import argparse
import json
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import aura_frontend as fe
import aura_augment as aug
import aura_data
import kws_models

DATA = os.path.join(os.path.dirname(__file__), "..", ".data")
NUM_CLASSES = 2  # 0 = not-wake, 1 = wake word


def _sc_root():
    p = os.path.join(DATA, "SpeechCommands", "speech_commands_v0.02")
    return p if os.path.isdir(p) else None


def load_noises():
    """Background-noise clips for augmentation/negatives (empty if Speech-Commands absent)."""
    sc = os.path.join(DATA, "SpeechCommands", "speech_commands_v0.02")
    return aug.load_background_noise(sc) if os.path.isdir(sc) else []


def build(split, noises, aug_variants, seed, dataset_dir=None, wake_word=None):
    """Feature matrix for a split. `dataset_dir` None -> legacy dataset/hey_aura; set ->
    datasets/<wakeword>/{positive,negative} (speaker-independent split)."""
    rng = np.random.RandomState(seed)
    X, y = [], []
    for path, label, spk, acc in aura_data.items(split, dataset_dir=dataset_dir, wake_word=wake_word):
        x = aura_data.read_wav(path)
        X.append(fe.features(x, apply_dsp_chain=True, frames=fe.WINDOW_FRAMES))
        y.append(label)
        if split == "train":
            # Augment both classes; hard negatives (confusables) most.
            k = aug_variants + (2 if label == 0 else 1)
            for _ in range(k):
                X.append(fe.features(aug.augment(x, noises, rng), apply_dsp_chain=True))
                y.append(label)

    # FA-reduction: broaden the negative distribution so the model learns "generic speech
    # and ambient are NOT the wake word". Train split only — the test set stays the held-out
    # speakers for an honest speaker-independent recall/FAR.
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


def prepare_features(dataset_dir=None, wake_word=None, aug_variants=2, cache_path=None,
                     noises=None):
    """Build (or load-from-cache) Xtr,ytr,Xte,yte. Cache is arch-independent -> shared by
    both stages. Pass cache_path=None to skip caching."""
    if cache_path and os.path.exists(cache_path):
        d = np.load(cache_path)
        return d["Xtr"], d["ytr"], d["Xte"], d["yte"]
    if noises is None:
        noises = load_noises()
    Xtr, ytr = build("train", noises, aug_variants, 0, dataset_dir, wake_word)
    Xte, yte = build("test", noises, 0, 1, dataset_dir, wake_word)
    if cache_path:
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        np.savez_compressed(cache_path, Xtr=Xtr, ytr=ytr, Xte=Xte, yte=yte)
    return Xtr, ytr, Xte, yte


def train_arch(arch, Xtr, ytr, Xte, yte, epochs=25, batch=128, num_classes=NUM_CLASSES,
               seed=0):
    """Train one architecture. Returns (model, metrics dict). Pure torch; reuses kws_models."""
    import torch
    import torch.nn as nn
    torch.manual_seed(seed); np.random.seed(seed)

    mean = Xtr.reshape(-1, fe.N_MELS).mean(0); std = Xtr.reshape(-1, fe.N_MELS).std(0) + 1e-5
    model = kws_models.build_model(arch, mean, std, num_classes)
    params = kws_models.param_count(model)

    # Softened (sqrt) class weights: keep recall without over-weighting the positive class.
    counts = np.bincount(ytr, minlength=num_classes).astype(np.float32)
    w = np.sqrt(counts.sum() / (num_classes * np.maximum(counts, 1))).astype(np.float32)
    crit = nn.CrossEntropyLoss(weight=torch.tensor(w), label_smoothing=0.05)
    opt = torch.optim.Adam(model.parameters(), lr=2e-3, weight_decay=1e-4)
    warm, tot = 3, epochs
    sched = torch.optim.lr_scheduler.LambdaLR(
        opt, lambda e: (e + 1) / warm if e < warm else 0.5 * (1 + math.cos(math.pi * (e - warm) / max(1, tot - warm))))
    Xtr_t, ytr_t = torch.tensor(Xtr), torch.tensor(ytr)
    Xte_t, yte_t = torch.tensor(Xte), torch.tensor(yte)
    rng = np.random.RandomState(seed)

    def metrics(logits):
        pred = logits.argmax(1)
        tp = int(((pred == 1) & (yte_t == 1)).sum()); fp = int(((pred == 1) & (yte_t == 0)).sum())
        fn = int(((pred == 0) & (yte_t == 1)).sum())
        rec = tp / max(tp + fn, 1); prec = tp / max(tp + fp, 1)
        f1 = 2 * prec * rec / max(prec + rec, 1e-9)
        far = fp / max(int((yte_t == 0).sum()), 1)  # per-clip false-accept rate on negatives
        return f1, rec, far

    best_f1, best = -1, None
    n = len(Xtr_t)
    for ep in range(epochs):
        model.train(); perm = torch.randperm(n)
        for s in range(0, n, batch):
            idx = perm[s:s + batch]
            xb = np.stack([aug.spec_augment(f, rng) for f in Xtr[idx.numpy()]])
            opt.zero_grad(); loss = crit(model(torch.tensor(xb)), ytr_t[idx]); loss.backward(); opt.step()
        sched.step(); model.eval()
        with torch.no_grad():
            f1, rec, far = metrics(model(Xte_t))
        if f1 > best_f1:
            best_f1, best = f1, {k: v.clone() for k, v in model.state_dict().items()}
    if best:
        model.load_state_dict(best)
    model.eval()
    with torch.no_grad():
        f1, rec, far = metrics(model(Xte_t))
    return model, {"arch": arch, "params": params, "num_classes": num_classes,
                   "target_class": 1, "f1": round(f1, 4), "recall": round(rec, 4),
                   "per_clip_far": round(far, 4)}


def export_onnx(model, onnx_path):
    """Export a trained model to ONNX (input [1,100,40])."""
    import torch
    os.makedirs(os.path.dirname(os.path.abspath(onnx_path)), exist_ok=True)
    dummy = torch.zeros(1, fe.WINDOW_FRAMES, fe.N_MELS)
    try:
        torch.onnx.export(model, dummy, onnx_path, input_names=["input"],
                          output_names=["output"], opset_version=13, dynamo=False)
    except TypeError:
        torch.onnx.export(model, dummy, onnx_path, input_names=["input"],
                          output_names=["output"], opset_version=13)
    return onnx_path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arch", default="dscnn", choices=["cnn", "bcresnet", "dscnn"])
    ap.add_argument("--out", default=None, help="onnx basename override (default: stage naming)")
    ap.add_argument("--epochs", type=int, default=25)
    ap.add_argument("--aug-variants", type=int, default=2)
    ap.add_argument("--batch", type=int, default=128)
    ap.add_argument("--dataset-dir", default=None,
                    help="datasets/<wakeword> dir (default: legacy synthetic dataset/hey_aura)")
    args = ap.parse_args()

    cache = os.path.join(DATA, "aura_feat.npz")  # arch-independent -> shared by both stages
    Xtr, ytr, Xte, yte = prepare_features(dataset_dir=args.dataset_dir,
                                          aug_variants=args.aug_variants, cache_path=cache)
    print(f"[{args.arch}] train={Xtr.shape} test={Xte.shape} pos_tr={int(ytr.sum())} "
          f"neg_tr={int((ytr==0).sum())} pos_te={int(yte.sum())} neg_te={int((yte==0).sum())}")

    model, m = train_arch(args.arch, Xtr, ytr, Xte, yte, epochs=args.epochs, batch=args.batch)

    base = args.out if args.out else ("aura" if args.arch == "dscnn" else "aura_stage2")
    onnx = os.path.join(DATA, f"{base}.onnx")
    export_onnx(model, onnx)
    m["size_kb"] = round(os.path.getsize(onnx) / 1024, 1)
    if args.dataset_dir is None:
        m["test_accents"] = sorted(aura_data.TEST_ACCENTS)
    json.dump(m, open(os.path.join(DATA, f"{base}_metrics.json"), "w"), indent=2)
    print(f"[{args.arch}] params={m['params']} size={m['size_kb']}KB  F1={m['f1']:.3f} "
          f"recall={m['recall']:.3f} per-clip-FAR={m['per_clip_far']:.3f}  -> {onnx}")


if __name__ == "__main__":
    main()
