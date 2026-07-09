# AURA Wake Word Engine

Cross-platform, on-device wake-word detection engine (Apache-2.0).

## Layout
- `core/` — platform-independent C++ engine (dependency-row-linted)
- `sdk/` — language bindings (Kotlin JNI + SDK)
- `apps/` — reference apps (Android reference app)
- `tests/`, `benchmarks/` — unit/golden tests and benchmark harness
- `docs/` — model/dataset cards, device runbook, build report; `docs/design/` holds the SAS and design/ADR docs

## Conventions
- Keep the `core/` dependency rows clean; run `python tools/lint_deps.py core` before changes.
- Build/test via CMake presets (host) and Gradle (Android) — see `README.md`.
