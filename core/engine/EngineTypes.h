// PROJECT AURA — core/engine/EngineTypes.h
//
// Value types used by the IWakeWordEngine facade (Stage 7 §4). These are
// referenced-but-undefined in the SAS; the layouts are our design (flagged).
#ifndef AURA_ENGINE_ENGINETYPES_H
#define AURA_ENGINE_ENGINETYPES_H

#include <filesystem>
#include <string>

#include "core/common/error.h"
#include "core/common/ids.h"

namespace aura::engine {

// Options passed to IWakeWordEngine::initialize(). If modelDir is empty, model
// loading from storage is skipped (used by host tests with a pre-provisioned /
// fake backend) — flagged in REPORT.md.
struct EngineOptions {
  std::filesystem::path modelDir{};    // where stage1/vad model files live; empty => skip loading
  bool synchronousForTest = false;     // true => no threads; drive via pumpForTest()
};

// One configured wake word (IWakeWordEngine::addWakeWord).
struct WakeWordSpec {
  std::string id;          // stable identifier (e.g. "marvin")
  std::string phrase;      // human-readable phrase
  float threshold = 0.6f;  // per-word Stage-1 threshold override
};

// Speaker enrollment request (enrollSpeaker) — NOT implemented in v0 (flagged).
struct SpeakerEnrollmentRequest {
  std::string speakerId;
};

// Surfaced via IWakeWordListener::onError.
struct EngineError {
  common::ErrorCode code = common::ErrorCode::kUnknown;
  std::string message;
};

}  // namespace aura::engine

#endif  // AURA_ENGINE_ENGINETYPES_H
