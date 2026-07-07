// PROJECT AURA — core/vad/SileroVad.h
//
// Silero VAD wrapped over ONNX Runtime (Stage 7 §3.9). Owns Silero's recurrent
// state (Stage 7 §3.9 "small internal LSTM state buffer"). Runs on the Audio
// thread. Buffers incoming blocks to Silero's native 512-sample @16 kHz chunk.
//
// core/vad -> ONNX Runtime is a core/ -> third_party dependency (allowed by
// Stage 7 §2), independent of core/runtime — so no Row violation. The header is
// ORT-free (pImpl) so it does not leak <onnxruntime_cxx_api.h> to includers.
//
// KNOWN v0 GAP (flagged in REPORT.md): ORT allocates internally during Run(),
// which technically violates the Audio-thread no-alloc rule. Input/output OrtValues
// are created once over reused buffers to minimize this; a full fix (custom ORT
// allocator / IoBinding, or a hand-rolled Silero) needs an ADR.
#ifndef AURA_VAD_SILEROVAD_H
#define AURA_VAD_SILEROVAD_H

#include <memory>

#include "core/common/tensor.h"
#include "core/vad/IVad.h"

namespace aura::vad {

class SileroVad final : public IVad {
 public:
  // `model` is the mmap'd silero_vad.onnx (owned by core/model). sampleRate must
  // be 16000. Returns via ok()/error through Create().
  static std::unique_ptr<SileroVad> Create(const common::ModelHandle& model, int sampleRate);
  ~SileroVad() override;

  float process(const float* samples, size_t n) override;
  void reset() override;

 private:
  struct Impl;
  explicit SileroVad(std::unique_ptr<Impl> impl);
  std::unique_ptr<Impl> impl_;
};

}  // namespace aura::vad

#endif  // AURA_VAD_SILEROVAD_H
