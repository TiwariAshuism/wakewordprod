// PROJECT AURA — core/detect/StreamingDetector.h
//
// Responsibilities : the on-device streaming counterpart of Stage1Detector. Where
//                    Stage1Detector re-windows a sliding [W, nMels] buffer and runs a
//                    windowed classifier every hop, StreamingDetector consumes ONE
//                    wake-probability PER FRAME from a stateful streaming scorer (a
//                    streaming ONNX model that carries its own recurrent/conv state)
//                    and applies the SAME decision policy — threshold + M-of-N
//                    consecutive smoothing + refractory — per frame, with NO
//                    per-hop windowing. On a sustained positive run it emits a
//                    DetectionEvent, identical in shape to the windowed path.
// Dependencies     : core/config, core/common only (Row 6 — no OS/SDK/PAL, no
//                    higher-row modules). The scorer is abstracted behind
//                    IStreamingScorer so the host supplies a fake and the device
//                    supplies the streaming model, with no dependency inversion.
// Thread ownership : single-threaded per instance — the Inference thread. Owns no
//                    thread and no window buffer (the scorer owns its own state).
// Memory ownership : owns nothing heap after construction; the hot path (pushFrame)
//                    is allocation-free (guarded by ScopedNoAllocGuard), except the
//                    rare detection-edge log line + listener hand-off, which open the
//                    documented ScopedAllowAllocGuard escape hatch (mirrors
//                    Stage1Detector::confirm).
#ifndef AURA_DETECT_STREAMINGDETECTOR_H
#define AURA_DETECT_STREAMINGDETECTOR_H

#include <cstdint>
#include <functional>

#include "core/common/ids.h"
#include "core/config/Config.h"

namespace aura::detect {

// The per-frame scoring plugin point. A streaming wake-word model is STATEFUL: each
// call advances the model's internal state by exactly one frame and returns that
// frame's wake probability in [0,1]. On host, a fake returns scripted scores; on
// device, a streaming ONNX backend runs one step. This mirrors the role
// IInferenceBackend plays for the windowed detector, but at frame (not window)
// granularity — there is no re-windowing.
class IStreamingScorer {
 public:
  virtual ~IStreamingScorer() = default;
  // Advance the stateful model by one log-Mel frame and return its wake probability
  // in [0,1]. `mel` points at `n` contiguous floats (one frame). Must be
  // allocation-free (it runs inside the detector's no-alloc hot path).
  virtual float scoreFrame(const float* mel, int n) = 0;
};

// Per-frame streaming detector. Reuses DetectConfig fields verbatim so the operating
// point matches the windowed detector: stage1Threshold (per-frame gate),
// stage1ConsecutiveWindows (here: M consecutive positive FRAMES), refractoryFrames.
class StreamingDetector {
 public:
  StreamingDetector(IStreamingScorer& scorer, const config::DetectConfig& detectCfg,
                    uint32_t wakeWordIndex);

  using DetectionCallback = std::function<void(const common::DetectionEvent&)>;
  void setOnDetection(DetectionCallback cb) { onDetection_ = std::move(cb); }

  // Feed exactly one log-Mel frame ([nMels] floats) + its capture timestamp. Runs on
  // the Inference thread. Allocation-free after construction except the rare log line
  // / listener hand-off on a detection edge. The scorer is always invoked (even in
  // refractory) so the stateful streaming model never misses a frame.
  void pushFrame(const float* mel, int nMels, uint64_t timestampNanos);

  void reset();

  // Observability (test witnesses).
  int consecutive() const { return consecutive_; }
  int refractory() const { return refractory_; }
  float lastScore() const { return lastScore_; }

 private:
  common::CorrelationId mintCorrelationId();
  void fire(uint64_t timestampNanos, float confidence);

  IStreamingScorer& scorer_;
  config::DetectConfig cfg_;
  uint32_t wakeWordIndex_;

  int consecutive_ = 0;   // count of consecutive >= threshold frames (posterior smoothing)
  int refractory_ = 0;    // frames remaining in the post-detection suppression window

  common::CorrelationId currentId_{};
  uint64_t idCounter_ = 0;  // deterministic (Stage 7 §14) — not time/random
  float lastScore_ = 0.0f;

  DetectionCallback onDetection_;
};

}  // namespace aura::detect

#endif  // AURA_DETECT_STREAMINGDETECTOR_H
