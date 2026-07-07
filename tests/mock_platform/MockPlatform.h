// PROJECT AURA — tests/mock_platform/MockPlatform.h
// Host-machine IPlatform simulation (Stage 7 §14). Deterministic: no real audio
// device, no wall clock. Audio is driven by feeding frames explicitly.
#ifndef AURA_TESTS_MOCK_PLATFORM_MOCKPLATFORM_H
#define AURA_TESTS_MOCK_PLATFORM_MOCKPLATFORM_H

#include <cstdlib>
#include <cstdio>
#include <filesystem>
#include <vector>

#include "core/platform/IPlatform.h"

namespace aura::test
{

  class MockClock final : public platform::IClock
  {
  public:
    uint64_t nowMonotonicNanos() const override { return now_; }
    uint64_t nowWallClockUnixMillis() const override { return now_ / 1000000ull; }
    void advance(uint64_t ns) { now_ += ns; }
    void set(uint64_t ns) { now_ = ns; }

  private:
    uint64_t now_ = 0;
  };

  class MockPowerManager final : public platform::IPowerManager
  {
  public:
    platform::PowerState currentState() const override { return platform::PowerState::kActive; }
    void onPowerStateChanged(std::function<void(platform::PowerState)>) override {}
  };

  class MockStorage final : public platform::IStorage
  {
  public:
    explicit MockStorage(std::filesystem::path base = ".") : base_(std::move(base)) {}
    std::filesystem::path baseDir() const override { return base_; }

    common::Result<platform::MappedRegion> mapReadOnly(const std::filesystem::path &path) override
    {
      const auto full = path.is_absolute() ? path : (base_ / path);
      FILE *f = std::fopen(full.string().c_str(), "rb");
      if (!f)
        return common::Err(common::ErrorCode::kNotFound, "MockStorage: not found");
      std::fseek(f, 0, SEEK_END);
      long sz = std::ftell(f);
      std::fseek(f, 0, SEEK_SET);
      if (sz <= 0)
      {
        std::fclose(f);
        return common::Err(common::ErrorCode::kIoError, "empty");
      }
      void *buf = std::malloc(static_cast<size_t>(sz));
      std::fread(buf, 1, static_cast<size_t>(sz), f);
      std::fclose(f);
      return platform::MappedRegion{buf, static_cast<size_t>(sz), buf};
    }
    void unmap(const platform::MappedRegion &r) override
    {
      if (r.opaque)
        std::free(r.opaque);
    }

  private:
    std::filesystem::path base_;
  };

  class MockAudioInput final : public platform::IAudioInput
  {
  public:
    explicit MockAudioInput(MockClock &clock) : clock_(clock) {}

    common::Result<void> start(const common::AudioFormat &fmt, FrameCallback cb) override
    {
      format_ = fmt;
      cb_ = std::move(cb);
      started_ = true;
      return {};
    }
    common::Result<void> stop() override
    {
      started_ = false;
      return {};
    }
    common::Result<common::AudioFormat> currentFormat() const override { return format_; }
    void onDeviceChanged(std::function<void(const common::DeviceChangeEvent &)>) override {}

    // Test driver: deliver one block of mono int16 PCM through the capture callback.
    void feed(const int16_t *data, size_t frames)
    {
      if (!started_ || !cb_)
        return;
      common::AudioFrameView v;
      v.i16 = data;
      v.frames = frames;
      v.channels = 1;
      v.sampleRate = format_.sampleRate;
      const uint64_t ts = clock_.nowMonotonicNanos();
      cb_(v, ts);
      // advance the mock clock by the block duration
      clock_.advance(frames * 1000000000ull / format_.sampleRate);
    }
    bool started() const { return started_; }

  private:
    MockClock &clock_;
    common::AudioFormat format_{};
    FrameCallback cb_;
    bool started_ = false;
  };

  class MockPlatform final : public platform::IPlatform
  {
  public:
    explicit MockPlatform(std::filesystem::path base = ".")
        : storage_(std::move(base)), audio_(clock_) {}

    platform::IAudioInput &audioInput() override { return audio_; }
    platform::IClock &clock() override { return clock_; }
    platform::IStorage &storage() override { return storage_; }
    platform::IPowerManager &powerManager() override { return power_; }

    MockAudioInput &mockAudio() { return audio_; }
    MockClock &mockClock() { return clock_; }

  private:
    MockClock clock_;
    MockStorage storage_;
    MockPowerManager power_;
    MockAudioInput audio_;
  };

} // namespace aura::test

#endif // AURA_TESTS_MOCK_PLATFORM_MOCKPLATFORM_H
