// PROJECT AURA — core/platform/IAudioInput.h
//
// Responsibilities : platform microphone capture (Stage 7 §3.1/§4).
// Dependencies     : core/common (value types) only (Row 0).
// Thread ownership : FrameCallback runs in the platform capture-callback context
//                    (ISR-equivalent): lock-free, allocation-free ONLY. start()
//                    fails fast on unsupported format; resampling is core/audio/'s
//                    job, not the platform's (verbatim Stage 7 §4 contract).
// Memory ownership : owns the raw capture buffer only until the callback hands it
//                    off; the AudioFrameView passed to the callback must not be
//                    stored beyond the callback (Stage 9 §3).
// Lifecycle        : owned by IPlatform; start()/stop() bracket capture.
#ifndef AURA_PLATFORM_IAUDIOINPUT_H
#define AURA_PLATFORM_IAUDIOINPUT_H

#include <cstdint>
#include <functional>

#include "core/common/audio_types.h"
#include "core/common/result.h"

namespace aura::platform {

// Exact signature per Stage 7 §4.
class IAudioInput {
 public:
  virtual ~IAudioInput() = default;

  using FrameCallback =
      std::function<void(const common::AudioFrameView& frame, uint64_t captureTimestampNanos)>;

  virtual common::Result<void> start(const common::AudioFormat& requestedFormat,
                                     FrameCallback cb) = 0;
  virtual common::Result<void> stop() = 0;
  virtual common::Result<common::AudioFormat> currentFormat() const = 0;
  virtual void onDeviceChanged(std::function<void(const common::DeviceChangeEvent&)> handler) = 0;
};

}  // namespace aura::platform

#endif  // AURA_PLATFORM_IAUDIOINPUT_H
