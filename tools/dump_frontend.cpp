// PROJECT AURA — tools/dump_frontend.cpp (host verification helper, not shipped).
// Runs a WAV through the REAL engine front-end (DspChain per-160-block + then
// LogMelExtractor, exactly as WakeWordEngine's audio sink does) and prints the
// resulting log-Mel frames as CSV. tools/verify_frontend_alignment.py compares
// this against tools/aura_frontend.py to prove numpy == C++ (the M3-risk check).
#include <cstdio>
#include <vector>

#include "core/config/Config.h"
#include "core/dsp/DspChain.h"
#include "core/features/LogMelExtractor.h"
#include "tests/support/WavIo.h"

int main(int argc, char** argv) {
  if (argc < 2) {
    std::fprintf(stderr, "usage: dump_frontend <wav>\n");
    return 2;
  }
  aura::test::WavData wav;
  if (!aura::test::ReadWav16(argv[1], wav)) {
    std::fprintf(stderr, "cannot read %s\n", argv[1]);
    return 1;
  }
  std::vector<float> x(wav.samples.size());
  for (size_t i = 0; i < wav.samples.size(); ++i) x[i] = wav.samples[i] / 32768.0f;

  aura::config::FeatureConfig fcfg;  // defaults: 16k/512/400/160/40
  aura::dsp::DspChain dsp;
  aura::features::LogMelExtractor mel(fcfg);

  const size_t block = 160;
  for (size_t off = 0; off < x.size(); off += block) {
    const size_t n = std::min(block, x.size() - off);
    (void)dsp.process(x.data() + off, n);       // in-place, per-block (engine order)
    mel.process(x.data() + off, n, [&](const float* m, int nm) {
      for (int i = 0; i < nm; ++i) std::printf("%s%.6f", i ? "," : "", m[i]);
      std::printf("\n");
    });
  }
  return 0;
}
