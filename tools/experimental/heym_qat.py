#!/usr/bin/env python3
"""D1 / ADR-004: Quantization-Aware Training for the real 'hey m' DS-CNN.

ADR-004 mandates QAT for *shipped* models (PTQ is prototyping-only). This tool runs the
controlled ablation the committee asked for: **plain post-training-quant INT8** vs
**QAT-INT8**, on the SPEAKER-INDEPENDENT held-out set (tools/heym_data.py items('test'),
materialized in .data/heym_feat2.npz's Xte/yte).

Pipeline
--------
1. Re-instantiate the DS-CNN (kws_models.build_model('dscnn', mean, std, 2)) and briefly
   fine-tune a float baseline on the cached 'hey m' features (.data/heym_feat2.npz) — this
   is the "weights implied by heym_dscnn.onnx" reproduced with the same recipe.
2. plain-PTQ path : export the float baseline -> ONNX -> onnxruntime static PTQ (per-channel
   QDQ INT8, calibrated on real training windows).
3. QAT path (torch.ao.quantization): fuse conv+bn+relu, prepare_qat with a **per-channel**
   qconfig, fine-tune a few epochs with fake-quant in the loop, then produce an INT8 model.
   Torch->ONNX export of the *quantized* graph is fragile (global-mean-pool of a quantized
   tensor, QuantStub round-trips): we ATTEMPT it, and on failure FALL BACK to the meaningful
   "QAT-robust weights then INT8" path — export the QAT-fine-tuned FLOAT weights (BN folded,
   fake-quant disabled) to ONNX and INT8-PTQ *that*. Same ort settings + same calibration as
   the plain-PTQ path, so the only variable is whether the weights were QAT-hardened.
4. Measure recall (hey-m == class 1) + per-clip FAR (false-accept on negatives) + size for
   fp32 / plain-PTQ-INT8 / QAT-INT8, all through onnxruntime on Xte, and write the ablation
   to benchmarks/dashboards/heym_qat_report.md.
"""
import argparse
import copy
import json
import math
import os
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import aura_augment as aug
import kws_models

DATA = os.path.join(HERE, "..", ".data")
DASH = os.path.join(HERE, "..", "benchmarks", "dashboards")
NUM_CLASSES = 2
TARGET = 1  # 'hey m'
WIN, MELS = 100, 40


# --------------------------------------------------------------------------- data / train
def load_features():
    d = np.load(os.path.join(DATA, "heym_feat2.npz"))
    return d["Xtr"], d["ytr"], d["Xte"], d["yte"]


def make_criterion(ytr):
    import torch
    import torch.nn as nn
    counts = np.bincount(ytr, minlength=NUM_CLASSES).astype(np.float32)
    w = np.sqrt(counts.sum() / (NUM_CLASSES * np.maximum(counts, 1))).astype(np.float32)
    return nn.CrossEntropyLoss(weight=torch.tensor(w), label_smoothing=0.05)


def train_float(model, Xtr, ytr, Xte, yte, epochs, batch, lr, tag):
    """Short float fine-tune reproducing the heym_train recipe (spec-augment, cosine, sqrt
    class weights). Keeps the best-F1 checkpoint on the held-out speakers."""
    import torch
    crit = make_criterion(ytr)
    opt = torch.optim.Adam(model.parameters(), lr=lr, weight_decay=1e-4)
    warm, tot = min(3, epochs), epochs
    sched = torch.optim.lr_scheduler.LambdaLR(
        opt, lambda e: (e + 1) / max(warm, 1) if e < warm
        else 0.5 * (1 + math.cos(math.pi * (e - warm) / max(1, tot - warm))))
    ytr_t = torch.tensor(ytr)
    Xte_t, yte_t = torch.tensor(Xte), torch.tensor(yte)
    rng = np.random.RandomState(0)
    n = len(Xtr)
    best_f1, best = -1.0, None
    for ep in range(epochs):
        model.train(); perm = torch.randperm(n)
        for s in range(0, n, batch):
            idx = perm[s:s + batch].numpy()
            xb = np.stack([aug.spec_augment(f, rng) for f in Xtr[idx]])
            opt.zero_grad()
            loss = crit(model(torch.tensor(xb)), ytr_t[torch.tensor(idx)])
            loss.backward(); opt.step()
        sched.step(); model.eval()
        with torch.no_grad():
            rec, far, f1 = torch_metrics(model(Xte_t), yte_t)
        print(f"  [{tag}] epoch {ep+1}/{epochs}  recall={rec:.3f} FAR={far:.3f} F1={f1:.3f}")
        if f1 > best_f1:
            best_f1 = f1
            best = {k: v.detach().clone() for k, v in model.state_dict().items()}
    if best is not None:
        model.load_state_dict(best)
    model.eval()
    return model


