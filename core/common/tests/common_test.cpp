// PROJECT AURA — core/common/tests/common_test.cpp
#include "core/common/result.h"
#include "core/common/ring_buffer.h"
#include "core/common/tensor.h"
#include "tests/support/test_framework.h"

using namespace aura::common;

TEST(Result, OkAndError) {
  Result<int> ok = 42;
  EXPECT_TRUE(static_cast<bool>(ok));
  EXPECT_EQ(ok.value(), 42);

  Result<int> bad = Err(ErrorCode::kInvalidArgument, "nope");
  EXPECT_FALSE(static_cast<bool>(bad));
  EXPECT_EQ(bad.error().code, ErrorCode::kInvalidArgument);

  Result<void> vok;
  EXPECT_TRUE(static_cast<bool>(vok));
  Result<void> verr = Err(ErrorCode::kIoError, "io");
  EXPECT_FALSE(static_cast<bool>(verr));
}

TEST(Arena, BumpAndReset) {
  Arena a(1024);
  float* p = a.allocateFloats(10);
  EXPECT_TRUE(p != nullptr);
  EXPECT_GE(a.highWater(), 40u);
  // Exhaustion returns nullptr, never grows (Stage 7 §5).
  EXPECT_TRUE(a.allocate(1 << 20) == nullptr);
  a.reset();
  EXPECT_TRUE(a.allocateFloats(10) != nullptr);
}

TEST(RingBuffer, DropOldestBackpressure) {
  RingBuffer<int> rb(3, BackpressurePolicy::kDropOldest);
  for (int i = 0; i < 5; ++i) {
    int* w = rb.acquireWrite();
    *w = i;
    rb.commitWrite();
  }
  EXPECT_EQ(rb.size(), 3u);
  EXPECT_EQ(rb.dropCount(), 2u);
  int expect = 2;  // oldest two (0,1) dropped
  while (const int* p = rb.acquireRead()) {
    EXPECT_EQ(*p, expect++);
    rb.commitRead();
  }
}

TEST(RingBuffer, DropNewestReturnsNullWhenFull) {
  RingBuffer<int> rb(2, BackpressurePolicy::kDropNewest);
  EXPECT_TRUE(rb.acquireWrite() != nullptr); rb.commitWrite();
  EXPECT_TRUE(rb.acquireWrite() != nullptr); rb.commitWrite();
  EXPECT_TRUE(rb.acquireWrite() == nullptr);  // full
  EXPECT_EQ(rb.dropCount(), 1u);
}
