// PROJECT AURA — core/detect/tests/detect_test.cpp
#include <vector>

#include "core/detect/Stage1Detector.h"
#include "tests/support/FakeInferenceBackend.h"
#include "tests/support/test_framework.h"

using namespace aura;

namespace {
features::FeatureFrame makeFrame(int nMels, float value, bool speech, uint64_t ts) {
  features::FeatureFrame f;
  f.nMels = nMels;
  f.speech = speech;
  f.captureTimestampNanos = ts;
  for (int i = 0; i < nMels; ++i) f.mel[i] = value;
  return f;
}
}  // namespace

TEST(Detect, FiresOnceWithCorrelationId) {
  const int nMels = 8;
  config::DetectConfig dc;
  dc.stage1WindowFrames = 20;
  dc.stage1NumClasses = 4;         // match the FakeInferenceBackend below
  dc.stage1TargetClass = 1;        // (independent of the app's default hey-aura index)
  dc.stage1ConsecutiveWindows = 1;  // these tests exercise single-window cascade mechanics
  dc.stage1HopFrames = 5;
  // peak-based fake: mel value 2.0 => peak 2.0 > gate 0 => fire.
  test::FakeInferenceBackend fake(4, /*target=*/1, /*gate=*/0.0f);
  detect::Stage1Detector det(fake, dc, nMels, /*wakeWordIndex=*/0);

  int count = 0;
  common::DetectionEvent last{};
  det.setOnDetection([&](const common::DetectionEvent& e) {
    ++count;
    last = e;
  });

  for (int i = 0; i < 30; ++i) det.pushFeature(makeFrame(nMels, 2.0f, /*speech=*/true, i));

  EXPECT_EQ(count, 1);  // refractory suppresses re-fire
  EXPECT_EQ(last.outcome, common::DetectionOutcome::kConfirmed);
  EXPECT_TRUE(last.correlationId.valid());
  EXPECT_GE(last.confidence, dc.stage1Threshold);
}

TEST(Detect, NoFireWhenNoSpeech) {
  const int nMels = 8;
  config::DetectConfig dc;
  dc.stage1WindowFrames = 20;
  dc.stage1NumClasses = 4;         // match the FakeInferenceBackend below
  dc.stage1TargetClass = 1;        // (independent of the app's default hey-aura index)
  dc.stage1ConsecutiveWindows = 1;  // these tests exercise single-window cascade mechanics
  test::FakeInferenceBackend fake(4, 1, 0.0f);
  detect::Stage1Detector det(fake, dc, nMels, 0);
  int count = 0;
  det.setOnDetection([&](const common::DetectionEvent&) { ++count; });
  // High energy but VAD gate closed (speech=false) => detector never runs Stage-1.
  for (int i = 0; i < 40; ++i) det.pushFeature(makeFrame(nMels, 2.0f, /*speech=*/false, i));
  EXPECT_EQ(count, 0);
}

TEST(Detect, RejectsLowEnergyWindow) {
  const int nMels = 8;
  config::DetectConfig dc;
  dc.stage1WindowFrames = 20;
  dc.stage1NumClasses = 4;         // match the FakeInferenceBackend below
  dc.stage1TargetClass = 1;        // (independent of the app's default hey-aura index)
  dc.stage1ConsecutiveWindows = 1;  // these tests exercise single-window cascade mechanics
  test::FakeInferenceBackend fake(4, 1, 0.0f);  // needs peak > 0
  detect::Stage1Detector det(fake, dc, nMels, 0);
  int count = 0;
  det.setOnDetection([&](const common::DetectionEvent&) { ++count; });
  // Speech gate open but the window content is below the model's decision gate.
  for (int i = 0; i < 40; ++i) det.pushFeature(makeFrame(nMels, -5.0f, /*speech=*/true, i));
  EXPECT_EQ(count, 0);
}

