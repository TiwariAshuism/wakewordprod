# PROJECT AURA — Software Architecture Specification (SAS)
### Stage 7 — Implementation-Ready Engineering Blueprint
### Version 1.0

This document assumes all prior ADRs (Stages 2–6) are final and does not re-derive them. Where a decision from a prior stage is load-bearing for a spec below, it is referenced by ADR ID, not re-argued. This is the document an engineer implements against directly.

---

## SECTION 1 — Repository Layout

```
aura/
├── apps/                          # Thin platform-specific application shells (not the SDK)
│   ├── android/                   # Demo/reference Android app consuming sdk/kotlin
│   ├── ios/                       # Demo/reference iOS app consuming sdk/swift
│   ├── linux/                     # Reference CLI + daemon for Linux/RPi
│   ├── windows/                   # Reference CLI/service for Windows
│   ├── mac/                       # Reference CLI/app for macOS
│   ├── flutter/                   # Reference Flutter app consuming sdk/dart
│   └── embedded/                  # Reference ESP-IDF/Zephyr firmware image
│       ├── esp32s3/
│       └── cortex_m/
├── sdk/                           # Generated + hand-written language bindings (consumers of core/)
│   ├── kotlin/                    # Generated via binding codegen (Stage 6 Finding 5) + idiomatic wrapper
│   ├── swift/
│   ├── dart/                      # Flutter plugin package
│   ├── python/                    # For tooling/benchmark-harness use, not a product SDK target
│   └── idl/                       # Single interface-definition source the codegen consumes
├── core/                          # Platform-independent C++ engine — the ONLY place business logic lives
│   ├── audio/                     # Audio Engine module
│   ├── dsp/                       # DSP Engine module
│   ├── features/                  # Feature Extraction module
│   ├── vad/                       # VAD module
│   ├── detect/                    # Stage-1 Detector + Stage-2 Verifier modules
│   ├── speaker/                   # Speaker Verification module
│   ├── runtime/                   # Inference Runtime module (IInferenceBackend + implementations)
│   ├── telemetry/                 # Telemetry module
│   ├── ota/                       # OTA module
│   ├── config/                    # Configuration module
│   ├── security/                  # Security module (signing, keystore access, attestation)
│   ├── scheduler/                 # Scheduler + threading primitives
│   ├── statemachine/              # Shared state-machine framework used by Section 7 machines
│   ├── power/                     # Power Manager module
│   ├── model/                     # Model Manager module (lifecycle, hot-swap, eviction)
│   ├── platform/                  # IPlatform interface + per-OS implementations (the PAL)
│   │   ├── android/
│   │   ├── ios/
│   │   ├── linux/
│   │   ├── windows/
│   │   ├── macos/
│   │   ├── esp32/
│   │   └── cortex_m/
│   └── discovery/                 # Local-discovery module (mDNS/BLE) for multi-device arbitration
├── benchmarks/                    # Benchmark harness, hardware matrix configs, golden-fixture corpus (DVC)
│   ├── corpus/                    # DVC-tracked audio fixtures (real-negative, positive, confusable)
│   ├── harness/                   # Automated FA/hr, DET, latency, power measurement code
│   └── dashboards/                # MLflow/W&B dashboard configs
├── examples/                      # Minimal standalone usage examples per SDK language
├── tests/                         # Cross-cutting integration/system tests (unit tests live beside their module)
│   ├── golden/                    # Golden-fixture regression tests
│   ├── fuzz/                      # Fuzz harnesses (audio input, model files, OTA packages)
│   ├── stress/                    # Soak/stress test drivers (24h/7-day)
│   └── mock_platform/             # IPlatform mock/simulation implementation for host-machine testing
├── docs/                          # This document set, ADR register, generated API docs, migration guides
├── tools/                         # Build tooling, codegen scripts, release/signing tooling, CI scripts
└── third_party/                   # Vendored/pinned external deps (ONNX Runtime, TFLite Micro, Silero VAD, etc.)
```

**Folder-ownership rule:** `core/` is the only folder permitted to contain business logic. `apps/` and `sdk/` are strictly consumers. This is enforced by the dependency graph in Section 2, not merely by convention.

---

## SECTION 2 — Package Dependency Graph

**Allowed dependency direction (top depends on bottom; no exceptions):**

```
apps/*  ---------------->  sdk/*  ---------------->  core/*  ---------------->  third_party/*
```

**Within `core/`, the following partial order is enforced (a module may depend only on modules at or below its own row):**

```
Row 0 (no internal deps):        platform/ (IPlatform + impls), config/
Row 1:                            scheduler/, statemachine/, security/
Row 2:                            audio/, telemetry/, model/, power/
Row 3:                            dsp/, ota/, discovery/
Row 4:                            features/, vad/
Row 5:                            runtime/ (IInferenceBackend + impls)
Row 6:                            detect/ (stage-1, stage-2)
Row 7:                            speaker/
Row 8 (top):                      IWakeWordEngine facade that composes everything above
```

**Forbidden imports:**
- No module in `core/` may `#include` any platform SDK header directly (no `<jni.h>`, no `<AudioToolbox/AudioToolbox.h>`, no ESP-IDF headers) — all platform access goes through `platform/IPlatform` only. This is the rule that makes the PAL real rather than aspirational.
- No module may import a module from a higher row.
- `sdk/*` may not import `third_party/*` directly — only through `core/`.
- Cyclic dependencies between any two `core/` submodules are a build failure, enforced by a CI dependency-graph linter (Section 15) that parses `#include` graphs and fails the build if a cycle or a forbidden-row import is detected — not merely a code-review convention.

---

## SECTION 3 — Core Engine Module Specifications

For each module: Responsibilities / Public API surface (names only — full signatures in Section 4) / Dependencies / Thread ownership / Memory ownership / Lifecycle.

### 3.1 Platform Layer (`core/platform/`)
- **Responsibilities:** sole gateway to OS primitives — audio I/O, clock/timer, filesystem, thread/task creation, power-state queries.
- **Public API:** `IPlatform`, `IAudioInput`, `IAudioOutput`, `IClock`, `IStorage`, `IPowerManager`.
- **Dependencies:** none within `core/` (Row 0).
- **Thread ownership:** owns the audio-capture callback context (ISR or OS-equivalent high-priority callback, per platform); delivers callbacks into threads owned by `scheduler/`, does not own a core-engine thread itself.
- **Memory ownership:** owns raw audio buffers only until handed off to `audio/` via the zero-copy handoff (Section 5); owns no long-lived engine state.
- **Lifecycle:** constructed once at engine startup, destroyed once at shutdown; per-platform implementations may reconstruct internal OS resources (e.g., on device hot-plug) without the `IPlatform` instance itself being recreated.

### 3.2 Configuration (`core/config/`)
- **Responsibilities:** merges compile-time defaults, platform overrides, and runtime-supplied configuration into one resolved `Config` snapshot; owns feature-flag evaluation.
- **Public API:** `IConfigProvider`.
- **Dependencies:** none (Row 0).
- **Thread ownership:** read-only after startup resolution from any thread; writes occur only on the Background thread and publish a new immutable `Config` snapshot rather than mutating in place.
- **Memory ownership:** owns the current `Config` snapshot; readers hold a `shared_ptr<const Config>` so a config update never invalidates an in-flight reader.
- **Lifecycle:** resolved once at startup; updated on remote-config/feature-flag change events for the engine's lifetime.

### 3.3 Scheduler (`core/scheduler/`)
- **Responsibilities:** owns thread creation, priority assignment, and lock-hierarchy enforcement.
- **Public API:** internal-only (`ITask`, `IScheduler`).
- **Dependencies:** `platform/` (Row 0 to Row 1).
- **Thread ownership:** creates and owns every thread listed in Section 6.
- **Memory ownership:** owns task queues; does not own audio/tensor buffers.
- **Lifecycle:** created first after `platform/`, torn down last, after all other modules have stopped submitting work.

### 3.4 State Machine Framework (`core/statemachine/`)
- **Responsibilities:** generic, reusable state-machine execution engine used by every state machine in Section 7.
- **Public API:** internal-only (`IStateMachine<TState, TEvent>`).
- **Dependencies:** `scheduler/` (Row 1).
- **Thread ownership:** each state machine instance is pinned to a single owning thread (specified per-machine in Section 7); transitions from other threads are queued as events, never executed cross-thread directly.
- **Memory ownership:** owns its own current-state value only.
- **Lifecycle:** one instance per state machine per engine instance, for the engine's lifetime.

