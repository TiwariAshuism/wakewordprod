// PROJECT AURA — core/vad/VadGate.h
// Debounced boolean gate over an IVad probability, per VadConfig (minSpeechFrames
// to open, hangoverFrames to close). Owns no model — wraps whichever IVad is
// injected. Allocation-free.
#ifndef AURA_VAD_VADGATE_H
#define AURA_VAD_VADGATE_H

#include "core/config/Config.h"
#include "core/vad/IVad.h"

namespace aura::vad {

class VadGate {
 public:
  VadGate(IVad& vad, const config::VadConfig& cfg) : vad_(vad), cfg_(cfg) {}

  // Returns true while the speech gate is open for this frame.
  bool process(const float* samples, size_t n) {
    const float p = vad_.process(samples, n);
    if (p >= cfg_.speechThreshold) {
      if (consecutive_ < cfg_.minSpeechFrames) ++consecutive_;
      hangover_ = cfg_.hangoverFrames;
    } else {
      consecutive_ = 0;
      if (hangover_ > 0) --hangover_;
    }
    open_ = (consecutive_ >= cfg_.minSpeechFrames) || (hangover_ > 0);
    return open_;
  }

  bool isOpen() const { return open_; }
  void reset() {
    vad_.reset();
    consecutive_ = 0;
    hangover_ = 0;
    open_ = false;
  }

 private:
  IVad& vad_;
  config::VadConfig cfg_;
  int consecutive_ = 0;
  int hangover_ = 0;
  bool open_ = false;
};

}  // namespace aura::vad

#endif  // AURA_VAD_VADGATE_H
