// PROJECT AURA — tests/fuzz/fuzz_frontend.cpp
//
// Coverage-guided libFuzzer harness for the audio front-end (Stage 7 §14 "continuous
// fuzzing lane"). Build with clang:
//   clang++ -std=c++20 -I. -g -fsanitize=fuzzer,address \
//       tests/fuzz/fuzz_frontend.cpp core/dsp/DspChain.cpp core/features/LogMelExtractor.cpp \
//       -o fuzz_frontend && ./fuzz_frontend corpus/
//
// Interprets the fuzzer input bytes as int16 PCM and streams them through the real
// DSP + log-Mel front-end. Not part of the host g++ unit build (needs libFuzzer).
#include <cstddef>
#include <cstdint>
#include <vector>

#include "core/dsp/DspChain.h"
#include "core/features/LogMelExtractor.h"

extern "C" int LLVMFuzzerTestOneInput(const uint8_t* data, size_t size) {
  using namespace aura;
  const size_t n = size / sizeof(int16_t);
  if (n == 0) return 0;
  const int16_t* pcm = reinterpret_cast<const int16_t*>(data);

  static config::FeatureConfig fcfg;
  static dsp::DspChain dspc;
  static features::LogMelExtractor mel(fcfg);

  // Convert to float mono and stream in 160-sample blocks (as the engine does).
  std::vector<float> block;
  block.reserve(160);
  for (size_t off = 0; off < n; off += 160) {
    const size_t c = (n - off) < 160 ? (n - off) : 160;
    block.assign(pcm + off, pcm + off + c);
    for (auto& v : block) v /= 32768.0f;
    (void)dspc.process(block.data(), c);
    mel.process(block.data(), c, [](const float*, int) {});
  }
  return 0;
}
