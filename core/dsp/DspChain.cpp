// PROJECT AURA — core/dsp/DspChain.cpp
#include "core/dsp/DspChain.h"

#include <cmath>

namespace aura::dsp {

using common::Result;

Result<void> AgcStage::process(float* samples, size_t n) {
  if (n == 0) return {};
  double sumSq = 0.0;
  for (size_t i = 0; i < n; ++i) sumSq += static_cast<double>(samples[i]) * samples[i];
  const float rms = static_cast<float>(std::sqrt(sumSq / static_cast<double>(n)));

  // Smoothly adapt the gain toward the one that would hit targetRms_. Clamp to a
  // sane range so silence doesn't blow up the gain.
  if (rms > 1e-5f) {
    const float desired = targetRms_ / rms;
    constexpr float kSmoothing = 0.05f;  // slow adaptation
    gain_ += kSmoothing * (desired - gain_);
    if (gain_ < 0.1f) gain_ = 0.1f;
    if (gain_ > 20.0f) gain_ = 20.0f;
  }
  for (size_t i = 0; i < n; ++i) {
    float v = samples[i] * gain_;
    if (v > 1.0f) v = 1.0f;
    if (v < -1.0f) v = -1.0f;
    samples[i] = v;
  }
  return {};
}

Result<void> NsStage::process(float* samples, size_t n) {
  if (n == 0) return {};
  // 1-pole high-pass (~removes DC / low rumble): y[n] = a*(y[n-1] + x[n] - x[n-1]).
  constexpr float kA = 0.97f;
  for (size_t i = 0; i < n; ++i) {
    const float x = samples[i];
    const float y = kA * (hpPrevOut_ + x - hpPrevIn_);
    hpPrevIn_ = x;
    hpPrevOut_ = y;
    samples[i] = y;
  }
  // Track a slow noise floor and apply a gentle expander below it.
  double sumSq = 0.0;
  for (size_t i = 0; i < n; ++i) sumSq += static_cast<double>(samples[i]) * samples[i];
  const float rms = static_cast<float>(std::sqrt(sumSq / static_cast<double>(n)));
  noiseFloor_ += 0.01f * (rms - noiseFloor_);
  if (rms < noiseFloor_ * 1.5f) {
    for (size_t i = 0; i < n; ++i) samples[i] *= 0.5f;  // soft attenuation of near-noise
  }
  return {};
}

DspChain::DspChain() {
  // Fixed order: AGC -> AEC -> NS (addendum §3).
  stages_.push_back(std::make_unique<AgcStage>());
  stages_.push_back(std::make_unique<AecStage>());
  stages_.push_back(std::make_unique<NsStage>());
}

Result<void> DspChain::process(float* samples, size_t n) {
  for (auto& stage : stages_) {
    auto r = stage->process(samples, n);
    if (!r) return r;  // propagate, never swallow (Stage 9 §3)
  }
  return {};
}

}  // namespace aura::dsp
