// PROJECT AURA — core/config/calibration_sidecar.cpp
//
// A tiny, dependency-free scanner for the ONE fixed labels.json CONFIDENCE-calibration
// schema (see calibration_sidecar.h). It is deliberately NOT a general JSON parser:
// it locates the "calibration" object, reads its "method", then reads the numeric
// {a,b,temperature} out of the "stage1"/"stage2" sub-objects. Anything it cannot find
// or parse is left at its identity default, so the result is always usable.
#include "core/config/calibration_sidecar.h"

#include <cstdlib>
#include <string>

namespace aura::config {
namespace {

constexpr std::size_t kNpos = std::string_view::npos;

bool isWs(char c) { return c == ' ' || c == '\t' || c == '\n' || c == '\r'; }

// Return the index just past the ':' that follows the quoted key `"<key>"`, or kNpos.
std::size_t findKeyColon(std::string_view s, std::string_view key, std::size_t from) {
  std::string needle;
  needle.reserve(key.size() + 2);
  needle.push_back('"');
  needle.append(key.data(), key.size());
  needle.push_back('"');
  const std::size_t k = s.find(needle, from);
  if (k == kNpos) return kNpos;
  const std::size_t colon = s.find(':', k + needle.size());
  return colon == kNpos ? kNpos : colon + 1;
}

// Parse a JSON number starting at/after `pos` (skips leading whitespace). Returns
// false (and leaves `out` untouched) if `pos` is kNpos or no number is present.
bool parseNumberAt(std::string_view s, std::size_t pos, float& out) {
  if (pos == kNpos) return false;
  while (pos < s.size() && isWs(s[pos])) ++pos;
  const std::size_t start = pos;
  while (pos < s.size()) {
    const char c = s[pos];
    if ((c >= '0' && c <= '9') || c == '-' || c == '+' || c == '.' || c == 'e' || c == 'E') {
      ++pos;
    } else {
      break;
    }
  }
  if (pos == start) return false;
  const std::string tmp(s.substr(start, pos - start));
  char* end = nullptr;
  const float v = std::strtof(tmp.c_str(), &end);
  if (end == tmp.c_str()) return false;  // no conversion
  out = v;
  return true;
}

// Locate the brace-balanced {...} object that is the value of `key`, searching from
// `from`. On success sets [objStart, objEnd] to the '{' and matching '}' indices.
bool findObject(std::string_view s, std::string_view key, std::size_t from,
                std::size_t& objStart, std::size_t& objEnd) {
  const std::size_t v = findKeyColon(s, key, from);
  if (v == kNpos) return false;
  std::size_t brace = v;
  while (brace < s.size() && isWs(s[brace])) ++brace;
  if (brace >= s.size() || s[brace] != '{') return false;
  int depth = 0;
  for (std::size_t i = brace; i < s.size(); ++i) {
    if (s[i] == '{') {
      ++depth;
    } else if (s[i] == '}') {
      if (--depth == 0) {
        objStart = brace;
        objEnd = i;
        return true;
      }
    }
  }
  return false;  // unbalanced -> malformed
}

}  // namespace

CalibrationSidecar parseCalibrationSidecar(std::string_view s) {
  CalibrationSidecar out{};  // identity defaults (method=none, a=1, b=0, T=1)

  std::size_t calStart = 0, calEnd = 0;
  if (!findObject(s, "calibration", 0, calStart, calEnd)) return out;  // no block -> identity
  const std::string_view cal = s.substr(calStart, calEnd - calStart + 1);

  // Method (applies to both stages per the fixed schema).
  StageCalibration::Method method = StageCalibration::kNone;
  const std::size_t mv = findKeyColon(cal, "method", 0);
  if (mv != kNpos) {
    const std::size_t q1 = cal.find('"', mv);
    const std::size_t q2 = (q1 == kNpos) ? kNpos : cal.find('"', q1 + 1);
    if (q1 != kNpos && q2 != kNpos) {
      const std::string_view m = cal.substr(q1 + 1, q2 - q1 - 1);
      if (m == "platt") {
        method = StageCalibration::kPlatt;
      } else if (m == "temperature") {
        method = StageCalibration::kTemperature;
      } else {
        method = StageCalibration::kNone;
      }
    }
  }

  // Fill one stage's params from its {a,b,temperature} sub-object. If the sub-object
  // is absent/malformed the stage is left at identity.
  const auto fillStage = [&](std::string_view stageKey, StageCalibration& sc) {
    std::size_t oS = 0, oE = 0;
    if (!findObject(cal, stageKey, 0, oS, oE)) return;  // stays identity
    const std::string_view obj = cal.substr(oS, oE - oS + 1);
    sc.method = method;
    float v = 0.0f;
    if (parseNumberAt(obj, findKeyColon(obj, "a", 0), v)) sc.plattA = v;
    if (parseNumberAt(obj, findKeyColon(obj, "b", 0), v)) sc.plattB = v;
    if (parseNumberAt(obj, findKeyColon(obj, "temperature", 0), v)) sc.temperature = v;
  };
  fillStage("stage1", out.stage1);
  fillStage("stage2", out.stage2);
  return out;
}

CalibrationSidecar parseCalibrationSidecar(const char* data, std::size_t size) {
  if (data == nullptr || size == 0) return CalibrationSidecar{};
  return parseCalibrationSidecar(std::string_view(data, size));
}

}  // namespace aura::config