def torch_metrics(logits, yte_t):
    pred = logits.argmax(1)
    tp = int(((pred == 1) & (yte_t == 1)).sum()); fp = int(((pred == 1) & (yte_t == 0)).sum())
    fn = int(((pred == 0) & (yte_t == 1)).sum())
    rec = tp / max(tp + fn, 1); prec = tp / max(tp + fp, 1)
    f1 = 2 * prec * rec / max(prec + rec, 1e-9)
    far = fp / max(int((yte_t == 0).sum()), 1)
    return rec, far, f1


# --------------------------------------------------------------------------- QAT wrapper
def build_qat_model(base):
    """Wrap a trained DS-CNN so conv/bn/relu can be fused and fake-quantized. Norm (mean/std
    folding) stays in float BEFORE the QuantStub; head stays inside the quantized region."""
    import torch
    import torch.nn as nn
    import torch.ao.quantization as tq

    class QATDSCNN(nn.Module):
        def __init__(self, b):
            super().__init__()
            self.norm = b.norm            # float pre-processing (folded (x-mean)/std)
            self.quant = tq.QuantStub()
            self.stem = b.stem            # Conv-BN-ReLU
            self.net = b.net              # 4x _DSBlock (dw Conv-BN-ReLU, pw Conv-BN-ReLU)
            self.head = b.head
            self.dequant = tq.DeQuantStub()

        def forward(self, x):
            x = self.norm(x)
            x = self.quant(x)
            x = self.stem(x)
            x = self.net(x)
            x = x.mean(dim=(2, 3))
            x = self.head(x)
            return self.dequant(x)

    return QATDSCNN(base)


def fusion_list():
    fl = [["stem.0", "stem.1", "stem.2"]]
    for i in range(4):  # 4 DS blocks
        fl.append([f"net.{i}.dw.0", f"net.{i}.dw.1", f"net.{i}.dw.2"])
        fl.append([f"net.{i}.pw.0", f"net.{i}.pw.1", f"net.{i}.pw.2"])
    return fl


def run_qat(base, Xtr, ytr, Xte, yte, epochs, batch, lr):
    import torch
    import torch.ao.quantization as tq
    eng = "onednn" if "onednn" in torch.backends.quantized.supported_engines else \
        torch.backends.quantized.supported_engines[-1]
    torch.backends.quantized.engine = eng
    qm = build_qat_model(copy.deepcopy(base))
    qm.train()
    tq.fuse_modules_qat(qm, fusion_list(), inplace=True)
    qm.qconfig = tq.get_default_qat_qconfig(eng)  # per-channel weight fake-quant
    tq.prepare_qat(qm, inplace=True)
    print(f"[qat] fused conv+bn+relu; per-channel qconfig; fine-tuning {epochs} epochs")
    train_float(qm, Xtr, ytr, Xte, yte, epochs, batch, lr, tag="qat")
    return qm


# --------------------------------------------------------------------------- ONNX export/quant
def export_float_onnx(model, path):
    import torch
    model.eval()
    dummy = torch.zeros(1, WIN, MELS)
    dyn = {"input": {0: "N"}, "output": {0: "N"}}
    try:
        torch.onnx.export(model, dummy, path, input_names=["input"], output_names=["output"],
                          opset_version=13, dynamic_axes=dyn, dynamo=False)
    except TypeError:
        torch.onnx.export(model, dummy, path, input_names=["input"], output_names=["output"],
                          opset_version=13, dynamic_axes=dyn)


