# Aura — on-device wake-word detection

On-device wake-word detection engine: a platform-independent C++ core with a Kotlin SDK and a reference Android app, plus a single-config training pipeline for building your own wake word.

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)

Audio never leaves the device. The engine runs a low-power always-on Stage-1 detector, an optional Stage-2 verifier cascade to cut false accepts, and a calibrated scorer, all fed by a DSP + log-Mel front-end that the training pipeline mirrors byte-for-byte.

## Features

- **Fully on-device** — capture → DSP → features → inference all run locally; no network, no cloud.
- **Two-stage cascade** — an always-on Stage-1 detector plus an optional heavier Stage-2 verifier that must also fire, trading a little compute for far fewer false accepts.
- **Streaming, real-time** — block-streamed at 10 ms (160-sample) hops with bounded, allocation-free hot paths.
- **Calibrated confidence** — Platt / temperature scaling with ECE/MCE reporting, so thresholds mean the same thing across models.
- **Train-serve parity** — the numpy training front-end (`tools/aura_frontend.py`) mirrors the on-device C++ front-end exactly, verified against a golden fixture.
- **Portable core** — the C++ engine builds and is fully tested on the host with no Android toolchain; a thin platform-abstraction layer keeps it device-agnostic.
- **Kotlin SDK + reference app** — a two-layer SDK (`JNI bindings` + `Flow<DetectionEvent>`) and a working Android app that toasts on detection.
- **Bring your own wake word** — one `config.yaml`, `python train.py`, `python evaluate.py`.

## Repository structure

```
.
├── core/            platform-independent C++ engine (dependency-row linted)
│   ├── audio/       capture + ring buffer
│   ├── dsp/         AGC / noise-suppression chain
│   ├── features/    log-Mel extractor
│   ├── vad/         voice-activity detection
│   ├── detect/      Stage-1 detector + streaming detector
│   ├── model/       model manager (ONNX Runtime)
│   ├── engine/      top-level WakeWordEngine
│   ├── config/      calibration sidecar + config
│   ├── scheduler/ statemachine/ runtime/ common/   supporting rows
│   └── platform/    platform-abstraction layer (PAL)
├── sdk/kotlin/      aura-core-bindings (JNI) + aura-sdk (Flow<DetectionEvent>)
├── apps/android/    reference app (mic permission → engine → toast on detection)
├── tools/           training pipeline + host verification (numpy/torch/onnx)
│   └── experimental/  research spikes (LibriSpeech, streaming, QAT)
├── benchmarks/      corpus, harness, and result dashboards
├── tests/           golden replay, integration, fuzz, stress, mock platform
├── docs/            model/dataset cards, device runbook, design specs + ADRs
│   └── design/      system architecture spec + adr/
├── train.py         training entry point   (reads config.yaml)
├── evaluate.py      evaluation entry point (reads config.yaml)
├── config.yaml      the ONE file you edit to train your own wake word
├── TRAINING.md      training quickstart
├── CMakeLists.txt   single source of truth for the native build
├── LICENSE          Apache-2.0
└── NOTICE
```

## Train your own wake word

Everything is driven by a single `config.yaml`. Full walkthrough in **[TRAINING.md](TRAINING.md)**.

```bash
# 1. Drop 16 kHz mono WAVs into:
#      datasets/<wake_word>/positive/*.wav   (clips that SAY the wake word)
#      datasets/<wake_word>/negative/*.wav   (other speech, noise, near-misses)

# 2. Set wake_word + dataset_dir in config.yaml (every field is commented)

# 3. Train  -> models/<wake_word>.onnx (+ optional _stage2.onnx) + labels.json
python train.py

# 4. Evaluate -> streaming FA/hr, FRR, and calibration (ECE/MCE)
python evaluate.py
```

`train.py` / `evaluate.py` are thin wrappers over the reusable pipeline in `tools/`
(loader + speaker-independent split, the parity front-end, augmentation, model zoo,
trainer, and calibration).

## Build

**Host (C++ core — no Android toolchain needed):**

```bash
python tools/lint_deps.py core                    # dependency-row / PAL / cycle lint
cmake --preset host-debug && cmake --build --preset host-debug
ctest --preset host-debug --output-on-failure     # golden replay + integration + fuzz + stress
```

**Android app** (JDK 17 + Android SDK + NDK + CMake; versions in `tools/versions.txt`):

```bash
# place silero_vad.onnx — see apps/android/src/main/assets/models/README.md
./gradlew :apps:android:assembleDebug
./gradlew :apps:android:installDebug              # then say the wake word; watch: adb logcat -s AURA
```

## Documentation

- **[TRAINING.md](TRAINING.md)** — train a custom wake word from one config file.
- **[docs/MODEL_CARD.md](docs/MODEL_CARD.md)** — model architecture, intended use, and limitations.
- **[docs/DATASET_CARD.md](docs/DATASET_CARD.md)** — dataset layout, sourcing, and the speaker-independent split.
- **[docs/DEVICE_RUNBOOK.md](docs/DEVICE_RUNBOOK.md)** — on-device build, speech test, and memory-measurement steps.
- **[docs/design/](docs/design/)** — system architecture spec and design reviews.
- **[docs/design/adr/](docs/design/adr/)** — architecture decision records (e.g. calibration).

## License

Licensed under the **Apache License 2.0** — see [LICENSE](LICENSE) and [NOTICE](NOTICE).