### 3.5 Security (`core/security/`)
- **Responsibilities:** model-signature verification, OTA-package signature verification, Secure Enclave/Keystore-backed key access, device attestation.
- **Public API:** internal-only, consumed by `ota/` and `model/`.
- **Dependencies:** `platform/` (Row 0 to Row 1).
- **Thread ownership:** signature verification runs on the OTA thread; no hot-path (audio/inference) code depends on this module.
- **Memory ownership:** owns key handles (opaque, hardware-backed where available); never holds raw private key material in process memory on platforms with Secure Enclave/Keystore support.
- **Lifecycle:** trust-anchor loaded once at startup (post-provisioning, Section 7.6); reused for the engine's lifetime.

### 3.6 Audio Engine (`core/audio/`)
- **Responsibilities:** owns the buffer-ownership/backpressure pipeline; owns device hot-plug/resample handling.
- **Public API:** internal-only (`IAudioPipeline`), fed by `platform/IAudioInput`, feeding `dsp/`.
- **Dependencies:** `platform/`, `scheduler/`, `power/` (Row 2).
- **Thread ownership:** owns the Audio thread (Section 6).
- **Memory ownership:** owns the ring-buffer pool defined in Section 5.
- **Lifecycle:** started/stopped by the System Startup / Power State state machines; may be paused/resumed without full teardown on audio-interruption events (e.g., phone call).

### 3.7 DSP Engine (`core/dsp/`)
- **Responsibilities:** AGC to AEC to NS pipeline stages, per the ordering already fixed in prior documents (not re-derived here).
- **Public API:** internal-only (`IDspStage` chain).
- **Dependencies:** `audio/` (Row 3).
- **Thread ownership:** executes on the Audio thread, in-line with capture (no separate DSP thread — latency-motivated, see Section 6).
- **Memory ownership:** operates in-place on buffers owned by `audio/`'s ring-buffer pool; zero heap allocation per frame (Section 5, arena-only).
- **Lifecycle:** stateless between frames except each stage's own adaptive-filter state (e.g., AEC coefficients), which persists for the pipeline's lifetime.

### 3.8 Feature Extraction (`core/features/`)
- **Responsibilities:** STFT/FFT, log-Mel (+ optional PCEN per prior ADR), frame buffering.
- **Public API:** internal-only.
- **Dependencies:** `dsp/` (Row 4).
- **Thread ownership:** Audio thread (same rationale as 3.7).
- **Memory ownership:** fixed-size arena buffer for FFT scratch space, sized at initialization from `Config`.
- **Lifecycle:** stateless per-frame beyond the ring buffer needed for overlapping windows.

### 3.9 VAD (`core/vad/`)
- **Responsibilities:** gates Stage-1 inference; wraps Silero VAD.
- **Public API:** internal-only.
- **Dependencies:** `features/` (Row 4) — VAD and feature extraction run in parallel off the same raw-audio buffer per prior pipeline-placement decision; implemented as two independent read-only consumers of the same ring-buffer segment, not a serial dependency.
- **Thread ownership:** Audio thread.
- **Memory ownership:** owns Silero VAD's small internal LSTM state buffer.
- **Lifecycle:** persistent internal state across the engine's lifetime (VAD is stateful frame-to-frame by design).

### 3.10 Inference Runtime (`core/runtime/`)
- **Responsibilities:** implements `IInferenceBackend` with concrete backends: `OnnxRuntimeBackend`, `TfliteMicroBackend`, `ExecuTorchBackend` (evaluation).
- **Public API:** `IInferenceBackend`.
- **Dependencies:** `features/`, `vad/` (Row 5).
- **Thread ownership:** executes on the Inference thread, separate from the Audio thread.
- **Memory ownership:** owns tensor arena allocations (Section 5); owns memory-mapped model weight regions (Section 3.13).
- **Lifecycle:** backend instance created per active model; Model Manager (3.13) owns backend instance lifetime, not the reverse.

### 3.11 Stage-1 Detector / Stage-2 Verifier (`core/detect/`)
- **Responsibilities:** cascade orchestration — invokes `runtime/` with the Stage-1 model on every VAD-positive frame window; on Stage-1 trigger, invokes `runtime/` with the Stage-2 model; owns cascade causal event-ID propagation.
- **Public API:** internal-only, feeds the top-level `IWakeWordEngine` facade.
- **Dependencies:** `runtime/` (Row 6).
- **Thread ownership:** orchestration logic runs on the Inference thread; does not create its own thread.
- **Memory ownership:** owns no tensors directly (delegates to `runtime/`); owns the correlation-ID-tagged event record for one detection cascade.
- **Lifecycle:** one cascade-orchestration instance per configured wake word (supports multi-wake-word requirement), sharing one `runtime/` backend instance where architecture allows, per Config.

### 3.12 Speaker Verification (`core/speaker/`)
- **Responsibilities:** ECAPA-TDNN-derived embedding comparison against enrolled templates, gated by the anti-spoofing checkpoint (prior ADR) before being enabled in any build.
- **Public API:** internal-only, invoked by `detect/` only after Stage-2 verification succeeds.
- **Dependencies:** `runtime/` (Row 7).
- **Thread ownership:** Inference thread.
- **Memory ownership:** owns enrolled-speaker embedding templates, stored via `security/`'s hardware-backed storage where available.
- **Lifecycle:** enrollment is a distinct, user-initiated lifecycle event; core engine exposes only `enroll()`/`verify()` primitives (enrollment UX lives at the SDK layer).

### 3.13 Model Manager (`core/model/`)
- **Responsibilities:** implements the hot-swap/mmap/eviction architecture.
- **Public API:** internal-only (`IModelLoader`), consumed by `runtime/` and `ota/`.
- **Dependencies:** `security/` (signature check before load), `platform/IStorage` (Row 2).
- **Thread ownership:** load/swap operations execute on the OTA thread; the atomic pointer swap (Section 5) is the only cross-thread-visible operation, observed by the Inference thread.
- **Memory ownership:** owns memory-mapped model file regions and the double-buffered active/staged model handles.
- **Lifecycle:** one Model Manager instance per model slot (Stage-1, Stage-2, Speaker-verification each have independent slots and independent hot-swap lifecycles).

### 3.14 Telemetry (`core/telemetry/`)
- **Responsibilities:** aggregate, privacy-reviewed metrics collection and correlation-ID-tagged event logging; never transmits raw audio.
- **Public API:** `ITelemetry`.
- **Dependencies:** `platform/`, `config/` (Row 2).
- **Thread ownership:** owns the Telemetry thread; all other modules enqueue telemetry events (non-blocking) rather than performing I/O themselves.
- **Memory ownership:** owns a bounded ring buffer of pending telemetry events; drops (with a drop-counter metric, never silently) under sustained backpressure rather than blocking any producer.
- **Lifecycle:** started early (to capture startup-sequence telemetry), stopped last.

### 3.15 OTA (`core/ota/`)
- **Responsibilities:** full OTA design (versioning, checksum, signed manifest, staged rollout, rollback, offline fallback) plus the provisioning/attestation dependency.
- **Public API:** internal-only (`IOtaClient`), status surfaced to SDK layer via `ITelemetry`/callback.
- **Dependencies:** `security/`, `model/`, `platform/IStorage` (Row 3).
- **Thread ownership:** owns the OTA thread.
- **Memory ownership:** owns the staged-download buffer/file until checksum+signature verification passes, at which point ownership transfers to `model/`.
- **Lifecycle:** polls/receives update notifications for the engine's lifetime once provisioning has completed; inert (but present) before provisioning completes.

### 3.16 Power Manager (`core/power/`)
- **Responsibilities:** owns the Power State machine, including the three-stage-cascade decision for MCU targets (analog/ultra-low-power gate to Stage-1 to Stage-2), exposed as a platform-conditional code path, not a universal one.
- **Public API:** internal-only, consumed by `audio/` and `detect/` to gate whether Stage-1 inference should run at all in the current power state.
- **Dependencies:** `platform/IPowerManager` (Row 2).
- **Thread ownership:** no dedicated thread; runs its state machine on the Audio thread (power-state transitions are latency-sensitive relative to the audio pipeline they gate).
- **Memory ownership:** trivial (current power-state enum plus hysteresis timers).
- **Lifecycle:** engine lifetime.

### 3.17 Discovery (`core/discovery/`)
- **Responsibilities:** implements the local-discovery protocol (mDNS on mobile/desktop tiers, BLE on MCU tiers per platform capability) for multi-device arbitration.
- **Public API:** internal-only (`IDeviceDiscovery`), consumed by the Multi-Device Arbitration sequence (Section 8.9).
- **Dependencies:** `platform/` (Row 3).
- **Thread ownership:** owns the Background thread's discovery sub-task (not a dedicated OS thread on most platforms; scheduled periodically).
- **Memory ownership:** owns the local peer-device table (bounded size, LRU-evicted).
- **Lifecycle:** starts after provisioning (a device needs an identity before it can meaningfully arbitrate); stops on shutdown.

---

## SECTION 4 — Public Interfaces

