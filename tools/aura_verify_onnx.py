#!/usr/bin/env python3
"""Load both exported hey-aura ONNX models with onnxruntime and assert I/O shapes [1,100,40]->[1,2]."""
import os
import numpy as np
import onnxruntime as ort

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".data")


def check(name):
    path = os.path.join(DATA, name)
    sess = ort.InferenceSession(path, providers=["CPUExecutionProvider"])
    inp = sess.get_inputs()[0]
    x = np.zeros((1, 100, 40), dtype=np.float32)
    out = sess.run(None, {inp.name: x})[0]
    size_kb = round(os.path.getsize(path) / 1024, 1)
    ok = tuple(out.shape) == (1, 2)
    print(f"{name}: in={inp.name}{inp.shape} out_shape={out.shape} size={size_kb}KB OK={ok}")
    return ok


if __name__ == "__main__":
    a = check("aura.onnx")
    b = check("aura_stage2.onnx")
    print("ALL_OK=" + str(a and b))
