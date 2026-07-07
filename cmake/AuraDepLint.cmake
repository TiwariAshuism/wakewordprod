# PROJECT AURA — cmake/AuraDepLint.cmake
# Wires the Stage 7 §2 dependency-graph linter as a build target. The linter runs
# platform-independently against the #include graph before compilation, so a
# forbidden-row import or a cycle fails in seconds, not after a cross-compile
# (Stage 7 §15). Attach it as a dependency of core targets so `cmake --build`
# always lints first.
find_package(Python3 COMPONENTS Interpreter QUIET)

if(Python3_Interpreter_FOUND)
  add_custom_target(aura_dep_lint ALL
    COMMAND ${Python3_EXECUTABLE} ${CMAKE_SOURCE_DIR}/tools/lint_deps.py ${CMAKE_SOURCE_DIR}/core
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
    COMMENT "AURA dependency-graph lint (row order / PAL isolation / cycles)"
    VERBATIM)
else()
  message(WARNING "Python3 not found: AURA dependency-graph lint is DISABLED for this build")
  add_custom_target(aura_dep_lint)  # empty, so dependencies still resolve
endif()
