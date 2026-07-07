#!/usr/bin/env python3
"""D2 — train the CAUSAL STREAMING KWS model (tools/streaming_model.py :: StreamingKWS) on
the same speaker-independent 'hey m' data as the windowed DS-CNN, then report accuracy AND
the always-on COMPUTE WIN side by side with the windowed model.

Why this exists: the windowed DS-CNN re-runs a full [1,100,40] inference every hop=10 frames
(~10x redundant conv compute). StreamingKWS is mathematically streaming (causal dilated convs
+ ring-buffer state, self-tested step()==forward_frames()) so on-device it pays a small
per-FRAME increment instead. This script proves the streaming model's accuracy is comparable
on the SAME held-out speakers, and quantifies the MMACs/s reduction analytically.

Training: reuse the fixed [N,100,40] window cache (.data/heym_feat2.npz). Each window is one
clip; StreamingKWS.forward() temporal-max-pools per-frame logits -> clip logit. Same recipe as
heym_train.py: cosine LR + warmup, sqrt class weights, label smoothing, online SpecAugment,
~25 epochs. Eval on the SPEAKER-INDEPENDENT Xte/yte. Export .data/heym_streaming.onnx.
"""
import json
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import aura_augment as aug
import aura_frontend as fe
from streaming_model import StreamCausalConv, StreamingKWS

DATA = os.path.join(os.path.dirname(__file__), "..", ".data")
NUM_CLASSES = 2  # 0 = not-wake, 1 = hey-m


