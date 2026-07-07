// PROJECT AURA — core/platform/IPowerManager.h
//
// Responsibilities : query/notify OS power state (Stage 7 §3.1 public API).
// Dependencies     : none within core/ (Row 0).
// Thread ownership : queried on the Audio thread (power gating is latency-sensitive
//                    relative to the audio pipeline, Stage 7 §3.16); must be
//                    wait-free.
// Memory ownership : none.
//
// NOTE: core/power (the Power Manager *module*, §3.16) is OUT OF SCOPE for v0.
// This is the *platform* interface, which IPlatform mandates. The Android impl
// reports kActive unconditionally (flagged in REPORT.md).
#ifndef AURA_PLATFORM_IPOWERMANAGER_H
#define AURA_PLATFORM_IPOWERMANAGER_H

#include <cstdint>
#include <functional>

namespace aura::platform {

enum class PowerState : uint8_t { kActive = 0, kLowPower, kDeepSleep };

class IPowerManager {
 public:
  virtual ~IPowerManager() = default;
  virtual PowerState currentState() const = 0;
  // Handler invoked on a background/platform thread on power-state transitions.
  virtual void onPowerStateChanged(std::function<void(PowerState)> handler) = 0;
};

}  // namespace aura::platform

#endif  // AURA_PLATFORM_IPOWERMANAGER_H
