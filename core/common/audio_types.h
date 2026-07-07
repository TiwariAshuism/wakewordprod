// PROJECT AURA — core/common/audio_types.h
//
// Responsibilities : Audio value types crossing the platform/ <-> audio/ boundary
//                    (Stage 7 §4: AudioFrameView, AudioFormat, DeviceChangeEvent).
// Dependencies     : none (foundation).
// Thread ownership : AudioFrameView is a non-owning view produced in the platform
//                    capture callback (ISR-equivalent); it must NOT outlive that
//                    callback (Stage 9 §3: never store a raw pointer across an
//                    async boundary). audio/ copies/moves the samples into a
//                    ring-buffer slot before the callback returns.
// Memory ownership : views only; own nothing.
#ifndef AURA_COMMON_AUDIO_TYPES_H
#define AURA_COMMON_AUDIO_TYPES_H

#include <cstddef>
#include <cstdint>

namespace aura::common
{

  enum class SampleFormat : uint8_t
  {
    kInt16 = 0,
    kFloat32
  };

  // The format audio/ requests of the platform. Resampling to this rate is
  // core/audio/'s job, not the platform's (Stage 7 §4 comment on IAudioInput::start).
  struct AudioFormat
  {
    uint32_t sampleRate = 16000; // AURA front-end operates at 16 kHz
    uint8_t channels = 1;        // mono
    SampleFormat format = SampleFormat::kInt16;
  };

  // A non-owning, read-only view of one captured PCM frame block. Exactly one of
  // the two pointers is non-null, per `format`.
  struct AudioFrameView
  {
    const int16_t *i16 = nullptr;
    const float *f32 = nullptr;
    size_t frames = 0; // sample count per channel
    uint32_t sampleRate = 16000;
    uint8_t channels = 1;

    constexpr bool isFloat() const { return f32 != nullptr; }
  };

  enum class DeviceChangeKind : uint8_t
  {
    kDefaultChanged = 0,
    kDisconnected,
    kConnected
  };

  struct DeviceChangeEvent
  {
    DeviceChangeKind kind = DeviceChangeKind::kDefaultChanged;
  };

} // namespace aura::common

#endif // AURA_COMMON_AUDIO_TYPES_H
