// PROJECT AURA — core/audio/AudioPipeline.cpp
#include "core/audio/AudioPipeline.h"

#include <algorithm>
#include <chrono>
#include <cstring>
#include <thread>
#include <utility>

#include "core/common/noalloc.h"

namespace aura::audio
{

  using common::AudioFrameView;
  using common::Err;
  using common::ErrorCode;
  using common::Result;

  AudioPipeline::AudioPipeline(const config::AudioConfig &cfg, scheduler::Scheduler &scheduler)
      : cfg_(cfg), scheduler_(scheduler)
  {
    ring_.reserve(cfg_.pcmSlotCount, cfg_.backpressure);
    monoScratch_.assign(kMaxPcmFrameSamples, 0.0f);
    resampleOut_.assign(4 * kMaxPcmFrameSamples, 0.0f);  // headroom for upsampling
  }

  AudioPipeline::~AudioPipeline() { (void)stop(); }

  void AudioPipeline::setFrameSink(FrameSink sink) { sink_ = std::move(sink); }

  // ISR-equivalent: no heap alloc on the steady path, no locks (Stage 7 §4/§6). Converts
  // interleaved I16/float capture to mono float32, resamples to the engine rate if the mic
  // isn't already at it (Arch Finding 3), and writes slot-sized blocks (drop-oldest).
  void AudioPipeline::onCaptureFrame(const AudioFrameView &frame, uint64_t captureTsNanos)
  {
    common::ScopedNoAllocGuard noalloc;
    const size_t n = std::min(frame.frames, kMaxPcmFrameSamples);
    const uint8_t ch = frame.channels ? frame.channels : 1;

    // 1) downmix to mono float32 into scratch.
    if (frame.isFloat())
    {
      for (size_t i = 0; i < n; ++i)
        monoScratch_[i] = frame.f32[i * ch];
    }
    else if (frame.i16)
    {
      constexpr float kInv = 1.0f / 32768.0f;
      for (size_t i = 0; i < n; ++i)
        monoScratch_[i] = static_cast<float>(frame.i16[i * ch]) * kInv;
    }
    else
    {
      return;
    }

    // 2) resample to the engine rate if needed.
    const float *samples = monoScratch_.data();
    size_t count = n;
    if (frame.sampleRate != 0 && frame.sampleRate != cfg_.sampleRate)
    {
      if (!resampler_ || resamplerInRate_ != frame.sampleRate)
      {
        // Rate discovery / device change is a rare event, not the steady hot path.
        common::ScopedAllowAllocGuard allow;
        resampler_ = std::make_unique<Resampler>(frame.sampleRate, cfg_.sampleRate);
        resamplerInRate_ = frame.sampleRate;
      }
      count = resampler_->process(monoScratch_.data(), n, resampleOut_.data(), resampleOut_.size());
      samples = resampleOut_.data();
    }

    // 3) write to the ring in slot-sized chunks (handles up/downsampled block sizes).
    size_t off = 0;
    while (off < count)
    {
      PcmFrame *slot = ring_.acquireWrite();
      if (!slot)
        break; // kDropNewest + full: drop remainder
      const size_t c = std::min(count - off, kMaxPcmFrameSamples);
      std::memcpy(slot->samples, samples + off, c * sizeof(float));
      slot->count = c;
      slot->captureTimestampNanos = captureTsNanos;
      ring_.commitWrite();
      off += c;
    }
  }

  void AudioPipeline::audioThreadTick()
  {
    // Drain all currently-available slots, running the injected chain in-line.
    bool did = false;
    while (const PcmFrame *slot = ring_.acquireRead())
    {
      did = true;
      if (sink_)
      {
        common::ScopedNoAllocGuard noalloc; // hot path: no heap alloc (Stage 7 §5/§6)
        sink_(const_cast<float *>(slot->samples), slot->count, slot->captureTimestampNanos);
      }
      ring_.commitRead();
    }
    if (!did)
    {
      // Nothing to do this tick; yield briefly so we don't busy-spin a core.
      std::this_thread::sleep_for(std::chrono::milliseconds(1));
    }
  }

  Result<void> AudioPipeline::start()
  {
    if (running_)
      return {};
    if (!sink_)
      return Err(ErrorCode::kFailedPrecondition, "AudioPipeline: no FrameSink set");
    running_ = true;
    thread_ = scheduler_.spawnLoop("aura-audio", scheduler::ThreadClass::kAudio,
                                   [this]
                                   { audioThreadTick(); });
    return {};
  }

  Result<void> AudioPipeline::stop()
  {
    if (!running_)
      return {};
    running_ = false;
    if (thread_)
    {
      thread_->stop();
      thread_->join();
      thread_ = nullptr;
    }
    return {};
  }

  void AudioPipeline::drainOnceForTest()
  {
    while (const PcmFrame *slot = ring_.acquireRead())
    {
      if (sink_)
        sink_(const_cast<float *>(slot->samples), slot->count, slot->captureTimestampNanos);
      ring_.commitRead();
    }
  }

} // namespace aura::audio
