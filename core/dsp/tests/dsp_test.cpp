// PROJECT AURA — core/dsp/tests/dsp_test.cpp
#include <cmath>
#include <vector>

#include "core/dsp/DspChain.h"
#include "tests/support/test_framework.h"

using namespace aura::dsp;

TEST(Dsp, AecIsIdentityPassthrough) {
  AecStage aec;
  std::vector<float> x{0.1f, -0.2f, 0.3f, -0.4f};
  const std::vector<float> before = x;
  EXPECT_TRUE(static_cast<bool>(aec.process(x.data(), x.size())));
  for (size_t i = 0; i < x.size(); ++i) EXPECT_EQ(x[i], before[i]);  // v0 no-op
}

TEST(Dsp, AgcRaisesQuietSignalTowardTarget) {
  AgcStage agc(0.1f);
  // Quiet sine well below target RMS; AGC should increase level over time.
  std::vector<float> block(160);
  float lastRms = 0.0f;
  for (int iter = 0; iter < 50; ++iter) {
    for (int i = 0; i < 160; ++i) block[i] = 0.01f * std::sin(2 * 3.14159f * 200.0f * i / 16000.0f);
    EXPECT_TRUE(static_cast<bool>(agc.process(block.data(), block.size())));
    double s = 0;
    for (float v : block) s += v * v;
    lastRms = std::sqrt(s / block.size());
  }
  EXPECT_GT(lastRms, 0.02f);  // amplified above the raw 0.007 RMS
}

TEST(Dsp, ChainRunsInFixedOrder) {
  DspChain chain;
  std::vector<float> x(160, 0.05f);
  EXPECT_TRUE(static_cast<bool>(chain.process(x.data(), x.size())));  // AGC->AEC->NS, no crash
}
