// PROJECT AURA — core/common/ids.h
//
// Responsibilities : CorrelationId + the public detection/event value types that
//                    cross the core/ -> SDK boundary (Stage 7 §4, §12).
// Dependencies     : none (foundation).
// Thread ownership : value types; CorrelationId is minted on the Audio thread at
//                    VadTriggered (Stage 7 §7.3) and read on every downstream thread.
// Memory ownership : plain values; no heap.
// Lifecycle        : ephemeral; one CorrelationId per detection cascade.
//
// NOTE (judgment call, flagged in REPORT.md): the SAS references these types in
// its §4 signatures but never defines their fields. The layouts below are our
// design, faithful to the documented behaviour ("DetectionEvent{CorrelationId,
// confidence, timestamp}" in sequence 8.3; DetectionOutcome::Confirmed in the
// Stage 9 §5 golden test).
#ifndef AURA_COMMON_IDS_H
#define AURA_COMMON_IDS_H

#include <cstdint>

namespace aura::common
{

  // A 128-bit correlation id, opaque to consumers. Minted once per cascade at
  // VadTriggered and threaded through every log line / telemetry event for that
  // cascade (Stage 7 §12 / ADR-Tracing). Deterministically constructed from a
  // monotonically increasing counter here (NOT time/random) so golden-fixture
  // replay is bit-reproducible (Stage 7 §14 determinism constraint).
  struct CorrelationId
  {
    uint64_t hi = 0;
    uint64_t lo = 0;

    constexpr bool operator==(const CorrelationId &o) const { return hi == o.hi && lo == o.lo; }
    constexpr bool operator!=(const CorrelationId &o) const { return !(*this == o); }
    constexpr bool valid() const { return hi != 0 || lo != 0; }
  };

  // Outcome of one detection cascade (Stage 9 §5 references ::Confirmed).
  // v0 is Stage-1-only, so Stage2Rejected / speaker outcomes are defined but the
  // cascade never reaches them (Stage-2 + speaker verification skipped — flagged).
  enum class DetectionOutcome : uint8_t
  {
    kRejected = 0,    // VAD opened but Stage-1 rejected
    kConfirmed,       // Stage-1 fired (v0 terminal state)
    kStage2Rejected,  // reserved (Stage-2 not built in v0)
    kSpeakerRejected, // reserved (speaker verification not built in v0)
  };

  // Emitted to IWakeWordListener::onWakeWordDetected (Stage 7 §4, sequence 8.3).
  struct DetectionEvent
  {
    CorrelationId correlationId{};
    float confidence = 0.0f;     // Stage-1 score in [0,1]
    uint64_t timestampNanos = 0; // capture-clock monotonic ns at confirmation
    DetectionOutcome outcome = DetectionOutcome::kRejected;
    uint32_t wakeWordIndex = 0; // which configured wake word matched
  };

  // Engine lifecycle states surfaced via IWakeWordListener::onStateChanged.
  enum class EngineState : uint8_t
  {
    kUninitialized = 0,
    kInitialized,
    kStarting,
    kRunning,
    kStopping,
    kStopped,
    kError,
  };

} // namespace aura::common

#endif // AURA_COMMON_IDS_H
