// PROJECT AURA — core/detect/tests/streaming_detector_test.cpp
//
// Proves the per-frame streaming decision policy mirrors the windowed detector:
//   - fires on a sustained high-score run (M consecutive positive FRAMES),
//   - does NOT fire below threshold,
//   - respects refractory (one spoken wake word => one detection, no double-fire),
//   - runs allocation-free on the hot path (guarded when instrumentation is built).
#include <vector>

#include "core/common/noalloc.h"
#include "core/detect/StreamingDetector.h"
#include "tests/support/test_framework.h"

using namespace aura;

namespace {

// Deterministic stateful-scorer double. The streaming ONNX model is exercised
// on-device; here the fake treats mel[0] as the per-frame wake probability the model
// would emit, so a test scripts the score stream directly. `calls` witnesses that the
// stateful model is advanced exactly once per frame (including during refractory).
struct FakeStreamingScorer final : detect::IStreamingScorer {
  int calls = 0;
  float scoreFrame(const float* mel, int n) override {
    ++calls;
    (void)n;
    return mel[0];  // frame's wake probability in [0,1]
  }
};

// Feed one frame whose scripted probability is `p`.
void pushProb(detect::StreamingDetector& det, float p, uint64_t ts, int nMels = 8) {
  float mel[8];
  for (int i = 0; i < nMels; ++i) mel[i] = p;
  det.pushFrame(mel, nMels, ts);
}

config::DetectConfig baseCfg() {
  config::DetectConfig dc;
  dc.stage1Threshold = 0.5f;
  dc.stage1ConsecutiveWindows = 3;  // here: M consecutive positive FRAMES
  dc.refractoryFrames = 100;
  return dc;
}

}  // namespace

// Fires exactly once on a sustained high-score run of M consecutive frames; the
// refractory then suppresses the rest of the run (one wake word => one detection).
TEST(StreamingDetect, FiresOnSustainedHighRun) {
  config::DetectConfig dc = baseCfg();  // M=3, refractory=100
  FakeStreamingScorer scorer;
  detect::StreamingDetector det(scorer, dc, /*wakeWordIndex=*/0);

  int count = 0;
  common::DetectionEvent last{};
  det.setOnDetection([&](const common::DetectionEvent& e) { ++count; last = e; });

  for (int i = 0; i < 20; ++i) pushProb(det, 0.9f, i);

  EXPECT_EQ(count, 1);
  EXPECT_EQ(last.outcome, common::DetectionOutcome::kConfirmed);
  EXPECT_TRUE(last.correlationId.valid());
  EXPECT_GE(last.confidence, dc.stage1Threshold);
  EXPECT_EQ(scorer.calls, 20);  // stateful model advanced once per frame, refractory included
}

// M consecutive positives are required: a run of only M-1 highs never fires.
TEST(StreamingDetect, RequiresMConsecutiveFrames) {
  config::DetectConfig dc = baseCfg();  // M=3
  FakeStreamingScorer scorer;
  detect::StreamingDetector det(scorer, dc, 0);
  int count = 0;
  det.setOnDetection([&](const common::DetectionEvent&) { ++count; });

  // Two high frames, then a low frame breaks the run, repeatedly — never 3 in a row.
  for (int i = 0; i < 30; i += 3) {
    pushProb(det, 0.9f, i);
    pushProb(det, 0.9f, i + 1);
    pushProb(det, 0.1f, i + 2);
  }
  EXPECT_EQ(count, 0);
}

// Does NOT fire when every frame is below threshold, however long the stream.
TEST(StreamingDetect, NoFireBelowThreshold) {
  config::DetectConfig dc = baseCfg();
  FakeStreamingScorer scorer;
  detect::StreamingDetector det(scorer, dc, 0);
  int count = 0;
  det.setOnDetection([&](const common::DetectionEvent&) { ++count; });

  for (int i = 0; i < 50; ++i) pushProb(det, 0.1f, i);  // all < 0.5
  EXPECT_EQ(count, 0);
}

// Refractory prevents a double-fire: with M=1 a long high run would fire every frame,
// but refractory collapses it to a single detection within the suppression window.
TEST(StreamingDetect, RespectsRefractoryNoDoubleFire) {
  config::DetectConfig dc = baseCfg();
  dc.stage1ConsecutiveWindows = 1;  // fire on the first positive frame
  dc.refractoryFrames = 100;        // longer than the run below
  FakeStreamingScorer scorer;
  detect::StreamingDetector det(scorer, dc, 0);
  int count = 0;
  det.setOnDetection([&](const common::DetectionEvent&) { ++count; });

  for (int i = 0; i < 50; ++i) pushProb(det, 0.9f, i);
  EXPECT_EQ(count, 1);  // 49 subsequent highs suppressed by refractory
}

// Refractory is a finite window, not a permanent latch: once it elapses the detector
// re-arms and a fresh high frame fires again (re-triggerable, still no double inside).
TEST(StreamingDetect, ReArmsAfterRefractoryElapses) {
  config::DetectConfig dc = baseCfg();
  dc.stage1ConsecutiveWindows = 1;
  dc.refractoryFrames = 5;
  FakeStreamingScorer scorer;
  detect::StreamingDetector det(scorer, dc, 0);
  int count = 0;
  det.setOnDetection([&](const common::DetectionEvent&) { ++count; });

  // Frame 0 fires (refractory=5). Frames 1..5 suppressed (refractory 5->0). Frame 6
  // fires again. Total: 2 detections across 7 frames.
  for (int i = 0; i < 7; ++i) pushProb(det, 0.9f, i);
  EXPECT_EQ(count, 2);
}

// Hot path is allocation-free: run a below-threshold stream entirely inside a
// ScopedNoAllocGuard. When AURA_ENABLE_DEBUG_LOCK_INSTRUMENTATION is built, any
// new/malloc on this path aborts the process; reaching the assertion proves no-alloc.
TEST(StreamingDetect, NoAllocOnHotPath) {
  config::DetectConfig dc = baseCfg();
  FakeStreamingScorer scorer;
  detect::StreamingDetector det(scorer, dc, 0);
  int count = 0;
  det.setOnDetection([&](const common::DetectionEvent&) { ++count; });

  {
    common::ScopedNoAllocGuard guard;  // any heap alloc under here aborts a debug build
    for (int i = 0; i < 200; ++i) pushProb(det, 0.2f, i);  // below threshold => no fire path
  }
  EXPECT_EQ(count, 0);
  EXPECT_EQ(scorer.calls, 200);
}