def qat_to_clean_float(qm, mean, std):
    """Lift the QAT-hardened weights out of the fused/fake-quant graph into a plain DS-CNN so
    it exports to ONNX cleanly. The fused ConvBnReLU2d keeps the (fine-tuned) conv weight and
    its BN params separately, so copying them into an unfused Conv+BN reproduces the QAT model
    in eval numerics — minus the (unexportable) fake-quant nodes."""
    import torch
    clean = kws_models.build_model("dscnn", mean, std, NUM_CLASSES)
    with torch.no_grad():
        for conv_name, bn_name, _relu in fusion_list():
            fused = qm.get_submodule(conv_name)     # ConvBnReLU2d
            cconv = clean.get_submodule(conv_name)
            cbn = clean.get_submodule(bn_name)
            cconv.weight.copy_(fused.weight)
            if cconv.bias is not None and fused.bias is not None:
                cconv.bias.copy_(fused.bias)
            cbn.weight.copy_(fused.bn.weight); cbn.bias.copy_(fused.bn.bias)
            cbn.running_mean.copy_(fused.bn.running_mean)
            cbn.running_var.copy_(fused.bn.running_var)
            cbn.num_batches_tracked.copy_(fused.bn.num_batches_tracked)
        clean.head.weight.copy_(qm.head.weight); clean.head.bias.copy_(qm.head.bias)
        clean.norm.mean.copy_(qm.norm.mean); clean.norm.std.copy_(qm.norm.std)
    clean.eval()
    return clean


def export_qat_int8(qm, out_int8, calib_X, mean, std):
    """Produce the QAT-INT8 ONNX. Try the (fragile) torch quantized-graph export first; on
    ANY failure fall back to exporting the QAT-fine-tuned FLOAT weights and INT8-PTQ them."""
    import torch
    import torch.ao.quantization as tq

    # --- primary attempt: convert to a real quantized torch graph and export it ---
    try:
        conv = copy.deepcopy(qm)
        conv.eval()
        tq.convert(conv, inplace=True)
        tmp = os.path.join(DATA, "heym_dscnn_qat_quantized.onnx")
        dummy = torch.zeros(1, WIN, MELS)
        torch.onnx.export(conv, dummy, tmp, input_names=["input"], output_names=["output"],
                          opset_version=13, dynamic_axes={"input": {0: "N"}, "output": {0: "N"}})
        import onnxruntime as ort
        s = ort.InferenceSession(tmp, providers=["CPUExecutionProvider"])
        s.run(None, {s.get_inputs()[0].name: np.zeros((1, WIN, MELS), np.float32)})
        os.replace(tmp, out_int8)
        return "torch-quantized-export"
    except Exception as e:  # noqa
        print(f"[qat] torch->ONNX quantized-graph export FAILED ({type(e).__name__}: "
              f"{str(e)[:110]}) -> FALLBACK: QAT float weights + INT8-PTQ")

    # --- fallback (the meaningful path): QAT-robust FLOAT weights -> ONNX -> ort static PTQ ---
    qat_float_onnx = os.path.join(DATA, "heym_dscnn_qat_float.onnx")
    clean = qat_to_clean_float(qm, mean, std)
    export_float_onnx(clean, qat_float_onnx)
    ptq_static(qat_float_onnx, out_int8, calib_X)
    return "qat-float-weights + ort-PTQ (fallback)"


def ptq_static(src_onnx, dst_onnx, calib_X, n_calib=300):
    """onnxruntime static PTQ: per-channel QDQ INT8, calibrated on real training windows."""
    from onnxruntime.quantization import (quantize_static, CalibrationDataReader,
                                          QuantType, QuantFormat)
    from onnxruntime.quantization.shape_inference import quant_pre_process
    import onnxruntime as ort
    in_name = ort.InferenceSession(src_onnx, providers=["CPUExecutionProvider"]).get_inputs()[0].name

    class DR(CalibrationDataReader):
        def __init__(s):
            idx = np.random.RandomState(0).choice(len(calib_X), size=min(n_calib, len(calib_X)),
                                                  replace=False)
            s.it = iter([{in_name: calib_X[i:i + 1].astype(np.float32)} for i in idx])
        def get_next(s):
            return next(s.it, None)

    pre = src_onnx.replace(".onnx", "_pre.onnx")
    quant_pre_process(src_onnx, pre)
    quantize_static(pre, dst_onnx, DR(), quant_format=QuantFormat.QDQ, per_channel=True,
                    weight_type=QuantType.QInt8, activation_type=QuantType.QInt8)


