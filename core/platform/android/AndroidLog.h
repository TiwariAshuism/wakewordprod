// PROJECT AURA — core/platform/android/AndroidLog.h
// Installs an Android logcat sink for core/common/log.h. This is one of the ONLY
// places <android/log.h> may be included (Stage 7 §2). Call InstallAndroidLogSink()
// once at engine startup (from the JNI layer) so AURA logs land in `adb logcat`.
#ifndef AURA_PLATFORM_ANDROID_ANDROIDLOG_H
#define AURA_PLATFORM_ANDROID_ANDROIDLOG_H

#include <android/log.h>

#include "core/common/log.h"

namespace aura::platform::android {

inline void InstallAndroidLogSink() {
  common::SetLogSink([](common::LogLevel level, common::LogCategory, const char* formatted) {
    int prio = ANDROID_LOG_INFO;
    switch (level) {
      case common::LogLevel::kTrace:
      case common::LogLevel::kDebug: prio = ANDROID_LOG_DEBUG; break;
      case common::LogLevel::kInfo: prio = ANDROID_LOG_INFO; break;
      case common::LogLevel::kWarn: prio = ANDROID_LOG_WARN; break;
      case common::LogLevel::kError: prio = ANDROID_LOG_ERROR; break;
      case common::LogLevel::kFatal: prio = ANDROID_LOG_FATAL; break;
    }
    __android_log_print(prio, "AURA", "%s", formatted);
  });
}

}  // namespace aura::platform::android

#endif  // AURA_PLATFORM_ANDROID_ANDROIDLOG_H