All interfaces below are C++ abstract base classes at the `core/` boundary; SDK bindings (Section 1, `sdk/`) are generated against these via the IDL in `sdk/idl/`.

```cpp
// ---- Platform Layer ----

class IClock {
public:
  virtual ~IClock() = default;
  virtual uint64_t nowMonotonicNanos() const = 0;
  virtual uint64_t nowWallClockUnixMillis() const = 0;
};

class IAudioInput {
public:
  virtual ~IAudioInput() = default;
  using FrameCallback = std::function<void(const AudioFrameView& frame, uint64_t captureTimestampNanos)>;
  virtual Result<void> start(const AudioFormat& requestedFormat, FrameCallback cb) = 0;
  virtual Result<void> stop() = 0;
  virtual Result<AudioFormat> currentFormat() const = 0;
  virtual void onDeviceChanged(std::function<void(const DeviceChangeEvent&)> handler) = 0;
};
// FrameCallback runs in the platform capture-callback context (ISR-equivalent): lock-free, allocation-free only.
// start() fails fast on unsupported format; resampling is core/audio/'s job, not the platform's.

class IPlatform {
public:
  virtual ~IPlatform() = default;
  virtual IAudioInput& audioInput() = 0;
  virtual IClock& clock() = 0;
  virtual IStorage& storage() = 0;
  virtual IPowerManager& powerManager() = 0;
};

// ---- Inference Runtime ----

class IInferenceBackend {
public:
  virtual ~IInferenceBackend() = default;
  virtual Result<void> loadModel(const ModelHandle& model) = 0;
  virtual Result<TensorView> infer(const TensorView& input, Arena& scratchArena) = 0;
  virtual BackendStats stats() const = 0;
  virtual BackendKind kind() const = 0;   // OnnxRuntime | TfliteMicro | ExecuTorch
};
// Single-threaded per instance (Inference thread only); infer() returns Result<T>, never throws.

class IModelLoader {
public:
  virtual ~IModelLoader() = default;
  virtual Result<ModelHandle> stage(const std::filesystem::path& verifiedModelPath) = 0;
  virtual Result<void> activate(const ModelHandle& staged) = 0;
  virtual Result<void> rollback() = 0;
  virtual ModelHandle current() const = 0;
};

// ---- Telemetry / Logging ----

class ITelemetry {
public:
  virtual ~ITelemetry() = default;
  virtual void recordEvent(const TelemetryEvent& event) = 0;
  virtual void recordMetric(std::string_view name, double value, const Tags& tags) = 0;
};
// TelemetryEvent has no field capable of holding raw PCM -- enforced by type, not policy.

class ILogger {
public:
  virtual ~ILogger() = default;
  virtual void log(LogLevel level, LogCategory category, std::string_view message, const CorrelationId& id) = 0;
};

// ---- Configuration ----

class IConfigProvider {
public:
  virtual ~IConfigProvider() = default;
  virtual std::shared_ptr<const Config> current() const = 0;
  virtual void onConfigChanged(std::function<void(std::shared_ptr<const Config>)> handler) = 0;
};

// ---- Top-level facade ----

class IWakeWordEngine {
public:
  virtual ~IWakeWordEngine() = default;
  virtual Result<void> initialize(const EngineOptions& options) = 0;
  virtual Result<void> start() = 0;
  virtual Result<void> stop() = 0;
  virtual Result<void> addWakeWord(const WakeWordSpec& spec) = 0;
  virtual Result<void> removeWakeWord(const std::string& id) = 0;
  virtual Result<void> enrollSpeaker(const SpeakerEnrollmentRequest& request) = 0;
  virtual void setListener(IWakeWordListener* listener) = 0;   // non-owning
};

class IWakeWordListener {
public:
  virtual ~IWakeWordListener() = default;
  virtual void onWakeWordDetected(const DetectionEvent& event) = 0;
  virtual void onError(const EngineError& error) = 0;
  virtual void onStateChanged(EngineState newState) = 0;
};
// Invoked only on the Callback thread -- never Audio or Inference -- so SDK/app code can safely block here.
```

**Ownership summary:** every `I*` interface is passed as a raw non-owning pointer/reference across `core/` module boundaries; ownership is via `unique_ptr` held by exactly one module (Section 3). `shared_ptr` is used only for the immutable `Config` snapshot and for `ModelHandle` during the staged-to-active transition window -- nowhere else (Section 16).

---

## SECTION 5 — Memory Architecture

**Buffer/tensor ownership flow:**

```
[platform capture callback] -- raw PCM, owned by platform until handoff
        v
[audio/ ring-buffer pool: N fixed-size slots, single-writer/single-reader per slot] -- moved, not copied
        v
[dsp/ in-place: AGC -> AEC -> NS]
        v
[features/ arena scratch for STFT, writes log-Mel into a second fixed-size slot pool]
        +----------------------+
        v                      v
   [vad/ reads slot]     [runtime/ reads slot when VAD gate is open]
                               v
                    [Arena allocator: per-inference scratch,
                     reset (not freed) after each call --
                     zero heap allocation on the hot path]
```

- **Ring-buffer sizing:** fixed at `initialize()` from `Config`; no dynamic growth. A full pool triggers backpressure, not allocation.
- **Backpressure policy (default):** drop-oldest -- a stale frame is worthless once superseded; blocking capture risks a platform-level overrun instead. `Config`-overridable.
- **Arena allocator:** one per `IInferenceBackend` instance, sized at model-load time from the model manifest (Section 9). `infer()` resets the high-water mark at entry, never calls the system allocator mid-call -- enforced by debug-build allocation-tracking instrumentation that fails the build if `malloc`/`new` fires on the Inference thread's hot path.
- **Model hot-swap:** `ModelManager` mmaps the new file (`stage()`), verifies signature via `security/`, then `activate()` performs one atomic pointer swap observed by `runtime/`. The old mmap region is unmapped only after a per-inference generation counter shows the Inference thread has moved past the swap point -- avoids both a use-after-unmap race and a full-engine pause.
- **Alignment:** all tensor/ring-buffer allocations are 64-byte aligned (cache-line-friendly, SIMD/NEON-compatible) via a custom aligned-allocation wrapper -- never raw `new`/`malloc`.
- **False-sharing avoidance:** ring-buffer slot header (write-index, read-index, sequence counter) is padded to its own cache line, separate from the payload, since Audio (writer) and Inference (reader) threads touch these concurrently.
- **Fragmentation strategy:** no heap allocation on Audio/Inference threads after startup; all steady-state allocation is arena/pool-based. Heap allocation is permitted only on Background, OTA, and Telemetry threads.

---

## SECTION 6 — Threading Model

| Thread | Owner module | Priority | Real-time? | Allowed locks | Forbidden |
|---|---|---|---|---|---|
| **Audio** | `audio/` | Highest (platform RT-audio class / ISR-equivalent) | Yes | Priority-inheritance mutexes, microseconds max | Heap alloc, blocking I/O, out-of-hierarchy locks |
| **Inference** | `runtime/`, `detect/`, `speaker/` | High | Soft real-time | Priority-inheritance mutex for ModelManager handle | Heap alloc on steady-state path, blocking network I/O |
| **OTA** | `ota/`, `security/`, `model/` (load/swap) | Low-Medium | No | Standard mutexes | Direct mutation of `runtime/`'s active model ref (must go through `ModelManager::activate()`) |
| **Telemetry** | `telemetry/` | Low | No | Standard mutexes | Blocking on any real-time thread's queue |
| **Background** | `config/` (writes), `discovery/` | Low | No | Standard mutexes | None beyond global hierarchy |
| **Callback** | dispatches `IWakeWordListener` | Medium | No | None held during listener invocation | Synchronous re-entry into mutating `core/` APIs from a listener |
| **Worker pool** (2-4) | `scheduler/` | Low | No | Standard mutexes | Any real-time work |

**Global lock hierarchy** (debug-build lock-order-verification instrumentation on every mutex acquisition):
```
1. Audio ring-buffer slot lock       (finest, shortest-held)
2. ModelManager handle lock
3. Config snapshot publish lock
4. OTA state-machine lock
5. Telemetry enqueue lock
6. Discovery peer-table lock         (coarsest, longest-held)
```
Acquiring a lower-numbered lock while holding a higher-numbered one is forbidden; the instrumentation aborts the debug build on any violation rather than letting a latent deadlock reach stress testing.

**Audio/Inference separation rationale:** DSP/feature extraction stay in-line on the Audio thread to minimize latency for the common "no speech" case; the Inference thread isolates model inference's higher, more variable latency so a slow inference call never causes the Audio thread to miss its real-time capture deadline.

---

## SECTION 7 — State Machines