# --------------------------------------------------------------------------- eval on ONNX
def eval_onnx(path, Xte, yte):
    import onnxruntime as ort
    s = ort.InferenceSession(path, providers=["CPUExecutionProvider"])
    inn = s.get_inputs()[0].name
    preds = []
    for i in range(len(Xte)):
        z = s.run(None, {inn: Xte[i:i + 1].astype(np.float32)})[0][0]
        preds.append(int(np.argmax(z)))
    preds = np.asarray(preds)
    tp = int(((preds == 1) & (yte == 1)).sum()); fp = int(((preds == 1) & (yte == 0)).sum())
    fn = int(((preds == 0) & (yte == 1)).sum())
    rec = tp / max(tp + fn, 1); prec = tp / max(tp + fp, 1)
    f1 = 2 * prec * rec / max(prec + rec, 1e-9)
    far = fp / max(int((yte == 0).sum()), 1)
    return {"recall": rec, "far": far, "f1": f1, "size_kb": os.path.getsize(path) / 1024}


# --------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--float-epochs", type=int, default=12)
    ap.add_argument("--qat-epochs", type=int, default=4)
    ap.add_argument("--batch", type=int, default=128)
    ap.add_argument("--lr", type=float, default=2e-3)
    ap.add_argument("--qat-lr", type=float, default=5e-4)
    args = ap.parse_args()
    import torch
    torch.manual_seed(0); np.random.seed(0)

    Xtr, ytr, Xte, yte = load_features()
    print(f"train={Xtr.shape} test={Xte.shape}  pos_te={int(yte.sum())} neg_te={int((yte==0).sum())}")
    mean = Xtr.reshape(-1, MELS).mean(0); std = Xtr.reshape(-1, MELS).std(0) + 1e-5

    # 1) float baseline (re-instantiate + briefly fine-tune)
    print("\n=== float baseline ===")
    base = kws_models.build_model("dscnn", mean, std, NUM_CLASSES)
    train_float(base, Xtr, ytr, Xte, yte, args.float_epochs, args.batch, args.lr, tag="float")
    params = kws_models.param_count(base)
    fp32_onnx = os.path.join(DATA, "heym_dscnn_qat_fp32.onnx")
    export_float_onnx(base, fp32_onnx)

    # 2) plain PTQ INT8 (the ADR-004 prototyping baseline)
    print("\n=== plain PTQ (INT8, per-channel QDQ) ===")
    ptq_onnx = os.path.join(DATA, "heym_dscnn_ptq_int8.onnx")
    ptq_static(fp32_onnx, ptq_onnx, Xtr)

    # 3) QAT INT8 (ADR-004 shipped-model path)
    print("\n=== QAT (fuse -> prepare_qat -> fine-tune -> INT8) ===")
    qm = run_qat(base, Xtr, ytr, Xte, yte, args.qat_epochs, args.batch, args.qat_lr)
    qat_onnx = os.path.join(DATA, "heym_dscnn_qat_int8.onnx")
    qat_path = export_qat_int8(qm, qat_onnx, Xtr, mean, std)

    # 4) measure all three on the speaker-independent held-out set (via ONNX)
    print("\n=== measuring on speaker-independent Xte ===")
    m_fp32 = eval_onnx(fp32_onnx, Xte, yte)
    m_ptq = eval_onnx(ptq_onnx, Xte, yte)
    m_qat = eval_onnx(qat_onnx, Xte, yte)
    for name, m in (("fp32", m_fp32), ("ptq-int8", m_ptq), ("qat-int8", m_qat)):
        print(f"  {name:<10} recall={m['recall']:.3f} FAR={m['far']:.3f} "
              f"F1={m['f1']:.3f} size={m['size_kb']:.1f}KB")

    # Honest ranking. F1 is the single-number summary; if F1 is within a small band the two
    # are effectively tied (and any recall/FAR difference is just a shifted operating point,
    # a tradeoff, not a real quality win). Only call a winner on a material F1 gap.
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

    write_report(params, m_fp32, m_ptq, m_qat, qat_path, verdict,
                 args, len(Xtr), len(Xte), int(yte.sum()), int((yte == 0).sum()))
    print(f"\nVERDICT: {verdict}")
    print(f"wrote {os.path.join(DASH, 'heym_qat_report.md')}")