// Posterior smoothing: with M=3, sustained speech accumulates 3 consecutive positive
// windows and fires exactly once (refractory suppresses the rest).
TEST(Detect, SmoothingFiresAfterConsecutiveWindows) {
  const int nMels = 8;
  config::DetectConfig dc;
  dc.stage1WindowFrames = 20;
  dc.stage1HopFrames = 5;
  dc.stage1NumClasses = 4;
  dc.stage1TargetClass = 1;
  dc.stage1ConsecutiveWindows = 3;
  dc.refractoryFrames = 200;
  test::FakeInferenceBackend fake(4, 1, 0.0f);
  detect::Stage1Detector det(fake, dc, nMels, 0);
  int count = 0;
  det.setOnDetection([&](const common::DetectionEvent&) { ++count; });
  for (int i = 0; i < 60; ++i) det.pushFeature(makeFrame(nMels, 2.0f, /*speech=*/true, i));
  EXPECT_EQ(count, 1);
}

// Two-stage cascade: Stage-1 triggers and the Stage-2 verifier AGREES -> confirmed.
TEST(Detect, Stage2ConfirmsWhenVerifierAgrees) {
  const int nMels = 8;
  config::DetectConfig dc;
  dc.stage1WindowFrames = 20;
  dc.stage1NumClasses = 4;
  dc.stage1TargetClass = 1;
  dc.stage1ConsecutiveWindows = 1;
  dc.stage2Enabled = true;
  dc.stage2NumClasses = 4;
  dc.stage2TargetClass = 1;
  dc.stage2Threshold = 0.5f;
  test::FakeInferenceBackend s1(4, 1, 0.0f);
  test::FakeInferenceBackend s2(4, 1, 0.0f);  // verifier fires on the same window
  detect::Stage1Detector det(s1, dc, nMels, 0, &s2);
  int count = 0;
  det.setOnDetection([&](const common::DetectionEvent&) { ++count; });
  for (int i = 0; i < 30; ++i) det.pushFeature(makeFrame(nMels, 2.0f, /*speech=*/true, i));
  EXPECT_EQ(count, 1);
}

// Two-stage cascade: Stage-1 triggers but the Stage-2 verifier DISAGREES -> suppressed.
TEST(Detect, Stage2RejectsWhenVerifierDisagrees) {
  const int nMels = 8;
  config::DetectConfig dc;
  dc.stage1WindowFrames = 20;
  dc.stage1NumClasses = 4;
  dc.stage1TargetClass = 1;
  dc.stage1ConsecutiveWindows = 1;
  dc.stage2Enabled = true;
  dc.stage2NumClasses = 4;
  dc.stage2TargetClass = 1;
  dc.stage2Threshold = 0.5f;
  test::FakeInferenceBackend s1(4, 1, 0.0f);
  test::FakeInferenceBackend s2(4, 1, 100.0f);  // gate 100 > peak 2.0 => verifier never fires
  detect::Stage1Detector det(s1, dc, nMels, 0, &s2);
  int count = 0;
  det.setOnDetection([&](const common::DetectionEvent&) { ++count; });
  for (int i = 0; i < 30; ++i) det.pushFeature(makeFrame(nMels, 2.0f, /*speech=*/true, i));
  EXPECT_EQ(count, 0);
}

// A very high consecutive requirement is never satisfied within the fed frames, so
// smoothing correctly suppresses firing even on sustained positive windows.
TEST(Detect, SmoothingSuppressesWhenConsecutiveNotMet) {
  const int nMels = 8;
  config::DetectConfig dc;
  dc.stage1WindowFrames = 20;
  dc.stage1HopFrames = 5;
  dc.stage1NumClasses = 4;
  dc.stage1TargetClass = 1;
  dc.stage1ConsecutiveWindows = 1000;  // impossibly high
  test::FakeInferenceBackend fake(4, 1, 0.0f);
  detect::Stage1Detector det(fake, dc, nMels, 0);
  int count = 0;
  det.setOnDetection([&](const common::DetectionEvent&) { ++count; });
  for (int i = 0; i < 60; ++i) det.pushFeature(makeFrame(nMels, 2.0f, /*speech=*/true, i));
  EXPECT_EQ(count, 0);
}
