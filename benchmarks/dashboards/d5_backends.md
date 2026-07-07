# D5 — Second-tier backends for the real "hey m" model

Producing the deployable model artifacts for the two non-ORT inference backends and
verifying they load + run and match the trained float ONNX. Source model:
`apps/android/src/main/assets/models/heym.onnx` (DS-CNN, input `[1,100,40]` log-Mel,
output `[1,2]` logits). Representative / eval data: `.data/heym_feat2.npz` (`Xtr` 17566×100×40,
`Xte` 483×100×40).

Platform: Windows 11, **Python 3.13.6**. All work done on this host (CPU-only torch).

## Summary

| Backend | Toolchain install | Artifact | Verified runs | Status |
|---|---|---|---|---|
| **TFLite Micro (INT8 `.tflite`)** | `tensorflow` 2.21.0, `onnx2tf` 2.5.0, `onnxsim` 0.6.5 — **installed OK** | `assets/models/heym.tflite`, **34.4 KB** | Yes — `tf.lite.Interpreter` | **DONE** |
| **ExecuTorch (`.pte`)** | `executorch` 1.3.1 (+ `onnx2torch` 1.5.15) — **installed OK** | `assets/models/heym.pte`, **64.7 KB** | Yes — `executorch.runtime.Runtime` | **DONE** |

Nothing is toolchain-blocked. Both installs that the task flagged as *possibly* unavailable
on Python 3.13 in fact provided cp313 wheels and imported cleanly on this Windows host.

---

## 1) TFLite INT8 — DONE (matches the `TfliteMicroBackend` contract)

TensorFlow **did** install on Python 3.13 (`tensorflow 2.21.0`, cp313 wheel) — the
`tools/convert_to_tflite.md` assumption that "TF is not installed" no longer holds here, so
the recipe was runnable directly.

Route taken (onnx2tf route from the recipe, adapted to the newer onnx2tf 2.5.0):

1. `onnxsim heym.onnx -> heym_simplified.onnx` (25 nodes: 9 Conv / 9 Relu / ReduceMean / Gemm).
2. `onnx2tf -i heym_simplified.onnx -o .data/heym_sm -kat input -osd -tb tf_converter`
   — emits a TF SavedModel with the input axes **kept as `[1,100,40]`** (`-kat input`).
   The default `flatbuffer_direct` fast path does **not** apply the representative-dataset
   calibration (it stamped a fixed 1/128 input scale → clipped the −13.8…+10.1 log-Mel range
   → accuracy collapsed to **0.236**). Forcing `-tb tf_converter` (needs `tf_keras`, installed)
   restores the real `TFLiteConverter` path.
3. `tf.lite.TFLiteConverter.from_saved_model(...)` with `Optimize.DEFAULT`, a
   `representative_dataset` over 200 real `Xtr` samples, `TFLITE_BUILTINS_INT8`, and
   `inference_input_type = inference_output_type = tf.int8` (exactly the recipe snippet).

Produced `apps/android/src/main/assets/models/heym.tflite`:

| Property | Value |
|---|---|
| Size | **34.4 KB** (within the recipe's 30–40 KB MCU budget) |
| Input | `[1,100,40]` **int8**, scale `0.092584`, zero-point `21` |
| Output | `[1,2]` **int8** logits, scale `0.023765`, zero-point `11` |
| INT8 accuracy on held-out `Xte` (483 clips) | **0.9151** |
| Float ONNX accuracy on the same set | **0.9151** (no drop from quantization) |
| argmax agreement INT8 vs float ONNX | **0.9959** (481/483) |

This satisfies the `core/runtime/TfliteMicroBackend` contract from `tools/convert_to_tflite.md`:
input `[1,100,40]` int8, output int8 logits, backend quantizes/dequantizes using the model's
scale/zero-point. Static tensor arena sizing (`TfliteMicroBackend(arenaBytes)`) is an
on-device concern; the arena is not exercised on this host.

Verified with `tf.lite.Interpreter(...).invoke()` on all 483 test clips (feature → quantize
with the input scale/zp → invoke → argmax).

## 2) ExecuTorch `.pte` — DONE

`pip install executorch` **succeeded** (`executorch 1.3.1`, cp313 wheel; pulled `torch 2.12.1`,
`torchao`, etc.). No toolchain block.

There is no saved PyTorch checkpoint for heym — `tools/heym_train.py` exports ONNX directly and
discards the state_dict. To get a faithful `nn.Module` for `torch.export`, the trained
`heym.onnx` was reimported with **onnx2torch** (a Windows tempfile bug in its
`safe_shape_inference` was bypassed by pre-running `onnx.shape_inference.infer_shapes`).
Fidelity check: onnx2torch module vs onnxruntime max abs diff **1.4e-6**, argmax identical.

Export pipeline (all steps ran on this host):

```
ep   = torch.export.export(module, (torch.zeros(1,100,40),))   # export OK
edge = executorch.exir.to_edge(ep)                             # to_edge OK
prog = edge.to_executorch()                                    # to_executorch OK
open("assets/models/heym.pte","wb").write(prog.buffer)         # 64.7 KB
```

Produced `apps/android/src/main/assets/models/heym.pte`:

| Property | Value |
|---|---|
| Size | **64.7 KB** |
| Quantization | **float32** (portable/no-delegate export; not INT8-quantized) |
| Output | `[1,2]` float32 logits |
| Accuracy on `Xte` | **0.9151** |
| agreement vs float ONNX | **1.0000** (483/483) |

Verified by loading in `executorch.runtime.Runtime` and executing `forward` on all 483 test
clips. (The runtime prints harmless Linux-sysfs `cpuinfo` probe warnings on Windows; execution
is unaffected.)

Note: this `.pte` is a **float32** program. A quantized (XNNPACK INT8) `.pte` was not produced —
that path needs the XNNPACK quantizer + partitioner flow, out of scope for D5's "export heym to
.pte" ask. The float `.pte` is a valid, runtime-verified ExecuTorch artifact.

---

## Reproduce

```
pip install tensorflow onnx2tf onnxsim tf_keras       # TFLite route (all cp313 wheels)
pip install executorch onnx2torch                      # ExecuTorch route (all cp313 wheels)

# TFLite:
python -m onnxsim apps/android/src/main/assets/models/heym.onnx .data/heym_simplified.onnx
python -m onnx2tf -i .data/heym_simplified.onnx -o .data/heym_sm -kat input -osd -tb tf_converter
#   then TFLiteConverter.from_saved_model(...) with representative_dataset over Xtr, int8 I/O
#   -> apps/android/src/main/assets/models/heym.tflite

# ExecuTorch:
#   onnx2torch(heym.onnx) -> torch.export -> exir.to_edge -> to_executorch
#   -> apps/android/src/main/assets/models/heym.pte
```

## Honest ledger

- **Not blocked by toolchain.** The task anticipated TF (and possibly ExecuTorch) having no
  Python-3.13 wheel; on this host both installed and imported. Reporting that outcome as-is.
- **One real failure caught and fixed, not hidden:** the onnx2tf `flatbuffer_direct` fast path
  produced a mis-calibrated INT8 tflite (acc 0.236, fixed 1/128 input scale). It was replaced
  with the `tf_converter` + `TFLiteConverter` representative-dataset path (acc 0.9151). The
  shipped `heym.tflite` is the good one.
- Dependency-resolver warnings during install (`streamlit`/`gtts` pin older `protobuf`/`click`)
  are pre-existing unrelated packages; they did not affect the conversion tools.
- Both shipped artifacts are runtime-verified against the trained float ONNX on the full
  483-clip held-out test set, not just "loads without error."
