# PROJECT AURA — v0 Vertical Slice: Build Report

This is AURA's first running code: a real, full-depth Android vertical slice built
against the Stage-7 SAS (`product/aura_sas.md`) and the Stage-8/9 process docs — not
a mockup. The platform-independent `core/` engine is implemented as the general
module it is specified to be, with only the Android platform wired up.

## What was built & verified

**Pipeline (real, not stubbed):** platform capture (Oboe on device / WAV-replay mock
on host) → `core/audio` SPSC ring buffer + drop-oldest backpressure → `core/dsp`
AGC→AEC(no-op)→NS in-place → `core/features` log-Mel (STFT) → `core/vad` gate
(Silero on device / EnergyVad on host) → `core/runtime` ONNX Runtime Stage-1 (device)
→ `core/detect` Stage-1 cascade FSM with `CorrelationId` → `DetectionEvent` on the
Callback thread → `sdk` JNI → `Flow<DetectionEvent>` → app toast/logcat.

**Exact SAS §4 interfaces implemented:** `IPlatform`, `IAudioInput`, `IClock`,
`IStorage`, `IPowerManager`, `IConfigProvider`, `IInferenceBackend`, `IModelLoader`,
`IWakeWordEngine`, `IWakeWordListener`, `IStateMachine<TState,TEvent>` — signatures
verbatim.

**Verified locally (Windows host, g++ 13.2 / Python 3.13 — no Android toolchain
present here):**
- `tools/lint_deps.py` — **PASS** on the real `core/` tree (Row 0–8 order, PAL
  isolation, no cycles). Verified it **fails** on an injected `dsp→engine` include
  (and the resulting cycle), then passes again after revert. It also caught a real
  violation during development — `core/common/log.h` including `<android/log.h>` —
  which was fixed by moving the logcat sink to `core/platform/android/`.
- **23/23 unit + golden tests PASS** (one+ test per `core/` module + a golden
  fixture replaying `benchmarks/corpus/positive/marvin_clean_en_us_001.wav`
  deterministically → exactly one `DetectionOutcome::Confirmed`).
- The debug **no-alloc assertion** (`AURA_ENABLE_DEBUG_LOCK_INSTRUMENTATION`,
  overriding `operator new`/`malloc`) was active across the whole suite and **never
  fired** — confirming the Audio/Inference hot paths are allocation-free.

**Not runnable on this machine (require the Android toolchain the user provides):**
`./gradlew :apps:android:assembleDebug` and on-device detection. No CMake, Gradle,
Android SDK/NDK, or ONNX Runtime is installed here; those layers are written against
the documented APIs but compiled/run on the user's device toolchain (per the plan's
prerequisites). The ORT-guarded TUs were confirmed to compile as empty on host, so
the `#if AURA_ENABLE_ONNXRUNTIME` guards are correct.

---

## Placeholders (flagged, not silent)

1. **KWS model** — no AURA-trained model exists. `tools/convert_kws_model.py`
   provides `--real` (recipe to export a permissively-licensed Speech Commands
   checkpoint that can truly recognize a keyword; requires torch) and `--synthetic`
   (shape-correct **random-weight** ONNX that exercises the native ORT path but does
   **not** recognize speech). The synthetic model was generated locally to prove the
   `onnx` toolchain works. **On-device true-positive detection depends on obtaining
   the real model** — see ADR needs below.
2. **Silero VAD model** — `silero_vad.onnx` (MIT) must be dropped into
   `apps/android/src/main/assets/models/` (git-ignored binary). App degrades to
   EnergyVad-in-logs / init-failed status if absent.
3. **AEC stage** — `core/dsp/AecStage` is a **no-op passthrough** (the reference app
   plays no audio back). The `IDspStage` slot is kept so real AEC is a one-line swap.
4. **NS stage** — `core/dsp/NsStage` is a minimal high-pass + soft gate; real
   RNNoise / WebRTC-APM NS is deferred.
5. **FFT** — `core/features/Fft.h` is a compact self-contained radix-2 FFT standing
   in for vendored KissFFT / Accelerate (addendum §3), so the host build needs no
   external FFT dependency.
6. **Model signature verification** — `ModelManager::verifySignature()` is a
   documented no-op (the `core/security` module is out of scope). Unsigned/placeholder
   models load. Never silent — it logs and is commented.
7. **Local logging** — `core/common/log.h` is a stderr/logcat stand-in for the full
   `ILogger`/`ITelemetry` (telemetry module out of scope); carries level/category/
   message/correlationId, so correlation tracing is demonstrable, but there is no
   upload path.
