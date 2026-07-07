# PROJECT AURA — top-level CMake build graph (Stage 7 §15 / ADR-Build).
# CMake is the single source of truth for how core/ compiles; Gradle (Android)
# wraps this via externalNativeBuild (Stage 8 §1). Modules are declared as static
# libraries in Row order (Stage 7 §2); the dependency-graph linter enforces the
# rules the link graph should also respect.
cmake_minimum_required(VERSION 3.22)
project(aura LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# ---- Options (Stage 7 §9 compile-time configuration) ------------------------
set(AURA_PLATFORM "host" CACHE STRING "Target platform: host | android")
option(AURA_ENABLE_ONNXRUNTIME "Link the ONNX Runtime inference backend (ADR-002)" OFF)
option(AURA_ENABLE_DEBUG_LOCK_INSTRUMENTATION "No-alloc / lock-order debug instrumentation" ON)
option(AURA_BUILD_TESTS "Build unit + golden tests" ON)

# The whole repo root is the single include root, so `#include "core/<module>/..."`
# resolves 1:1 to the physical tree (see REPORT.md on the include-prefix choice).
set(AURA_INCLUDE_ROOT ${CMAKE_SOURCE_DIR})

include(cmake/AuraDepLint.cmake)

# Shared compile definitions.
add_library(aura_flags INTERFACE)
target_include_directories(aura_flags INTERFACE ${AURA_INCLUDE_ROOT})
if(AURA_ENABLE_DEBUG_LOCK_INSTRUMENTATION)
  target_compile_definitions(aura_flags INTERFACE AURA_ENABLE_DEBUG_LOCK_INSTRUMENTATION)
endif()
if(AURA_ENABLE_ONNXRUNTIME)
  target_compile_definitions(aura_flags INTERFACE AURA_ENABLE_ONNXRUNTIME)
endif()

# ---- Row -1: foundation ------------------------------------------------------
add_library(aura_common STATIC core/common/noalloc.cpp core/common/lockorder.cpp)
target_link_libraries(aura_common PUBLIC aura_flags)
add_dependencies(aura_common aura_dep_lint)

# Header-only modules as INTERFACE libs.
add_library(aura_config INTERFACE)      # Row 0
target_link_libraries(aura_config INTERFACE aura_common)
add_library(aura_platform INTERFACE)    # Row 0 (interfaces; impls are per-OS)
target_link_libraries(aura_platform INTERFACE aura_common)
add_library(aura_statemachine INTERFACE)  # Row 1
target_link_libraries(aura_statemachine INTERFACE aura_common)

# ---- Row 1 -------------------------------------------------------------------
add_library(aura_scheduler STATIC core/scheduler/Scheduler.cpp)
target_link_libraries(aura_scheduler PUBLIC aura_common aura_platform)

# ---- Row 2 -------------------------------------------------------------------
add_library(aura_audio STATIC core/audio/AudioPipeline.cpp)
target_link_libraries(aura_audio PUBLIC aura_common aura_config aura_scheduler)

add_library(aura_model STATIC core/model/ModelManager.cpp)
target_link_libraries(aura_model PUBLIC aura_common aura_platform)

# ---- Row 3 -------------------------------------------------------------------
add_library(aura_dsp STATIC core/dsp/DspChain.cpp)
target_link_libraries(aura_dsp PUBLIC aura_common)

# ---- Row 4 -------------------------------------------------------------------
add_library(aura_features STATIC core/features/LogMelExtractor.cpp)
target_link_libraries(aura_features PUBLIC aura_common aura_config)

add_library(aura_vad STATIC core/vad/SileroVad.cpp)  # SileroVad body is #if'd on ORT
target_link_libraries(aura_vad PUBLIC aura_common aura_config)

# ---- Row 5 -------------------------------------------------------------------
add_library(aura_runtime STATIC
  core/runtime/OnnxRuntimeBackend.cpp     # body #if'd on AURA_ENABLE_ONNXRUNTIME
  core/runtime/TfliteMicroBackend.cpp)    # body #if'd on AURA_ENABLE_TFLITE_MICRO (MCU tier)
target_link_libraries(aura_runtime PUBLIC aura_common)
option(AURA_ENABLE_TFLITE_MICRO "Link the TFLite Micro backend (ESP32/Cortex-M, ADR-002)" OFF)
if(AURA_ENABLE_TFLITE_MICRO)
  target_compile_definitions(aura_runtime PUBLIC AURA_ENABLE_TFLITE_MICRO)
  # target_link_libraries(aura_runtime PUBLIC tflite-micro)  # provided by the ESP-IDF/Cortex-M toolchain
endif()

# ---- Row 6 -------------------------------------------------------------------
add_library(aura_detect STATIC core/detect/Stage1Detector.cpp core/detect/StreamingDetector.cpp)
target_link_libraries(aura_detect PUBLIC aura_common aura_config aura_statemachine
                                          aura_features aura_runtime)

# ---- Row 8: facade -----------------------------------------------------------
add_library(aura_engine STATIC core/engine/WakeWordEngine.cpp)
target_link_libraries(aura_engine PUBLIC aura_common aura_config aura_platform aura_scheduler
                                          aura_audio aura_model aura_dsp aura_features
                                          aura_vad aura_runtime aura_detect)

# ---- Platform + third-party wiring ------------------------------------------
if(AURA_PLATFORM STREQUAL "android")
  # Oboe + ONNX Runtime consumed as Prefab AARs (find_package CONFIG), per the
  # locked decision (see REPORT.md); NOT vendored in third_party/.
  find_package(oboe REQUIRED CONFIG)  # Oboe ships Prefab metadata
  # ONNX Runtime's onnxruntime-android AAR does NOT ship Prefab (only headers/ + jni/<abi>/*.so),
  # so find_package(onnxruntime CONFIG) cannot work. Wire it as an imported target from the
  # extracted headers + .so (third_party/onnxruntime). The runtime .so is still packaged into the
  # APK by Gradle via the implementation(libs.onnxruntime.android) dependency.
  add_library(onnxruntime::onnxruntime SHARED IMPORTED)
  set_target_properties(onnxruntime::onnxruntime PROPERTIES
    IMPORTED_LOCATION "${CMAKE_SOURCE_DIR}/third_party/onnxruntime/lib/${ANDROID_ABI}/libonnxruntime.so"
    INTERFACE_INCLUDE_DIRECTORIES "${CMAKE_SOURCE_DIR}/third_party/onnxruntime/include")
  find_library(android_log_lib log)

  add_library(aura_platform_android STATIC
    core/platform/android/OboeAudioInput.cpp
    core/platform/android/AndroidStorage.cpp)
  target_link_libraries(aura_platform_android PUBLIC aura_common aura_platform
                        oboe::oboe ${android_log_lib})

  target_link_libraries(aura_vad PUBLIC onnxruntime::onnxruntime)
  target_link_libraries(aura_runtime PUBLIC onnxruntime::onnxruntime)

  # The hand-written JNI shared library (sdk/kotlin/aura-core-bindings). Gradle's
  # externalNativeBuild points here; the .so is packaged into the AAR/APK.
  add_library(aura_jni SHARED sdk/kotlin/aura-core-bindings/src/main/cpp/aura_jni.cpp)
  target_link_libraries(aura_jni PRIVATE aura_engine aura_platform_android
                        onnxruntime::onnxruntime ${android_log_lib})
endif()

# ---- Tests (host) ------------------------------------------------------------
if(AURA_BUILD_TESTS AND NOT AURA_PLATFORM STREQUAL "android")
  enable_testing()
  include(FetchContent)
  FetchContent_Declare(googletest
    GIT_REPOSITORY https://github.com/google/googletest.git
    GIT_TAG release-1.14.0)
  set(gtest_force_shared_crt ON CACHE BOOL "" FORCE)
  FetchContent_MakeAvailable(googletest)

  add_executable(aura_tests
    core/common/tests/common_test.cpp
    core/config/tests/config_test.cpp
    core/statemachine/tests/statemachine_test.cpp
    core/audio/tests/audio_test.cpp
    core/dsp/tests/dsp_test.cpp
    core/features/tests/features_test.cpp
    core/vad/tests/vad_test.cpp
    core/model/tests/model_test.cpp
    core/detect/tests/detect_test.cpp
    core/detect/tests/streaming_detector_test.cpp
    core/runtime/tests/streaming_window_test.cpp
    tests/golden/golden_cascade_test.cpp)
  target_link_libraries(aura_tests PRIVATE
    aura_common aura_config aura_statemachine aura_scheduler aura_audio aura_model
    aura_dsp aura_features aura_vad aura_runtime aura_detect aura_engine
    GTest::gtest GTest::gtest_main)
  include(GoogleTest)
  gtest_discover_tests(aura_tests WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})
endif()
