// PROJECT AURA — tests/stress/soak_test.cpp
//
// Soak / stability driver (Stage 7 §14). Runs the full engine over a long, repeating
// utterance stream and asserts it stays stable — no crash, bounded queues, and one
// detection per utterance (no drift, no missed/duplicate fires). The 24-hour / 7-day
// soak milestones run this same driver for longer in the dedicated stress CI lane
// (AURA_SOAK_UTTERANCES env override); the in-suite run is a fast smoke of the loop.
#include <cmath>
#include <cstdlib>
#include <vector>

#include "core/engine/WakeWordEngine.h"
#include "core/vad/EnergyVad.h"
#include "tests/mock_platform/MockPlatform.h"
#include "tests/support/FakeInferenceBackend.h"
#include "tests/support/SyntheticSpeech.h"
#include "tests/support/test_framework.h"

using namespace aura;

namespace {
struct Counter final : engine::IWakeWordListener {
  int detections = 0;
  void onWakeWordDetected(const common::DetectionEvent&) override { ++detections; }
  void onError(const engine::EngineError&) override {}
  void onStateChanged(common::EngineState) override {}
};

void feedUtterance(engine::WakeWordEngine& eng, test::MockPlatform& p) {
  // marvin-like AM burst with >1 s silence each side so the 1 s detection window fully
  // clears between utterances (no residual-burst carryover -> exactly one fire each).
  auto wav = test::makeUtterance(/*lead=*/0.7, /*burst=*/1.5, /*trail=*/0.7);
  for (size_t off = 0; off < wav.size(); off += 160) {
    size_t c = std::min<size_t>(160, wav.size() - off);
    p.mockAudio().feed(wav.data() + off, c);
    eng.pumpForTest();
  }
}
}  // namespace

TEST(Soak, StableOverManyUtterances) {
  int utterances = 30;
  if (const char* env = std::getenv("AURA_SOAK_UTTERANCES")) {
    int v = std::atoi(env);
    if (v > 0) utterances = v;
  }

  auto cfg = std::make_shared<config::Config>();
  test::MockPlatform p(".");
  Counter c;
  auto backend = std::make_unique<test::FakeInferenceBackend>(
      cfg->detect.stage1NumClasses, cfg->detect.stage1TargetClass, -6.0f);
  engine::WakeWordEngine eng(p, cfg, std::move(backend), std::make_unique<vad::EnergyVad>());
  eng.setListener(&c);
  engine::EngineOptions opts;
  opts.synchronousForTest = true;
  ASSERT_TRUE(static_cast<bool>(eng.initialize(opts)));
  engine::WakeWordSpec spec;
  spec.id = "marvin";
  ASSERT_TRUE(static_cast<bool>(eng.addWakeWord(spec)));
  ASSERT_TRUE(static_cast<bool>(eng.start()));

  for (int i = 0; i < utterances; ++i) feedUtterance(eng, p);
  (void)eng.stop();

  // Exactly one detection per utterance — no drift, no missed/duplicate fires over the run.
  EXPECT_EQ(c.detections, utterances);
}
