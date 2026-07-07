# PROJECT AURA — Android Vertical Slice (v0)

AURA's first running code: a real Android app that captures microphone audio and
detects the wake word **"marvin"** through the actual layered architecture
(Oboe → ring buffer → DSP → log-Mel features → Silero VAD → ONNX Runtime Stage-1
inference → `DetectionEvent`), built against the Stage-7 SAS in `product/`.

See **[REPORT.md](REPORT.md)** (v0 scope/placeholders) and **[REPORT_v1.md](REPORT_v1.md)**
(real model, ADR resolutions, host verification). Device-side steps (build + on-device
speech test + ORT-alloc measurement) are in **[DEVICE_RUNBOOK.md](DEVICE_RUNBOOK.md)**.

## Layout (Stage 7 §1)

```
core/            platform-independent C++ engine (Row 0–8, dependency-linted)
sdk/kotlin/      two-layer SDK: aura-core-bindings (JNI) + aura-sdk (Flow<DetectionEvent>)
apps/android/    reference app (mic permission → engine → toast on detection)
tests/           mock_platform, golden fixture, support
build-logic/     Gradle convention plugins;  gradle/libs.versions.toml  version catalog
CMakeLists.txt   single native build source of truth;  tools/lint_deps.py  row linter
```

## Build & test

**Host (core logic — no Android toolchain needed):**
```bash
python tools/lint_deps.py core                 # dependency-row / PAL / cycle lint
cmake --preset host-debug && cmake --build --preset host-debug
ctest --preset host-debug --output-on-failure  # 23 tests incl. golden replay
```

**Real placeholder KWS model** (host, needs torch/scipy/onnx — downloads Speech Commands ~2.3 GB):
```bash
python tools/train_kws_model.py            # trains "marvin" model -> assets/models/kws_marvin.onnx + labels.json
python tools/verify_kws_host.py            # real-model TP/FP on held-out clips (host proxy for on-device)
python tools/verify_frontend_alignment.py <dump_frontend_exe>   # proves numpy front-end == C++
```

**Android app** (requires **JDK 17** + Android SDK + NDK r27 + CMake 3.22.1; see `tools/versions.txt`):
```bash
# place silero_vad.onnx — see apps/android/src/main/assets/models/README.md
./gradlew :apps:android:assembleDebug      # Gradle wrapper jar is committed (v1)
./gradlew :apps:android:installDebug       # then say "marvin"; watch: adb logcat -s AURA
```

> Full device steps (build, on-device speech test, ORT-allocation measurement) with
> exact commands are in **DEVICE_RUNBOOK.md**.
