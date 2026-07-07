// PROJECT AURA — core/common/tests/lockorder_test.cpp
#include "core/common/lockorder.h"
#include "tests/support/test_framework.h"

using namespace aura::common;

namespace {
int g_violations = 0;
LockLevel g_lastAttempted{}, g_lastHeld{};
void recordViolation(LockLevel a, LockLevel h) {
  ++g_violations;
  g_lastAttempted = a;
  g_lastHeld = h;
}
}  // namespace

TEST(LockOrder, IncreasingOrderIsClean) {
  g_violations = 0;
  SetLockOrderViolationHandler(&recordViolation);
  OrderedMutex a(LockLevel::kAudioRingSlot);   // 1
  OrderedMutex b(LockLevel::kModelHandle);     // 2
  {
    OrderedLock la(a);  // hold 1
    OrderedLock lb(b);  // acquire 2 while holding 1 — OK (increasing)
  }
  EXPECT_EQ(g_violations, 0);
  SetLockOrderViolationHandler(nullptr);  // restore default (abort)
}

TEST(LockOrder, ReversedOrderIsFlagged) {
  g_violations = 0;
  SetLockOrderViolationHandler(&recordViolation);
  OrderedMutex a(LockLevel::kAudioRingSlot);   // 1
  OrderedMutex c(LockLevel::kConfigPublish);   // 3
  {
    OrderedLock lc(c);  // hold 3
    OrderedLock la(a);  // acquire 1 while holding 3 — VIOLATION
  }
#if defined(AURA_ENABLE_DEBUG_LOCK_INSTRUMENTATION)
  EXPECT_EQ(g_violations, 1);
  EXPECT_EQ(g_lastAttempted, LockLevel::kAudioRingSlot);
  EXPECT_EQ(g_lastHeld, LockLevel::kConfigPublish);
#endif
  SetLockOrderViolationHandler(nullptr);
}
