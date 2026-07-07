// PROJECT AURA — tests/support/WavIo.h
// Minimal 16-bit mono PCM WAV read/write for golden fixtures (host tests only).
#ifndef AURA_TESTS_SUPPORT_WAVIO_H
#define AURA_TESTS_SUPPORT_WAVIO_H

#include <cstdint>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

namespace aura::test
{

  struct WavData
  {
    uint32_t sampleRate = 16000;
    std::vector<int16_t> samples; // mono
  };

  inline bool WriteWav16(const std::string &path, const WavData &wav)
  {
    FILE *f = std::fopen(path.c_str(), "wb");
    if (!f)
      return false;
    const uint32_t dataBytes = static_cast<uint32_t>(wav.samples.size() * sizeof(int16_t));
    const uint32_t byteRate = wav.sampleRate * 2;
    auto w32 = [&](uint32_t v)
    { std::fwrite(&v, 4, 1, f); };
    auto w16 = [&](uint16_t v)
    { std::fwrite(&v, 2, 1, f); };
    std::fwrite("RIFF", 1, 4, f);
    w32(36 + dataBytes);
    std::fwrite("WAVE", 1, 4, f);
    std::fwrite("fmt ", 1, 4, f);
    w32(16);
    w16(1);
    w16(1); // PCM, mono
    w32(wav.sampleRate);
    w32(byteRate);
    w16(2);
    w16(16);
    std::fwrite("data", 1, 4, f);
    w32(dataBytes);
    std::fwrite(wav.samples.data(), 1, dataBytes, f);
    std::fclose(f);
    return true;
  }

  inline bool ReadWav16(const std::string &path, WavData &out)
  {
    FILE *f = std::fopen(path.c_str(), "rb");
    if (!f)
      return false;
    char hdr[44];
    if (std::fread(hdr, 1, 44, f) != 44)
    {
      std::fclose(f);
      return false;
    }
    std::memcpy(&out.sampleRate, hdr + 24, 4);
    uint32_t dataBytes = 0;
    std::memcpy(&dataBytes, hdr + 40, 4);
    out.samples.resize(dataBytes / sizeof(int16_t));
    std::fread(out.samples.data(), 1, dataBytes, f);
    std::fclose(f);
    return true;
  }

} // namespace aura::test

#endif // AURA_TESTS_SUPPORT_WAVIO_H
