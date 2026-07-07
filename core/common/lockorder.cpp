// PROJECT AURA — core/common/lockorder.cpp
#include "core/common/lockorder.h"

#include <cstdio>
#include <cstdlib>

namespace aura::common {

namespace {

void defaultHandler(LockLevel attempted, LockLevel held) {
  std::fprintf(stderr,
               "[AURA][FATAL] lock-order violation: acquiring level %d while holding %d "
               "(Stage 7 §6 — acquire in increasing order)\n",
               static_cast<int>(attempted), static_cast<int>(held));
  std::abort();
}

LockOrderViolationHandler g_handler = &defaultHandler;

#if defined(AURA_ENABLE_DEBUG_LOCK_INSTRUMENTATION)
constexpr int kMaxHeld = 16;
thread_local int t_held[kMaxHeld];
thread_local int t_count = 0;
#endif

}  // namespace

void SetLockOrderViolationHandler(LockOrderViolationHandler handler) {
  g_handler = handler ? handler : &defaultHandler;
}

void OrderedMutex::lock() {
#if defined(AURA_ENABLE_DEBUG_LOCK_INSTRUMENTATION)
  const int lvl = static_cast<int>(level_);
  // Must be strictly greater than every lock currently held on this thread.
  for (int i = 0; i < t_count; ++i) {
    if (t_held[i] >= lvl) {
      g_handler(level_, static_cast<LockLevel>(t_held[i]));
      break;  // handler may return (tests); still record + proceed to acquire
    }
  }
  if (t_count < kMaxHeld) t_held[t_count++] = lvl;
#endif
  mutex_.lock();
}

void OrderedMutex::unlock() {
  mutex_.unlock();
#if defined(AURA_ENABLE_DEBUG_LOCK_INSTRUMENTATION)
  const int lvl = static_cast<int>(level_);
  // Remove the most recent matching level from the held set.
  for (int i = t_count - 1; i >= 0; --i) {
    if (t_held[i] == lvl) {
      for (int j = i; j < t_count - 1; ++j) t_held[j] = t_held[j + 1];
      --t_count;
      break;
    }
  }
#endif
}

}  // namespace aura::common
