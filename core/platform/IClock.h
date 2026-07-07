// PROJECT AURA — core/platform/IClock.h
//
// Responsibilities : monotonic + wall-clock time source (Stage 7 §3.1/§4).
// Dependencies     : none within core/ (Row 0).
// Thread ownership : callable from any thread; implementations must be thread-safe
//                    and wait-free (queried on the Audio/Inference hot path for
//                    capture/latency timestamps).
// Memory ownership : none.
// Lifecycle        : one instance for the engine lifetime, owned by IPlatform.
#ifndef AURA_PLATFORM_ICLOCK_H
#define AURA_PLATFORM_ICLOCK_H

#include <cstdint>

namespace aura::platform {

// Exact signature per Stage 7 §4.
class IClock {
 public:
  virtual ~IClock() = default;
  // Monotonic clock in nanoseconds — for latency/interval math. Wait-free.
  virtual uint64_t nowMonotonicNanos() const = 0;
  // Wall-clock in Unix epoch milliseconds — for log/telemetry timestamps.
  virtual uint64_t nowWallClockUnixMillis() const = 0;
};

}  // namespace aura::platform

#endif  // AURA_PLATFORM_ICLOCK_H
