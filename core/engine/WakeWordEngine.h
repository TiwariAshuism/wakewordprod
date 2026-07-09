// PROJECT AURA — core/engine/WakeWordEngine.h
//
// The IWakeWordEngine facade (Row 8). Composes platform + config + scheduler +
// audio + dsp + features + vad + model + runtime + detect, and owns the Inference
// and Callback threads (audio/ owns the Audio thread). Listener callbacks are
// dispatched only on the Callback thread (Stage 7 §4).
//
// The inference backend and VAD are injected so the same facade serves both the
// Android build (OnnxRuntimeBackend + SileroVad) and host/golden tests
// (FakeInferenceBackend + EnergyVad).
#ifndef AURA_ENGINE_WAKEWORDENGINE_H
#define AURA_ENGINE_WAKEWORDENGINE_H

#include <memory>
#include <mutex>
#include <queue>
#include <vector>

#include "core/audio/AudioPipeline.h"
#include "core/config/Config.h"
#include "core/detect/Stage1Detector.h"
#include "core/dsp/DspChain.h"
#include "core/engine/IWakeWordEngine.h"
#include "core/features/FeatureFrame.h"
#include "core/features/LogMelExtractor.h"
#include "core/model/ModelManager.h"
#include "core/platform/IPlatform.h"
#include "core/runtime/IInferenceBackend.h"
#include "core/scheduler/Scheduler.h"
#include "core/vad/IVad.h"
#include "core/vad/VadGate.h"

namespace aura::engine {

class WakeWordEngine final : public IWakeWordEngine {
 public:
  WakeWordEngine(platform::IPlatform& platform, std::shared_ptr<const config::Config> config,
                 std::unique_ptr<runtime::IInferenceBackend> stage1Backend,
                 std::unique_ptr<vad::IVad> vad,
                 std::unique_ptr<runtime::IInferenceBackend> stage2Backend = nullptr);
  ~WakeWordEngine() override;

  common::Result<void> initialize(const EngineOptions& options) override;
  common::Result<void> start() override;
  common::Result<void> stop() override;
  common::Result<void> addWakeWord(const WakeWordSpec& spec) override;
  common::Result<void> removeWakeWord(const std::string& id) override;
  common::Result<void> enrollSpeaker(const SpeakerEnrollmentRequest& request) override;
  void setListener(IWakeWordListener* listener) override { listener_ = listener; }

  // Host/deterministic-test hook: run the whole pipeline synchronously (no
  // threads). Drains the audio ring -> DSP/features/VAD -> feature ring ->
  // detector -> callback queue -> listener, on the calling thread.
  void pumpForTest();

 private:
  void buildAudioSink();
  void inferenceThreadTick();
  void callbackThreadTick();
  void postState(common::EngineState s);

  struct CallbackMsg {
    enum class Kind { kDetection, kState, kError } kind;
    common::DetectionEvent detection{};
    common::EngineState state{};
    EngineError error{};
  };
  void enqueueCallback(CallbackMsg msg);

  platform::IPlatform& platform_;
  std::shared_ptr<const config::Config> config_;
  // Local, patchable copy of config_->detect: at init we overlay the model's
  // labels.json CONFIDENCE-calibration onto it, then build the detector from this copy
  // (the shared Config snapshot stays immutable). Identity when no sidecar is present.
  config::DetectConfig detectCfg_{};

  scheduler::Scheduler scheduler_;
  std::unique_ptr<audio::AudioPipeline> audio_;
  dsp::DspChain dsp_;
  std::unique_ptr<features::LogMelExtractor> mel_;
  std::unique_ptr<vad::IVad> vad_;
  std::unique_ptr<vad::VadGate> gate_;
  std::unique_ptr<model::ModelManager> stage1Model_;
  std::unique_ptr<model::ModelManager> stage2Model_;
  std::unique_ptr<runtime::IInferenceBackend> backend_;
  std::unique_ptr<runtime::IInferenceBackend> stage2Backend_;
  std::unique_ptr<detect::Stage1Detector> detector_;

  common::RingBuffer<features::FeatureFrame> featureRing_;
  bool gateOpenForBlock_ = false;  // updated per audio block, applied to mel frames

  scheduler::ManagedThread* inferenceThread_ = nullptr;
  scheduler::ManagedThread* callbackThread_ = nullptr;

  std::mutex cbMutex_;
  std::queue<CallbackMsg> cbQueue_;

  IWakeWordListener* listener_ = nullptr;  // non-owning (Stage 7 §4)
  common::EngineState state_ = common::EngineState::kUninitialized;
  std::vector<WakeWordSpec> wakeWords_;
  bool synchronous_ = false;
};

}  // namespace aura::engine

#endif  // AURA_ENGINE_WAKEWORDENGINE_H
