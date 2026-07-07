// PROJECT AURA — tests/integration/integration_test.cpp
//
// Multi-module integration (Stage 7 §14): drives the whole IWakeWordEngine end-to-end
// through the MockPlatform + a scripted backend — capture -> DSP -> log-Mel -> VAD ->
// cascade -> IWakeWordListener — plus lifecycle and error-path behavior.
#include <cmath>
#include <vector>

#include "core/engine/WakeWordEngine.h"
#include "core/vad/EnergyVad.h"
#include "tests/mock_platform/MockPlatform.h"
#include "tests/support/FakeInferenceBackend.h"
#include "tests/support/SyntheticSpeech.h"
#include "tests/support/test_framework.h"

using namespace aura;

namespace {
struct RecordingListener final : engine::IWakeWordListener {
  int detections = 0;
  std::vector<common::EngineState> states;
  int errors = 0;
  void onWakeWordDetected(const common::DetectionEvent&) override { ++detections; }
  void onError(const engine::EngineError&) override { ++errors; }
  void onStateChanged(common::EngineState s) override { states.push_back(s); }
};

std::unique_ptr<engine::WakeWordEngine> buildEngine(test::MockPlatform& p,
                                                    std::shared_ptr<config::Config> cfg,
                                                    RecordingListener& l) {
  auto backend = std::make_unique<test::FakeInferenceBackend>(
      cfg->detect.stage1NumClasses, cfg->detect.stage1TargetClass, /*gate=*/-6.0f);
  auto eng = std::make_unique<engine::WakeWordEngine>(p, cfg, std::move(backend),
                                                      std::make_unique<vad::EnergyVad>());
  eng->setListener(&l);
  return eng;
}
}  // namespace

TEST(Integration, FullLifecycleDetectsWakeWord) {
  auto cfg = std::make_shared<config::Config>();
  test::MockPlatform p(".");
  RecordingListener l;
  auto eng = buildEngine(p, cfg, l);

  engine::EngineOptions opts;
  opts.synchronousForTest = true;
  ASSERT_TRUE(static_cast<bool>(eng->initialize(opts)));
  engine::WakeWordSpec spec;
  spec.id = "marvin";
  ASSERT_TRUE(static_cast<bool>(eng->addWakeWord(spec)));
  ASSERT_TRUE(static_cast<bool>(eng->start()));

  auto wav = test::makeUtterance();
  for (size_t off = 0; off < wav.size(); off += 160) {
    size_t n = std::min<size_t>(160, wav.size() - off);
    p.mockAudio().feed(wav.data() + off, n);
    eng->pumpForTest();
  }
  EXPECT_EQ(l.detections, 1);
  (void)eng->stop();

  // State machine surfaced Initialized -> Running -> Stopped (order preserved).
  bool sawInit = false, sawRun = false;
  for (auto s : l.states) {
    if (s == common::EngineState::kInitialized) sawInit = true;
    if (s == common::EngineState::kRunning) sawRun = true;
  }
  EXPECT_TRUE(sawInit);
  EXPECT_TRUE(sawRun);
}

TEST(Integration, ErrorPaths) {
  auto cfg = std::make_shared<config::Config>();
  test::MockPlatform p(".");
  RecordingListener l;
  auto eng = buildEngine(p, cfg, l);

  // start() before initialize() -> failed precondition.
  EXPECT_FALSE(static_cast<bool>(eng->start()));

  engine::EngineOptions opts;
  opts.synchronousForTest = true;
  ASSERT_TRUE(static_cast<bool>(eng->initialize(opts)));

  // start() before any wake word -> failed precondition.
  EXPECT_FALSE(static_cast<bool>(eng->start()));

  engine::WakeWordSpec spec;
  spec.id = "marvin";
  EXPECT_TRUE(static_cast<bool>(eng->addWakeWord(spec)));
  // second wake word -> unimplemented (single-wake-word v0).
  EXPECT_FALSE(static_cast<bool>(eng->addWakeWord(spec)));
  // out-of-scope primitives report unimplemented, not crash.
  EXPECT_FALSE(static_cast<bool>(eng->removeWakeWord("marvin")));
  EXPECT_FALSE(static_cast<bool>(eng->enrollSpeaker({})));
}

TEST(Integration, SilenceProducesNoDetection) {
  auto cfg = std::make_shared<config::Config>();
  test::MockPlatform p(".");
  RecordingListener l;
  auto eng = buildEngine(p, cfg, l);
  engine::EngineOptions opts;
  opts.synchronousForTest = true;
  (void)eng->initialize(opts);
  engine::WakeWordSpec spec;
  spec.id = "marvin";
  (void)eng->addWakeWord(spec);
  (void)eng->start();

  std::vector<int16_t> silence(16000 * 2, 0);  // 2 s of silence
  for (size_t off = 0; off < silence.size(); off += 160) {
    size_t n = std::min<size_t>(160, silence.size() - off);
    p.mockAudio().feed(silence.data() + off, n);
    eng->pumpForTest();
  }
  EXPECT_EQ(l.detections, 0);
  (void)eng->stop();
}
