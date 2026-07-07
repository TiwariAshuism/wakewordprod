# Converting the KWS model to INT8 `.tflite` (for `core/runtime/TfliteMicroBackend`)

The TFLite Micro backend (ESP32-S3 / Cortex-M tier, ADR-002) needs an **INT8 `.tflite`**
model. TensorFlow is **not installed in the AURA dev/CI image used here**, so this is a
recipe to run where TF is available (a training box or a dedicated conversion job) — the
resulting `kws_marvin.tflite` is placed alongside the ONNX assets.

Two routes from the trained PyTorch DS-CNN (`.data/kws_dscnn.pt`, `tools/train_kws_model.py`):

## Route A — via ONNX → TF → TFLite (onnx2tf)
```bash
pip install tensorflow onnx2tf onnxsim
# 1) simplify the exported ONNX
onnxsim apps/android/src/main/assets/models/kws_marvin.onnx /tmp/kws_simplified.onnx
# 2) ONNX -> TF SavedModel
onnx2tf -i /tmp/kws_simplified.onnx -o /tmp/kws_tf
# 3) INT8 full-integer quantization with a representative dataset
python - <<'PY'
import tensorflow as tf, numpy as np
X = np.load(".data/aura_feat_aug.npz")["Xtr"]  # [N,100,40] real training features
def rep():
    for i in range(200):
        yield [X[i][None].astype("float32")]
c = tf.lite.TFLiteConverter.from_saved_model("/tmp/kws_tf")
c.optimizations = [tf.lite.Optimize.DEFAULT]
c.representative_dataset = rep
c.target_spec.supported_ops = [tf.lite.OpsSet.TFLITE_BUILTINS_INT8]
c.inference_input_type = tf.int8
c.inference_output_type = tf.int8
open("apps/android/src/main/assets/models/kws_marvin.tflite","wb").write(c.convert())
PY
```

## Route B — native TF training
Retrain the DS-CNN directly in Keras with the same 13-class head + the same front-end
features, then apply the same INT8 `representative_dataset` conversion above. Preferred if a
TF training path is stood up, since it avoids ONNX→TF op-mapping quirks.

## Notes
- The INT8 contract must match `TfliteMicroBackend`: input `[1,100,40]` int8 (quantized
  log-Mel), output int8 logits; the backend quantizes/dequantizes using the model's
  scale/zero-point.
- Size on an MCU: the DS-CNN INT8 is ~30-40 KB (cf. the ONNX INT8 measured at ~39 KB,
  `benchmarks/dashboards/quant_report.md`) — within the Cortex-M/ESP32 budget.
- Static tensor arena only (no heap on the hot path) — the embedded non-negotiable
  (audit §10). Size the arena from the model; `TfliteMicroBackend(arenaBytes)`.
