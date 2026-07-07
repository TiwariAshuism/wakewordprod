// PROJECT AURA — core/audio/tests/audio_test.cpp
#include <cmath>
#include <vector>

#include "core/audio/AudioPipeline.h"
#include "core/audio/Resampler.h"
#include "core/scheduler/Scheduler.h"
#include "tests/support/test_framework.h"

using namespace aura;

TEST(Resampler, PassthroughWhenRatesMatch) {
  audio::Resampler r(16000, 16000);
  EXPECT_TRUE(r.passthrough());
  std::vector<float> in{0.1f, -0.2f, 0.3f}, out(8, 0.0f);
  EXPECT_EQ(r.process(in.data(), in.size(), out.data(), out.size()), 3u);
  EXPECT_NEAR(out[1], -0.2f, 1e-6);
}

TEST(Resampler, Downsample48kTo16kLengthAndDcPreserved) {
  audio::Resampler r(48000, 16000);
  EXPECT_FALSE(r.passthrough());
  // Constant (DC) input should resample to ~the same constant.
  std::vector<float> in(4800, 0.5f), out(4800, 0.0f);
  size_t produced = 0, off = 0;
  // stream in 160-sample blocks
  while (off < in.size()) {
    size_t nb = std::min<size_t>(160, in.size() - off);
    produced += r.process(in.data() + off, nb, out.data() + produced, out.size() - produced);
    off += nb;
  }
  // 48k -> 16k => ~1/3 the samples.
  EXPECT_GT(produced, 1500u);
  EXPECT_LT(produced, 1700u);
  // steady-state output should track the DC level (skip edge transients)
  float mid = out[produced / 2];
  EXPECT_NEAR(mid, 0.5f, 0.05f);
}

TEST(Resampler, SinePreservedThroughDownsample) {
  audio::Resampler r(32000, 16000);
  std::vector<float> in(3200), out(2000, 0.0f);
  for (int i = 0; i < 3200; ++i) in[i] = std::sin(2 * 3.14159f * 1000.0f * i / 32000.0f);
  size_t produced = r.process(in.data(), in.size(), out.data(), out.size());
  EXPECT_GT(produced, 1400u);  // ~half
  // output amplitude preserved (RMS near a full-scale sine's ~0.707), not collapsed
  double s = 0; for (size_t i = 100; i < produced - 100; ++i) s += out[i] * out[i];
  float rms = std::sqrt(s / (produced - 200));
  EXPECT_GT(rms, 0.5f);
  EXPECT_LT(rms, 0.85f);
}

TEST(Audio, SinkReceivesConvertedFrames) {
  config::AudioConfig cfg;
  scheduler::Scheduler sched;
  audio::AudioPipeline ap(cfg, sched);

  int frames = 0;
  float firstSample = 0.0f;
  ap.setFrameSink([&](float* s, size_t n, uint64_t) {
    if (frames == 0 && n > 0) firstSample = s[0];
    ++frames;
  });

  std::vector<int16_t> pcm(160, 16384);  // ~0.5 full-scale
  common::AudioFrameView v;
  v.i16 = pcm.data();
  v.frames = 160;
  v.channels = 1;
  v.sampleRate = 16000;
  for (int i = 0; i < 3; ++i) ap.onCaptureFrame(v, i);
  ap.drainOnceForTest();

  EXPECT_EQ(frames, 3);
  EXPECT_NEAR(firstSample, 0.5f, 0.01f);  // 16384/32768
}

TEST(Audio, DropOldestUnderBackpressure) {
  config::AudioConfig cfg;
  cfg.pcmSlotCount = 4;
  cfg.backpressure = common::BackpressurePolicy::kDropOldest;
  scheduler::Scheduler sched;
  audio::AudioPipeline ap(cfg, sched);
  ap.setFrameSink([](float*, size_t, uint64_t) {});

  std::vector<int16_t> pcm(160, 1000);
  common::AudioFrameView v;
  v.i16 = pcm.data();
  v.frames = 160;
  v.channels = 1;
  v.sampleRate = 16000;
  for (int i = 0; i < 10; ++i) ap.onCaptureFrame(v, i);  // flood a depth-4 ring
  EXPECT_GT(ap.dropCount(), 0u);
  EXPECT_LE(ap.ringDepth(), 4u);
}
