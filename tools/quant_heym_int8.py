#!/usr/bin/env python3
"""INT8 static PTQ for the shipped 'hey m' Stage-1 model.

Quantizes apps/android/.../heym.onnx (DS-CNN Stage-1 winner) to heym_int8.onnx
using onnxruntime static QDQ, per-channel QInt8 weights+activations, calibrated
on .data/heym_feat2.npz['Xtr'] (the expanded 17.4k-window train set). Verified to
run: prints float/int8 sizes and confirms an inference forward pass on the INT8 graph.
"""
import os
import numpy as np
import onnx
import onnxruntime as ort
from onnxruntime.quantization import (
    quantize_static, CalibrationDataReader, QuantType, QuantFormat,
)
from onnxruntime.quantization.shape_inference import quant_pre_process

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "apps/android/src/main/assets/models/heym.onnx")
PRE = os.path.join(ROOT, ".data/heym_int8_preproc.onnx")
DST = os.path.join(ROOT, "apps/android/src/main/assets/models/heym_int8.onnx")
CAL = os.path.join(ROOT, ".data/heym_feat2.npz")

# Resolve the model's real (non-initializer) input name.
m = onnx.load(SRC)
inits = {i.name for i in m.graph.initializer}
inp_name = [i.name for i in m.graph.input if i.name not in inits][0]
print("input name:", inp_name)

X = np.load(CAL)["Xtr"].astype(np.float32)   # (N,100,40)
print("calibration source: .data/heym_feat2.npz['Xtr']", X.shape)


class DR(CalibrationDataReader):
    def __init__(self, X, n=300):
        self.data = [{inp_name: X[i:i + 1]} for i in range(min(n, len(X)))]
        self.it = iter(self.data)

    def get_next(self):
        return next(self.it, None)


quant_pre_process(SRC, PRE)
quantize_static(
    PRE, DST,
    calibration_data_reader=DR(X),
    quant_format=QuantFormat.QDQ,
    per_channel=True,
    weight_type=QuantType.QInt8,
    activation_type=QuantType.QInt8,
)

fk = os.path.getsize(SRC) / 1024
qk = os.path.getsize(DST) / 1024
print(f"RESULT float_kb={fk:.1f} int8_kb={qk:.1f} reduction={100*(1-qk/fk):.1f}%")

# Sanity: run the INT8 graph on one window.
s = ort.InferenceSession(DST, providers=["CPUExecutionProvider"])
out = s.run(None, {inp_name: X[:1]})
print("int8 inference OK, out shape:", [o.shape for o in out])
