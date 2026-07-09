// PROJECT AURA — core/engine/WakeWordEngine.cpp
#include "core/engine/WakeWordEngine.h"

#include <algorithm>
#include <chrono>
#include <cstring>
#include <thread>
#include <utility>

#include "core/common/log.h"
#include "core/common/noalloc.h"
#include "core/config/calibration_sidecar.h"

namespace aura::engine {

using common::Err;
using common::ErrorCode;
using common::LogCategory;
using common::LogLevel;
using common::Result;

WakeWordEngine::WakeWordEngine(platform::IPlatform& platform,
                               std::shared_ptr<const config::Config> config,
                               std::unique_ptr<runtime::IInferenceBackend> stage1Backend,
                               std::unique_ptr<vad::IVad> vad,
                               std::unique_ptr<runtime::IInferenceBackend> stage2Backend)
    : platform_(platform),
      config_(std::move(config)),
      vad_(std::move(vad)),
      backend_(std::move(stage1Backend)),
      stage2Backend_(std::move(stage2Backend)) {
  audio_ = std::make_unique<audio::AudioPipeline>(config_->audio, scheduler_);
  mel_ = std::make_unique<features::LogMelExtractor>(config_->features);
  gate_ = std::make_unique<vad::VadGate>(*vad_, config_->vad);
  featureRing_.reserve(config_->audio.featureSlotCount, common::BackpressurePolicy::kDropOldest);
}

WakeWordEngine::~WakeWordEngine() { (void)stop(); }

Result<void> WakeWordEngine::initialize(const EngineOptions& options) {
  synchronous_ = options.synchronousForTest;

  // Start from the immutable snapshot's DetectConfig; we may overlay CONFIDENCE
  // calibration parsed from the model's labels.json below. Identity if none.
  detectCfg_ = config_->detect;

  // Load the Stage-1 model from storage (unless running with a pre-provisioned /
  // fake backend, i.e. empty modelDir).
  if (!options.modelDir.empty()) {
    stage1Model_ = std::make_unique<model::ModelManager>(platform_.storage(),
                                                         common::ModelSlot::kStage1);
    auto staged = stage1Model_->stage(options.modelDir / config_->models.stage1ModelFile);
    if (!staged) {
      common::Log(LogLevel::kError, LogCategory::kModel, "stage1 model load failed");
      return staged.error();
    }
    auto activated = stage1Model_->activate(staged.value());
    if (!activated) return activated.error();
    auto loaded = backend_->loadModel(staged.value());
    if (!loaded) return loaded.error();

    // Stage-2 verifier model (two-stage cascade). Optional: if the backend or file is
    // absent, the cascade runs Stage-1-only (graceful).
    if (stage2Backend_ && config_->detect.stage2Enabled) {
      stage2Model_ = std::make_unique<model::ModelManager>(platform_.storage(),
                                                           common::ModelSlot::kStage2);
      auto s2 = stage2Model_->stage(options.modelDir / config_->models.stage2ModelFile);
      if (s2 && stage2Model_->activate(s2.value()) && stage2Backend_->loadModel(s2.value())) {
        common::Log(LogLevel::kInfo, LogCategory::kModel, "stage2 verifier model loaded");
      } else {
        common::Log(LogLevel::kWarn, LogCategory::kModel,
                    "stage2 model unavailable; running Stage-1-only cascade");
        stage2Backend_.reset();  // fall back to Stage-1-only
      }
    }

    // Confidence-calibration sidecar (labels.json). Optional + tolerant: a missing or
    // malformed file leaves detectCfg_ at identity calibration (no behavior change).
    // (This is posterior confidence calibration, NOT PTQ 'quantization calibration'.)
    auto cal = platform_.storage().mapReadOnly(options.modelDir / "labels.json");
    if (cal) {
      const auto parsed = config::parseCalibrationSidecar(
          static_cast<const char*>(cal.value().data), cal.value().size);
      detectCfg_.stage1Calibration = parsed.stage1;
      detectCfg_.stage2Calibration = parsed.stage2;
      platform_.storage().unmap(cal.value());
      common::Log(LogLevel::kInfo, LogCategory::kModel, "confidence calibration loaded (labels.json)");
    } else {
      common::Log(LogLevel::kInfo, LogCategory::kModel,
                  "no labels.json calibration; using identity confidence calibration");
    }
  } else {
    common::Log(LogLevel::kInfo, LogCategory::kModel,
                "no modelDir: assuming pre-provisioned/fake backend (test path)");
  }

  detector_ = std::make_unique<detect::Stage1Detector>(
      *backend_, detectCfg_, config_->features.nMels, /*wakeWordIndex=*/0,
      stage2Backend_ ? stage2Backend_.get() : nullptr);
  detector_->setOnDetection([this](const common::DetectionEvent& ev) {
    enqueueCallback(CallbackMsg{CallbackMsg::Kind::kDetection, ev, {}, {}});
  });

  state_ = common::EngineState::kInitialized;
  postState(state_);
  return {};
}

Result<void> WakeWordEngine::addWakeWord(const WakeWordSpec& spec) {
  if (!wakeWords_.empty()) {
    // v0 supports a single wake word; multi-wake-word cascade is a real feature,
    // deferred (flagged in REPORT.md).
    return Err(ErrorCode::kUnimplemented, "v0 supports a single wake word");
  }
  wakeWords_.push_back(spec);
  common::Log(LogLevel::kInfo, LogCategory::kEngine, "wake word registered");
  return {};
}

Result<void> WakeWordEngine::removeWakeWord(const std::string& /*id*/) {
  return Err(ErrorCode::kUnimplemented, "removeWakeWord not implemented in v0");
}

Result<void> WakeWordEngine::enrollSpeaker(const SpeakerEnrollmentRequest& /*request*/) {
  // Speaker verification (core/speaker) is OUT OF SCOPE for v0 (flagged).
  return Err(ErrorCode::kUnimplemented, "speaker enrollment not implemented in v0");
}

void WakeWordEngine::buildAudioSink() {
  audio_->setFrameSink([this](float* s, size_t n, uint64_t ts) {
    // Runs in-line on the Audio thread (Stage 7 §6). Allocation-free.
    (void)dsp_.process(s, n);                 // AGC -> AEC(no-op) -> NS, in place
    gateOpenForBlock_ = gate_->process(s, n); // VAD reads post-DSP audio (addendum §3)
    mel_->process(s, n, [this, ts](const float* mel, int nm) {
      features::FeatureFrame* slot = featureRing_.acquireWrite();
      if (!slot) return;
      const int m = std::min(nm, features::kMaxMels);
      std::memcpy(slot->mel, mel, static_cast<size_t>(m) * sizeof(float));
      slot->nMels = m;
      slot->speech = gateOpenForBlock_;
      slot->captureTimestampNanos = ts;
      featureRing_.commitWrite();
    });
  });
}

Result<void> WakeWordEngine::start() {
  if (!detector_) return Err(ErrorCode::kFailedPrecondition, "initialize() not called");
  if (wakeWords_.empty()) return Err(ErrorCode::kFailedPrecondition, "no wake word added");

  buildAudioSink();
  state_ = common::EngineState::kStarting;

  // Register the platform capture callback (delivers into the audio ring).
  common::AudioFormat fmt;
  fmt.sampleRate = config_->audio.sampleRate;
  fmt.channels = config_->audio.channels;
  fmt.format = common::SampleFormat::kInt16;
  auto started = platform_.audioInput().start(
      fmt, [this](const common::AudioFrameView& v, uint64_t ts) { audio_->onCaptureFrame(v, ts); });
  if (!started) return started.error();

  if (!synchronous_) {
    auto ar = audio_->start();
    if (!ar) return ar.error();
    inferenceThread_ = scheduler_.spawnLoop("aura-inference", scheduler::ThreadClass::kInference,
                                            [this] { inferenceThreadTick(); });
    callbackThread_ = scheduler_.spawnLoop("aura-callback", scheduler::ThreadClass::kCallback,
                                           [this] { callbackThreadTick(); });
  }

  state_ = common::EngineState::kRunning;
  postState(state_);
  common::Log(LogLevel::kInfo, LogCategory::kEngine, "engine running");
  return {};
}

Result<void> WakeWordEngine::stop() {
  if (state_ == common::EngineState::kStopped || state_ == common::EngineState::kUninitialized) {
    return {};
  }
  state_ = common::EngineState::kStopping;
  (void)platform_.audioInput().stop();
  if (audio_) (void)audio_->stop();
  scheduler_.joinAll();
  inferenceThread_ = nullptr;
  callbackThread_ = nullptr;
  state_ = common::EngineState::kStopped;
  return {};
}

void WakeWordEngine::inferenceThreadTick() {
  bool did = false;
  while (const features::FeatureFrame* slot = featureRing_.acquireRead()) {
    did = true;
    {
      common::ScopedNoAllocGuard noalloc;  // Inference-thread hot path (Stage 7 §6)
      detector_->pushFeature(*slot);
    }
    featureRing_.commitRead();
  }
  if (!did) std::this_thread::sleep_for(std::chrono::milliseconds(1));
}

void WakeWordEngine::callbackThreadTick() {
  CallbackMsg msg;
  bool have = false;
  {
    std::lock_guard<std::mutex> lock(cbMutex_);
    if (!cbQueue_.empty()) {
      msg = cbQueue_.front();
      cbQueue_.pop();
      have = true;
    }
  }
  if (!have) {
    std::this_thread::sleep_for(std::chrono::milliseconds(1));
    return;
  }
  if (!listener_) return;
  switch (msg.kind) {
    case CallbackMsg::Kind::kDetection: listener_->onWakeWordDetected(msg.detection); break;
    case CallbackMsg::Kind::kState: listener_->onStateChanged(msg.state); break;
    case CallbackMsg::Kind::kError: listener_->onError(msg.error); break;
  }
}

void WakeWordEngine::enqueueCallback(CallbackMsg msg) {
  std::lock_guard<std::mutex> lock(cbMutex_);
  cbQueue_.push(std::move(msg));
}

void WakeWordEngine::postState(common::EngineState s) {
  enqueueCallback(CallbackMsg{CallbackMsg::Kind::kState, {}, s, {}});
}

void WakeWordEngine::pumpForTest() {
  // Synchronous, thread-free pipeline drive for deterministic golden replay.
  audio_->drainOnceForTest();  // audio ring -> DSP/features/VAD -> feature ring
  while (const features::FeatureFrame* slot = featureRing_.acquireRead()) {
    detector_->pushFeature(*slot);
    featureRing_.commitRead();
  }
  // Deliver any queued callbacks (detection/state) to the listener on this thread.
  for (;;) {
    CallbackMsg msg;
    {
      std::lock_guard<std::mutex> lock(cbMutex_);
      if (cbQueue_.empty()) break;
      msg = cbQueue_.front();
      cbQueue_.pop();
    }
    if (!listener_) continue;
    switch (msg.kind) {
      case CallbackMsg::Kind::kDetection: listener_->onWakeWordDetected(msg.detection); break;
      case CallbackMsg::Kind::kState: listener_->onStateChanged(msg.state); break;
      case CallbackMsg::Kind::kError: listener_->onError(msg.error); break;
    }
  }
}

}  // namespace aura::engine