### 7.1 System Startup
```
States: Uninitialized -> PlatformInit -> ConfigResolved -> ModelsLoading -> Provisioned? -> Ready -> Running
                                                                  |no
                                                                  v
                                                        ProvisioningPending (OTA/discovery inert, Section 3.15/3.17)
Owning thread: control path serialized through Scheduler; no single thread "owns" startup, each state's work
is dispatched to the thread that owns the corresponding module (e.g., ModelsLoading dispatches to OTA thread).
Terminal failure state: StartupFailed(reason) -- surfaced via IWakeWordListener::onError, engine remains
constructible but inert; caller may retry initialize() after resolving the reported cause.
```

### 7.2 Model Loading (per model slot, Section 3.13)
```
Unloaded -> Staging (mmap in progress) -> Verifying (signature check) -> Verified -> Active
                                                  |fail                                |new version staged
                                                  v                                    v
                                              Rejected (rollback to previous Active, if any)   Staging (next)
```

### 7.3 Wake Detection Cascade (per configured wake word, owned by `detect/` on the Inference thread)
```
Idle (VAD gate closed) -> VadTriggered -> Stage1Running -> Stage1Rejected -> Idle
                                                 |
                                                 v Stage1Triggered
                                          Stage2Running -> Stage2Rejected -> Idle
                                                 |
                                                 v Stage2Triggered
                                   SpeakerVerifying (only if speaker verification enabled + past ADR gate)
                                                 |
                                                 v
                                          DetectionConfirmed -> emits DetectionEvent via Callback thread -> Idle
```
Every transition carries the CorrelationId established at `VadTriggered` (Section 12).

### 7.4 OTA Update (owned by `ota/` on the OTA thread)
```
Idle -> CheckingForUpdate -> Downloading -> ChecksumVerifying -> SignatureVerifying -> Staged
   -> (RemoteConfig says "rollout eligible"?) -> Activating -> SelfTesting -> Committed
                                                                     |fail
                                                                     v
                                                                RollingBack -> Idle (previous version restored)
```
`SelfTesting` runs the post-update synthetic self-test clip (prior ADR) before `Committed`; failure at any state after `Staged` triggers `RollingBack`, never a partial/undefined state.

### 7.5 Error Recovery (cross-cutting; supervises the other machines)
```
Normal -> Degraded(subsystem) -> [subsystem-specific recovery attempt, bounded retry per Section 11]
   -> Recovered -> Normal
   -> RecoveryExhausted -> SafeMode(subsystem disabled, rest of engine continues where independent)
```
`SafeMode` is per-subsystem, not global: e.g., a persistently failing OTA subsystem enters `SafeMode` (stops attempting updates, surfaces `onError`) while wake-word detection itself continues unaffected, since `ota/` sits at Row 3 and nothing in Rows 4-8 depends on it.

### 7.6 Device Provisioning (owned by `security/`, runs once per device lifetime unless factory-reset)
```
Unprovisioned -> AwaitingTrustAnchor -> TrustAnchorInstalled -> AttestationKeyGenerated
   -> AttestationCompleted -> Provisioned
```
`AwaitingTrustAnchor` is satisfied either by a factory-flashed trust anchor (embedded targets) or a first-boot provisioning-service handshake (mobile/desktop targets) -- both paths converge at `TrustAnchorInstalled`. `Provisioned` gates `ota/` and `discovery/` activation (Sections 3.15, 3.17).

### 7.7 Power State (owned by `power/`, runs on the Audio thread)
```
Active -> [VAD silence timeout] -> LowPower -> [platform-supported deep sleep available?]
   yes -> DeepSleep(analog gate only, digital Stage-1 suspended) -> [analog trigger] -> Active
   no  -> LowPower (digital Stage-1 continues at reduced duty cycle, per platform capability)
```
The `DeepSleep` branch exists only where the platform layer reports analog-wake-capable hardware (ESP32/Cortex-M reference designs); mobile/desktop platforms remain in `LowPower` since they lack this hardware path.

### 7.8 Microphone Changes (owned by `audio/`, on the Audio thread)
```
Capturing(deviceA) -> DeviceChangeDetected -> Draining(deviceA) -> Reconfiguring
   -> [resample needed?] -> ResamplerActive -> Capturing(deviceB)
   -> [format incompatible] -> AwaitingDevice (no capture; onError surfaced; auto-retries on next device event)
```

---

## SECTION 8 — Sequence Diagrams (textual)

### 8.1 Cold Startup
```
App -> IWakeWordEngine::initialize(options)
  Engine -> Scheduler: create threads
  Engine -> IPlatform: construct per-OS implementation
  Engine -> ConfigProvider: resolve Config (compile-time defaults + platform overrides)
  Engine -> ModelManager (x N slots): stage() + activate() for each configured model, from local storage
  Engine -> Security: load trust anchor (fails into ProvisioningPending if absent, Section 7.6)
  Engine -> Telemetry: start (captures the above as startup-latency metric, Section 13)
  Engine --> App: Result<void> Ready | StartupFailed(reason)
```

### 8.2 Warm Startup (models already resident from a prior session, platform did not evict process)
```
App -> initialize()
  Engine -> ModelManager: current() returns already-mmap'd handles (no re-verification of signature needed
             within the same process lifetime -- verification is a load-time, not a per-inference, cost)
  Engine --> App: Ready (materially lower latency than 8.1; this delta is the "warm vs cold start" metric, Section 13)
```

### 8.3 Wake Word Detection (happy path)
```
Platform capture callback -> audio/ ring buffer -> dsp/ (in-place) -> features/ -> vad/: speech detected
  vad/ -> detect/: VadTriggered(CorrelationId=new)
  detect/ -> runtime/: infer(Stage1Model, window)
  runtime/ --> detect/: Stage1Triggered(confidence)
  detect/ -> runtime/: infer(Stage2Model, extended window)
  runtime/ --> detect/: Stage2Triggered(confidence)
  detect/ -> speaker/ (if enabled): verify(embedding, enrolledTemplate)
  speaker/ --> detect/: Verified
  detect/ -> Callback thread: onWakeWordDetected(DetectionEvent{CorrelationId, confidence, timestamp})
  detect/ -> telemetry/: recordEvent(cascade-path, same CorrelationId)
```

### 8.4 False Reject (Stage-1 rejects a true positive, or VAD never triggers)
```
Same path as 8.3 up to vad/ or Stage1 -- terminates at Stage1Rejected or VAD-never-triggers.
No DetectionEvent emitted. If golden-fixture testing (Section 14) flags this fixture as an expected-positive
that produced no event, the fixture+CorrelationId (if any) is attached to the regression report automatically.
```

### 8.5 False Accept (Stage-2 or full cascade triggers on a non-wake-word utterance)
```
Same path as 8.3, cascade completes to DetectionEvent on audio that the benchmark corpus (Section 14/Section
"benchmarks/") labels as negative. Telemetry's CorrelationId-tagged event allows the benchmark harness to
retrieve the exact per-stage confidence scores that led to the false accept for regression analysis --
this is precisely the mechanism Stage 6 Finding 10 was designed to enable.
```

### 8.6 OTA Update
```
ota/ -> remote endpoint: check for update (per staged-rollout eligibility, Section "cloud infra" already scoped)
  remote --> ota/: manifest(version, checksum, signature, rollout-percentage)
  ota/ -> security/: verify manifest signature
  ota/ -> platform/IStorage: download to staged path
  ota/ -> security/: verify checksum
  ota/ -> ModelManager: stage(path)
  ModelManager -> security/: verify model-file signature (independent of manifest signature)
  ModelManager --> ota/: Staged
  ota/ -> ModelManager: activate() [see 8.7]
```

### 8.7 Model Swap
```
ota/ -> ModelManager::activate(stagedHandle)
  ModelManager -> runtime/: atomic pointer swap of active ModelHandle
  runtime/ (Inference thread, next inference call): observes new handle via generation counter
  ModelManager -> [self-test clip via detect/ cascade, Section 7.4 SelfTesting]
  self-test result: pass -> Committed, unmap old handle once generation counter confirms no in-flight reader
                    fail -> rollback() -> restore previous ModelHandle atomically, same swap mechanism in reverse
```

### 8.8 Device Discovery
```
discovery/ (Background thread) -> local network: mDNS advertise(deviceId, capability=wakeword-arbitration)
  discovery/ <- local network: peer advertisements
  discovery/ -> peer table: upsert(peerId, lastSeen, capabilities)
```

### 8.9 Multi-Device Arbitration
```
Device A: detect/ reaches Stage1Triggered with confidence C_A, timestamp T_A
  Device A -> discovery/: broadcast ArbitrationCandidate(CorrelationId, C_A, T_A) over local transport
  Device A <- Device B, Device C: their own ArbitrationCandidate broadcasts (if they also triggered within
              the arbitration time window, Config-defined, e.g. a few hundred milliseconds)
  Each device independently computes: am I the max-confidence candidate among all received within the window?
  Winning device: proceeds to Stage2Running (8.3 continues)
  Losing device(s): transition back to Idle (7.3) without proceeding to Stage2 -- avoids duplicate wake events
                      and avoids the losing device wasting Stage2/speaker-verification compute
```

