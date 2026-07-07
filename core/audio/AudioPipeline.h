// PROJECT AURA — core/audio/AudioPipeline.h
#ifndef AURA_AUDIO_AUDIOPIPELINE_H
#define AURA_AUDIO_AUDIOPIPELINE_H

#include <memory>
#include <vector>

#include "core/audio/IAudioPipeline.h"
#include "core/audio/PcmFrame.h"
#include "core/audio/Resampler.h"
#include "core/common/ring_buffer.h"
#include "core/config/Config.h"
#include "core/scheduler/Scheduler.h"

namespace aura::audio
{

  // Concrete audio pipeline. Owns the raw-PCM ring and (via the scheduler) the
  // Audio thread. See IAudioPipeline for the threading contract.
  class AudioPipeline final : public IAudioPipeline
  {
  public:
    AudioPipeline(const config::AudioConfig &cfg, scheduler::Scheduler &scheduler);
    ~AudioPipeline() override;

    void setFrameSink(FrameSink sink) override;
    void onCaptureFrame(const common::AudioFrameView &frame, uint64_t captureTsNanos) override;
    common::Result<void> start() override;
    common::Result<void> stop() override;
    size_t ringDepth() const override { return ring_.size(); }
    uint64_t dropCount() const override { return ring_.dropCount(); }

    // Test/host hook: run one drain iteration synchronously (used by the golden
    // replay so the pipeline is deterministic without a live Audio thread).
    void drainOnceForTest();

  private:
    void audioThreadTick();

    config::AudioConfig cfg_;
    scheduler::Scheduler &scheduler_;
    common::RingBuffer<PcmFrame> ring_;
    FrameSink sink_;
    scheduler::ManagedThread *thread_ = nullptr;
    bool running_ = false;

    // Resampling of non-16 kHz input (USB/BT mics) to the engine rate (Arch Finding 3).
    std::unique_ptr<Resampler> resampler_;
    uint32_t resamplerInRate_ = 0;
    std::vector<float> monoScratch_;      // one converted mono block
    std::vector<float> resampleOut_;      // resampled output before slotting
  };

} // namespace aura::audio

#endif // AURA_AUDIO_AUDIOPIPELINE_H
