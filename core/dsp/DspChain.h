// PROJECT AURA — core/dsp/DspChain.h
//
// The fixed AGC -> AEC -> NS pipeline (addendum §3). Ordering is a correctness
// decision, not a runtime customization point (Stage 7 §10). AEC is a no-op
// passthrough in v0 (the Android reference app plays no audio back); the interface
// slot is kept so enabling real AEC later is a one-line swap, not a redesign
// (flagged in REPORT.md).
#ifndef AURA_DSP_DSPCHAIN_H
#define AURA_DSP_DSPCHAIN_H

#include <memory>
#include <string_view>
#include <vector>

#include "core/dsp/IDspStage.h"

namespace aura::dsp {

// --- Stage 1: Automatic Gain Control ---------------------------------------
// AGC runs BEFORE AEC/NS (addendum §3): normalizing level first gives the
// downstream filters a consistent input range. Simple RMS-target smoothed gain.
class AgcStage final : public IDspStage {
 public:
  explicit AgcStage(float targetRms = 0.1f) : targetRms_(targetRms) {}
  common::Result<void> process(float* samples, size_t n) override;
  std::string_view name() const override { return "agc"; }

 private:
  float targetRms_;
  float gain_ = 1.0f;      // adaptive, persists across frames
};

// --- Stage 2: Acoustic Echo Cancellation (no-op passthrough in v0) ----------
class AecStage final : public IDspStage {
 public:
  common::Result<void> process(float* /*samples*/, size_t /*n*/) override { return {}; }
  std::string_view name() const override { return "aec-noop"; }
};

// --- Stage 3: Noise Suppression (minimal placeholder in v0) -----------------
// A 1-pole DC/rumble high-pass plus a soft noise gate. Real RNNoise / WebRTC-APM
// NS is deferred (flagged in REPORT.md).
class NsStage final : public IDspStage {
 public:
  common::Result<void> process(float* samples, size_t n) override;
  std::string_view name() const override { return "ns-minimal"; }

 private:
  float hpPrevIn_ = 0.0f;
  float hpPrevOut_ = 0.0f;
  float noiseFloor_ = 1e-4f;   // slowly-tracked
};

// The composed, fixed-order chain.
class DspChain {
 public:
  DspChain();
  // Runs AGC -> AEC -> NS in place. Audio-thread hot path; no allocation.
  common::Result<void> process(float* samples, size_t n);

 private:
  std::vector<std::unique_ptr<IDspStage>> stages_;  // built once at startup
};

}  // namespace aura::dsp

#endif  // AURA_DSP_DSPCHAIN_H