### 8.10 Shutdown
```
App -> stop()
  Engine -> audio/: stop() (drains in-flight frame, does not process new ones)
  Engine -> Telemetry: flush pending events (bounded timeout, then proceeds regardless)
  Engine -> ModelManager (all slots): release mmap handles
  Engine -> Scheduler: join all threads in reverse creation order
  Engine --> App: Result<void>
```


---

## SECTION 9 — Configuration

**Compile-time configuration** (CMake options, resolved at build time, cannot change without a rebuild):
- Target platform (`AURA_PLATFORM=android|ios|linux|windows|macos|esp32|cortex_m`) -- selects which `platform/` subfolder compiles in; all others are excluded from the build entirely (not merely `#ifdef`'d out), keeping embedded binary size minimal.
- Inference backend inclusion flags (`AURA_ENABLE_ONNXRUNTIME`, `AURA_ENABLE_TFLITE_MICRO`, `AURA_ENABLE_EXECUTORCH`) -- a given build links only the backend(s) it needs; MCU builds link `TfliteMicro` only.
- `AURA_ENABLE_SPEAKER_VERIFICATION` -- compiled out entirely for any build/platform combination that hasn't cleared the anti-spoofing ADR gate; this is a compile-time, not runtime, gate, so the feature cannot be silently re-enabled by a runtime config flag alone.
- `AURA_ENABLE_DEBUG_LOCK_INSTRUMENTATION` -- the lock-order-verification and allocation-tracking instrumentation from Sections 5/6, present in debug/CI builds, compiled out of release builds for performance.

**Runtime configuration** (the `Config` snapshot, Section 3.2), sourced in this precedence order (highest wins): remote config (if `ota/`/provisioning has completed and connectivity exists) > on-device persisted overrides (e.g., a developer debug override) > compiled-in defaults. A resolved `Config` is always fully populated (no partial/optional fields at the consumption site) -- unresolved remote values fall back to the next-highest-precedence source before publishing, so no module ever needs to null-check a config field.

**Feature flags:** boolean/enum entries within `Config`, evaluated identically whether sourced from remote config or local override -- there is no separate "feature flag system" from the configuration system; this deliberately avoids the two-systems-doing-similar-things anti-pattern.

**Model selection:** the active model for each slot (Stage-1/Stage-2/Speaker) is a `Config` field (a model identifier + minimum-compatible-runtime-version, per the versioning scheme already fixed in prior documents); `ModelManager` reacts to a `Config` change here exactly like an OTA-triggered swap (Section 8.7) -- model selection via config and model selection via OTA share the same underlying swap mechanism, not two parallel code paths.

**Platform overrides:** a per-platform `Config` overlay (e.g., different ring-buffer sizes for MCU vs. desktop, different backpressure policy defaults) applied before remote/local overrides in the precedence order above -- expressed as data (a per-platform default-config file compiled in), not as scattered `#ifdef`s throughout module code.

---

## SECTION 10 — Plugin Architecture

| Plugin point | Interface | Built-in implementations | Notes |
|---|---|---|---|
| Inference backend | `IInferenceBackend` | OnnxRuntime, TfliteMicro, ExecuTorch | New backend = new class in `core/runtime/`, registered in the backend factory at compile time via the `AURA_ENABLE_*` flags (Section 9); no dynamic plugin loading on embedded targets (binary-size/security reasons), reflection-based registration permitted on desktop-tier builds only. |
| DSP stage | `IDspStage` | AGC, AEC, NS implementations named in prior documents | Stages are composed into a fixed pipeline order (`aura_addendum_v4.md` §3) at build/config time, not dynamically reordered at runtime -- ordering is a correctness-relevant decision, not a customization point. |
| Telemetry sink | `ITelemetrySink` (consumed internally by `ITelemetry`) | Local-file sink (offline fallback), remote-endpoint sink | Multiple sinks may be active simultaneously (e.g., always write local, opportunistically flush remote) -- this is the concrete mechanism satisfying the "offline guarantees" requirement from the original project brief. |
| Storage backend | `IStorage` (part of `IPlatform`) | Per-OS filesystem implementation | Not independently pluggable beyond the platform layer -- a deliberate scope decision; storage backend swapping is a platform concern, not an application-level plugin concern. |
| Platform | `IPlatform` | One per OS target (Section 3.1) | The primary, load-bearing plugin point of the whole architecture (this is the PAL). |
| Authentication (speaker verification enrollment identity, if ever extended beyond on-device-only) | Not yet specified as an interface -- explicitly out of scope for this SAS version, since no prior ADR established a requirement for external identity-provider integration. Recorded here as a known future extension point, not designed now. |
| Discovery transport | `IDeviceDiscovery` | mDNS implementation, BLE implementation | Selected per-platform via `Config`, per Stage 6 Finding 9 (mDNS on mobile/desktop, BLE on MCU). |
| Future hardware (NPU/DSP accelerators, e.g. Ethos-U) | Exposed as an additional `IInferenceBackend` implementation, not a separate plugin category -- Ethos-U-backed inference is architecturally identical to any other backend from `runtime/`'s perspective (this is precisely why Finding 12's backend-abstraction investment pays off here). |

---

## SECTION 11 — Error Handling

**Error model:** `Result<T>` (a tagged union of `T` or `Error`), used for every fallible operation on the Audio/Inference hot path -- no exceptions on these threads (Section 16). Exceptions are permitted only on the OTA/Telemetry/Background threads, where the cost of unwinding is acceptable and the ergonomic benefit is worthwhile.

| Error category | Examples | Recovery policy | Retry policy | Fatal? |
|---|---|---|---|---|
| Transient platform I/O | audio device busy, storage temporarily unavailable | Exponential backoff, bounded attempts | Yes, bounded (Config-defined max attempts) | No -- surfaces `onError`, engine continues in degraded mode where possible |
| Model verification failure | signature mismatch, checksum mismatch | Reject the staged model, keep running on the current `Active` model | No retry of the same artifact; a new OTA check may fetch a corrected one later | No |
| Inference backend failure | backend reports an internal error (e.g., unsupported op post-update) | Roll back to previous model version (Section 7.2/8.7) | No retry with the same model | No, unless rollback itself fails (see below) |
| Rollback failure (no known-good model available) | e.g., very first boot with a corrupted initial model | Enter `SafeMode` for detection specifically | N/A | **Yes**, for the detection subsystem only -- engine remains alive for OTA/diagnostics purposes |
| Provisioning failure | no trust anchor obtainable | Remain in `ProvisioningPending` indefinitely, retry per Config interval | Yes, unbounded but rate-limited | No -- device functions with detection disabled until provisioned, per product requirements to be set outside this SAS |
| Audio pipeline overrun | ring buffer full despite backpressure policy | Apply configured backpressure policy (default drop-oldest, Section 5) | N/A (per-frame, not a retryable operation) | No |
| Deadlock/lock-order violation | debug-build instrumentation detects out-of-order acquisition | Immediate abort with diagnostic dump (debug builds only) | N/A | Yes, in debug builds by design (fail loud in CI, never in production since the ordering is statically correct in release builds by construction) |

**Graceful degradation principle (applies across the table above):** a failure in any Row-3-or-higher module (Section 2) must not take down Row-0/1/2 modules -- e.g., OTA/discovery failures never affect core detection; a speaker-verification failure falls back to Stage-2-only detection (with `onError` surfaced) rather than blocking the wake event entirely, unless speaker verification was explicitly configured as access-control-required for a given wake word (a `Config`-level choice, not a hardcoded behavior).

---

## SECTION 12 — Logging

**Structured logging:** every log line is a structured record (not a free-text string), with fields: `timestamp`, `level`, `category`, `correlationId` (nullable only for logs that genuinely precede any correlation-worthy event, e.g., early startup), `message`, `moduleTag`.

**Log levels:** `Trace` (debug builds only, compiled out of release), `Debug`, `Info`, `Warn`, `Error`, `Fatal`.

**Categories:** one per Section 3 module (`Audio`, `Dsp`, `Features`, `Vad`, `Detect`, `Speaker`, `Runtime`, `Model`, `Ota`, `Security`, `Telemetry`, `Discovery`, `Power`, `Config`, `Platform`) -- allows per-category log-level filtering in the field without a full redeploy (a `Config`-controlled field, Section 9).

