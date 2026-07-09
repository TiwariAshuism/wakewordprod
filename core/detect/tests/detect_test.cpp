// PROJECT AURA — core/detect/tests/detect_test.cpp
#include <cmath>
#include <vector>

#include "core/config/Config.h"
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

// Build a rank-1 TensorView over `buf` (logits/probs) for the static scoreFromOutput.
common::TensorView logitsView(std::vector<float>& buf) {
  common::TensorView v;
  v.data = buf.data();
  v.rank = 1;
  v.shape[0] = static_cast<int64_t>(buf.size());
  return v;
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

// ---- Confidence calibration (Part B) ---------------------------------------------
// NOTE: this is posterior CONFIDENCE calibration, distinct from PTQ 'quantization
// calibration'. scoreFromOutput is the single point where it is applied.

// Identity calibration (method=none) leaves the score exactly at the raw softmax value.
TEST(Calibration, IdentityLeavesScoreUnchanged) {
  std::vector<float> logits = {0.0f, 2.0f};
  auto v = logitsView(logits);
  config::StageCalibration none{};  // kNone, a=1, b=0, T=1
  const float got = detect::Stage1Detector::scoreFromOutput(v, /*target=*/1, /*softmax=*/true, none);
  const float baseline = std::exp(2.0f) / (1.0f + std::exp(2.0f));  // softmax[1]
  EXPECT_NEAR(got, baseline, 1e-5);
}

// Temperature T>1 softens the softmax: confidence decreases monotonically as T grows.
TEST(Calibration, TemperatureLowersConfidenceMonotonically) {
  std::vector<float> logits = {0.0f, 2.0f};
  auto v = logitsView(logits);
  auto scoreAt = [&](float T) {
    config::StageCalibration c;
    c.method = config::StageCalibration::kTemperature;
    c.temperature = T;
    return detect::Stage1Detector::scoreFromOutput(v, 1, /*softmax=*/true, c);
  };
  const float t1 = scoreAt(1.0f), t2 = scoreAt(2.0f), t4 = scoreAt(4.0f);
  EXPECT_GT(t1, t2);
  EXPECT_GT(t2, t4);
  // Sanity: T=1 equals the identity/raw softmax value.
  EXPECT_NEAR(t1, std::exp(2.0f) / (1.0f + std::exp(2.0f)), 1e-5);
}

// Platt maps a known logit through sigmoid(a*z + b) to a known probability.
TEST(Calibration, PlattMapsKnownLogitToKnownProb) {
  std::vector<float> logit = {2.0f};  // n==1, 2.0 > 1 => treated as a logit
  auto v = logitsView(logit);
  config::StageCalibration c;
  c.method = config::StageCalibration::kPlatt;
  c.plattA = 1.0f;
  c.plattB = 0.0f;
  const float p = detect::Stage1Detector::scoreFromOutput(v, /*target=*/0, /*softmax=*/false, c);
  EXPECT_NEAR(p, 1.0f / (1.0f + std::exp(-2.0f)), 1e-5);  // sigmoid(2) ~= 0.8808

  config::StageCalibration c2;
  c2.method = config::StageCalibration::kPlatt;
  c2.plattA = 2.0f;
  c2.plattB = -1.0f;
  const float p2 = detect::Stage1Detector::scoreFromOutput(v, 0, false, c2);
  EXPECT_NEAR(p2, 1.0f / (1.0f + std::exp(-(2.0f * 2.0f - 1.0f))), 1e-5);  // sigmoid(3)
}

// The stage's own calibration params are honored: different per-stage a/b produce
// different calibrated confidences from the same logits.
TEST(Calibration, PerStageParamsUsed) {
  std::vector<float> logits = {0.0f, 2.0f};
  auto v = logitsView(logits);
  config::StageCalibration s1;
  s1.method = config::StageCalibration::kPlatt;
  s1.plattA = 1.0f;
  s1.plattB = 0.0f;
  config::StageCalibration s2;
  s2.method = config::StageCalibration::kPlatt;
  s2.plattA = 3.0f;
  s2.plattB = 0.5f;
  const float a = detect::Stage1Detector::scoreFromOutput(v, 1, true, s1);
  const float b = detect::Stage1Detector::scoreFromOutput(v, 1, true, s2);
  EXPECT_NE(a, b);
}

// End-to-end: with Stage-2 enabled, the confirmed confidence reflects the STAGE-2
// calibration (runStage2 uses cfg.stage2Calibration), proving per-stage routing.
TEST(Calibration, Stage2CalibrationDrivesConfirmedConfidence) {
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
  // Stage-2 Platt: sigmoid(0.5*z + 0.25). The fake emits target logit 10 => softmax[1]~1,
  // so the confirmed confidence ~= sigmoid(0.5*1 + 0.25) = sigmoid(0.75).
  dc.stage2Calibration.method = config::StageCalibration::kPlatt;
  dc.stage2Calibration.plattA = 0.5f;
  dc.stage2Calibration.plattB = 0.25f;
  test::FakeInferenceBackend s1(4, 1, 0.0f);
  test::FakeInferenceBackend s2(4, 1, 0.0f);
  detect::Stage1Detector det(s1, dc, nMels, 0, &s2);
  int count = 0;
  common::DetectionEvent last{};
  det.setOnDetection([&](const common::DetectionEvent& e) { ++count; last = e; });
  for (int i = 0; i < 30; ++i) det.pushFeature(makeFrame(nMels, 2.0f, /*speech=*/true, i));
  EXPECT_EQ(count, 1);
  EXPECT_NEAR(last.confidence, 1.0f / (1.0f + std::exp(-0.75f)), 2e-3);
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
