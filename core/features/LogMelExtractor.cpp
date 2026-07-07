// PROJECT AURA — core/features/LogMelExtractor.cpp
#include "core/features/LogMelExtractor.h"

#include <algorithm>
#include <cmath>

namespace aura::features {

namespace {
constexpr float kPi = 3.14159265358979323846f;
float hzToMel(float hz) { return 2595.0f * std::log10(1.0f + hz / 700.0f); }
float melToHz(float mel) { return 700.0f * (std::pow(10.0f, mel / 2595.0f) - 1.0f); }
}  // namespace

LogMelExtractor::LogMelExtractor(const config::FeatureConfig& cfg)
    : cfg_(cfg), fft_(static_cast<size_t>(cfg.fftSize)) {
  // Hann window over winLength.
  window_.resize(cfg_.winLength);
  for (int i = 0; i < cfg_.winLength; ++i) {
    window_[i] = 0.5f * (1.0f - std::cos(2.0f * kPi * static_cast<float>(i) /
                                         static_cast<float>(cfg_.winLength - 1)));
  }
  overlap_.assign(cfg_.winLength, 0.0f);
  fftInput_.assign(cfg_.fftSize, 0.0f);
  power_.assign(cfg_.fftSize / 2 + 1, 0.0f);
  melOut_.assign(cfg_.nMels, 0.0f);
  buildMelFilterbank();
}

void LogMelExtractor::buildMelFilterbank() {
  const int nBins = cfg_.fftSize / 2 + 1;
  const float melMin = hzToMel(cfg_.melFmin);
  const float melMax = hzToMel(cfg_.melFmax);
  // nMels+2 edge points, triangular filters between consecutive triples.
  std::vector<float> edgeHz(cfg_.nMels + 2);
  for (int i = 0; i < cfg_.nMels + 2; ++i) {
    const float mel = melMin + (melMax - melMin) * static_cast<float>(i) /
                                   static_cast<float>(cfg_.nMels + 1);
    edgeHz[i] = melToHz(mel);
  }
  auto hzToBin = [&](float hz) {
    return hz * static_cast<float>(cfg_.fftSize) / static_cast<float>(cfg_.sampleRate);
  };

  melStart_.assign(cfg_.nMels, 0);
  melWeights_.assign(cfg_.nMels, {});
  for (int m = 0; m < cfg_.nMels; ++m) {
    const float lo = hzToBin(edgeHz[m]);
    const float ctr = hzToBin(edgeHz[m + 1]);
    const float hi = hzToBin(edgeHz[m + 2]);
    const int binLo = std::max(0, static_cast<int>(std::floor(lo)));
    const int binHi = std::min(nBins - 1, static_cast<int>(std::ceil(hi)));
    melStart_[m] = binLo;
    for (int k = binLo; k <= binHi; ++k) {
      float w = 0.0f;
      const float kf = static_cast<float>(k);
      if (kf >= lo && kf <= ctr && ctr > lo) w = (kf - lo) / (ctr - lo);
      else if (kf > ctr && kf <= hi && hi > ctr) w = (hi - kf) / (hi - ctr);
      melWeights_[m].push_back(std::max(0.0f, w));
    }
  }
}

void LogMelExtractor::reset() {
  std::fill(overlap_.begin(), overlap_.end(), 0.0f);
  filled_ = 0;
}

void LogMelExtractor::process(const float* samples, size_t n, const FrameCallback& onFrame) {
  const size_t win = static_cast<size_t>(cfg_.winLength);
  const size_t hop = static_cast<size_t>(cfg_.hopLength);
  size_t idx = 0;
  while (idx < n) {
    // Append into the analysis buffer up to a full window.
    const size_t take = std::min(win - filled_, n - idx);
    std::copy(samples + idx, samples + idx + take, overlap_.begin() + filled_);
    filled_ += take;
    idx += take;
    if (filled_ == win) {
      computeFrameFromWindow(onFrame);
      // Slide by hop: drop the first `hop` samples, keep the rest for overlap.
      std::copy(overlap_.begin() + hop, overlap_.end(), overlap_.begin());
      filled_ = win - hop;
    }
  }
}

void LogMelExtractor::computeFrameFromWindow(const FrameCallback& onFrame) {
  // Window + zero-pad into fftInput_.
  for (int i = 0; i < cfg_.fftSize; ++i) {
    fftInput_[i] = (i < cfg_.winLength) ? overlap_[i] * window_[i] : 0.0f;
  }
  fft_.powerSpectrum(fftInput_.data(), power_.data());
  // Mel projection + log compression.
  for (int m = 0; m < cfg_.nMels; ++m) {
    float acc = 0.0f;
    const int start = melStart_[m];
    const auto& w = melWeights_[m];
    for (size_t j = 0; j < w.size(); ++j) acc += w[j] * power_[start + static_cast<int>(j)];
    melOut_[m] = cfg_.logMel ? std::log(acc + 1e-6f) : acc;
  }
  onFrame(melOut_.data(), cfg_.nMels);
}

}  // namespace aura::features
