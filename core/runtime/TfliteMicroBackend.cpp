// PROJECT AURA — core/runtime/TfliteMicroBackend.cpp
// Compiled only when AURA_ENABLE_TFLITE_MICRO is defined (ESP32/Cortex-M builds); the host
// and Android(ORT) builds exclude this TU, so it compiles to nothing there.
#include "core/runtime/TfliteMicroBackend.h"

#if defined(AURA_ENABLE_TFLITE_MICRO)

#include "tensorflow/lite/micro/micro_interpreter.h"
#include "tensorflow/lite/micro/micro_mutable_op_resolver.h"
#include "tensorflow/lite/micro/micro_log.h"
#include "tensorflow/lite/schema/schema_generated.h"

#include <cstring>
#include <vector>

namespace aura::runtime {

using common::Arena;
using common::BackendStats;
using common::Err;
using common::ErrorCode;
using common::ModelHandle;
using common::Result;
using common::TensorView;

// Op resolver covers the ops the DS-CNN uses (conv/depthwise/pool/fc/softmax/quantize).
using OpResolver = tflite::MicroMutableOpResolver<8>;

struct TfliteMicroBackend::Impl {
  std::vector<uint8_t> arena;  // statically-sized tensor arena (no hot-path heap, audit §10)
  OpResolver resolver;
  const tflite::Model* model = nullptr;
  std::unique_ptr<tflite::MicroInterpreter> interp;
  BackendStats stats;

  explicit Impl(size_t bytes) : arena(bytes) {
    resolver.AddConv2D();
    resolver.AddDepthwiseConv2D();
    resolver.AddMaxPool2D();
    resolver.AddMean();          // global average pool
    resolver.AddFullyConnected();
    resolver.AddSoftmax();
    resolver.AddQuantize();
    resolver.AddDequantize();
  }
};

TfliteMicroBackend::TfliteMicroBackend(size_t arenaBytes)
    : impl_(std::make_unique<Impl>(arenaBytes)) {}
TfliteMicroBackend::~TfliteMicroBackend() = default;

Result<void> TfliteMicroBackend::loadModel(const ModelHandle& model) {
  if (!model.valid()) return Err(ErrorCode::kInvalidArgument, "loadModel: invalid handle");
  impl_->model = tflite::GetModel(model.data);
  if (impl_->model->version() != TFLITE_SCHEMA_VERSION) {
    return Err(ErrorCode::kVerificationFailed, "tflite schema version mismatch");
  }
  impl_->interp = std::make_unique<tflite::MicroInterpreter>(
      impl_->model, impl_->resolver, impl_->arena.data(), impl_->arena.size());
  if (impl_->interp->AllocateTensors() != kTfLiteOk) {
    return Err(ErrorCode::kBackendError, "tflite AllocateTensors failed (arena too small?)");
  }
  return {};
}

Result<TensorView> TfliteMicroBackend::infer(const TensorView& input, Arena& scratchArena) {
  if (!impl_->interp) return Err(ErrorCode::kFailedPrecondition, "no model loaded");
  TfLiteTensor* in = impl_->interp->input(0);
  // Quantize float log-Mel input into the model's int8 input (per its scale/zero-point).
  const int64_t n = input.elementCount();
  const float scale = in->params.scale;
  const int zp = in->params.zero_point;
  int8_t* q = in->data.int8;
  for (int64_t i = 0; i < n; ++i) {
    int v = static_cast<int>(std::lround(input.data[i] / scale)) + zp;
    q[i] = static_cast<int8_t>(v < -128 ? -128 : (v > 127 ? 127 : v));
  }
  if (impl_->interp->Invoke() != kTfLiteOk) {
    return Err(ErrorCode::kBackendError, "tflite Invoke failed");
  }
  // Dequantize the int8 output logits into the caller's arena.
  TfLiteTensor* out = impl_->interp->output(0);
  const size_t outN = out->bytes;  // int8 count
  float* dst = scratchArena.allocateFloats(outN);
  if (!dst) return Err(ErrorCode::kBackendError, "scratch arena exhausted");
  const float os = out->params.scale;
  const int oz = out->params.zero_point;
  for (size_t i = 0; i < outN; ++i) dst[i] = (static_cast<int>(out->data.int8[i]) - oz) * os;

  impl_->stats.inferenceCount++;
  TensorView v;
  v.data = dst;
  v.rank = 1;
  v.shape[0] = static_cast<int64_t>(outN);
  return v;
}

BackendStats TfliteMicroBackend::stats() const { return impl_->stats; }

}  // namespace aura::runtime

#endif  // AURA_ENABLE_TFLITE_MICRO
