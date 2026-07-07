// PROJECT AURA — core/features/Fft.h
//
// Compact iterative radix-2 FFT (real input) used by log-Mel extraction. This is
// a self-contained placeholder for the production KissFFT / Accelerate backend
// named in addendum §3 — flagged in REPORT.md. Header-only generic utility
// (permitted, Stage 7 §16). Buffers are pre-sized at construction; transform() is
// allocation-free (Audio-thread hot path).
#ifndef AURA_FEATURES_FFT_H
#define AURA_FEATURES_FFT_H

#include <cmath>
#include <cstddef>
#include <vector>

namespace aura::features {

class RealFft {
 public:
  explicit RealFft(size_t size) : n_(size) {
    re_.assign(n_, 0.0f);
    im_.assign(n_, 0.0f);
    // Precompute bit-reversal permutation and twiddles.
    bitrev_.assign(n_, 0);
    size_t bits = 0;
    while ((size_t{1} << bits) < n_) ++bits;
    for (size_t i = 0; i < n_; ++i) {
      size_t x = i, r = 0;
      for (size_t b = 0; b < bits; ++b) {
        r = (r << 1) | (x & 1);
        x >>= 1;
      }
      bitrev_[i] = r;
    }
  }

  size_t size() const { return n_; }

  // Compute the power spectrum |X[k]|^2 for k in [0, n/2], writing n/2+1 values
  // into `powerOut`. `input` holds n real (already windowed, zero-padded) samples.
  void powerSpectrum(const float* input, float* powerOut) {
    for (size_t i = 0; i < n_; ++i) {
      re_[bitrev_[i]] = input[i];
      im_[bitrev_[i]] = 0.0f;
    }
    for (size_t len = 2; len <= n_; len <<= 1) {
      const float ang = -2.0f * kPi / static_cast<float>(len);
      const float wlenRe = std::cos(ang);
      const float wlenIm = std::sin(ang);
      for (size_t i = 0; i < n_; i += len) {
        float wRe = 1.0f, wIm = 0.0f;
        for (size_t j = 0; j < len / 2; ++j) {
          const size_t a = i + j;
          const size_t b = i + j + len / 2;
          const float uRe = re_[a], uIm = im_[a];
          const float vRe = re_[b] * wRe - im_[b] * wIm;
          const float vIm = re_[b] * wIm + im_[b] * wRe;
          re_[a] = uRe + vRe;
          im_[a] = uIm + vIm;
          re_[b] = uRe - vRe;
          im_[b] = uIm - vIm;
          const float nwRe = wRe * wlenRe - wIm * wlenIm;
          wIm = wRe * wlenIm + wIm * wlenRe;
          wRe = nwRe;
        }
      }
    }
    const size_t half = n_ / 2;
    for (size_t k = 0; k <= half; ++k) {
      powerOut[k] = re_[k] * re_[k] + im_[k] * im_[k];
    }
  }

 private:
  static constexpr float kPi = 3.14159265358979323846f;
  size_t n_;
  std::vector<size_t> bitrev_;
  std::vector<float> re_, im_;
};

}  // namespace aura::features

#endif  // AURA_FEATURES_FFT_H
