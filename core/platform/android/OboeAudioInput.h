// PROJECT AURA — core/platform/android/OboeAudioInput.h
//
// IAudioInput backed by Oboe (ADR-MicInput / Stage 9 §8.1). Oboe's data callback
// IS the ISR-equivalent capture context (Stage 7 §4): the onAudioReady body is
// lock-free and allocation-free and simply forwards a non-owning AudioFrameView to
// the registered FrameCallback (which moves it into core/audio's ring buffer).
//
// This is one of the ONLY files permitted to include a platform SDK header
// (<oboe/Oboe.h>) — Stage 7 §2.
#ifndef AURA_PLATFORM_ANDROID_OBOEAUDIOINPUT_H
#define AURA_PLATFORM_ANDROID_OBOEAUDIOINPUT_H

#include <oboe/Oboe.h>

#include <memory>

#include "core/platform/IAudioInput.h"
#include "core/platform/IClock.h"

namespace aura::platform::android {

class OboeAudioInput final : public IAudioInput,
                             public oboe::AudioStreamDataCallback,
                             public oboe::AudioStreamErrorCallback {
 public:
  explicit OboeAudioInput(IClock& clock) : clock_(clock) {}
  ~OboeAudioInput() override { (void)stop(); }

  common::Result<void> start(const common::AudioFormat& requestedFormat,
                             FrameCallback cb) override;
  common::Result<void> stop() override;
  common::Result<common::AudioFormat> currentFormat() const override;
  void onDeviceChanged(std::function<void(const common::DeviceChangeEvent&)> handler) override;

  // oboe::AudioStreamDataCallback
  oboe::DataCallbackResult onAudioReady(oboe::AudioStream* stream, void* audioData,
                                        int32_t numFrames) override;
  // oboe::AudioStreamErrorCallback
  void onErrorAfterClose(oboe::AudioStream* stream, oboe::Result error) override;

 private:
  IClock& clock_;
  std::shared_ptr<oboe::AudioStream> stream_;
  FrameCallback frameCallback_;
  std::function<void(const common::DeviceChangeEvent&)> deviceChangedHandler_;
  common::AudioFormat format_{};
};

}  // namespace aura::platform::android

#endif  // AURA_PLATFORM_ANDROID_OBOEAUDIOINPUT_H
