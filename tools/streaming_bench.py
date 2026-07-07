#!/usr/bin/env python3
"""D2 - Streaming-native inference MEASUREMENT (host prototype).

The shipped always-on detector (core/detect Stage1Detector) runs a sliding
window: it recomputes a full [1, WINDOW=100, 40] convolutional inference every
stage1HopFrames = 10 frames. Because the window (100 frames = 1 s) is 10x wider
than the hop (10 frames = 100 ms), every 10 ms input frame is pushed through the
whole conv stack ~window/hop = 10 times before it leaves the window. For an
always-on model that is a large, permanent, redundant compute (and battery) cost.

This tool QUANTIFIES that redundancy and prototypes the streaming win using the
SHIPPED model (apps/.../models/heym.onnx) and the EXACT on-device front-end
(tools/aura_frontend.py):

  (1) MACs/second, analytically, for the WINDOWED schedule (one full window
      inference per hop) vs an idealized STREAMING schedule (each frame's conv
      footprint computed once, amortized), and the redundancy factor.
  (2) Wall-clock inference throughput on a continuous 60 s stream for the
      windowed schedule (a real, measured number on this host) and the
      streaming-equivalent estimate.
  (3) A dashboard report benchmarks/dashboards/streaming_bench.md with the
      MAC / latency / redundancy numbers, the achievable always-on-compute
      reduction and its power implication, AND an honest statement of the
      remaining step: a *mathematically* streaming model needs a causal
      architecture (no global-window pooling) trained for it.

HOST caveat: wall-clock is x86 CPU + onnxruntime desktop and is NOT
device-representative in absolute ms. The redundancy factor and the MAC ratio
are architecture/schedule properties and transfer directly to device.
"""
import argparse
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))
import aura_frontend as fe  # noqa: E402

ASSET = os.path.join(ROOT, "apps", "android", "src", "main", "assets", "models")
DASH = os.path.join(ROOT, "benchmarks", "dashboards")

MODEL = os.path.join(ASSET, "heym.onnx")
WINDOW = fe.WINDOW_FRAMES          # 100 frames = stage1WindowFrames
HOP_FRAMES = 10                    # stage1HopFrames (windowed re-score cadence)
FRAME_RATE = fe.SR / fe.HOP        # 100 frames/s (16000 / 160)


