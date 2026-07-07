// PROJECT AURA — core/vad/IVad.h
//
// Responsibilities : gate Stage-1 inference (Stage 7 §3.9). VAD consumes post-DSP
//                    time-domain audio in parallel with the log-Mel front-end
//                    (addendum §3: Silero operates on raw audio directly).
// Dependencies     : core/features (Row 4). Runs on the Audio thread; owns its own
//                    internal state (Silero LSTM state / energy tracker).
//
// Two implementations: SileroVad (ONNX Runtime, device build) and EnergyVad
// (dependency-free, the host/golden-test default). See REPORT.md for why the
// deterministic host test uses EnergyVad rather than Silero.
#ifndef AURA_VAD_IVAD_H
#define AURA_VAD_IVAD_H

#include <cstddef>

#include "core/common/result.h"

namespace aura::vad {

class IVad {
 public:
  virtual ~IVad() = default;
  // Feed one post-DSP mono block; returns speech probability in [0, 1]. Stateful
  // frame-to-frame (Stage 7 §3.9). Audio-thread hot path.
  virtual float process(const float* samples, size_t n) = 0;
  virtual void reset() = 0;
};

}  // namespace aura::vad

#endif  // AURA_VAD_IVAD_H