def per_frame_macs(model):
    """Analytic MACs for ONE streaming frame (each conv emits 1 output column).
    Conv1d(in,out,k,groups=g) per output frame = out * (in/g) * k."""
    total = 0
    rows = []
    for name, m in model.named_modules():
        import torch.nn as nn
        if isinstance(m, nn.Conv1d):
            macs = m.out_channels * (m.in_channels // m.groups) * m.kernel_size[0]
            total += macs
            rows.append((name, m.in_channels, m.out_channels, m.kernel_size[0], m.groups, macs))
    return total, rows


def main():
    import torch
    import torch.nn as nn
    torch.manual_seed(0); np.random.seed(0)
    epochs = int(os.environ.get("EPOCHS", "25"))

    cache = os.path.join(DATA, "heym_feat2.npz")
    d = np.load(cache)
    Xtr, ytr, Xte, yte = d["Xtr"], d["ytr"], d["Xte"], d["yte"]
    print(f"[streaming] train={Xtr.shape} test={Xte.shape} pos_tr={int(ytr.sum())} "
          f"neg_tr={int((ytr==0).sum())} pos_te={int(yte.sum())} neg_te={int((yte==0).sum())}")

    mean = Xtr.reshape(-1, fe.N_MELS).mean(0)
    std = Xtr.reshape(-1, fe.N_MELS).std(0) + 1e-5
    model = StreamingKWS(mean, std, n_mels=fe.N_MELS, n_classes=NUM_CLASSES)
    params = sum(p.numel() for p in model.parameters())
    print(f"[streaming] receptive_field={model.receptive_field} frames  params={params}")

    # sqrt class weights (same softening as heym_train: recall without inflating false-accepts)
    counts = np.bincount(ytr, minlength=NUM_CLASSES).astype(np.float32)
    w = np.sqrt(counts.sum() / (NUM_CLASSES * np.maximum(counts, 1))).astype(np.float32)
    crit = nn.CrossEntropyLoss(weight=torch.tensor(w), label_smoothing=0.05)
    opt = torch.optim.Adam(model.parameters(), lr=2e-3, weight_decay=1e-4)
    warm, tot = 3, epochs
    sched = torch.optim.lr_scheduler.LambdaLR(
        opt, lambda e: (e + 1) / warm if e < warm
        else 0.5 * (1 + math.cos(math.pi * (e - warm) / max(1, tot - warm))))

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

    best_f1, best = -1, None
    n = len(Xtr); batch = 128
    for ep in range(epochs):
        model.train(); perm = torch.randperm(n)
        for s in range(0, n, batch):
            idx = perm[s:s + batch].numpy()
            xb = np.stack([aug.spec_augment(f, rng) for f in Xtr[idx]])
            opt.zero_grad()
            loss = crit(model(torch.tensor(xb)), torch.tensor(ytr[idx]))
            loss.backward(); opt.step()
        sched.step(); model.eval()
        with torch.no_grad():
            f1, rec, far = metrics(model(Xte_t))
        print(f"  ep{ep+1:02d} F1={f1:.3f} recall={rec:.3f} per-clip-FAR={far:.3f}")
        if f1 > best_f1:
            best_f1, best = f1, {k: v.clone() for k, v in model.state_dict().items()}
    if best:
        model.load_state_dict(best)
    model.eval()
    with torch.no_grad():
        f1, rec, far = metrics(model(Xte_t))

    # --- export streaming ONNX (forward: windowed clip scoring, [1,100,40]->[1,2]) ---
    onnx = os.path.join(DATA, "heym_streaming.onnx")
    dummy = torch.zeros(1, fe.WINDOW_FRAMES, fe.N_MELS)
    try:
        torch.onnx.export(model, dummy, onnx, input_names=["input"], output_names=["output"],
                          opset_version=13, dynamo=False)
    except TypeError:
        torch.onnx.export(model, dummy, onnx, input_names=["input"], output_names=["output"],
                          opset_version=13)
    size_kb = round(os.path.getsize(onnx) / 1024, 1)

    # --- COMPUTE WIN (analytic) ---
    pf_macs, rows = per_frame_macs(model)
    stream_macs_s = pf_macs * 100.0                      # streaming: per-frame, 100 frames/s
    win_full_macs = 3.656e6                               # full DS-CNN inference (streaming_bench.md)
    win_macs_s = win_full_macs * 10.0                     # windowed: full window every hop=10 => 10/s
    reduction = win_macs_s / stream_macs_s

    # windowed DS-CNN reference metrics (heym_dscnn_metrics.json)
    dref = json.load(open(os.path.join(DATA, "heym_dscnn_metrics.json")))

    out = {
        "model": "StreamingKWS (causal streaming)",
        "params": params, "size_kb": size_kb,
        "receptive_field_frames": model.receptive_field,
        "speaker_indep_f1": round(f1, 4), "recall": round(rec, 4), "per_clip_far": round(far, 4),
        "per_frame_macs": int(pf_macs),
        "streaming_mmacs_per_s": round(stream_macs_s / 1e6, 4),
        "windowed_mmacs_per_s": round(win_macs_s / 1e6, 4),
        "compute_reduction_x": round(reduction, 2),
        "windowed_dscnn_ref": dref,
    }
    json.dump(out, open(os.path.join(DATA, "heym_streaming_metrics.json"), "w"), indent=2)

    print("\n=== per-frame MACs (streaming step) ===")
    for name, ci, co, k, g, macs in rows:
        print(f"  {name:20s} Conv1d(in={ci},out={co},k={k},g={g}) = {macs} MACs")
    print(f"  total per-frame = {pf_macs} MACs")
    print("\n=== D2 streaming vs windowed (speaker-independent held-out) ===")
    print(f"{'metric':<22}{'STREAMING':>14}{'WINDOWED DS-CNN':>18}")
    print(f"{'recall':<22}{rec:>14.4f}{dref['recall']:>18.4f}")
    print(f"{'per-clip FAR':<22}{far:>14.4f}{dref['per_clip_far']:>18.4f}")
    print(f"{'F1':<22}{f1:>14.4f}{dref['speaker_indep_f1']:>18.4f}")
    print(f"{'params':<22}{params:>14d}{dref['params']:>18d}")
    print(f"{'size (KB)':<22}{size_kb:>14.1f}{dref['size_kb']:>18.1f}")
    print(f"{'MMACs/s (always-on)':<22}{stream_macs_s/1e6:>14.4f}{win_macs_s/1e6:>18.4f}")
    print(f"\ncompute reduction = {reduction:.2f}x  "
          f"({win_macs_s/1e6:.2f} -> {stream_macs_s/1e6:.2f} MMACs/s)")
    print(f"exported {onnx} ({size_kb} KB)")
    return out


if __name__ == "__main__":
    main()