# --------------------------------------------------------------------------
# (1) Analytic MAC accounting from the ONNX graph
# --------------------------------------------------------------------------
def conv_macs(node, shapes):
    """MACs for one Conv = Cout * Hout * Wout * (Cin/group) * kH * kW."""
    out = shapes[node.output[0]]              # [1, Cout, Hout, Wout]
    cin = shapes[node.input[0]][1]            # input channels
    _, cout, hout, wout = out
    attrs = {a.name: a for a in node.attribute}
    kh, kw = list(attrs["kernel_shape"].ints)
    group = attrs["group"].i if "group" in attrs else 1
    return cout * hout * wout * (cin // group) * kh * kw


def gemm_macs(node, shapes):
    """MACs for Gemm (fully connected) = M * K * N ~ in_features * out_features."""
    out = shapes[node.output[0]]              # [1, N]
    inp = shapes[node.input[0]]               # [1, K]
    return out[-1] * inp[-1]


def analyze_macs():
    import onnx
    from onnx import shape_inference

    m = shape_inference.infer_shapes(onnx.load(MODEL))
    g = m.graph
    shapes = {}
    for vi in list(g.value_info) + list(g.input) + list(g.output):
        shapes[vi.name] = [d.dim_value for d in vi.type.tensor_type.shape.dim]

    layers = []          # (name, op, macs, out_shape)
    total = 0
    has_global_pool = False
    for n in g.node:
        if n.op_type == "Conv":
            mac = conv_macs(n, shapes)
        elif n.op_type == "Gemm":
            mac = gemm_macs(n, shapes)
        elif n.op_type == "ReduceMean":
            has_global_pool = True
            continue
        else:
            continue
        layers.append((n.name, n.op_type, mac, shapes[n.output[0]]))
        total += mac
    return layers, total, has_global_pool


# --------------------------------------------------------------------------
# (2) Wall-clock throughput on a continuous 60 s stream (windowed schedule)
# --------------------------------------------------------------------------
def make_stream(seconds, seed=0):
    """A continuous audio stream through the real front-end -> [T, 40] mel."""
    rng = np.random.RandomState(seed)
    n = int(seconds * fe.SR)
    # pink-ish noise + a couple of tones so DSP/VAD behave like real ambient speech-ish audio
    x = rng.randn(n).astype(np.float64) * 0.02
    t = np.arange(n) / fe.SR
    x += 0.05 * np.sin(2 * np.pi * 220 * t) * (np.sin(2 * np.pi * 0.7 * t) > 0)
    dsp = fe.apply_dsp(x)
    mel = fe.log_mel(dsp)
    return mel


def measure_windowed(sess, in_name, mel):
    """Run the shipped windowed schedule over the whole stream, timing inference."""
    T = len(mel)
    hop_pts = list(range(WINDOW, T + 1, HOP_FRAMES))
    # warmup
    dummy = mel[:WINDOW][None].astype(np.float32)
    for _ in range(8):
        sess.run(None, {in_name: dummy})
    per = []
    t_all = time.perf_counter()
    for tpt in hop_pts:
        w = mel[tpt - WINDOW:tpt][None].astype(np.float32)   # [1,100,40]
        t0 = time.perf_counter()
        sess.run(None, {in_name: w})
        per.append((time.perf_counter() - t0) * 1000.0)
    wall = time.perf_counter() - t_all
    return hop_pts, np.array(per), wall


# --------------------------------------------------------------------------
def fmt_macs(x):
    if x >= 1e6:
        return f"{x/1e6:.3f} M"
    if x >= 1e3:
        return f"{x/1e3:.1f} k"
    return f"{x:.0f}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=60.0,
                    help="continuous stream length for wall-clock throughput")
    args = ap.parse_args()

    import onnxruntime as ort

    # ---- (1) MAC accounting ----
    layers, macs_window, has_pool = analyze_macs()
    # windowed schedule: one full-window inference per hop => FRAME_RATE/HOP inferences/s
    inf_per_s = FRAME_RATE / HOP_FRAMES                       # 10 inferences/s
    macs_s_windowed = macs_window * inf_per_s
    # idealized streaming: each frame's conv footprint computed once, amortized over
    # the whole stream => full-window conv-work spread across WINDOW frames, at frame rate.
    macs_s_streaming = macs_window / WINDOW * FRAME_RATE
    redundancy = macs_s_windowed / macs_s_streaming          # == WINDOW / (HOP*inf... ) == window/hop
    reduction_pct = (1.0 - macs_s_streaming / macs_s_windowed) * 100.0

    # ---- (2) wall-clock on a real continuous stream ----
    print(f"building {args.seconds:.0f}s stream through the on-device front-end...")
    mel = make_stream(args.seconds)
    dur_s = len(mel) / FRAME_RATE
    sess = ort.InferenceSession(MODEL, providers=["CPUExecutionProvider"])
    in_name = sess.get_inputs()[0].name
    print(f"stream: {dur_s:.1f}s -> {len(mel)} frames; scoring windowed schedule...")
    hop_pts, per_ms, wall = measure_windowed(sess, in_name, mel)

    n_inf = len(hop_pts)
    infer_rtf = wall / dur_s                                  # inference wall-time / audio-time
    wall_streaming = wall / redundancy                        # amortized estimate
    rt_budget_ms = HOP_FRAMES / FRAME_RATE * 1000.0           # 100 ms per hop (real-time deadline)

    # ---- (3) report ----
    os.makedirs(DASH, exist_ok=True)
    out = os.path.join(DASH, "streaming_bench.md")
    with open(out, "w", encoding="utf-8") as f:
        w = f.write
        w("# Streaming-Native Inference: Redundancy Measurement (D2)\n\n")
        w(f"Model: `heym.onnx` (input `[1,{WINDOW},40]`, output `[1,2]`, "
          f"{sum(1 for _,op,_,_ in layers if op=='Conv')} conv layers, "
          "depthwise-separable). Front-end: `tools/aura_frontend.py` (numpy == on-device C++).\n\n")
        w("Always-on schedule under test: `Stage1Detector` re-scores a "
          f"**{WINDOW}-frame ({WINDOW*fe.HOP/fe.SR*1000:.0f} ms) window every "
          f"stage1HopFrames = {HOP_FRAMES} frames ({rt_budget_ms:.0f} ms)**, i.e. "
          f"{inf_per_s:.0f} full-window inferences per second, forever.\n\n")

        w("## 1. Redundant compute (analytic MACs)\n\n")
        w(f"One full `[1,{WINDOW},40]` inference = **{fmt_macs(macs_window)}MACs**.\n\n")
        w("| layer | op | out shape | MACs |\n|---|---|---|---|\n")
        for name, op, mac, shp in layers:
            w(f"| `{name.strip('/')}` | {op} | {shp} | {fmt_macs(mac)} |\n")
        w(f"| **total** | | | **{fmt_macs(macs_window)}** |\n\n")

        w("| schedule | inferences/s | **MACs/s** | note |\n|---|---|---|---|\n")
        w(f"| windowed (shipped) | {inf_per_s:.0f} | **{fmt_macs(macs_s_windowed)}** | "
          f"full window every {HOP_FRAMES} frames |\n")
        w(f"| streaming (idealized) | {FRAME_RATE:.0f} (per-frame) | **{fmt_macs(macs_s_streaming)}** | "
          "each frame's conv footprint computed once |\n\n")
        w(f"**Redundancy factor = {redundancy:.1f}x** (= window/hop = {WINDOW}/{HOP_FRAMES}). "
          f"Under the windowed schedule every 10 ms frame is pushed through the conv stack "
          f"~{redundancy:.0f} times before it leaves the window.\n\n")
        w(f"**Achievable always-on-compute reduction: {reduction_pct:.0f}%** of convolutional "
          f"MAC/s ({fmt_macs(macs_s_windowed)}MACs/s -> {fmt_macs(macs_s_streaming)}MACs/s).\n\n")

        w("## 2. Wall-clock throughput (HOST, measured)\n\n")
        w(f"Continuous **{dur_s:.0f} s** stream ({len(mel)} frames) through the real "
          f"front-end, {n_inf} windowed inferences:\n\n")
        w(f"- per-inference latency: p50 **{np.percentile(per_ms,50):.3f} ms**, "
          f"p95 {np.percentile(per_ms,95):.3f} ms, mean {per_ms.mean():.3f} ms\n")
        w(f"- total inference wall-time for {dur_s:.0f}s of audio: **{wall*1000:.0f} ms** "
          f"(real-time factor {infer_rtf*100:.2f}% of audio duration)\n")
        w(f"- real-time budget per hop: {rt_budget_ms:.0f} ms; headroom "
          f"~{rt_budget_ms/np.percentile(per_ms,50):.0f}x on this host\n")
        w(f"- **streaming-equivalent estimate: ~{wall*1000/redundancy:.0f} ms** total "
          f"({redundancy:.0f}x less inference wall-time for the same {dur_s:.0f}s of audio)\n\n")
        w("> Absolute ms are x86 + onnxruntime desktop and are NOT device-representative. "
          "The redundancy factor and MAC ratio are schedule/architecture properties and "
          "transfer to device; on a phone this ~10x is the difference between the DSP/NPU "
          "waking for one window per hop vs a small per-frame increment, which is the dominant "
          "term in always-on wake-word power.\n\n")

        w("## 3. Power implication\n\n")
        w("Always-on inference energy is ~proportional to MAC/s at a fixed operating point. "
          f"Cutting convolutional MAC/s by **{reduction_pct:.0f}% ({redundancy:.0f}x)** cuts the "
          "detector's compute-energy share by the same factor. Wake-word detection is one of the "
          "few blocks running 24/7 on a sleeping device, so this compute is on the always-on "
          "power budget rather than amortized against active use - the reduction is meaningful "
          "for standby battery life.\n\n")

        w("## 4. Honest remaining step: a causal streaming architecture\n\n")
        pool = "present" if has_pool else "absent"
        w(f"The {redundancy:.0f}x above is the *idealized* bound; it is NOT free with the "
          "current model. `heym.onnx` ends in a **global `ReduceMean` over the full "
          f"[5x13] time-frequency map** (global-window pooling: {pool}) followed by the "
          "classifier head. That global pool makes the output a function of the *entire* "
          "window, so the network as trained is fundamentally windowed - you cannot emit a "
          "correct per-frame posterior by only computing the newest columns.\n\n")
        w("To realize the win, the remaining step is a **mathematically streaming (causal) "
          "model**:\n\n")
        w("- replace global-window pooling with a **causal temporal aggregator** "
          "(causal/streaming convolutions, a ring-buffered receptive field, or an RNN/state "
          "so each new frame updates a running state instead of re-pooling the whole window);\n")
        w("- keep strided/downsampling convs **causal** (left-padding only) so no layer needs "
          "future frames;\n")
        w("- **retrain** for the streaming objective (per-frame targets) and re-verify FA/hr "
          "and FRR - a streaming model is a different model, not a repack of this one;\n")
        w("- export a stateful ONNX (carry the conv/RNN state across calls) so the runtime does "
          "the small per-frame increment measured as the idealized schedule above.\n\n")
        w(f"This measurement quantifies the prize ({redundancy:.0f}x / {reduction_pct:.0f}% "
          "always-on conv compute) and localizes the blocker (the global `ReduceMean`); the "
          "causal redesign + retrain is the follow-on engineering task.\n")

    # console summary (this is the tool's stdout, not a report file)
    print(f"\nMACs/full-window inference : {fmt_macs(macs_window)}MACs")
    print(f"MACs/s windowed (shipped)  : {fmt_macs(macs_s_windowed)}MACs/s")
    print(f"MACs/s streaming (ideal)   : {fmt_macs(macs_s_streaming)}MACs/s")
    print(f"redundancy factor          : {redundancy:.2f}x  (window/hop = {WINDOW}/{HOP_FRAMES})")
    print(f"always-on compute reduction: {reduction_pct:.1f}%")
    print(f"wall-clock {dur_s:.0f}s stream     : {wall*1000:.0f} ms "
          f"({n_inf} inf, p50 {np.percentile(per_ms,50):.3f} ms/inf)")
    print(f"streaming-equivalent wall  : ~{wall*1000/redundancy:.0f} ms")
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
