// PROJECT AURA — core/runtime/TfliteMicroBackend.h
//
// Second IInferenceBackend (ADR-002 / SAS §3.10): TensorFlow Lite Micro, the runtime for
// the ESP32-S3 / Cortex-M tier where ONNX Runtime is too heavy (audit §9/§10). Compiled
// only when AURA_ENABLE_TFLITE_MICRO is defined; the host/Android(ORT) builds exclude this
// TU. Header is TFLM-free (pImpl) so <tensorflow/lite/micro/...> doesn't leak to includers.
//
// The model is an INT8 .tflite (static tensor arena, no heap on the hot path — the embedded
// non-negotiable from audit §10). See tools/convert_to_tflite.md for producing it from the
// trained model. This backend is device/MCU-verified only; it is not exercised on the host.
#ifndef AURA_RUNTIME_TFLITEMICROBACKEND_H
#define AURA_RUNTIME_TFLITEMICROBACKEND_H

#include <memory>

#include "core/runtime/IInferenceBackend.h"

namespace aura::runtime {

class TfliteMicroBackend final : public IInferenceBackend {
 public:
  // arenaBytes: the fixed tensor arena (statically owned; sized from the model manifest).
  explicit TfliteMicroBackend(size_t arenaBytes);
  ~TfliteMicroBackend() override;

  common::Result<void> loadModel(const common::ModelHandle& model) override;
  common::Result<common::TensorView> infer(const common::TensorView& input,
                                           common::Arena& scratchArena) override;
  common::BackendStats stats() const override;
  common::BackendKind kind() const override { return common::BackendKind::kTfliteMicro; }

 private:
  struct Impl;
  std::unique_ptr<Impl> impl_;
};

}  // namespace aura::runtime

#endif  // AURA_RUNTIME_TFLITEMICROBACKEND_H
