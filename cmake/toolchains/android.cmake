# PROJECT AURA — cmake/toolchains/android.cmake
#
# Thin shim over the NDK's own toolchain file. When the Android build is driven by
# Gradle's externalNativeBuild (the normal path, Stage 8 §1), Gradle injects the
# NDK toolchain, ABI, and platform level directly, so this file is not needed. It
# exists for standalone `cmake` invocations (e.g. the android-arm64-debug preset)
# and simply forwards to the NDK toolchain located via ANDROID_NDK_HOME.
if(NOT DEFINED ENV{ANDROID_NDK_HOME})
  message(FATAL_ERROR "ANDROID_NDK_HOME is not set; cannot locate the NDK toolchain")
endif()

if(NOT DEFINED ANDROID_ABI)
  set(ANDROID_ABI "arm64-v8a")
endif()
if(NOT DEFINED ANDROID_PLATFORM)
  set(ANDROID_PLATFORM "android-26")  # minSdk 26 (Stage 9 §1 pins in tools/versions.txt)
endif()

include("$ENV{ANDROID_NDK_HOME}/build/cmake/android.toolchain.cmake")
