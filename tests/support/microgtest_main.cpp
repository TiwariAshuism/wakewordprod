// PROJECT AURA — tests/support/microgtest_main.cpp
// Host-only entry point for the dependency-free microgtest runner. The CMake/CI
// build uses real GoogleTest (gtest_main) and does NOT compile this file.
#define AURA_USE_MICROGTEST
#define AURA_MICROGTEST_MAIN
#include "tests/support/test_framework.h"
