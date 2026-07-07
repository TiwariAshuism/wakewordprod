// PROJECT AURA — core/common/lockorder.h
//
// Debug lock-order verification (Stage 7 §6 / Arch Finding 7). Every mutex carries a
// level from the global lock hierarchy; the instrumentation records the locks held per
// thread and flags acquiring a lower-or-equal-level lock while holding a higher one —
// the class of latent deadlock the hierarchy exists to prevent. Active only when
// AURA_ENABLE_DEBUG_LOCK_INSTRUMENTATION is defined (debug/CI); a plain mutex otherwise.
//
// Global hierarchy (Stage 7 §6), acquire in strictly INCREASING order:
//   1 Audio ring-buffer slot  2 ModelManager handle  3 Config publish
//   4 OTA state machine        5 Telemetry enqueue     6 Discovery peer table
#ifndef AURA_COMMON_LOCKORDER_H
#define AURA_COMMON_LOCKORDER_H

#include <mutex>

namespace aura::common {

enum class LockLevel : int {
  kAudioRingSlot = 1,
  kModelHandle = 2,
  kConfigPublish = 3,
  kOtaState = 4,
  kTelemetryEnqueue = 5,
  kDiscoveryPeerTable = 6,
};

// Called on a detected violation. Default aborts (debug builds fail loud, Stage 7 §6);
// tests may install a recording handler instead. Args: attempted level, offending
// already-held level.
using LockOrderViolationHandler = void (*)(LockLevel attempted, LockLevel held);
void SetLockOrderViolationHandler(LockOrderViolationHandler handler);

class OrderedMutex {
 public:
  explicit OrderedMutex(LockLevel level) : level_(level) {}
  OrderedMutex(const OrderedMutex&) = delete;
  OrderedMutex& operator=(const OrderedMutex&) = delete;

  void lock();
  void unlock();
  LockLevel level() const { return level_; }

 private:
  std::mutex mutex_;
  LockLevel level_;
};

// RAII, like std::lock_guard.
class OrderedLock {
 public:
  explicit OrderedLock(OrderedMutex& m) : m_(m) { m_.lock(); }
  ~OrderedLock() { m_.unlock(); }
  OrderedLock(const OrderedLock&) = delete;
  OrderedLock& operator=(const OrderedLock&) = delete;

 private:
  OrderedMutex& m_;
};

}  // namespace aura::common

#endif  // AURA_COMMON_LOCKORDER_H
