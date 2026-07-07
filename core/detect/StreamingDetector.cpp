// PROJECT AURA — core/detect/StreamingDetector.cpp
#include "core/detect/StreamingDetector.h"

#include "core/common/log.h"
#include "core/common/noalloc.h"

namespace aura::detect {

using common::CorrelationId;
using common::DetectionEvent;
using common::DetectionOutcome;
using common::LogCategory;
using common::LogLevel;

StreamingDetector::StreamingDetector(IStreamingScorer& scorer,
                                     const config::DetectConfig& detectCfg,
                                     uint32_t wakeWordIndex)
    : scorer_(scorer), cfg_(detectCfg), wakeWordIndex_(wakeWordIndex) {}

CorrelationId StreamingDetector::mintCorrelationId() {
  ++idCounter_;  // deterministic, reproducible across golden replays (Stage 7 §14)
  return CorrelationId{0x5DDA0000ull | wakeWordIndex_, idCounter_};
}

void StreamingDetector::fire(uint64_t timestampNanos, float confidence) {
  refractory_ = cfg_.refractoryFrames;
  DetectionEvent ev;
  ev.correlationId = currentId_;
  ev.confidence = confidence;
  ev.timestampNanos = timestampNanos;
  ev.outcome = DetectionOutcome::kConfirmed;
  ev.wakeWordIndex = wakeWordIndex_;
  // Rare detection edge (logging + listener hand-off may allocate): open the
  // documented escape hatch, exactly as Stage1Detector::confirm does.
  common::ScopedAllowAllocGuard allow;
  Log(LogLevel::kInfo, LogCategory::kDetect, "wake word CONFIRMED (streaming)", currentId_);
  if (onDetection_) onDetection_(ev);
}

void StreamingDetector::pushFrame(const float* mel, int nMels, uint64_t timestampNanos) {
  // Steady-state hot path: no heap allocation. A debug build aborts on any new/malloc
  // here (Stage 7 §5). The scorer must also be allocation-free.
  common::ScopedNoAllocGuard noAlloc;

  // Always advance the stateful streaming model by one frame — even during the
  // refractory window — so its recurrent/conv state never sees a gap. This is the
  // key difference from the windowed detector, which simply skips inference while
  // suppressed. NO re-windowing: exactly one score per frame.
  const float score = scorer_.scoreFrame(mel, nMels);
  lastScore_ = score;

  // Post-detection refractory: suppress re-fire for N frames so one spoken wake word
  // yields one detection, not a rapid double. Break any in-flight positive run.
  if (refractory_ > 0) {
    --refractory_;
    consecutive_ = 0;
    return;
  }

  // Same policy as the windowed path (Stage1Detector::runStage1), applied per frame:
  // threshold gate + M consecutive positive frames (posterior smoothing).
  const int needed = cfg_.stage1ConsecutiveWindows > 0 ? cfg_.stage1ConsecutiveWindows : 1;
  if (score >= cfg_.stage1Threshold) {
    if (consecutive_ == 0) currentId_ = mintCorrelationId();  // new positive run
    ++consecutive_;
    if (consecutive_ >= needed) {
      consecutive_ = 0;
      fire(timestampNanos, score);
    }
  } else {
    consecutive_ = 0;  // a below-threshold frame breaks the run
  }
}

void StreamingDetector::reset() {
  consecutive_ = 0;
  refractory_ = 0;
  currentId_ = {};
  lastScore_ = 0.0f;
  // idCounter_ intentionally NOT reset: correlation ids stay monotonic across resets.
}

}  // namespace aura::detect
