// PROJECT AURA — core/platform/android/AndroidPlatform.h
// IPlatform aggregate for Android — owns the concrete OS-primitive singletons.
#ifndef AURA_PLATFORM_ANDROID_ANDROIDPLATFORM_H
#define AURA_PLATFORM_ANDROID_ANDROIDPLATFORM_H

#include <filesystem>

#include "core/platform/IPlatform.h"
#include "core/platform/android/AndroidClock.h"
#include "core/platform/android/AndroidPowerManager.h"
#include "core/platform/android/AndroidStorage.h"
#include "core/platform/android/OboeAudioInput.h"

namespace aura::platform::android {

class AndroidPlatform final : public IPlatform {
 public:
  explicit AndroidPlatform(std::filesystem::path filesDir)
      : storage_(std::move(filesDir)), audioInput_(clock_) {}

  IAudioInput& audioInput() override { return audioInput_; }
  IClock& clock() override { return clock_; }
  IStorage& storage() override { return storage_; }
  IPowerManager& powerManager() override { return power_; }

 private:
  AndroidClock clock_;
  AndroidStorage storage_;
  AndroidPowerManager power_;
  OboeAudioInput audioInput_;  // constructed after clock_ (declared after; see ctor)
};

}  // namespace aura::platform::android

#endif  // AURA_PLATFORM_ANDROID_ANDROIDPLATFORM_H
