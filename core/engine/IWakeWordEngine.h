// PROJECT AURA — core/engine/IWakeWordEngine.h
//
// Responsibilities : the top-level facade composing every module below (Stage 7
//                    §2 Row 8, §4).
// Dependencies     : all lower rows (Row 8).
// Thread ownership : listener callbacks are invoked ONLY on the Callback thread —
//                    never Audio or Inference — so SDK/app code may safely block
//                    inside them (verbatim Stage 7 §4 contract).
#ifndef AURA_ENGINE_IWAKEWORDENGINE_H
#define AURA_ENGINE_IWAKEWORDENGINE_H

#include <string>

#include "core/common/ids.h"
#include "core/common/result.h"
#include "core/engine/EngineTypes.h"

namespace aura::engine {

class IWakeWordListener {
 public:
  virtual ~IWakeWordListener() = default;
  virtual void onWakeWordDetected(const common::DetectionEvent& event) = 0;
  virtual void onError(const EngineError& error) = 0;
  virtual void onStateChanged(common::EngineState newState) = 0;
};
// Invoked only on the Callback thread (Stage 7 §4).

// Exact signature per Stage 7 §4.
class IWakeWordEngine {
 public:
  virtual ~IWakeWordEngine() = default;
  virtual common::Result<void> initialize(const EngineOptions& options) = 0;
  virtual common::Result<void> start() = 0;
  virtual common::Result<void> stop() = 0;
  virtual common::Result<void> addWakeWord(const WakeWordSpec& spec) = 0;
  virtual common::Result<void> removeWakeWord(const std::string& id) = 0;
  virtual common::Result<void> enrollSpeaker(const SpeakerEnrollmentRequest& request) = 0;
  virtual void setListener(IWakeWordListener* listener) = 0;  // non-owning
};

}  // namespace aura::engine

#endif  // AURA_ENGINE_IWAKEWORDENGINE_H
