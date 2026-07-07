// PROJECT AURA — core/runtime/OnnxRuntimeBackend.h
//
// The one concrete IInferenceBackend for v0 (ADR-002, ONNX Runtime Mobile).
// Header is ORT-free (pImpl) so <onnxruntime_cxx_api.h> does not leak to includers.
// Compiled only when AURA_ENABLE_ONNXRUNTIME is defined (the Android build); the
// host build excludes this TU and tests use FakeInferenceBackend instead.
#ifndef AURA_RUNTIME_ONNXRUNTIMEBACKEND_H
#define AURA_RUNTIME_ONNXRUNTIMEBACKEND_H

#include <memory>

#include "core/runtime/IInferenceBackend.h"

namespace aura::runtime
{

  class OnnxRuntimeBackend final : public IInferenceBackend
  {
  public:
    OnnxRuntimeBackend();
    ~OnnxRuntimeBackend() override;

    common::Result<void> loadModel(const common::ModelHandle &model) override;
    common::Result<common::TensorView> infer(const common::TensorView &input,
                                             common::Arena &scratchArena) override;
    common::BackendStats stats() const override;
    common::BackendKind kind() const override { return common::BackendKind::kOnnxRuntime; }

  private:
    struct Impl;
    std::unique_ptr<Impl> impl_;
  };

} // namespace aura::runtime

#endif // AURA_RUNTIME_ONNXRUNTIMEBACKEND_H