**Event IDs and Correlation IDs (implements Stage 6 Finding 10):** a `CorrelationId` is minted once at `VadTriggered` (Section 7.3) and threaded through every subsequent log line and telemetry event for that detection cascade, including across the OTA/model-swap boundary if a swap occurs mid-cascade (the in-flight cascade completes against its already-loaded model generation; the correlation record notes which model generation actually served the request). A separate, install-scoped `DeviceCorrelationId` (not the per-cascade one) tags cross-cascade telemetry aggregates (e.g., "this device's FA rate over the last hour") without ever being a stable cross-device identifier usable for tracking (rotated per the telemetry privacy design already established in prior documents).

**Sampling:** `Trace`/`Debug` levels are sampled (not 100%-logged) on production builds even when enabled for a cohort, at a `Config`-controlled rate, to bound both storage cost and the risk of any category inadvertently capturing more detail than the privacy review intends; `Warn`/`Error`/`Fatal` are never sampled (always logged in full).

**Privacy requirement (restates, does not re-derive, prior documents' constraint as a concrete logging-system rule):** the `TelemetryEvent`/log-record types have no field of a type capable of holding raw PCM audio or a raw speaker-embedding vector -- this is a type-system-level guarantee (Section 4), not a code-review-time policy, so a future engineer cannot accidentally log raw audio by passing the wrong variable to a correctly-typed logging call.

---

## SECTION 13 — Metrics

All metrics are emitted via `ITelemetry::recordMetric`, tagged with at least `{platform, buildVersion, modelVersion}`; per-cascade metrics additionally carry the `CorrelationId`.

| Metric | Unit | Emitted by | Notes |
|---|---|---|---|
| `wake.latency.e2e` | ms | `detect/` | VadTriggered timestamp to DetectionConfirmed timestamp; the primary metric against the <100ms target. |
| `wake.latency.stage1` / `wake.latency.stage2` | ms | `runtime/` (via `BackendStats`) | Per-stage breakdown of the above, for regression attribution. |
| `cpu.utilization.audio_thread` / `.inference_thread` | % | `scheduler/` (periodic sampling on Background thread) | Sampled, not per-frame (per-frame CPU measurement itself would perturb the measurement). |
| `memory.rss.current` / `.high_water_mark` | bytes | `platform/IPlatform` (OS-specific query) | High-water mark specifically catches transient spikes (e.g., during model hot-swap, Section 5) that an average would hide. |
| `power.draw.estimated` | mW (where platform exposes it) or a proxy duty-cycle percentage otherwise | `power/` | Platform-dependent availability; falls back to reporting Active/LowPower/DeepSleep duty-cycle percentages where direct power measurement isn't exposed by the OS/hardware. |
| `model.load_time.cold` / `.warm` | ms | `model/` | Corresponds to Sequence 8.1/8.2. |
| `model.swap.duration` / `.self_test_result` | ms / bool | `model/`, `ota/` | Corresponds to Sequence 8.7. |
| `cache.model_mmap.page_faults` | count | `platform/IPlatform` (where the OS exposes this) | A proxy for whether the mmap'd model is actually warm in the OS page cache post-load. |
| `queue.ring_buffer.depth` / `.drop_count` | count | `audio/` | Directly measures the backpressure policy's actual behavior in the field, not just in benchmark conditions. |
| `queue.telemetry.drop_count` | count | `telemetry/` | Per Section 3.14's explicit non-silent-drop requirement. |
| `ota.rollout.stage` / `.rollback_count` | enum / count | `ota/` | Feeds the staged-rollout/canary monitoring already scoped in prior documents. |
| `fa_rate` / `fr_rate` (aggregate, opt-in, privacy-reviewed) | per-hour / % | `telemetry/`, aggregated from anonymized on-device proxies, never raw audio | This is the field-measured counterpart to the benchmark-harness's lab-measured FA/hr -- both must exist; they answer different questions (lab-representative-corpus accuracy vs. real-world-fleet accuracy) and are reported separately, not conflated into one number. |

---

## SECTION 14 — Testing Architecture

| Layer | Location | Scope | Runs where |
|---|---|---|---|
| Unit tests | beside each module in `core/*/tests/` | Single-module logic, using `tests/mock_platform/` for any `IPlatform` dependency | Every CI run, every platform target (cross-compiled and run in emulation/QEMU for embedded targets where hardware-in-loop isn't available) |
| Integration tests | `tests/` | Multi-module interactions (e.g., full cascade from synthetic audio input through `IWakeWordListener` callback) using `mock_platform/` | Every CI run, host-machine only (fast feedback); a subset also runs on real-hardware CI (see below) |
| Golden-fixture tests | `tests/golden/`, reading from `benchmarks/corpus/` | Deterministic replay (Section 5's determinism constraints on the pipeline make this possible) of specific recorded audio against the exact expected cascade outcome, per fixture | Every CI run; a regression here blocks merge |
| Hardware-in-loop tests | `tests/` gated behind a hardware-availability CI runner tag | Real ESP32-S3/Cortex-M/reference Android/iOS device farm, per the hardware matrix (Stage 6 Finding, benchmark harness) | Nightly, and on every release-candidate build; not on every commit (cost/turnaround trade-off) |
| Regression/benchmark framework | `benchmarks/harness/` | Automated FA/hr, DET, latency, CPU, RAM, power measurement against the versioned corpus | Nightly on the hardware matrix; results published to the dashboard (Section 1, `benchmarks/dashboards/`) with automated regression-threshold alerting |
| Power benchmarks | `benchmarks/harness/`, hardware-in-loop only | Actual current-draw measurement on reference hardware (requires physical measurement equipment in the CI hardware farm, not simulatable) | Nightly, release-candidate gating |
| Stress tests | `tests/stress/` | 24-hour and 7-day continuous soak runs (named milestones, per prior documents) | Dedicated long-running CI lane, not part of the standard per-commit pipeline |
| Fuzz tests | `tests/fuzz/` | Malformed audio streams, malformed model files, malformed OTA packages (Stage 6 Finding, security appendix) | Continuous fuzzing lane (e.g., coverage-guided fuzzing running persistently, not just per-commit) |
| Deterministic replay / simulation | `tests/mock_platform/` + Section 5's determinism guarantees | Enables reproducing a specific field-reported issue by replaying its exact audio + config on a developer's host machine | On-demand, developer-invoked; also the mechanism by which a field bug report becomes a new golden fixture (closing the loop back into the golden-fixture suite) |
| Emulator/simulation for embedded | QEMU (Cortex-M) / ESP32 emulation where available, else `mock_platform/` | Enables unit/integration testing of embedded-targeted `core/` code without physical hardware for every commit | Every CI run |

---

## SECTION 15 — Build System

**Repository strategy:** single monorepo (per Stage 6 Finding 6's recommendation), containing `core/`, all `sdk/*` bindings, all `apps/*` reference applications, `benchmarks/`, and `tools/` -- chosen specifically because the cross-language-binding codegen (Section 1, `sdk/idl/`) and the dependency-graph linter (Section 2) both require atomic, whole-repository visibility to function correctly; a polyrepo split would require these to operate across repository boundaries, adding synchronization complexity without a corresponding benefit at this project's team size.

**Build graph:** CMake (per Stage 6 Finding 6) as the primary build-graph definition for `core/` and all native `apps/*`/`sdk/*` glue code, with per-platform toolchain files (`cmake/toolchains/android.cmake`, `ios.cmake`, `esp32.cmake`, etc.) selecting the appropriate cross-compiler and the `AURA_PLATFORM`/`AURA_ENABLE_*` options from Section 9. Gradle (Android) and Xcode/xcodebuild (iOS) wrap the CMake build as a subordinate step for their respective `apps/`/`sdk/` layers, rather than reimplementing the native build logic -- CMake remains the single source of truth for how `core/` itself compiles.

**Cross compilation:** each platform target has a dedicated CMake toolchain file (above) and a dedicated CI job; no single "universal" build invocation attempts all platforms at once. The dependency-graph linter (Section 2) runs once, platform-independently, against the `#include` graph before any platform-specific compilation begins, so a forbidden-import violation is caught in seconds, not after a 20-minute embedded cross-compile.

**Hermetic / reproducible builds:** third-party dependencies (`third_party/`) are vendored and pinned by exact version/commit hash, not fetched by floating version range, specifically to support the SBOM/supply-chain requirements already scoped in prior documents and to make a "bit-identical output from identical input" claim achievable per-platform (full bit-for-bit reproducibility across all 11 targets is not asserted here as already-solved -- it is a build-system goal this SAS establishes the prerequisite for, not a completed guarantee).

**Incremental builds / build cache:** CMake's native incremental-build support is used as the default; a shared build-cache (e.g., ccache-style object-file caching) is used in CI specifically to keep the 11-platform CI matrix's turnaround time bounded, given how much of `core/` is shared, platform-independent code that shouldn't need recompilation per platform-specific CI job beyond its final link step.

**Artifact management:** compiled `core/` static/shared libraries per platform, generated SDK packages per language (Kotlin AAR, Swift Package, Dart/Flutter plugin package, Python wheel), and signed firmware images (embedded targets) are each versioned and published to an internal artifact registry (the same registry underlying the model-registry/MLOps tooling already scoped, reused rather than standing up a second, parallel artifact store).

**SDK generation:** driven by `sdk/idl/`'s interface definitions (Section 1/4) through the binding-codegen tool (Stage 6 Finding 5) as a build step invoked from the top-level CMake build, not as a manually-run, easily-forgotten side process -- a stale generated binding is a build failure (checksum mismatch between the IDL and the checked-in generated code, in repositories where generated code is checked in for review-diff visibility), not a silent drift.

**CI layout:** per-platform build+unit-test jobs (fast, every commit) -> integration+golden-fixture jobs (every commit) -> nightly hardware-in-loop+benchmark+power jobs -> release-candidate gate (requires all of the above green, plus the dependency-graph linter, plus SBOM generation, per prior security-appendix requirements).

---

## SECTION 16 — Coding Standards

- **Naming:** modules/namespaces use `aura::<module>` (e.g., `aura::audio`, `aura::runtime`); interfaces prefixed `I` (Section 4); implementation classes suffixed with their concrete identity (e.g., `OnnxRuntimeBackend`), never a generic `*Impl` suffix.
- **Ownership:** `unique_ptr` is the default for all owned pointers; `shared_ptr` is permitted only for the two cases named in Section 4 (Config snapshot, in-flight ModelHandle transition) -- any other proposed `shared_ptr` use requires explicit sign-off, since implicit shared ownership is exactly the pattern that makes the memory-ownership guarantees in Section 5 hard to reason about.
- **Const correctness:** all read-only interface methods are `const`-qualified; any interface method that is not `const` is, by convention, assumed to mutate state and must be documented with its thread-safety contract (Section 4's per-interface comments are the required template, not optional documentation).
- **Error handling:** `Result<T>` (Section 11) on the Audio/Inference threads, no exceptions; standard C++ exceptions permitted on OTA/Telemetry/Background threads only, and must never propagate across a thread boundary (caught and converted to `Result<T>`/`Error` at the boundary where a cross-thread call occurs).
- **Exceptions:** disabled entirely (`-fno-exceptions` equivalent) in the embedded (ESP32/Cortex-M) build configuration, per standard embedded C++ practice and binary-size constraints; mobile/desktop builds compile with exceptions enabled (for third-party dependency compatibility) but `core/`'s own code follows the no-throw-on-hot-path rule regardless.
- **RTTI:** disabled in embedded builds (binary size); avoided by convention (not physically disabled) in mobile/desktop `core/` code -- `dynamic_cast` on an `I*` interface is a code-review-blocking pattern, since the module-boundary interfaces in Section 4 are designed specifically so downcasting should never be necessary.
- **Templates:** permitted for genuinely generic, header-only utility code (e.g., the `Result<T>` type itself, the `IStateMachine<TState, TEvent>` framework); not permitted as a substitute for the virtual-interface module-boundary pattern established in Section 4 -- module boundaries are always virtual interfaces, never template-parameterized, so that the dependency graph (Section 2) remains statically analyzable by the CI linter without template instantiation analysis.
- **Thread safety:** every public method on every `I*` interface must document its thread-safety contract in a comment directly above the declaration (per the Section 4 examples) -- this is a required code-review checklist item, not a best-effort convention.
- **Documentation:** every module's public header carries a top-of-file comment stating its Section-3-equivalent Responsibilities/Dependencies/Thread-ownership/Memory-ownership/Lifecycle summary, so the SAS and the codebase cannot silently drift apart -- a module header missing this summary is a lint failure (Section 15's CI).

---

## SECTION 17 — Implementation Roadmap

| Milestone | Deliverables | Dependencies | Acceptance criteria | Key risks | Estimated effort |
|---|---|---|---|---|---|
| **M0 — Skeleton** | Repo layout (Section 1), CMake build graph (Section 15) building an empty `core/` across all 11 platform toolchains, dependency-graph linter operational | None | CI green on an empty-but-correctly-structured `core/` for every platform target | Toolchain setup for the least-common platforms (ESP32/Cortex-M cross-compilation) is typically the long pole | Medium |
| **M1 — Platform Abstraction Layer** | `IPlatform` + all per-OS implementations (Section 3.1), `mock_platform/` for testing | M0 | Every platform implementation passes the same `IPlatform` conformance test suite | Android/iOS audio-API ADRs (Oboe/AVAudioEngine) must be finalized before this milestone, not during it | High |
| **M2 — Audio Pipeline** | `audio/`, `dsp/`, `features/`, `vad/` (Sections 3.6-3.9), memory architecture (Section 5) fully implemented and lock/allocation-instrumented | M1 | Golden-fixture tests (silence, clean speech, noisy speech) pass deterministically; zero heap allocation confirmed on Audio thread via instrumentation | Determinism (Section 14) is easy to lose accidentally (e.g., an unseeded RNG in an augmentation-adjacent code path) -- must be caught here, not later | High |
| **M3 — Inference Runtime + Backend Plugin Interface** | `IInferenceBackend`, `OnnxRuntimeBackend`, `TfliteMicroBackend` (ExecuTorch backend deferred to M3b as an evaluation-only path) | M2 | `detect/` cascade (Stage-1 only) produces correct results against golden fixtures on at least one mobile and one embedded target | Model-format/tensor-layout mismatches between training pipeline output and runtime input are a common integration failure point | High |
| **M4 — Full Cascade + Model Manager** | Stage-2 verifier integration, `model/` hot-swap architecture (Section 5), state machines 7.2/7.3 | M3 | Hot-swap sequence (8.7) demonstrated with zero missed detections during a swap, on real hardware | Generation-counter-based unmap timing (Section 5) needs careful stress testing -- a subtle race here is exactly the class of bug this design is meant to prevent, but only if correctly implemented | Medium-High |
| **M5 — Security + OTA + Provisioning** | `security/`, `ota/` full state machine (7.4), provisioning state machine (7.6) | M4 | End-to-end OTA update demonstrated on a provisioned device, including a forced-failure rollback test | Provisioning's manufacturing-process dependency (Stage 6 Finding 8) means this milestone has a non-engineering dependency (CoBuild Labs manufacturing process definition) that can block it | High |
| **M6 — Telemetry, Logging, Metrics** | `telemetry/`, correlation-ID propagation (Section 12), metrics (Section 13) | M4 (can parallelize with M5) | A field-reported false accept can be traced end-to-end via its CorrelationId in the dashboard | Privacy-review sign-off on the telemetry schema is a process dependency, not purely an engineering one | Medium |
| **M7 — SDK Bindings** | `sdk/kotlin`, `sdk/swift`, `sdk/dart` generated via the codegen pipeline (Section 15), reference apps in `apps/` | M4 | A reference app on Android, iOS, and Flutter each successfully registers a wake word and receives `onWakeWordDetected` | Binding-codegen tool adoption/learning curve is the primary risk, as flagged in the prior architecture review | Medium |
| **M8 — Multi-Device Arbitration + Discovery** | `discovery/` (mDNS + BLE), arbitration sequence (8.9) | M7 (needs a working SDK to test multi-device scenarios realistically) | Two physical reference devices correctly suppress the losing device's Stage-2/speaker-verification compute in a controlled test | This entire milestone remains contingent on the product-priority decision flagged in the prior review -- may be deprioritized relative to M9/M10 depending on that decision | Medium-High |
| **M9 — Power/MCU-tier hardening** | Three-stage cascade for MCU targets (7.7's DeepSleep branch), analog-gate hardware reference integration | M4, and a hardware reference design from CoBuild Labs | Measured battery life on a coin-cell reference design meets the product's (not-yet-set-by-this-SAS) target | This milestone's necessity is itself conditional on a product decision (mains-powered vs. battery-powered MCU deployment) not yet made, per the prior review's own flag | High |
| **M10 — Full benchmark harness + CI hardening** | `benchmarks/harness/` automated on the full hardware matrix, nightly dashboards, fuzz/stress/soak lanes (Section 14) fully wired into CI | M2 onward, incrementally | 7-day soak test passes with zero memory growth/crashes on every Tier-1 platform (Stage 6's platform tiering, prior ADR) | Physical hardware-farm provisioning and maintenance is an ongoing operational cost this SAS does not itself resolve | High |

**Sequencing note:** M1-M4 are strictly sequential (each depends on the previous); M5-M10 can partially parallelize across engineers once M4 is complete, as noted in the Dependencies column.

---

## SECTION 18 — Definition of Done (per subsystem, applies to every module in Section 3)

A module is Done only when **all** of the following are true:
1. **Code complete:** implements its full Section 3 responsibility set; no `TODO`/stub methods remain on any code path reachable from `IWakeWordEngine`'s public API.
2. **Tests complete:** unit tests (Section 14) at the module boundary achieve the project's mandated coverage threshold (threshold value itself is a team decision outside this SAS's scope, but the requirement that one exist and be enforced in CI is not optional); at least one golden fixture exercises the module's behavior end-to-end where applicable.
3. **Benchmarks complete:** for any module on the Audio/Inference thread (Section 6), its contribution to `wake.latency.e2e` (Section 13) is individually measured and within its allocated sub-budget (sub-budget allocation across modules is a Phase-2a-established number, not invented here); for any module with a memory footprint, its high-water mark is measured against the target device tier's budget.
4. **Documentation complete:** the module's header carries the Section-16-mandated summary; any public interface change is reflected in `sdk/idl/` and the generated-binding diff is reviewed, not just the C++ change.
5. **Platform validation:** the module's `IPlatform`-dependent behavior (if any) has been exercised on every Tier-1 platform (per the platform-tiering ADR) at minimum, with Tier-2/Tier-3 validation tracked but not blocking for modules where those tiers are explicitly deferred per the roadmap (Section 17).
6. **Performance validation:** no regression against the previous release's benchmark numbers beyond the CI-enforced threshold (Section 14's regression framework) for any metric this module contributes to.
7. **Security validation:** for any module handling model files, OTA payloads, or key material (`security/`, `ota/`, `model/` specifically), the relevant fuzz-test suite (Section 14) has run for a minimum duration with zero crashes, and the module has been included in the most recent SBOM generation pass.

---

## SECTION 19 — Architecture Decision Register (Index)

| ADR ID | Title | Status | Owner (role, not name) | Depends on |
|---|---|---|---|---|
| ADR-001 | First-stage model architecture (BC-ResNet vs. MatchboxNet vs. Keyword Transformer) | Deferred — pending Phase 2a experimentation | ML Architect | — |
| ADR-002 | Cross-platform inference runtime (ONNX Runtime + TFLite Micro primary; ExecuTorch evaluated) | Accepted (primary path); ExecuTorch sub-decision Deferred | Runtime Architect | Finding-12 (backend plugin interface) |
| ADR-003 | Feature front-end (log-Mel default; PCEN evaluated for far-field) | Accepted (default); PCEN sub-decision Deferred | DSP Architect | — |
| ADR-004 | Quantization strategy (QAT default for shipped models) | Accepted | ML Architect | — |
| ADR-005 | Speaker verification architecture + anti-spoofing gate | Accepted (architecture: ECAPA-TDNN); Deferred (ship gate: pending ASVspoof-methodology evaluation) | Security Architect + ML Architect (joint) | ADR-002 (runtime), Security ADR-provisioning |
| ADR-006 | Platform tiering (Tier 1/2/3 sequencing) | Accepted (as a framework); specific tier assignment Deferred pending business/staffing input | Product Architect | — |
| ADR-PAL | Platform Abstraction Layer boundary (Section 1-3.1) | Accepted | Systems Architect | — |
| ADR-AudioBuf | Audio buffer ownership / backpressure model (Section 5) | Accepted | Systems Architect | ADR-PAL |
| ADR-MicInput | Heterogeneous mic input / resampling architecture (Section 3.6) | Accepted | Audio Engineer | ADR-AudioBuf |
| ADR-ModelLifecycle | Model hot-swap / mmap / arena architecture (Section 5, 3.13) | Accepted | Runtime Architect | ADR-PAL |
| ADR-Binding | Cross-language binding codegen tool selection (Section 1, 15) | Accepted (approach); specific tool (UniFFI vs. custom) Deferred pending M7 prototyping | SDK Architect | ADR-PAL, Section 4 interfaces frozen |
| ADR-Build | Build system (CMake primary, Gradle/Xcode as wrappers) | Accepted | Build Systems Engineer | — |
| ADR-Repo | Monorepo strategy | Accepted | Build Systems Engineer | ADR-Build |
| ADR-LockHierarchy | Global lock-acquisition ordering (Section 6) | Accepted | Systems Architect | ADR-PAL, ADR-AudioBuf |
| ADR-Provisioning | Device provisioning / trust-anchor bootstrapping (Section 7.6) | Accepted (architecture); Deferred (manufacturing-process specifics, owned jointly with CoBuild Labs hardware operations) | Security Architect | — |
| ADR-Discovery | Local-discovery protocol (mDNS/BLE) for multi-device arbitration | Accepted | Distributed Systems Engineer | ADR-Provisioning |
| ADR-Tracing | Cascade causal event-ID / correlation-ID architecture (Section 12) | Accepted | Production ML Infra Architect | — |
| ADR-GoldenTest | Golden-fixture / deterministic-replay testing architecture (Section 14) | Accepted | Testing Architect | ADR-AudioBuf (determinism constraint) |
| ADR-PowerCascade | Three-stage cascade for MCU deep-sleep targets (Section 7.7) | **Deferred** — explicitly conditional on a not-yet-made product decision (battery vs. mains-powered MCU deployment) | Embedded Systems Architect | ADR-PAL |
| ADR-Legal-DPDP | India DPDP Act / CCPA compliance architecture for telemetry and enrollment data | **Deferred** — pending formal legal review (not an engineering decision this SAS can close) | Security Architect (liaison to legal) | ADR-Tracing (telemetry schema) |
| ADR-Patent-FTO | Patent freedom-to-operate scope (cascade, personalization, enrollment) | **Deferred** — pending formal legal search, not performed by any prior document in this set | (Legal, not an engineering role) | ADR-005, ADR-Discovery |
| ADR-KWS-Placeholder | Placeholder Stage-1 KWS model + log-Mel front-end contract (v1 vertical slice) | **Accepted (v1)** — a Speech-Commands-trained placeholder recognizing "marvin", exported to ONNX against a frozen front-end contract; supersedes the v0 synthetic-model judgment call. NOT the AURA-trained model (research track produces that later). | ML/Runtime Engineer | ADR-003 (log-Mel front-end), Section 4 tensor contract |
| ADR-VAD-RTAlloc | Silero/ORT allocation on the real-time Audio thread | **Deferred** — pending on-device allocation measurement (v1 delivered a measurement harness + preliminary recommendation, not a fix). Candidates: (a) ORT custom allocator over the Section-5 arena, (b) IoBinding with pre-bound reused I/O `OrtValue`s, (c) hand-rolled Silero VAD off ORT. | Runtime/Audio Engineer | ADR-002 (ORT), Section 5/6 (arena, threading) |

**Superseded/Rejected:** none from Stage 2–6. v1 addendum: ADR-KWS-Placeholder graduates the v0 "placeholder model" judgment call to an accepted decision (routine model *selection* would not warrant an ADR per Stage 9's contribution guide, but this decision *defines the front-end input contract*, which does). ADR-Binding (codegen) remains **Accepted (approach)/Deferred (tool)**; the v1 JNI-drift check confirmed the hand-written `sdk/kotlin/aura-core-bindings` layer is still thin/mechanical and remains a realistic drop-in for future generated code.

---

## SECTION 19b — v1 Front-End Contract (frozen by ADR-KWS-Placeholder)

The Stage-1 model input contract, aligned by construction across training
(`tools/aura_frontend.py`), the on-device engine (`core/features` + `core/dsp`), and
verified numerically equal by `tools/verify_frontend_alignment.py` (max abs log-Mel
diff 0.010 over a full clip):

| Property | Value |
|---|---|
| Sample rate | 16 kHz mono |
| Pre-emphasis / DSP | AGC → AEC(no-op) → NS, block-streamed at 160 samples (Section 3.7 order) |
| Window / hop | 400 samples (25 ms) Hann (symmetric) / 160 samples (10 ms), center=False |
| FFT | 512-point, power spectrum |X|² |
| Mel | 40 HTK bins, [20, 8000] Hz, unnormalized triangular |
| Compression | natural log(mel + 1e-6) |
| Model input | `[1, 100, 40]` (100 frames = `DetectConfig.stage1WindowFrames`); per-mel normalization folded into the graph |
| Model output | `[1, 13]` logits, softmax; target class = "marvin" (`DetectConfig.stage1TargetClass` = 0). 13 classes = 11 words + `_unknown_` + `_silence_` |
| Decision | fire on **M consecutive** windows with softmax[marvin] ≥ `stage1Threshold` (`DetectConfig.stage1ConsecutiveWindows`, posterior smoothing), then `refractoryFrames` suppression |
| Training | augmented (noise/SNR-curriculum, reverb, speed, gain, SpecAugment); head-to-head arch selection (`tools/select_best_model.py`) |

---

*End of Software Architecture Specification, Version 1.0. This document, together with the six prior stages, constitutes the complete PROJECT AURA architecture record as of this review. Items marked Deferred above are the only remaining blockers between this specification and unblocked implementation start.*
