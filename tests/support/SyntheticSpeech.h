// PROJECT AURA — tests/support/SyntheticSpeech.h
// Deterministic "marvin-like" synthetic utterance (mirrors tools/gen_golden_fixture.py):
// silence + an amplitude-modulated dual-tone burst + silence. The 6 Hz AM keeps an
// energy-based VAD open through the burst (a pure tone lets the noise floor catch up and
// close the gate early), so the whole detection cascade exercises reliably.
#ifndef AURA_TESTS_SUPPORT_SYNTHETICSPEECH_H
#define AURA_TESTS_SUPPORT_SYNTHETICSPEECH_H

#include <cmath>
#include <cstdint>
#include <vector>

namespace aura::test {

inline std::vector<int16_t> makeUtterance(double leadSilenceS = 0.3, double burstS = 1.5,
                                          double trailSilenceS = 0.3, int sr = 16000) {
  std::vector<int16_t> s;
  const int lead = static_cast<int>(leadSilenceS * sr);
  const int n = static_cast<int>(burstS * sr);
  const int trail = static_cast<int>(trailSilenceS * sr);
  const int fade = static_cast<int>(0.03 * sr);
  s.reserve(lead + n + trail);
  for (int i = 0; i < lead; ++i) s.push_back(0);
  for (int i = 0; i < n; ++i) {
    const double t = static_cast<double>(i) / sr;
    double env = 1.0;
    if (i < fade) env = 0.5 * (1 - std::cos(3.14159265 * i / fade));
    else if (i > n - fade) env = 0.5 * (1 - std::cos(3.14159265 * (n - i) / fade));
    const double am = 0.7 + 0.3 * std::sin(2 * 3.14159265 * 6.0 * t);
    const double v = std::sin(2 * 3.14159265 * 320.0 * t) +
                     0.6 * std::sin(2 * 3.14159265 * 1100.0 * t);
    double x = 0.35 * env * am * v;
    if (x > 1.0) x = 1.0;
    if (x < -1.0) x = -1.0;
    s.push_back(static_cast<int16_t>(x * 32767));
  }
  for (int i = 0; i < trail; ++i) s.push_back(0);
  return s;
}

}  // namespace aura::test

#endif  // AURA_TESTS_SUPPORT_SYNTHETICSPEECH_H
