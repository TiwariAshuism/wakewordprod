// PROJECT AURA — core/common/log.h
//
// Minimal structured local logger. A v0 stand-in for the full ILogger / ITelemetry
// design (Stage 7 §4/§12) — the telemetry module is OUT OF SCOPE, so there is no
// upload path (flagged in REPORT.md). It carries the Stage 7 §12 fields: level,
// category, message, correlationId, so correlation-id tracing is demonstrable.
//
// PLATFORM-FREE by design (Stage 7 §2): common/ must not include any OS/SDK header.
// Output goes to stderr by default; the platform layer installs a sink (e.g.
// Android logcat via core/platform/android/AndroidLog.h) at startup. Formatting
// uses a fixed stack buffer — no heap allocation — but it is still intended for
// setup/teardown/detection-edge use, not the per-frame hot path.
#ifndef AURA_COMMON_LOG_H
#define AURA_COMMON_LOG_H

#include <cstdint>
#include <cstdio>
#include <string_view>

#include "core/common/ids.h"

namespace aura::common {

enum class LogLevel : uint8_t { kTrace = 0, kDebug, kInfo, kWarn, kError, kFatal };

// One category per Section-3 module (Stage 7 §12).
enum class LogCategory : uint8_t {
  kPlatform = 0, kConfig, kAudio, kDsp, kFeatures, kVad, kRuntime, kDetect, kModel, kEngine
};

inline std::string_view levelName(LogLevel l) {
  switch (l) {
    case LogLevel::kTrace: return "TRACE";
    case LogLevel::kDebug: return "DEBUG";
    case LogLevel::kInfo: return "INFO";
    case LogLevel::kWarn: return "WARN";
    case LogLevel::kError: return "ERROR";
    case LogLevel::kFatal: return "FATAL";
  }
  return "?";
}

inline std::string_view categoryName(LogCategory c) {
  switch (c) {
    case LogCategory::kPlatform: return "Platform";
    case LogCategory::kConfig: return "Config";
    case LogCategory::kAudio: return "Audio";
    case LogCategory::kDsp: return "Dsp";
    case LogCategory::kFeatures: return "Features";
    case LogCategory::kVad: return "Vad";
    case LogCategory::kRuntime: return "Runtime";
    case LogCategory::kDetect: return "Detect";
    case LogCategory::kModel: return "Model";
    case LogCategory::kEngine: return "Engine";
  }
  return "?";
}

// A platform-installed sink receives the fully-formatted line. Set from the
// platform layer (Android logcat, etc.); nullptr => stderr fallback.
using LogSinkFn = void (*)(LogLevel level, LogCategory cat, const char* formatted);

inline LogSinkFn& logSink() {
  static LogSinkFn sink = nullptr;
  return sink;
}
inline void SetLogSink(LogSinkFn fn) { logSink() = fn; }

inline void Log(LogLevel level, LogCategory cat, std::string_view msg,
                const CorrelationId& id = {}) {
  char buf[256];
  std::snprintf(buf, sizeof(buf), "[%.*s] cid=%llx%llx %.*s",
                static_cast<int>(categoryName(cat).size()), categoryName(cat).data(),
                static_cast<unsigned long long>(id.hi), static_cast<unsigned long long>(id.lo),
                static_cast<int>(msg.size()), msg.data());
  if (logSink()) {
    logSink()(level, cat, buf);
  } else {
    std::fprintf(stderr, "[AURA][%.*s]%s\n", static_cast<int>(levelName(level).size()),
                 levelName(level).data(), buf);
  }
}

}  // namespace aura::common

#endif  // AURA_COMMON_LOG_H
