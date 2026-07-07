#!/usr/bin/env python3
"""Produce the PLACEHOLDER Stage-1 KWS ONNX model for the AURA v0 vertical slice.

There is no AURA-trained model yet (the research track produces it later). This
tool provides two paths, both flagged as placeholders in REPORT.md:

  --real       Export a permissively-licensed pretrained Speech Commands KWS model
               to ONNX (requires torch/torchaudio + network). This is the path that
               can actually recognize a spoken keyword on-device. You must confirm
               the exported model's class index for the target word and set
               core/config/Config.h DetectConfig.stage1TargetClass accordingly.

  --synthetic  Emit a shape-correct, RANDOM-WEIGHT ONNX model (requires `onnx`).
               It matches the I/O contract so the full native path (Oboe -> DSP ->
               log-Mel -> VAD -> ONNX Runtime) can be exercised end-to-end, but it
               does NOT truly recognize "marvin". Useful for integration smoke
               tests before a trained model exists.

FRONT-END CONTRACT (must match core/config/Config.h FeatureConfig) — this alignment
is the single biggest integration risk (Stage 7 M3):
  sample_rate = 16000
  window      = 400 samples (25 ms), hop = 160 samples (10 ms), Hann window
  n_mels      = 40, log-Mel (natural log)
  input shape = [1, T, 40]  (T = DetectConfig.stage1WindowFrames, default 100)
  output      = [num_classes] logits; softmax; target class = "marvin"
"""
import argparse
import os
import sys

OUT = os.path.join(os.path.dirname(__file__), "..", "apps", "android", "src", "main",
                   "assets", "models", "kws_marvin.onnx")

FRONTEND = {
    "sample_rate": 16000, "window": 400, "hop": 160, "n_mels": 40,
    "log_mel": True, "input_shape": [1, 100, 40], "num_classes": 12,
    "target_class_name": "marvin",
}


def print_frontend():
    print("AURA Stage-1 front-end contract (align core/config/Config.h):")
    for k, v in FRONTEND.items():
        print(f"  {k:18} = {v}")


def make_synthetic(path):
    try:
        import numpy as np
        import onnx
        from onnx import helper, TensorProto
    except ImportError:
        print("ERROR: --synthetic needs `pip install onnx numpy`", file=sys.stderr)
        return 1
    T, M, C = 100, FRONTEND["n_mels"], FRONTEND["num_classes"]
    # A trivial graph: GlobalAveragePool over time -> Gemm -> logits. Random weights.
    flat = T * M
    w = (np.random.RandomState(0).randn(flat, C).astype("float32") * 0.01)
    b = np.zeros((C,), dtype="float32")
    inp = helper.make_tensor_value_info("input", TensorProto.FLOAT, [1, T, M])
    out = helper.make_tensor_value_info("output", TensorProto.FLOAT, [1, C])
    reshape_shape = helper.make_tensor("shape", TensorProto.INT64, [2], [1, flat])
    W = helper.make_tensor("W", TensorProto.FLOAT, [flat, C], w.flatten())
    B = helper.make_tensor("B", TensorProto.FLOAT, [C], b)
    nodes = [
        helper.make_node("Reshape", ["input", "shape"], ["flat"]),
        helper.make_node("Gemm", ["flat", "W", "B"], ["output"]),
    ]
    graph = helper.make_graph(nodes, "aura_kws_placeholder", [inp], [out],
                              initializer=[reshape_shape, W, B])
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 13)])
    onnx.checker.check_model(model)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    onnx.save(model, path)
    print(f"wrote SYNTHETIC placeholder (random weights, does NOT recognize speech): {path}")
    return 0


def make_real(path):
    print("The --real export requires torch/torchaudio and a chosen pretrained "
          "Speech Commands checkpoint. Recommended: a small BC-ResNet / MatchboxNet "
          "trained on Speech Commands v2 (35-word set includes 'marvin').")
    print("Steps (documented, not auto-run here to avoid pulling heavy deps):")
    print("  1. pip install torch torchaudio onnx")
    print("  2. Load the checkpoint; wrap so the model input is [1, T, 40] log-Mel.")
    print("  3. torch.onnx.export(model, dummy, '%s', input_names=['input'], "
          "output_names=['output'], opset_version=13)" % path)
    print("  4. Confirm the 'marvin' class index -> set DetectConfig.stage1TargetClass.")
    print("Flagged in REPORT.md: sourcing/aligning this real model is the primary "
          "remaining integration task for true on-device detection.")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--synthetic", action="store_true", help="emit a random-weight shape-correct ONNX")
    ap.add_argument("--real", action="store_true", help="print the real-model export recipe")
    ap.add_argument("--out", default=OUT)
    args = ap.parse_args()
    print_frontend()
    print()
    if args.synthetic:
        return make_synthetic(args.out)
    if args.real:
        return make_real(args.out)
    print("Choose --synthetic (integration smoke) or --real (true detection). "
          "See --help.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
