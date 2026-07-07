// PROJECT AURA — core/runtime/tests/streaming_window_test.cpp
//
// Proves the streaming feature-window accumulator (D2):
//   1. FIFO ordering — oldest frames fall off the front, newest lands at the end.
//   2. The [windowFrames, nMels] view equals exactly the last `windowFrames` frames.
//   3. push() is O(1) in window size — constant per-push work, no full-window recompute.
#include <cstdint>
#include <cstring>
#include <vector>

#include "core/runtime/StreamingWindow.h"
#include "tests/support/test_framework.h"

using aura::runtime::StreamingWindow;

namespace {
// Push one frame whose every mel bin holds `value`, so a frame is identifiable by a
// single scalar. Returns nothing; the buffer is local to the call.
void pushValue(StreamingWindow& w, float value) {
  std::vector<float> frame(static_cast<size_t>(w.nMels()), value);
  w.push(frame.data());
}

// True iff every one of the frame's mel bins equals `value`.
bool frameAll(const StreamingWindow& w, int i, float value) {
  const float* f = w.frame(i);
  for (int j = 0; j < w.nMels(); ++j)
    if (f[j] != value) return false;
  return true;
}
}  // namespace

// After pushing more frames than the window holds, the view is exactly the last
// `windowFrames` frames, in temporal order with the newest at the end.
TEST(StreamingWindow, FifoOrderingViewEqualsLastN) {
  const int W = 100, M = 40;
  StreamingWindow w(W, M);
  const int total = 250;
  for (int k = 0; k < total; ++k) pushValue(w, static_cast<float>(k));

  EXPECT_TRUE(w.full());
  EXPECT_EQ(w.filled(), W);
  // Newest frame (k = 249) sits at the last view slot; oldest surviving is k = 150.
  EXPECT_TRUE(frameAll(w, W - 1, static_cast<float>(total - 1)));  // 249
  EXPECT_TRUE(frameAll(w, 0, static_cast<float>(total - W)));      // 150
  // Every slot matches its expected FIFO value, and the view is genuinely contiguous.
  const float* v = w.view();
  bool contiguousOk = true;
  for (int i = 0; i < W; ++i) {
    const float expected = static_cast<float>(total - W + i);  // 150..249
    if (!frameAll(w, i, expected)) contiguousOk = false;
    for (int j = 0; j < M; ++j)
      if (v[static_cast<size_t>(i) * M + j] != expected) contiguousOk = false;
  }
  EXPECT_TRUE(contiguousOk);
}

// Before the window fills, the view carries a zero pre-roll with the real frames
// packed against the newest (last) slot — matching the detector's window layout.
TEST(StreamingWindow, ZeroPrerollBeforeFull) {
  const int W = 100, M = 40;
  StreamingWindow w(W, M);
  const int pushed = 30;
  for (int k = 0; k < pushed; ++k) pushValue(w, static_cast<float>(k + 1));  // 1..30, nonzero

  EXPECT_FALSE(w.full());
  EXPECT_EQ(w.filled(), pushed);
  EXPECT_TRUE(frameAll(w, W - 1, static_cast<float>(pushed)));       // newest (30) at end
  EXPECT_TRUE(frameAll(w, W - pushed, 1.0f));                        // oldest real frame
  EXPECT_TRUE(frameAll(w, W - pushed - 1, 0.0f));                    // pre-roll is zero
  EXPECT_TRUE(frameAll(w, 0, 0.0f));
}

// Cross-check the view against an independent naive shift-buffer reference, so the
// ring's answer is validated against a known-good FIFO for a wrapped, partially-full,
// and full history.
TEST(StreamingWindow, MatchesNaiveReference) {
  const int W = 16, M = 4;
  StreamingWindow w(W, M);
  std::vector<float> ref(static_cast<size_t>(W) * M, 0.0f);  // naive last-W buffer

  for (int k = 0; k < 55; ++k) {
    const float val = static_cast<float>(k * 3 + 1);
    pushValue(w, val);
    // naive: shift everything one frame toward the front, append newest at the end.
    std::memmove(ref.data(), ref.data() + M, (ref.size() - M) * sizeof(float));
    for (int j = 0; j < M; ++j) ref[ref.size() - M + j] = val;

    const float* v = w.view();
    bool eq = true;
    for (size_t n = 0; n < ref.size(); ++n)
      if (v[n] != ref[n]) eq = false;
    EXPECT_TRUE(eq);
  }
}

// O(1) push: per-push work is a fixed two-row copy independent of window size. Two
// windows of very different capacities do the SAME total copy work for the same number
// of pushes. A naive shift-by-one buffer would instead copy ~windowFrames rows/push,
// so its total would scale with capacity — this asserts that does NOT happen.
TEST(StreamingWindow, PushIsConstantWorkIndependentOfCapacity) {
  const int M = 40, pushes = 500;
  StreamingWindow small(100, M);
  StreamingWindow large(5000, M);
  for (int k = 0; k < pushes; ++k) {
    pushValue(small, static_cast<float>(k));
    pushValue(large, static_cast<float>(k));
  }
  // Exactly two rows copied per push, for both — independent of windowFrames.
  EXPECT_EQ(small.pushRowCopies(), static_cast<uint64_t>(2) * pushes);
  EXPECT_EQ(large.pushRowCopies(), static_cast<uint64_t>(2) * pushes);
  EXPECT_EQ(small.pushRowCopies(), large.pushRowCopies());
}

// reset() returns the accumulator to its constructed state (zeroed view, empty, and
// the work counter cleared) so an instance can be reused across utterances.
TEST(StreamingWindow, ResetClearsState) {
  const int W = 8, M = 4;
  StreamingWindow w(W, M);
  for (int k = 0; k < 20; ++k) pushValue(w, static_cast<float>(k + 1));
  EXPECT_TRUE(w.full());
  w.reset();
  EXPECT_FALSE(w.full());
  EXPECT_EQ(w.filled(), 0);
  EXPECT_EQ(w.pushRowCopies(), static_cast<uint64_t>(0));
  bool allZero = true;
  for (int i = 0; i < W; ++i)
    if (!frameAll(w, i, 0.0f)) allZero = false;
  EXPECT_TRUE(allZero);
}
