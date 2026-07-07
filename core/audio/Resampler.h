// PROJECT AURA — core/audio/Resampler.h
//
// Streaming windowed-sinc (Lanczos) sample-rate converter (Arch Finding 3 / ADR-MicInput:
// "a real resampler — polyphase or windowed-sinc — not naive linear"). Converts arbitrary
// input rates (USB/BT mics, non-16 kHz native) to the engine's 16 kHz before feature
// extraction. Anti-aliased on downsampling (sinc cutoff at the lower Nyquist).
//
// Thread: runs in the capture path (allocation-free at steady state — the small carry
// buffer is reserved at construction).
#ifndef AURA_AUDIO_RESAMPLER_H
#define AURA_AUDIO_RESAMPLER_H

#include <cmath>
#include <cstddef>
#include <cstdint>
#include <vector>

namespace aura::audio {

class Resampler {
 public:
  Resampler(uint32_t inRate, uint32_t outRate)
      : inRate_(inRate), outRate_(outRate) {
    ratio_ = static_cast<double>(inRate) / static_cast<double>(outRate);
    cutoff_ = std::min(1.0, static_cast<double>(outRate) / static_cast<double>(inRate));
    carry_.reserve(kTaps + kMaxBlock);   // steady-state alloc-free
    work_.reserve(kTaps + kMaxBlock);
    reset();
  }

  bool passthrough() const { return inRate_ == outRate_; }
  uint32_t inRate() const { return inRate_; }

  void reset() {
    carry_.assign(kTaps, 0.0f);  // zero left-context
    phase_ = static_cast<double>(kTaps);  // first output maps to first real input sample
  }

  // Resample `n` input samples into `out` (capacity `outCap`). Returns #samples written.
  size_t process(const float* in, size_t n, float* out, size_t outCap) {
    if (passthrough()) {
      const size_t m = n < outCap ? n : outCap;
      for (size_t i = 0; i < m; ++i) out[i] = in[i];
      return m;
    }
    // work = carried context + new input (bounded: caller feeds <= ~512-sample blocks).
    work_.assign(carry_.begin(), carry_.end());
    work_.insert(work_.end(), in, in + n);
    const int total = static_cast<int>(work_.size());

    size_t produced = 0;
    while (produced < outCap) {
      const int center = static_cast<int>(std::floor(phase_));
      if (center + kHalf >= total) break;  // kernel right edge would read past available input
      double acc = 0.0, wsum = 0.0;
      for (int i = center - kHalf + 1; i <= center + kHalf; ++i) {
        if (i < 0 || i >= total) continue;
        const double x = (phase_ - i) * cutoff_;
        const double w = cutoff_ * sinc(x) * lanczos(phase_ - i);
        acc += w * work_[i];
        wsum += w;
      }
      out[produced++] = static_cast<float>(wsum > 1e-9 ? acc / wsum : acc);
      phase_ += ratio_;
    }

    // Carry the tail so future outputs have their left context. Keep from the earliest
    // sample any future output could need: floor(phase_) - kHalf + 1.
    int base = static_cast<int>(std::floor(phase_)) - kHalf + 1;
    if (base < 0) base = 0;
    if (base > total) base = total;
    carry_.assign(work_.begin() + base, work_.end());
    phase_ -= base;  // rebase phase to the new carry buffer
    return produced;
  }

 private:
  static constexpr int kHalf = 8;       // sinc half-width (16 taps)
  static constexpr int kTaps = 2 * kHalf;
  static constexpr int kMaxBlock = 1024;  // max input block per process() call

  static double sinc(double x) {
    if (std::fabs(x) < 1e-9) return 1.0;
    const double px = 3.14159265358979323846 * x;
    return std::sin(px) / px;
  }
  // Lanczos window of width kHalf over the *unscaled* distance.
  static double lanczos(double d) {
    if (std::fabs(d) >= kHalf) return 0.0;
    return sinc(d / kHalf);
  }

  uint32_t inRate_, outRate_;
  double ratio_, cutoff_;
  double phase_ = 0.0;
  std::vector<float> carry_;
  std::vector<float> work_;
};

}  // namespace aura::audio

#endif  // AURA_AUDIO_RESAMPLER_H
