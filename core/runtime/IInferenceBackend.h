// PROJECT AURA — core/runtime/IInferenceBackend.h
//
// Responsibilities : the inference backend plugin point (Stage 7 §3.10/§4/§10,
//                    ADR-002). v0 ships exactly ONE concrete backend
//                    (OnnxRuntimeBackend); TFLite Micro / ExecuTorch are NOT built.
// Dependencies     : core/features, core/vad (Row 5). Executes on the Inference
//                    thread, separate from the Audio thread (Stage 7 §6).
// Thread ownership : single-threaded per instance (Inference thread only). infer()
//                    returns Result<T>, never throws (Stage 7 §4).
// Memory ownership : owns model-weight regions (via ModelHandle) + any internal
//                    scratch; writes its output into the caller-supplied Arena.
#ifndef AURA_RUNTIME_IINFERENCEBACKEND_H
#define AURA_RUNTIME_IINFERENCEBACKEND_H

#include "core/common/result.h"
#include "core/common/tensor.h"

namespace aura::runtime {

// Exact signature per Stage 7 §4. `scratchArena` supplies the memory the output
// TensorView points into; it stays valid until the caller resets the arena.
class IInferenceBackend {
 public:
  virtual ~IInferenceBackend() = default;
  virtual common::Result<void> loadModel(const common::ModelHandle& model) = 0;
  virtual common::Result<common::TensorView> infer(const common::TensorView& input,
                                                   common::Arena& scratchArena) = 0;
  virtual common::BackendStats stats() const = 0;
  virtual common::BackendKind kind() const = 0;  // OnnxRuntime | TfliteMicro | ExecuTorch
};

}  // namespace aura::runtime

#endif  // AURA_RUNTIME_IINFERENCEBACKEND_H
