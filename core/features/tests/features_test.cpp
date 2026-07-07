// PROJECT AURA — core/features/tests/features_test.cpp
#include <cmath>
#include <vector>

#include "core/config/Config.h"
#include "core/features/LogMelExtractor.h"
#include "tests/support/test_framework.h"

using namespace aura;

TEST(Features, ProducesExpectedFrameCount) {
  config::FeatureConfig cfg;  // 16k, win 400, hop 160, 40 mel
  features::LogMelExtractor mel(cfg);
  std::vector<float> audio(16000, 0.0f);
  for (int i = 0; i < 16000; ++i)
    audio[i] = 0.2f * std::sin(2 * 3.14159f * 440.0f * i / 16000.0f);

  int frames = 0;
  int lastN = 0;
  // feed in 160-sample hops
  for (size_t off = 0; off < audio.size(); off += 160) {
    mel.process(audio.data() + off, 160, [&](const float*, int n) {
      ++frames;
      lastN = n;
    });
  }
  // (16000 - 400)/160 + 1 = 98
  EXPECT_EQ(frames, 98);
  EXPECT_EQ(lastN, 40);
}

TEST(Features, ToneHasEnergyNearItsMelBand) {
  config::FeatureConfig cfg;
  features::LogMelExtractor mel(cfg);
  std::vector<float> tone(4000);
  for (int i = 0; i < 4000; ++i) tone[i] = 0.3f * std::sin(2 * 3.14159f * 1000.0f * i / 16000.0f);
  std::vector<float> silence(4000, 0.0f);

  float toneMax = -1e9f, silMax = -1e9f;
  auto grab = [](float& acc) {
    return [&acc](const float* m, int n) {
      for (int i = 0; i < n; ++i) acc = std::max(acc, m[i]);
    };
  };
  for (size_t off = 0; off + 160 <= tone.size(); off += 160) mel.process(tone.data() + off, 160, grab(toneMax));
  mel.reset();
  for (size_t off = 0; off + 160 <= silence.size(); off += 160) mel.process(silence.data() + off, 160, grab(silMax));

  EXPECT_GT(toneMax, silMax);  // a real tone has more log-Mel energy than silence
}
