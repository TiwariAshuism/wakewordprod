// PROJECT AURA — core/detect/Stage1Detector.h
//
// Responsibilities : Stage-1-only cascade orchestration (Stage 7 §3.11/§7.3). On a
//                    VAD-open edge it mints a CorrelationId and runs the Stage-1
//                    model over a sliding log-Mel window; on trigger it emits a
//                    DetectionEvent. Threads the CorrelationId through every state
//                    transition (Stage 7 §12 / ADR-Tracing).
// Dependencies     : core/runtime, core/features, core/statemachine (Row 6).
// Thread ownership : runs on the Inference thread; owns no thread of its own.
// Memory ownership : owns the mel-window buffer + one Arena for building the input
//                    tensor and receiving the backend output. Owns no model tensors
//                    directly (delegates to runtime/).
//
// SCOPE GAP (flagged): Stage-2 verifier and speaker verification are NOT built.
// The cascade terminates at Stage-1 (DetectionConfirmed) — see REPORT.md.
#ifndef AURA_DETECT_STAGE1DETECTOR_H
#define AURA_DETECT_STAGE1DETECTOR_H

#include <functional>
#include <vector>

#include "core/common/ids.h"
#include "core/common/tensor.h"
#include "core/config/Config.h"
#include "core/features/FeatureFrame.h"
#include "core/runtime/IInferenceBackend.h"
#include "core/statemachine/IStateMachine.h"

namespace aura::detect {

// Cascade states (Stage 7 §7.3). Speaker-verification state omitted (out of scope).
enum class CascadeState : uint8_t {
  kIdle = 0, kVadTriggered, kStage1Running, kStage2Running, kDetectionConfirmed
};
enum class CascadeEvent : uint8_t {
  kVadOpened = 0, kVadClosed, kStage1Started, kStage1Fired, kStage1Rejected,
  kStage2Fired, kStage2Rejected
};

class Stage1Detector {
 public:
  // stage2Backend is optional: nullptr (or cfg.stage2Enabled == false) => Stage-1-only
  // cascade (back-compatible). When present, a Stage-1 trigger must be confirmed by the
  // Stage-2 verifier before a DetectionEvent is emitted (Stage 7 §7.3).
  Stage1Detector(runtime::IInferenceBackend& backend, const config::DetectConfig& detectCfg,
                 int nMels, uint32_t wakeWordIndex,
                 runtime::IInferenceBackend* stage2Backend = nullptr);

  using DetectionCallback = std::function<void(const common::DetectionEvent&)>;
  void setOnDetection(DetectionCallback cb) { onDetection_ = std::move(cb); }

  // Feed one log-Mel feature frame (with its VAD speech flag). Runs on the
  // Inference thread. Allocation-free after construction except the (rare) log
  // line on a detection edge.
  void pushFeature(const features::FeatureFrame& frame);

  void reset();
  CascadeState state() const { return fsm_.state(); }

 private:
  common::CorrelationId mintCorrelationId();
  void runStage1(uint64_t timestampNanos);
  void runStage2(uint64_t timestampNanos);
  void confirm(uint64_t timestampNanos, float confidence);
  float scoreFromOutput(const common::TensorView& out, int numClasses, int targetClass) const;

  runtime::IInferenceBackend& backend_;
  runtime::IInferenceBackend* stage2Backend_ = nullptr;
  config::DetectConfig cfg_;
  int nMels_;
  uint32_t wakeWordIndex_;

  statemachine::StateMachine<CascadeState, CascadeEvent> fsm_;
  common::Arena arena_;

  std::vector<float> window_;     // stage1WindowFrames * nMels, row-major
  int framesFilled_ = 0;
  int framesSinceInfer_ = 0;
  int refractory_ = 0;
  int consecutivePositive_ = 0;   // posterior smoothing: count of consecutive >=threshold windows
  bool prevSpeech_ = false;

  common::CorrelationId currentId_{};
  uint64_t idCounter_ = 0;        // deterministic (Stage 7 §14) — not time/random
  float lastScore_ = 0.0f;
  uint64_t lastTs_ = 0;

  DetectionCallback onDetection_;
};

}  // namespace aura::detect

#endif  // AURA_DETECT_STAGE1DETECTOR_H
