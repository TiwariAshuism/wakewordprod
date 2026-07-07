// PROJECT AURA — core/vad/tests/vad_test.cpp
#include <cmath>
#include <vector>

#include "core/config/Config.h"
#include "core/vad/EnergyVad.h"
#include "core/vad/VadGate.h"
#include "tests/support/test_framework.h"

using namespace aura;

TEST(Vad, SilenceClosedSpeechOpen) {
  config::VadConfig cfg;
  vad::EnergyVad ev;
  vad::VadGate gate(ev, cfg);

  std::vector<float> silence(160, 0.0f);
  for (int i = 0; i < 20; ++i) gate.process(silence.data(), silence.size());
  EXPECT_FALSE(gate.isOpen());

  std::vector<float> tone(160);
  bool opened = false;
  for (int iter = 0; iter < 20; ++iter) {
    for (int i = 0; i < 160; ++i) tone[i] = 0.3f * std::sin(2 * 3.14159f * 300.0f * i / 16000.0f);
    if (gate.process(tone.data(), tone.size())) opened = true;
  }
  EXPECT_TRUE(opened);
}

TEST(Vad, GateHasHangover) {
  config::VadConfig cfg;
  cfg.hangoverFrames = 5;
  vad::EnergyVad ev;
  vad::VadGate gate(ev, cfg);
  std::vector<float> tone(160), silence(160, 0.0f);
  for (int i = 0; i < 160; ++i) tone[i] = 0.3f * std::sin(2 * 3.14159f * 300.0f * i / 16000.0f);
  for (int i = 0; i < 10; ++i) gate.process(tone.data(), 160);
  EXPECT_TRUE(gate.isOpen());
  // one silent frame: hangover keeps it open
  EXPECT_TRUE(gate.process(silence.data(), 160));
}
