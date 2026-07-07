// PROJECT AURA — core/audio/IAudioPipeline.h
//
// Responsibilities : buffer-ownership/backpressure pipeline; owns the raw-PCM ring
//                    pool and the Audio thread (Stage 7 §3.6/§5/§6).
// Dependencies     : core/platform, core/scheduler (Row 2). Does NOT depend on
//                    dsp/features/vad (higher rows) — the per-frame processing
//                    chain is injected as a FrameSink by the engine, so audio/ has
//                    no compile-time dependency on higher-row modules (Stage 7 §2).
// Thread ownership : onCaptureFrame() runs in the platform capture callback (ISR-
//                    equivalent, alloc-free); the Audio thread drains slots and
//                    invokes the FrameSink in-line (Stage 7 §6).
// Memory ownership : owns the raw-PCM ring pool.
#ifndef AURA_AUDIO_IAUDIOPIPELINE_H
#define AURA_AUDIO_IAUDIOPIPELINE_H

#include <cstdint>
#include <functional>

#include "core/common/audio_types.h"
#include "core/common/result.h"

namespace aura::audio
{

  // The per-frame processing chain injected by the engine (DSP -> features -> VAD).
  // Invoked in-line on the Audio thread. Must be allocation-free after startup.
  // `samples` is MUTABLE: DSP processes the owned slot in place (Stage 7 §5). The
  // consumer owns the slot exclusively at this point, so mutation is safe.
  //   samples: mono float32 block; n: sample count; ts: capture monotonic ns.
  using FrameSink = std::function<void(float *samples, size_t n, uint64_t ts)>;

  class IAudioPipeline
  {
  public:
    virtual ~IAudioPipeline() = default;

    // Register the processing chain. Call once before start().
    virtual void setFrameSink(FrameSink sink) = 0;

    // Called from the platform capture callback (ISR context): convert + enqueue.
    virtual void onCaptureFrame(const common::AudioFrameView &frame, uint64_t captureTsNanos) = 0;

    virtual common::Result<void> start() = 0;
    virtual common::Result<void> stop() = 0;

    // Metrics (Stage 7 §13: queue.ring_buffer.depth / drop_count).
    virtual size_t ringDepth() const = 0;
    virtual uint64_t dropCount() const = 0;
  };

} // namespace aura::audio

#endif // AURA_AUDIO_IAUDIOPIPELINE_H
