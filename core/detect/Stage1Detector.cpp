// PROJECT AURA — core/detect/Stage1Detector.cpp
#include "core/detect/Stage1Detector.h"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstring>

#include "core/common/log.h"
#include "core/common/noalloc.h"

namespace aura::detect {

using common::CorrelationId;
using common::DetectionEvent;
using common::DetectionOutcome;
using common::LogCategory;
using common::LogLevel;
using common::TensorView;

namespace {
// Cascade transition function (Stage 7 §7.3 subset). After a Stage-1 rejection we
// return to VadTriggered (not Idle) so the detector keeps scanning while the VAD
// gate stays open on a continuous utterance — a small, documented practical
// refinement of the diagram (flagged in REPORT.md).
CascadeState transition(CascadeState s, const CascadeEvent& e) {
  switch (s) {
    case CascadeState::kIdle:
      return e == CascadeEvent::kVadOpened ? CascadeState::kVadTriggered : s;
    case CascadeState::kVadTriggered:
      if (e == CascadeEvent::kStage1Started) return CascadeState::kStage1Running;
      if (e == CascadeEvent::kVadClosed) return CascadeState::kIdle;
      return s;
    case CascadeState::kStage1Running:
      // Stage-1 accumulated enough consecutive positives -> hand to Stage-2 (Stage 7 §7.3).
      if (e == CascadeEvent::kStage1Fired) return CascadeState::kStage2Running;
      if (e == CascadeEvent::kStage1Rejected) return CascadeState::kVadTriggered;
      if (e == CascadeEvent::kVadClosed) return CascadeState::kIdle;
      return s;
    case CascadeState::kStage2Running:
      if (e == CascadeEvent::kStage2Fired) return CascadeState::kDetectionConfirmed;
      if (e == CascadeEvent::kStage2Rejected) return CascadeState::kVadTriggered;
      if (e == CascadeEvent::kVadClosed) return CascadeState::kIdle;
      return s;
    case CascadeState::kDetectionConfirmed:
      if (e == CascadeEvent::kVadClosed) return CascadeState::kIdle;
      if (e == CascadeEvent::kVadOpened) return CascadeState::kVadTriggered;  // re-arm
      return s;
  }
  return s;
}
}  // namespace

Stage1Detector::Stage1Detector(runtime::IInferenceBackend& backend,
                               const config::DetectConfig& detectCfg, int nMels,
                               uint32_t wakeWordIndex, runtime::IInferenceBackend* stage2Backend)
    : backend_(backend),
      stage2Backend_(stage2Backend),
      cfg_(detectCfg),
      nMels_(nMels),
      wakeWordIndex_(wakeWordIndex),
      fsm_(CascadeState::kIdle, transition) {
  window_.assign(static_cast<size_t>(cfg_.stage1WindowFrames) * nMels_, 0.0f);
  // Arena sized for the flattened input window + a generous output allowance.
  const size_t inputBytes = window_.size() * sizeof(float);
  arena_.reserve(inputBytes + 64 * 1024);
}

CorrelationId Stage1Detector::mintCorrelationId() {
  ++idCounter_;  // deterministic, reproducible across golden replays (Stage 7 §14)
  return CorrelationId{0xA0DA0000ull | wakeWordIndex_, idCounter_};
}

float Stage1Detector::scoreFromOutput(const TensorView& out, int /*numClasses*/,
                                      int targetClass) const {
  const int64_t n = out.shape[0];
  if (n <= 0 || out.data == nullptr) return 0.0f;
  if (n == 1) {  // single-logit / prob model
    const float v = out.data[0];
    return v > 1.0f || v < 0.0f ? 1.0f / (1.0f + std::exp(-v)) : v;  // sigmoid if logit
  }
  const int target = std::clamp(targetClass, 0, static_cast<int>(n) - 1);
  if (!cfg_.softmaxOutput) return std::clamp(out.data[target], 0.0f, 1.0f);
  // softmax over classes, return target-class probability.
  float maxLogit = out.data[0];
  for (int64_t i = 1; i < n; ++i) maxLogit = std::max(maxLogit, out.data[i]);
  float sum = 0.0f;
  for (int64_t i = 0; i < n; ++i) sum += std::exp(out.data[i] - maxLogit);
  return std::exp(out.data[target] - maxLogit) / std::max(sum, 1e-9f);
}

void Stage1Detector::runStage1(uint64_t timestampNanos) {
  fsm_.dispatch(CascadeEvent::kStage1Started);
  arena_.reset();

  // Linearize the circular mel window into arena input, temporal order.
  const int W = cfg_.stage1WindowFrames;
  float* in = arena_.allocateFloats(window_.size());
  if (!in) return;
  // window_ is filled circularly; when full, oldest frame is at framesFilled_==W
  // starting at (writePos). We store in write order and it is already contiguous
  // per frame; copy frames in the order they were written.
  std::memcpy(in, window_.data(), window_.size() * sizeof(float));

  TensorView input;
  input.data = in;
  input.rank = 3;
  input.shape[0] = 1;
  input.shape[1] = W;
  input.shape[2] = nMels_;

  auto out = backend_.infer(input, arena_);
  if (!out) {
    common::ScopedAllowAllocGuard allow;  // rare error path, off the steady hot path
    Log(LogLevel::kWarn, LogCategory::kRuntime, "stage1 infer failed", currentId_);
    fsm_.dispatch(CascadeEvent::kStage1Rejected);
    return;
  }
  lastScore_ = scoreFromOutput(out.value(), cfg_.stage1NumClasses, cfg_.stage1TargetClass);
  lastTs_ = timestampNanos;

  // Posterior smoothing: a single window over threshold is not enough — require M
  // consecutive positive windows (classic KWS posterior handling). This suppresses
  // transient-noise false accepts independent of the model.
  const int needed = cfg_.stage1ConsecutiveWindows > 0 ? cfg_.stage1ConsecutiveWindows : 1;
  if (lastScore_ >= cfg_.stage1Threshold) {
    ++consecutivePositive_;
    if (consecutivePositive_ >= needed) {
      consecutivePositive_ = 0;
      fsm_.dispatch(CascadeEvent::kStage1Fired);  // -> Stage2Running
      runStage2(timestampNanos);
    } else {
      // positive but not yet enough consecutive windows — stay armed, keep scanning
      fsm_.dispatch(CascadeEvent::kStage1Rejected);
    }
  } else {
    consecutivePositive_ = 0;  // a below-threshold window breaks the run
    fsm_.dispatch(CascadeEvent::kStage1Rejected);
  }
}

// Stage-2 verification (Stage 7 §7.3). Re-runs an independent model over the same
// window that triggered Stage-1; both must agree before confirming. With no Stage-2
// backend (or stage2Enabled == false) it passes through, i.e. Stage-1-only cascade.
// The input tensor built by runStage1 lives at the front of the arena; we reuse it.
void Stage1Detector::runStage2(uint64_t timestampNanos) {
  if (!stage2Backend_ || !cfg_.stage2Enabled) {
    fsm_.dispatch(CascadeEvent::kStage2Fired);
    confirm(timestampNanos, lastScore_);
    return;
  }
  // The window is still in window_; re-linearize into a fresh arena region so the
  // Stage-1 output (also in the arena) isn't clobbered.
  TensorView input;
  float* in = arena_.allocateFloats(window_.size());
  if (!in) {  // arena exhausted: fail safe (do not confirm on a broken verify)
    fsm_.dispatch(CascadeEvent::kStage2Rejected);
    return;
  }
  std::memcpy(in, window_.data(), window_.size() * sizeof(float));
  input.data = in;
  input.rank = 3;
  input.shape[0] = 1;
  input.shape[1] = cfg_.stage1WindowFrames;
  input.shape[2] = nMels_;

  auto out = stage2Backend_->infer(input, arena_);
  if (!out) {
    common::ScopedAllowAllocGuard allow;
    Log(LogLevel::kWarn, LogCategory::kRuntime, "stage2 infer failed", currentId_);
    fsm_.dispatch(CascadeEvent::kStage2Rejected);
    return;
  }
  const float s2 = scoreFromOutput(out.value(), cfg_.stage2NumClasses, cfg_.stage2TargetClass);
  if (s2 >= cfg_.stage2Threshold) {
    fsm_.dispatch(CascadeEvent::kStage2Fired);
    confirm(timestampNanos, s2);
  } else {
    common::ScopedAllowAllocGuard allow;
    Log(LogLevel::kDebug, LogCategory::kDetect, "stage2 rejected (verifier disagreed)", currentId_);
    fsm_.dispatch(CascadeEvent::kStage2Rejected);
  }
}

void Stage1Detector::confirm(uint64_t timestampNanos, float confidence) {
  refractory_ = cfg_.refractoryFrames;
  DetectionEvent ev;
  ev.correlationId = currentId_;
  ev.confidence = confidence;
  ev.timestampNanos = timestampNanos;
  ev.outcome = DetectionOutcome::kConfirmed;
  ev.wakeWordIndex = wakeWordIndex_;
  // Rare edge (logging + listener hand-off may allocate): open the escape hatch.
  common::ScopedAllowAllocGuard allow;
  Log(LogLevel::kInfo, LogCategory::kDetect,
      stage2Backend_ && cfg_.stage2Enabled ? "wake word CONFIRMED (stage1+stage2)"
                                           : "wake word CONFIRMED (stage1)",
      currentId_);
  if (onDetection_) onDetection_(ev);
}

void Stage1Detector::pushFeature(const features::FeatureFrame& frame) {
  if (refractory_ > 0) --refractory_;

  // Append this frame's mel row into the window buffer (write order == temporal).
  // Shift-by-one-frame keeps the buffer temporally contiguous for the model.
  const size_t row = static_cast<size_t>(nMels_);
  if (framesFilled_ < cfg_.stage1WindowFrames) {
    std::memcpy(window_.data() + framesFilled_ * row, frame.mel, row * sizeof(float));
    ++framesFilled_;
  } else {
    std::memmove(window_.data(), window_.data() + row, (window_.size() - row) * sizeof(float));
    std::memcpy(window_.data() + (window_.size() - row), frame.mel, row * sizeof(float));
  }

  const bool speech = frame.speech;
  if (speech && !prevSpeech_) {  // VAD-open edge: new cascade
    if (fsm_.state() == CascadeState::kIdle || fsm_.state() == CascadeState::kDetectionConfirmed) {
      currentId_ = mintCorrelationId();
      fsm_.dispatch(CascadeEvent::kVadOpened);
      Log(LogLevel::kDebug, LogCategory::kVad, "VAD triggered", currentId_);
    }
    framesSinceInfer_ = cfg_.stage1HopFrames;  // allow inference as soon as window is ready
  } else if (!speech && prevSpeech_) {  // VAD-close edge
    fsm_.dispatch(CascadeEvent::kVadClosed);
    // NOTE: do NOT reset consecutivePositive_ here. Smoothing counts consecutive
    // positive *inference windows*; a brief VAD flicker (e.g. an amplitude dip in
    // continuous speech) only pauses inference, it must not break the run. The count
    // is reset only by a below-threshold inference window (see runStage1) or reset().
  }
  prevSpeech_ = speech;
  ++framesSinceInfer_;

  const bool armed = fsm_.state() == CascadeState::kVadTriggered ||
                     fsm_.state() == CascadeState::kStage1Running;
  if (speech && armed && refractory_ == 0 && framesFilled_ >= cfg_.stage1WindowFrames &&
      framesSinceInfer_ >= cfg_.stage1HopFrames) {
    framesSinceInfer_ = 0;
    runStage1(frame.captureTimestampNanos);
  }
}

void Stage1Detector::reset() {
  std::fill(window_.begin(), window_.end(), 0.0f);
  framesFilled_ = 0;
  framesSinceInfer_ = 0;
  refractory_ = 0;
  consecutivePositive_ = 0;
  prevSpeech_ = false;
  currentId_ = {};
  lastScore_ = 0.0f;
  while (fsm_.state() != CascadeState::kIdle) fsm_.dispatch(CascadeEvent::kVadClosed);
}

}  // namespace aura::detect
