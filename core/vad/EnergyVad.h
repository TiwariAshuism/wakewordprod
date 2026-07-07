// PROJECT AURA — core/vad/EnergyVad.h
// Dependency-free RMS-energy VAD. The default on hosts and in the deterministic
// golden test (no ONNX Runtime dependency). Tracks a slow noise floor and maps the
// energy ratio above it to a pseudo-probability. Allocation-free.
#ifndef AURA_VAD_ENERGYVAD_H
#define AURA_VAD_ENERGYVAD_H

#include <algorithm>
#include <cmath>

#include "core/vad/IVad.h"

namespace aura::vad {

class EnergyVad final : public IVad {
 public:
  float process(const float* samples, size_t n) override {
    if (n == 0) return 0.0f;
    double sumSq = 0.0;
    for (size_t i = 0; i < n; ++i) sumSq += static_cast<double>(samples[i]) * samples[i];
    const float rms = static_cast<float>(std::sqrt(sumSq / static_cast<double>(n)));
    // Adapt the noise floor slowly, faster downward than upward.
    const float rate = (rms < noiseFloor_) ? 0.05f : 0.005f;
    noiseFloor_ += rate * (rms - noiseFloor_);
    const float ratio = rms / std::max(noiseFloor_, 1e-5f);
    // ratio ~1 -> noise (~0 prob); ratio >= 3 -> speech (~1 prob).
    const float p = std::clamp((ratio - 1.5f) / 1.5f, 0.0f, 1.0f);
    return p;
  }
  void reset() override { noiseFloor_ = 1e-3f; }

 private:
  float noiseFloor_ = 1e-3f;
};

}  // namespace aura::vad

#endif  // AURA_VAD_ENERGYVAD_H
