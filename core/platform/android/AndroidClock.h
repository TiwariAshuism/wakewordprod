// PROJECT AURA — core/platform/android/AndroidClock.h
// IClock implementation for Android (Row 0, platform/android — allowed to use OS
// headers). Wait-free; safe on the Audio/Inference hot path.
#ifndef AURA_PLATFORM_ANDROID_ANDROIDCLOCK_H
#define AURA_PLATFORM_ANDROID_ANDROIDCLOCK_H

#include <ctime>

#include "core/platform/IClock.h"

namespace aura::platform::android {

class AndroidClock final : public IClock {
 public:
  uint64_t nowMonotonicNanos() const override {
    timespec ts{};
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return static_cast<uint64_t>(ts.tv_sec) * 1000000000ull + static_cast<uint64_t>(ts.tv_nsec);
  }
  uint64_t nowWallClockUnixMillis() const override {
    timespec ts{};
    clock_gettime(CLOCK_REALTIME, &ts);
    return static_cast<uint64_t>(ts.tv_sec) * 1000ull + static_cast<uint64_t>(ts.tv_nsec) / 1000000ull;
  }
};

}  // namespace aura::platform::android

#endif  // AURA_PLATFORM_ANDROID_ANDROIDCLOCK_H
