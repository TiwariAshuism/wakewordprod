// PROJECT AURA — core/platform/android/AndroidPowerManager.h
// Minimal IPowerManager for v0: always reports kActive. The real Power Manager
// module (core/power, Stage 7 §3.16) is OUT OF SCOPE — flagged in REPORT.md. This
// exists only because IPlatform mandates a powerManager() accessor.
#ifndef AURA_PLATFORM_ANDROID_ANDROIDPOWERMANAGER_H
#define AURA_PLATFORM_ANDROID_ANDROIDPOWERMANAGER_H

#include "core/platform/IPowerManager.h"

namespace aura::platform::android {

class AndroidPowerManager final : public IPowerManager {
 public:
  PowerState currentState() const override { return PowerState::kActive; }
  void onPowerStateChanged(std::function<void(PowerState)>) override { /* v0: never fires */ }
};

}  // namespace aura::platform::android

#endif  // AURA_PLATFORM_ANDROID_ANDROIDPOWERMANAGER_H
