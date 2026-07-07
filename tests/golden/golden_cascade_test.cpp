// PROJECT AURA — tests/golden/golden_cascade_test.cpp
//
// Golden-fixture regression (Stage 7 §14 / Stage 9 §5 / ADR-GoldenTest). Replays a
// recorded clip through the REAL DSP -> log-Mel -> VAD pipeline deterministically,
// with a scripted FakeInferenceBackend for Stage-1 (see FakeInferenceBackend.h for
// why the deterministic host test does not use ONNX Runtime), and asserts the
// exact cascade outcome: exactly one DetectionOutcome::Confirmed event.
#include <string>
#include <vector>

#include "core/engine/WakeWordEngine.h"
#include "core/vad/EnergyVad.h"
#include "tests/mock_platform/MockPlatform.h"
#include "tests/support/FakeInferenceBackend.h"
#include "tests/support/WavIo.h"
#include "tests/support/test_framework.h"

namespace {

using namespace aura;

struct CountingListener final : engine::IWakeWordListener {
  int detections = 0;
  common::DetectionEvent last{};
  int stateChanges = 0;
  void onWakeWordDetected(const common::DetectionEvent& e) override {
    ++detections;
    last = e;
  }
  void onError(const engine::EngineError&) override {}
  void onStateChanged(common::EngineState) override { ++stateChanges; }
};

const char* kFixture = "benchmarks/corpus/positive/marvin_clean_en_us_001.wav";

}  // namespace

TEST(GoldenCascade, CleanSpeechWakeWordTriggersDetection) {
  test::WavData wav;
  ASSERT_TRUE(test::ReadWav16(kFixture, wav));
  ASSERT_TRUE(wav.samples.size() > 16000u);

  auto cfg = std::make_shared<config::Config>();
  // Fake backend fires the "marvin" (class 1) when the mean log-Mel of the window
  // exceeds the gate — separating the energetic burst window from silence.
  auto backend = std::make_unique<test::FakeInferenceBackend>(
      cfg->detect.stage1NumClasses, cfg->detect.stage1TargetClass, /*gate=*/-6.0f);
  auto vad = std::make_unique<vad::EnergyVad>();

  test::MockPlatform platform(".");
  engine::WakeWordEngine eng(platform, cfg, std::move(backend), std::move(vad));

  CountingListener listener;
  eng.setListener(&listener);

  engine::EngineOptions opts;
  opts.synchronousForTest = true;  // no threads; deterministic
  ASSERT_TRUE(static_cast<bool>(eng.initialize(opts)));

  engine::WakeWordSpec spec;
  spec.id = "marvin";
  spec.phrase = "marvin";
  spec.threshold = cfg->detect.stage1Threshold;
  ASSERT_TRUE(static_cast<bool>(eng.addWakeWord(spec)));
  ASSERT_TRUE(static_cast<bool>(eng.start()));

  // Replay the clip in 160-sample (10 ms) blocks, pumping the pipeline after each.
  const size_t block = 160;
  for (size_t off = 0; off < wav.samples.size(); off += block) {
    const size_t n = std::min(block, wav.samples.size() - off);
    platform.mockAudio().feed(wav.samples.data() + off, n);
    eng.pumpForTest();
  }

  EXPECT_EQ(listener.detections, 1);
  EXPECT_EQ(listener.last.outcome, common::DetectionOutcome::kConfirmed);
  EXPECT_GE(listener.last.confidence, cfg->detect.stage1Threshold);
  EXPECT_TRUE(listener.last.correlationId.valid());

  (void)eng.stop();
}
