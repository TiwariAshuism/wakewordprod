// PROJECT AURA — core/config/Config.h
//
// Responsibilities : the resolved, fully-populated immutable Config snapshot
//                    (Stage 7 §3.2/§9). A resolved Config is always complete — no
//                    consumer null-checks a field (Stage 7 §9).
// Dependencies     : core/common only (Row 0).
// Thread ownership : read-only after startup from any thread; published as
//                    shared_ptr<const Config> (Stage 7 §3.2).
//
// v0 scope: compiled-in defaults only (no remote config / platform overlay).
#ifndef AURA_CONFIG_CONFIG_H
#define AURA_CONFIG_CONFIG_H

#include <cstddef>
#include <cstdint>
#include <string>

#include "core/common/ring_buffer.h"

namespace aura::config {

// Feature front-end parameters. MUST match the placeholder KWS model's training
// front-end (Stage 7 M3 integration risk) — see tools/convert_kws_model.py.
struct FeatureConfig {
  uint32_t sampleRate = 16000;
  int fftSize = 512;
  int winLength = 400;   // 25 ms @ 16 kHz
  int hopLength = 160;   // 10 ms @ 16 kHz
  int nMels = 40;
  float melFmin = 20.0f;
  float melFmax = 8000.0f;
  bool logMel = true;    // natural-log compression of mel energies
};

struct VadConfig {
  float speechThreshold = 0.5f;   // Silero probability gate; EnergyVad uses RMS proxy
  int minSpeechFrames = 3;        // debounce before opening the gate
  int hangoverFrames = 8;         // keep gate open briefly after speech ends
};

// Per-stage CONFIDENCE calibration (posterior calibration): maps a raw model score
// to a calibrated probability so the threshold operates on a well-scaled confidence.
// This is NOT PTQ 'quantization calibration' (which collects activation ranges to
// pick INT8 scales) — same word, unrelated mechanism. Identity defaults (method=none,
// a=1, b=0, T=1) are a no-op, so pre-existing configs behave exactly as before.
//   temperature : softmax(logits / T)          (T > 1 softens/lowers confidence)
//   platt       : p = sigmoid(a * z + b)        (z = logit or post-softmax prob)
struct StageCalibration {
  enum Method { kNone, kTemperature, kPlatt } method = kNone;
  float temperature = 1.0f;
  float plattA = 1.0f, plattB = 0.0f;
};

struct DetectConfig {
  int stage1WindowFrames = 100;   // log-Mel frames per Stage-1 inference window (~1 s)
  int stage1HopFrames = 10;       // slide the window every N frames
  float stage1Threshold = 0.35f;  // Stage-1 gate (kept low-ish for recall on marginal live
                                  // scores); Stage-2 cascade below does the FA filtering.
  int stage1ConsecutiveWindows = 1;  // require M consecutive positive windows before firing
                                     // (M=1 for the hey-aura model: on-device live speech scores
                                     //  are marginal ~0.5-0.76 and oscillate, so M>=2 never
                                     //  confirms; benchmark already flagged M-of-N as
                                     //  over-conservative here. Trade: slightly higher FA.)
  int refractoryFrames = 100;     // suppress re-fire for N frames (~1s) after a detection
                                  // (one spoken wake word => one detection, not a rapid double)
  int stage1NumClasses = 2;       // hey-aura model: 2-class {not-wake, hey-aura} (tools/heym_train.py)
  int stage1TargetClass = 1;      // "hey aura" class index
  bool softmaxOutput = true;      // model emits logits -> softmax; else raw prob

  // --- Stage-2 verifier (two-stage cascade, Stage 7 §3.11/§7.3) ---
  // On a Stage-1 trigger, a second (independent) model verifies before confirming;
  // both must agree, which cuts false accepts. Disabled or with no Stage-2 backend
  // wired, the cascade is Stage-1-only (back-compatible).
  //
  // DEFAULT OFF for the current placeholder: the shipped Stage-1 (dscnn) already
  // measures ~0% false-accept @0.5, so requiring Stage-2 agreement only reduces recall
  // (72.8% -> 55.9% on the noisy test) with no FP to remove. The cascade earns its keep
  // when Stage-1 is a cheaper/noisier always-on model (FP to filter, or a power win from
  // a tiny always-on + accurate on-demand model) — which needs the benchmark harness to
  // quantify. The infra + tests are in place; flip this on when it's measurably justified.
  bool stage2Enabled = false;     // OFF: on the user's off-distribution live voice the Stage-2
                                  // verifier (same training data) rejects real "hey aura" too — it
                                  // makes correlated errors, so it kills recall. Re-enable once
                                  // Stage-2 is retrained to be genuinely independent/stronger.
  float stage2Threshold = 0.5f;   // Stage-2 softmax[target] gate
  int stage2NumClasses = 2;
  int stage2TargetClass = 1;

  // Per-stage confidence calibration (see StageCalibration above). Identity by
  // default => fully back-compatible. Populated at engine init from the model's
  // labels.json sidecar (core/config/calibration_sidecar).
  StageCalibration stage1Calibration{}, stage2Calibration{};
};

struct ModelConfig {
  std::string stage1ModelFile = "aura.onnx";          // Stage-1 (always-on, tiny) — dscnn (hey-aura)
  std::string stage2ModelFile = "aura_stage2.onnx";   // Stage-2 (verifier) — cnn (hey-aura)
  std::string vadModelFile = "silero_vad.onnx";
  std::string stage1WakeWord = "hey aura";
};

struct AudioConfig {
  uint32_t sampleRate = 16000;
  uint8_t channels = 1;
  int captureFrames = 160;        // 10 ms capture blocks
  size_t pcmSlotFrames = 160;     // one slot == one 10 ms block
  size_t pcmSlotCount = 32;       // raw-PCM ring depth
  size_t featureSlotCount = 256;  // log-Mel feature ring depth
  common::BackpressurePolicy backpressure = common::BackpressurePolicy::kDropOldest;
};

// The complete snapshot.
struct Config {
  AudioConfig audio{};
  FeatureConfig features{};
  VadConfig vad{};
  DetectConfig detect{};
  ModelConfig models{};
  size_t inferenceArenaBytes = 4u * 1024 * 1024;  // per-backend scratch (Stage 7 §5)
};

}  // namespace aura::config

#endif  // AURA_CONFIG_CONFIG_H
