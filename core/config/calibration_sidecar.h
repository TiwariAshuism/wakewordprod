// PROJECT AURA — core/config/calibration_sidecar.h
//
// Responsibilities : a minimal, DEPENDENCY-FREE parser for the fixed labels.json
//                    CONFIDENCE-calibration block that ships alongside a model. It
//                    fills two StageCalibration values (Stage-1 + Stage-2). No JSON
//                    library is used or allowed here (Row 0, core/config depends on
//                    core/common only) — this is a tiny hand-rolled scanner over the
//                    single, agreed schema, not a general JSON parser.
// Dependencies     : core/config (Config.h), core/common — Row 0.
// Tolerance        : on a missing file / missing "calibration" block / malformed
//                    input, every field falls back to identity (method=none, a=1,
//                    b=0, T=1). Never throws, never allocates beyond small temporaries.
//
// NOTE: "calibration" here means CONFIDENCE calibration (posterior score scaling),
// NOT PTQ 'quantization calibration' (INT8 activation-range collection) — see
// StageCalibration in Config.h.
//
// Fixed schema (agreed):
//   {"wake_word":"hey aura","arch":"dscnn","num_classes":2,"target_index":1,
//    "labels":[...],
//    "calibration":{"method":"platt"|"temperature"|"none",
//                   "stage1":{"a":..,"b":..,"temperature":..},
//                   "stage2":{"a":..,"b":..,"temperature":..}}}
#ifndef AURA_CONFIG_CALIBRATION_SIDECAR_H
#define AURA_CONFIG_CALIBRATION_SIDECAR_H

#include <cstddef>
#include <string_view>

#include "core/config/Config.h"

namespace aura::config {

// The two per-stage confidence-calibration parameter sets parsed from labels.json.
struct CalibrationSidecar {
  StageCalibration stage1{};  // identity by default
  StageCalibration stage2{};  // identity by default
};

// Parse the fixed labels.json calibration block from a raw byte buffer. Tolerant:
// any missing/malformed input yields identity calibration. `data` need not be
// NUL-terminated; `size` bounds the scan.
CalibrationSidecar parseCalibrationSidecar(const char* data, std::size_t size);

// Convenience overload.
CalibrationSidecar parseCalibrationSidecar(std::string_view json);

}  // namespace aura::config

#endif  // AURA_CONFIG_CALIBRATION_SIDECAR_H
