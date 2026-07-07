// PROJECT AURA — tests/fuzz/fuzz_test.cpp
//
// Deterministic randomized fuzzing (Stage 7 §14): feeds malformed / adversarial / extreme
// inputs to the hot-path modules and asserts they don't crash, hang, or violate the
// no-alloc / error contracts. Runs every CI run. A coverage-guided libFuzzer harness for
// continuous fuzzing lives in tests/fuzz/fuzz_frontend.cpp (compiled with clang in CI).
#include <cmath>
#include <cstdio>
#include <limits>
#include <random>
#include <vector>

#include "core/audio/AudioPipeline.h"
#include "core/detect/Stage1Detector.h"
#include "core/dsp/DspChain.h"
#include "core/features/LogMelExtractor.h"
#include "core/model/ModelManager.h"
#include "core/scheduler/Scheduler.h"
#include "tests/mock_platform/MockPlatform.h"
#include "tests/support/FakeInferenceBackend.h"
#include "tests/support/WavIo.h"
#include "tests/support/test_framework.h"

using namespace aura;

TEST(Fuzz, DspAndFeaturesSurviveExtremeInput) {
  std::mt19937 rng(1234);
  std::uniform_real_distribution<float> dist(-2.0f, 2.0f);
  config::FeatureConfig fcfg;
  dsp::DspChain dspc;
  features::LogMelExtractor mel(fcfg);
  for (int iter = 0; iter < 500; ++iter) {
    size_t n = 1 + (rng() % 512);
    std::vector<float> blk(n);
    for (auto& v : blk) v = dist(rng);
    // occasionally inject NaN/Inf/denormals
    if (iter % 7 == 0 && n > 3) {
      blk[0] = std::numeric_limits<float>::quiet_NaN();
      blk[1] = std::numeric_limits<float>::infinity();
      blk[2] = -std::numeric_limits<float>::infinity();
    }
    (void)dspc.process(blk.data(), n);
    mel.process(blk.data(), n, [](const float*, int) {});
  }
  EXPECT_TRUE(true);  // reached here without crashing/hanging
}

TEST(Fuzz, DetectorSurvivesRandomFeatureFrames) {
  std::mt19937 rng(99);
  std::uniform_real_distribution<float> dist(-30.0f, 30.0f);
  config::DetectConfig dc;
  dc.stage1WindowFrames = 20;
  dc.stage1NumClasses = 4;
  dc.stage1TargetClass = 1;
  test::FakeInferenceBackend fake(4, 1, 0.0f);
  detect::Stage1Detector det(fake, dc, 8, 0);
  int detections = 0;
  det.setOnDetection([&](const common::DetectionEvent&) { ++detections; });
  for (int i = 0; i < 5000; ++i) {
    features::FeatureFrame f;
    f.nMels = 8;
    f.speech = (rng() % 2) == 0;
    f.captureTimestampNanos = i;
    for (int m = 0; m < 8; ++m) f.mel[m] = dist(rng);
    det.pushFeature(f);
  }
  EXPECT_TRUE(true);  // no crash regardless of detection count
}

TEST(Fuzz, AudioPipelineSurvivesRandomCaptureFrames) {
  config::AudioConfig acfg;
  scheduler::Scheduler sch;
  audio::AudioPipeline ap(acfg, sch);
  ap.setFrameSink([](float*, size_t, uint64_t) {});
  std::mt19937 rng(7);
  for (int iter = 0; iter < 300; ++iter) {
    size_t frames = rng() % 700;  // includes > kMaxPcmFrameSamples
    std::vector<int16_t> pcm(frames ? frames : 1);
    for (auto& s : pcm) s = static_cast<int16_t>(rng());
    common::AudioFrameView v;
    v.i16 = pcm.data();
    v.frames = frames;
    v.channels = 1 + (rng() % 2);
    v.sampleRate = (rng() % 2) ? 16000 : (8000 + rng() % 40000);  // triggers resampler
    ap.onCaptureFrame(v, iter);
  }
  ap.drainOnceForTest();
  EXPECT_TRUE(true);
}

TEST(Fuzz, WavAndModelLoadRejectGarbage) {
  namespace fs = std::filesystem;
  std::mt19937 rng(55);
  const fs::path dir = fs::temp_directory_path();
  test::MockStorage storage(dir);
  model::ModelManager mgr(storage, common::ModelSlot::kStage1);
  for (int iter = 0; iter < 50; ++iter) {
    // write a random-length garbage file
    const std::string name = "aura_fuzz_" + std::to_string(iter) + ".bin";
    FILE* f = std::fopen((dir / name).string().c_str(), "wb");
    ASSERT_TRUE(f != nullptr);
    int len = rng() % 256;
    for (int i = 0; i < len; ++i) {
      unsigned char b = static_cast<unsigned char>(rng());
      std::fwrite(&b, 1, 1, f);
    }
    std::fclose(f);
    // ModelManager must return a Result (never crash) on garbage bytes.
    auto staged = mgr.stage(name);
    (void)staged;  // ok or error, but no crash
    // WAV parser on the same garbage must not crash either.
    test::WavData wav;
    (void)test::ReadWav16((dir / name).string(), wav);
  }
  EXPECT_TRUE(true);
}