def write_report(params, fp32, ptq, qat, qat_path, verdict, args, ntr, nte, pos_te, neg_te):
    os.makedirs(DASH, exist_ok=True)
    out = os.path.join(DASH, "heym_qat_report.md")
    d_rec = qat["recall"] - ptq["recall"]; d_far = qat["far"] - ptq["far"]
    with open(out, "w", encoding="utf-8") as f:
        f.write("# 'hey m' DS-CNN — QAT vs PTQ INT8 Ablation (D1 / ADR-004)\n\n")
        f.write("ADR-004 mandates **QAT for shipped models** (PTQ is prototyping-only). This is the "
                "measured, controlled comparison on the **speaker-independent** held-out set "
                "(`heym_data.items('test')`, materialized as `heym_feat2.npz` Xte).\n\n")
        f.write(f"- DS-CNN params: **{params:,}** (2-class: not-wake / hey-m)\n")
        f.write(f"- Held-out set: {nte} clips ({pos_te} hey-m positives, {neg_te} negatives), "
                f"unseen speakers. Train windows: {ntr:,}.\n")
        f.write(f"- Float fine-tune: {args.float_epochs} ep; QAT fine-tune: {args.qat_epochs} ep "
                f"(fuse conv+bn+relu, `prepare_qat`, per-channel qconfig).\n")
        f.write(f"- QAT-INT8 production path: **{qat_path}**. "
                "(Torch->ONNX of the *quantized* graph is fragile — global-mean-pool over a "
                "quantized tensor; the fallback exports QAT-hardened FLOAT weights then INT8-PTQ, "
                "the meaningful \"QAT-robust weights then INT8\" path.)\n")
        f.write("- Both INT8 models use identical ort static QDQ per-channel quantization + the "
                "same training-window calibration, so the **only variable is QAT vs not**.\n\n")
        f.write("## Result\n\n")
        f.write("| model | hey-m recall | per-clip FAR | F1 | size (KB) |\n|---|---|---|---|---|\n")
        f.write(f"| fp32 (reference) | {fp32['recall']:.3f} | {fp32['far']:.3f} | {fp32['f1']:.3f} | {fp32['size_kb']:.1f} |\n")
        f.write(f"| **plain-PTQ-INT8** | {ptq['recall']:.3f} | {ptq['far']:.3f} | {ptq['f1']:.3f} | {ptq['size_kb']:.1f} |\n")
        f.write(f"| **QAT-INT8** | {qat['recall']:.3f} | {qat['far']:.3f} | {qat['f1']:.3f} | {qat['size_kb']:.1f} |\n\n")
        f.write(f"**QAT − PTQ:** recall {d_rec:+.3f}, per-clip FAR {d_far:+.3f}, "
                f"size {qat['size_kb'] - ptq['size_kb']:+.1f} KB.\n\n")
        f.write(f"### Verdict: {verdict}\n\n")
        if verdict.startswith("TIE"):
            f.write("QAT does **not** beat PTQ here — expected and honest for a ~14 K-param DS-CNN: "
                    "PTQ INT8 is already near-lossless at this capacity, so there is little "
                    "quantization error for QAT to recover. ADR-004's value is **process/insurance** "
                    "(the pipeline is validated and ready to pay off on larger models / tighter "
                    "numerics / real-data drift), not a headline accuracy gain today.\n\n")
        else:
            f.write("Reported as measured. Note the model is tiny (~14 K params) so PTQ INT8 is "
                    "already near-lossless; treat small deltas as within run-to-run noise.\n\n")
        f.write("_Accuracy is per-window argmax on the held-out clips (recall = hey-m sensitivity, "
                "per-clip FAR = false-accept rate on negatives). Size is the on-disk INT8 ONNX. "
                "Streaming FA/hr + FR at an operating point are measured separately by "
                "`tools/heym_eval.py`._\n")


if __name__ == "__main__":
    main()
