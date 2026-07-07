#!/usr/bin/env bash
# PROJECT AURA — leak / use-after-free detection via AddressSanitizer (Stage 7 §14
# "Memory-leak detection: ASan on desktop"). Runs the host unit + golden + integration +
# fuzz tests AND a long soak under ASan+LSan. Intended for the CI desktop lane (Linux/gcc
# or clang); ASan is not available in the Windows/MinGW dev image (compile the same way in
# CI). Non-zero exit on any leak/UAF.
set -euo pipefail
cd "$(dirname "$0")/.."

CXX="${CXX:-g++}"
OUT="${TMPDIR:-/tmp}/aura_tests_asan"

echo "== building host tests with AddressSanitizer (LeakSanitizer) =="
$CXX -std=c++20 -I. -g -O1 -fsanitize=address,undefined -fno-omit-frame-pointer \
  -DAURA_USE_MICROGTEST -DAURA_ENABLE_DEBUG_LOCK_INSTRUMENTATION \
  tests/support/microgtest_main.cpp \
  core/*/tests/*.cpp tests/golden/golden_cascade_test.cpp \
  tests/integration/integration_test.cpp tests/fuzz/fuzz_test.cpp tests/stress/soak_test.cpp \
  core/scheduler/Scheduler.cpp core/audio/AudioPipeline.cpp core/dsp/DspChain.cpp \
  core/features/LogMelExtractor.cpp core/model/ModelManager.cpp core/detect/Stage1Detector.cpp \
  core/engine/WakeWordEngine.cpp core/common/noalloc.cpp core/common/lockorder.cpp \
  -o "$OUT"

echo "== running under ASan (short) =="
ASAN_OPTIONS=detect_leaks=1 "$OUT"

echo "== running the soak longer under ASan (leak/growth over many utterances) =="
AURA_SOAK_UTTERANCES="${AURA_SOAK_UTTERANCES:-2000}" ASAN_OPTIONS=detect_leaks=1 "$OUT"

echo "ASan run clean."
