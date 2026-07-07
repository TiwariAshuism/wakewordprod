// PROJECT AURA — core/dsp/IDspStage.h
//
// Responsibilities : one time-domain DSP stage operating in place on a mono float
//                    block (Stage 7 §3.7; addendum §3 ordering AGC -> AEC -> NS).
// Dependencies     : core/audio (Row 3). Executes on the Audio thread, in-line,
//                    zero heap allocation per frame (Stage 7 §5).
#ifndef AURA_DSP_IDSPSTAGE_H
#define AURA_DSP_IDSPSTAGE_H

#include <cstddef>
#include <string_view>

#include "core/common/result.h"

namespace aura::dsp {

class IDspStage {
 public:
  virtual ~IDspStage() = default;
  // In-place processing. Must not allocate (Audio-thread hot path).
  virtual common::Result<void> process(float* samples, size_t n) = 0;
  virtual std::string_view name() const = 0;
};

}  // namespace aura::dsp

#endif  // AURA_DSP_IDSPSTAGE_H