8. **Golden test backend** — uses a scripted `FakeInferenceBackend`, not ORT,
   because ORT output is not guaranteed bit-reproducible across builds while a golden
   fixture must be exact. Real ORT inference is validated on-device (acceptance #2).
9. **Golden fixture audio** — `marvin_clean_en_us_001.wav` is a synthetic
   deterministic stimulus (`tools/gen_golden_fixture.py`), not a real recording.

## Explicitly skipped (real specs exist; scoping for this PR, not "unnecessary")

- **Absent modules (no stubs):** `core/telemetry`, `core/security`, `core/ota`,
  `core/power`, `core/discovery`, `core/speaker`. An absent module is more honest
  than a fake one.
- **Features:** Stage-2 verifier, speaker verification/enrollment, model hot-swap /
  OTA / rollback (`rollback()` returns `kUnimplemented`), remote config / feature
  flags (compiled-in defaults only), multi-device arbitration, telemetry upload,
  multi-wake-word (`addWakeWord` accepts one; a second returns `kUnimplemented`),
  `sdk/idl` codegen, and every platform other than Android.
- `IPowerManager` **is** implemented (minimal, reports `Active`) because `IPlatform`
  mandates it, even though the `core/power` module is skipped.

## Judgment calls (not fully specified in `product/`)

1. **Undefined value types** — the SAS references `Result<T>`, `Error`,
   `CorrelationId`, `DetectionEvent`, `AudioFrameView`, `TensorView`, `Arena`,
   `Config`, etc. in its §4 signatures but never defines their fields or assigns them
   a module. **Decision (approved):** a header-only `core/common/` foundation below
   Row 0 holds them all; the linter treats it as the base row.
2. **Native deps sourcing** — SAS §15 says `third_party/` is "vendored/pinned," but
   Oboe + ONNX Runtime ship Prefab AARs. **Decision (approved):** consume them via
   Gradle AAR + `find_package(... CONFIG)`, versions pinned in `libs.versions.toml`.
   Deviates from the literal "vendored" wording.
3. **Wake word** — **Decision (approved):** "marvin" (Speech Commands 35-word set).
4. **Include prefix** — the SAS writes `#include "aura/<module>/..."`, which can't
   resolve to the physical `core/<module>/` tree without fragile symlink aliasing on
   Windows. **Decision:** use `#include "core/<module>/..."` with the repo root as the
   single include root (1:1 with the physical tree); the `aura::` C++ namespace (what
   §16 actually mandates) is unchanged. The linter parses per-module regardless.
5. **Concrete toolchain versions** — the SAS defers every version to
   `tools/versions.txt`. Pinned: JDK 17, AGP 8.7.2, Gradle 8.11.1, Kotlin 2.0.21,
   NDK r27, CMake 3.22.1, minSdk 26 / target 35, C++20, Oboe 1.9.0, ORT-Android 1.20.0.
6. **VAD runs Silero via ORT directly** (`core/vad` → third_party, allowed; not via
   `core/runtime`, so no Row violation), owning its LSTM state, per §3.9.
7. **Cascade refinement** — after a Stage-1 rejection the FSM returns to
   `VadTriggered` (not `Idle`) so it keeps scanning while the VAD gate stays open on a
   continuous utterance — a small practical refinement of the §7.3 diagram.
8. **Hand-written JNI** — per the task (no codegen tool exists yet). Kept thin and
   handle-based (opaque `jlong`, no C++ objects across the FFI boundary, per Stage 9
   §3 ABI guidance) so generated code can replace it later without touching `aura-sdk`.

## What needs a real ADR before this goes further

1. **Placeholder KWS model + front-end contract.** The chosen model dictates (or must
   match) the log-Mel front-end (16 kHz, 25 ms/10 ms, 40 mel). This alignment is the
   SAS's own M3 integration risk ("model-format/tensor-layout mismatch"). Picking the
   real Speech-Commands checkpoint, confirming its "marvin" class index (→
   `DetectConfig.stage1TargetClass`), and locking the front-end deserves an ADR.
2. **Silero/ORT allocation on the RT Audio thread.** VAD runs on the Audio thread
   (§3.9), but ORT `Run()` allocates internally, which the no-alloc guard cannot cover
   (it guards our code only). v0 minimizes this by reusing input/output `OrtValue`s;
   a real fix (custom ORT allocator / IoBinding, or a hand-rolled Silero) needs a
   decision.
3. **Reinstating `sdk/idl` codegen** (ADR-Binding) to replace the hand-written JNI —
   the layer is deliberately mechanical to make this a drop-in.
4. **Gradle wrapper jar** is not committed (binary). Run `gradle wrapper
   --gradle-version 8.11.1` once (or open in Android Studio) to materialize it before
   `./gradlew` works.

## Acceptance criteria status

| # | Criterion | Status |
|---|---|---|
| 1 | `./gradlew :apps:android:assembleDebug` builds | Written correctly; **not runnable here** (no Android toolchain). Needs user's SDK/NDK + wrapper jar. |
| 2 | Real pipeline logs a detection when target word spoken | Pipeline is real & verified deterministically on host; on-device true-positive needs the real KWS model (ADR #1). |
| 3 | ≥1 unit test per `core/` module + a golden replay test | **Done** — 23/23 pass, incl. golden fixture. |
| 4 | This report | **This document.** |
