// PROJECT AURA — core/audio/PcmFrame.h
// Fixed-size raw-PCM ring-buffer slot (Stage 7 §5 pool #1). POD; filled in place.
#ifndef AURA_AUDIO_PCMFRAME_H
#define AURA_AUDIO_PCMFRAME_H

#include <cstddef>
#include <cstdint>

namespace aura::audio
{

  inline constexpr size_t kMaxPcmFrameSamples = 512; // >= one 10 ms block @16 kHz (160)

  // One capture block, converted to mono float32 in [-1, 1]. `count` samples valid.
  struct PcmFrame
  {
    float samples[kMaxPcmFrameSamples];
    size_t count = 0;
    uint64_t captureTimestampNanos = 0;
  };

} // namespace aura::audio

#endif // AURA_AUDIO_PCMFRAME_H
