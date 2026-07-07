// PROJECT AURA — core/runtime/OnnxRuntimeBackend.cpp
// Compiled only when ONNX Runtime is available (AURA_ENABLE_ONNXRUNTIME).
#include "core/runtime/OnnxRuntimeBackend.h"

#if defined(AURA_ENABLE_ONNXRUNTIME)

#include <onnxruntime_cxx_api.h>
#if defined(__ANDROID__)
#include <nnapi_provider_factory.h>  // OrtSessionOptionsAppendExecutionProvider_Nnapi
#endif

#include <cstring>
#include <ctime>
#include <string>
#include <vector>

#include "core/common/noalloc.h"  // ScopedAllowAllocGuard (ORT allocation boundary)

namespace aura::runtime {

using common::Arena;
using common::BackendStats;
using common::Err;
using common::ErrorCode;
using common::ModelHandle;
using common::Result;
using common::TensorView;

namespace {
uint64_t monoNanos() {
  timespec ts{};
  clock_gettime(CLOCK_MONOTONIC, &ts);
  return static_cast<uint64_t>(ts.tv_sec) * 1000000000ull + static_cast<uint64_t>(ts.tv_nsec);
}
}  // namespace

struct OnnxRuntimeBackend::Impl {
  Ort::Env env{ORT_LOGGING_LEVEL_WARNING, "aura-kws"};
  Ort::SessionOptions opts;
  std::unique_ptr<Ort::Session> session;
  Ort::MemoryInfo memInfo = Ort::MemoryInfo::CreateCpu(OrtArenaAllocator, OrtMemTypeDefault);

  std::string inputName, outputName;
  std::vector<int64_t> inputShape;   // model's declared input shape (dynamic dims as -1)
  int64_t inputElems = 0;            // product of fixed dims (>=1)
  BackendStats stats;
};

OnnxRuntimeBackend::OnnxRuntimeBackend() : impl_(std::make_unique<Impl>()) {
  impl_->opts.SetIntraOpNumThreads(1);
  impl_->opts.SetGraphOptimizationLevel(GraphOptimizationLevel::ORT_ENABLE_ALL);

  // Execution-provider selection (audit §9): NNAPI is tried first on Android for
  // hardware acceleration, but its quality varies by OEM/SoC, so **XNNPACK must always
  // be present as the portable CPU-accelerated fallback**, and ORT's default CPU EP is
  // the final fallback. Each append is best-effort: if an EP isn't in this build, we log
  // and continue — a missing EP must never break model load (CPU always works).
#if defined(__ANDROID__)
  try {
    // NNAPI: sustained-speed + fp16 relaxation are reasonable for an always-on KWS model.
    const uint32_t kNnapiFlags = 0;  // NNAPI_FLAG_USE_NONE; keep default (no fp16 by default)
    Ort::ThrowOnError(OrtSessionOptionsAppendExecutionProvider_Nnapi(impl_->opts, kNnapiFlags));
  } catch (const Ort::Exception&) {
    // NNAPI unavailable on this device/build — fall through to XNNPACK/CPU.
  }
#endif
  try {
    // XNNPACK CPU-accelerated EP — always present (audit requirement).
    impl_->opts.AppendExecutionProvider("XNNPACK",
                                        {{"intra_op_num_threads", "1"}});
  } catch (const Ort::Exception&) {
    // XNNPACK not in this build — ORT's default CPU EP still handles inference.
  }
}
OnnxRuntimeBackend::~OnnxRuntimeBackend() = default;

Result<void> OnnxRuntimeBackend::loadModel(const ModelHandle& model) {
  if (!model.valid()) return Err(ErrorCode::kInvalidArgument, "loadModel: invalid handle");
  try {
    impl_->session = std::make_unique<Ort::Session>(impl_->env, model.data, model.size, impl_->opts);
    Ort::AllocatorWithDefaultOptions alloc;
    impl_->inputName = impl_->session->GetInputNameAllocated(0, alloc).get();
    impl_->outputName = impl_->session->GetOutputNameAllocated(0, alloc).get();
    auto info = impl_->session->GetInputTypeInfo(0).GetTensorTypeAndShapeInfo();
    impl_->inputShape = info.GetShape();
    int64_t elems = 1;
    for (auto d : impl_->inputShape) elems *= (d > 0 ? d : 1);  // treat dynamic dims as 1
    impl_->inputElems = elems;
  } catch (const Ort::Exception& e) {
    return Err(ErrorCode::kBackendError, "ORT loadModel failed");
  }
  return {};
}

Result<TensorView> OnnxRuntimeBackend::infer(const TensorView& input, Arena& scratchArena) {
  if (!impl_->session) return Err(ErrorCode::kFailedPrecondition, "no model loaded");

  // ONNX Runtime's Run() allocates internally (input/output OrtValues, EP scratch) — an
  // unavoidable third-party allocation boundary. The inference thread runs under a
  // ScopedNoAllocGuard (WakeWordEngine §6), which would abort() on those allocations (this
  // is a device-only crash: the host build stubs ORT out). Mark the ORT call as an allowed
  // allocation site, so the guard still protects our own steady-state hot path.
  // TODO(perf): eliminate with ORT IoBinding + pre-allocated OrtValues for true zero-alloc.
  common::ScopedAllowAllocGuard allow;

  const int64_t n = input.elementCount();
  // Feed the flat input data using the model's declared shape (fixing any dynamic
  // batch dim to 1). Element count must match (Stage 7 M3 tensor-layout risk).
  std::vector<int64_t> shape = impl_->inputShape;
  if (shape.empty()) shape = {1, n};
  for (auto& d : shape) if (d < 0) d = 1;

  int64_t shapeElems = 1;
  for (auto d : shape) shapeElems *= d;
  if (shapeElems != n) {
    return Err(ErrorCode::kInvalidArgument, "input element count != model input shape");
  }

  try {
    Ort::Value in = Ort::Value::CreateTensor<float>(impl_->memInfo, input.data,
                                                    static_cast<size_t>(n), shape.data(),
                                                    shape.size());
    const char* inNames[] = {impl_->inputName.c_str()};
    const char* outNames[] = {impl_->outputName.c_str()};

    const uint64_t t0 = monoNanos();
    auto outputs = impl_->session->Run(Ort::RunOptions{nullptr}, inNames, &in, 1, outNames, 1);
    const uint64_t t1 = monoNanos();
    impl_->stats.lastInferenceNanos = t1 - t0;
    impl_->stats.inferenceCount++;

    auto& out = outputs[0];
    const auto outInfo = out.GetTensorTypeAndShapeInfo();
    const size_t outN = static_cast<size_t>(outInfo.GetElementCount());
    // Copy ORT's output into the caller's arena so it stays valid after `outputs`
    // is destroyed (Stage 7 §4/§5).
    float* dst = scratchArena.allocateFloats(outN);
    if (!dst) return Err(ErrorCode::kBackendError, "scratch arena exhausted");
    std::memcpy(dst, out.GetTensorData<float>(), outN * sizeof(float));

    TensorView view;
    view.data = dst;
    view.rank = 1;
    view.shape[0] = static_cast<int64_t>(outN);
    return view;
  } catch (const Ort::Exception&) {
    return Err(ErrorCode::kBackendError, "ORT infer failed");
  }
}

BackendStats OnnxRuntimeBackend::stats() const { return impl_->stats; }

}  // namespace aura::runtime

#endif  // AURA_ENABLE_ONNXRUNTIME
