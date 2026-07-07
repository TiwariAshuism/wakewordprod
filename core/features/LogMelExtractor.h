// PROJECT AURA — core/features/LogMelExtractor.h
//
// Responsibilities : framing/windowing -> STFT -> log-Mel (Stage 7 §3.8; ADR-003
//                    log-Mel default). Produces one FeatureFrame per hop.
// Dependencies     : core/dsp (Row 4). Runs on the Audio thread, in-line.
// Memory ownership : fixed-size scratch buffers sized from Config at construction;
//                    process() is allocation-free (Stage 7 §5).
// Lifecycle        : stateless per-frame beyond the overlap ring for windowing.
//
// The mel/window/FFT parameters MUST match the placeholder KWS model's training
// front-end (Stage 7 M3 integration risk) — see tools/convert_kws_model.py.
#ifndef AURA_FEATURES_LOGMELEXTRACTOR_H
#define AURA_FEATURES_LOGMELEXTRACTOR_H

#include <functional>
#include <vector>

#include "core/config/Config.h"
#include "core/features/Fft.h"

namespace aura::features {

class LogMelExtractor {
 public:
  explicit LogMelExtractor(const config::FeatureConfig& cfg);

  // Feed a block of mono float samples. For every complete hop, invokes onFrame
  // with a pointer to nMels log-Mel values (valid only during the callback).
  // Allocation-free after construction.
  using FrameCallback = std::function<void(const float* mel, int nMels)>;
  void process(const float* samples, size_t n, const FrameCallback& onFrame);

  int nMels() const { return cfg_.nMels; }
  void reset();

 private:
  void computeFrameFromWindow(const FrameCallback& onFrame);
  void buildMelFilterbank();

  config::FeatureConfig cfg_;
  RealFft fft_;

  std::vector<float> window_;        // Hann window (winLength)
  std::vector<float> overlap_;       // rolling analysis buffer (winLength)
  size_t filled_ = 0;                // valid samples currently in overlap_
  std::vector<float> fftInput_;      // fftSize, zero-padded windowed frame
  std::vector<float> power_;         // fftSize/2 + 1 power bins
  std::vector<float> melOut_;        // nMels

  // Mel filterbank stored as (start bin, weights) per mel — sparse, alloc-free at
  // runtime.
  std::vector<int> melStart_;
  std::vector<std::vector<float>> melWeights_;
};

}  // namespace aura::features

#endif  // AURA_FEATURES_LOGMELEXTRACTOR_H
