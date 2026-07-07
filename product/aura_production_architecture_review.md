# PROJECT AURA — Production Architecture Blueprint Review
### FAANG-style Pre-Implementation Design Review

Filtered against all six prior documents. Only findings that would change implementation, latency, memory, power, reliability, scalability, maintainability, testing, deployment, developer experience, or production debugging are included. Everything else: **Coverage Complete.**

12 findings survive the filter — not padded to a round number.

---

### 1. No Platform Abstraction Layer (PAL) has been specified

**Why it matters:** the entire premise of "one C++ core across 11 platforms" (already assumed throughout the document set's runtime/ADR discussions) is unimplementable without a formal boundary between platform-independent logic (DSP, inference orchestration, cascade state machine) and platform-specific primitives (audio capture, filesystem, clock, timer, thread creation, power state queries). No prior document specifies this boundary as an actual interface.
**Architecture impact:** requires a defined `IPlatform` interface (audio I/O, clock/timer, filesystem, thread/task creation, power-state query) implemented once per OS (Android/iOS/Linux/Windows/macOS/ESP32/Cortex-M), with the core engine depending only on this interface — not on any OS header directly.
**Implementation impact:** every subsystem discussed so far (audio pipeline, OTA, model loading, telemetry) needs to be re-expressed in terms of this interface rather than assumed to "just work" per-platform.
**Performance impact:** a poorly designed PAL (e.g., virtual-call-heavy on the audio hot path) can itself become a latency source; the PAL boundary should be coarse-grained (buffers/callbacks), not fine-grained (per-sample virtual calls).
**Risk if ignored:** without this, each platform port becomes an ad hoc reimplementation rather than a binding against a stable core — directly undermining the "cross-platform" value proposition and multiplying the maintenance-burden risk already flagged as the top business risk in `aura_phase1_audit.md` §15.
**Production examples:** this is the same pattern used by cross-platform media engines (e.g., WebRTC's own platform-abstraction layer for audio/video capture across its supported OSes) and by cross-platform game engines' HAL layers.
**References:** General Knowledge — standard cross-platform C++ systems architecture pattern, not a single citable paper.
**Confidence:** General Knowledge.
**Priority:** **Critical** — this is a prerequisite for Phase 2a multi-platform prototyping, not a later refinement.
**ADR required:** Yes.
**Experiment required:** No — this is a design decision, not an empirical question.
**Estimated engineering effort:** High (foundational; affects every subsequent subsystem's implementation).

---

### 2. Audio pipeline has no specified buffer-ownership / zero-copy / backpressure model

**Why it matters:** the document set specifies DSP *stage order* (`aura_addendum_v4.md` §3) and the ISR-to-task ring-buffer handoff (`aura_final_gap_analysis.md` §17), but never specifies who **owns** a buffer as it moves through capture → AGC → AEC → NS → feature extraction → VAD → model, whether data is copied at each stage boundary, or what happens when the inference stage falls behind the capture rate.
**Architecture impact:** requires an explicit buffer-ownership model (e.g., a single-writer/single-reader ring buffer per stage boundary with move semantics, not copy, between stages) and an explicit backpressure policy (drop oldest frame vs. drop newest vs. block capture — each has different failure characteristics for a real-time audio system).
**Implementation impact:** every DSP/model stage's function signature and threading model depends on this decision; retrofitting it after stages are implemented independently is expensive.
**Performance impact:** unnecessary copies at each of 5+ pipeline stages directly add to both CPU cost (already power-constrained per the whole document set's recurring theme) and to the latency budget against the <100ms target stated in the original project brief.
**Risk if ignored:** silent frame drops or growing latency under any transient CPU contention (e.g., a concurrent OTA download or telemetry flush) — a production reliability failure mode, not merely a performance nit.
**Production examples:** WebRTC's audio processing module and most professional audio-graph engines (e.g., JUCE's audio graph) use exactly this zero-copy, explicit-backpressure-policy pattern for the same reasons.
**References:** General Knowledge — standard real-time audio systems engineering practice.
**Confidence:** General Knowledge.
**Priority:** **Critical.**
**ADR required:** Yes.
**Experiment required:** Yes — the specific backpressure policy's effect on FA/FR under transient CPU load is Needs Experimentation.
**Estimated engineering effort:** High.

---

### 3. No architecture for heterogeneous/hot-pluggable microphone input (USB, Bluetooth, multiple mics, sample-rate mismatch)

**Why it matters:** the document set assumes a single, fixed-sample-rate microphone throughout every DSP discussion. Real deployments (Linux/Windows/macOS/Raspberry Pi targets explicitly in scope) routinely involve USB mics, Bluetooth mics (which introduce variable/non-16kHz native rates and connection-drop/reconnect events), and multi-mic setups — none of which are addressed.
**Architecture impact:** requires (a) a sample-rate-conversion stage before feature extraction when the input device's native rate isn't the model's expected rate, (b) a device hot-plug/disconnect event model feeding into the PAL from Finding 1, and (c) explicit handling of the audio-interruption-and-recovery case (e.g., a phone call interrupting capture on mobile, or a Bluetooth mic dropping out).
**Implementation impact:** the audio-capture layer must expose device-change events up through the pipeline, and the pipeline must be able to reset/resync cleanly rather than assume a continuous, unchanging input stream for the device's lifetime.
**Performance impact:** naive sample-rate conversion (e.g., linear interpolation) can introduce aliasing that measurably degrades KWS accuracy; this needs a real resampler (e.g., a polyphase or windowed-sinc resampler), not an afterthought.
**Risk if ignored:** on desktop/Linux/Pi platforms specifically, this is not an edge case — USB/Bluetooth mics are a common real-world configuration, and silent failure (engine simply stops working after a mic hot-plug event) is a severe, visible product defect.
**Production examples:** every production voice-assistant desktop client (and WebRTC-based conferencing apps generally) handles device hot-plug and rate mismatch as first-class events, not exceptions.
**References:** General Knowledge.
**Confidence:** General Knowledge.
**Priority:** **High** for Linux/Windows/macOS/Pi tiers specifically; lower urgency for the ESP32/Cortex-M tier (fixed hardware mic, no hot-plug).
**ADR required:** Yes.
**Experiment required:** Yes — resampler quality's effect on FA/FR is Needs Experimentation.
**Estimated engineering effort:** Medium-High.

---

### 4. No model-lifecycle architecture (mmap loading, hot-swap, eviction, arena allocation for tensors)

**Why it matters:** the OTA design (`aura_addendum_v4.md` §6) specifies *how a new model version gets onto the device*, but not *how the running inference engine actually swaps to it* without dropping audio frames, without a duplicate-memory spike, and without a restart.
**Architecture impact:** requires (a) memory-mapping model weight files (via `mmap`, where the OS supports it) rather than heap-loading them, so the OS page cache — not application heap — bears the cost of having both old and new model versions briefly resident during a hot-swap, and (b) a double-buffered "active model handle" that the audio-processing thread atomically swaps, rather than mutating a shared model object in place while inference may be concurrently reading it.
**Implementation impact:** the inference-engine API needs an explicit `swapModel()` operation as a first-class concept, not just a `loadModel()` called once at startup — this is a materially different API shape than what any prior document implies.
**Performance impact:** directly determines whether an OTA model update causes a visible audio glitch/dropped-detection-window or not; also determines peak RAM usage during update, which matters against the stated <20MB mobile RAM target.
**Risk if ignored:** an OTA update could cause a missed wake-word trigger during the swap window, or a memory spike that fails on the most RAM-constrained target devices.
**Production examples:** this mirrors the general "double-buffered configuration swap" pattern used broadly in production systems for zero-downtime config/model updates (e.g., how most production feature-flag/config systems perform atomic swaps rather than in-place mutation).
**References:** General Knowledge.
**Confidence:** General Knowledge.
**Priority:** **High.**
**ADR required:** Yes.
**Experiment required:** Yes — actual swap-induced glitch/dropout measurement is Needs Experimentation.
**Estimated engineering effort:** Medium.

---

### 5. No cross-language binding architecture — SDK surface for Kotlin/Swift/Dart/etc. is unspecified

**Why it matters:** the project targets Flutter, React Native, Kotlin (Android), Swift (iOS), and a C++ core, per the original project brief — but no document specifies *how* the C++ core's API is exposed to each language, which is a first-order maintainability and correctness risk given the number of bindings.
**Architecture impact:** hand-writing and hand-maintaining N separate language bindings against an evolving C++ core is a well-known source of binding drift and subtle memory-ownership bugs (especially across the C++/Kotlin JNI and C++/Swift boundaries specifically). A **binding-generation tool** (e.g., Mozilla's UniFFI, or a custom cbindgen/JNI-codegen pipeline) that generates Kotlin/Swift/Dart bindings from a single interface definition should be an explicit architecture decision, not left to be discovered ad hoc during Android/iOS/Flutter implementation.
**Implementation impact:** determines the shape of the core C++ API itself (must be expressed in a binding-tool-compatible interface definition, which is more constrained than idiomatic C++) — this needs deciding before, not after, the core API is written.
**Performance impact:** poorly designed bindings (e.g., excessive JSON serialization across the FFI boundary for what should be a raw audio buffer handoff) can reintroduce exactly the copy/latency costs Finding 2 is trying to eliminate, at the language-binding boundary instead of the internal pipeline.
**Risk if ignored:** binding drift across 5+ language surfaces as the core evolves, and duplicated bugs that must be fixed N times instead of once.
**Production examples:** this is precisely the problem UniFFI (used in production by Mozilla for Firefox's Rust-core-plus-many-language-bindings architecture) was built to solve; the same pattern applies whether the core is Rust or C++.
**References:** General Knowledge (UniFFI's public design goals and usage are well documented; General Knowledge rather than a peer-reviewed citation).
**Confidence:** General Knowledge.
**Priority:** **High** — directly affects developer experience and the SDK's long-term maintainability, both explicit review criteria.
**ADR required:** Yes.
**Experiment required:** No — this is a tooling/architecture decision.
**Estimated engineering effort:** Medium (mostly upfront tooling investment, which pays down over every subsequent binding).

---

### 6. No build-system or monorepo/polyrepo decision has been made

**Why it matters:** an 11-platform, multi-language-binding, firmware-plus-mobile-plus-desktop-plus-cloud project has a first-order build-system decision (CMake vs. Bazel vs. a hybrid) that determines cross-compilation ergonomics, build reproducibility, and CI cost — never addressed in any prior document, which focused on runtime/inference tooling, not the build system that produces the artifacts in the first place.
**Architecture impact:** CMake has the broadest existing ecosystem overlap with the Android NDK, iOS toolchains, and embedded (ESP-IDF/Cortex-M) toolchains already assumed elsewhere in the document set, at the cost of weaker hermetic/reproducible-build guarantees than Bazel; Bazel gives stronger reproducibility and remote-caching at greater initial tooling investment and a steeper embedded-toolchain integration curve.
**Implementation impact:** determines how cross-compilation for 11 targets is actually invoked and cached in CI, and whether "hermetic build" (same input → bit-identical output, relevant to the model-signing/supply-chain-security work already scoped in `aura_final_gap_analysis.md` §5) is achievable without extra tooling layered on top.
**Performance impact:** N/A to runtime; materially affects CI turnaround time and therefore engineering velocity.
**Risk if ignored:** ad hoc per-platform build scripts that diverge over time — a direct multiplier on the maintenance-burden risk already identified as the project's top business risk.
**Production examples:** CMake is the dominant choice for cross-platform C++ projects spanning mobile+embedded+desktop (e.g., most cross-platform game/audio engines); Bazel is the dominant choice inside large monorepos prioritizing hermetic builds (Google-scale practice) but has real friction with embedded toolchains that don't natively fit its sandboxed build model.
**References:** General Knowledge.
**Confidence:** General Knowledge.
**Priority:** **High** — this blocks Phase 2a's parallel-prototyping-across-platforms plan (already recommended in `aura_investment_committee_report.md` ADR-006) if left undecided.
**ADR required:** Yes.
**Experiment required:** No.
**Estimated engineering effort:** Medium (decision + initial scaffolding), ongoing cost either way.

---

### 7. No lock hierarchy / deadlock-avoidance policy across the growing subsystem set

**Why it matters:** priority inversion (mutex-level) was already identified and fixed via priority-inheritance mutexes (`aura_expert_panel_review.md`), but a **separate** problem — deadlock from inconsistent lock-acquisition ordering — was not addressed. The system now has multiple independently-designed subsystems that may need to hold locks simultaneously: the model registry (Finding 4's hot-swap), the OTA download/install state machine, the telemetry buffer, and the multi-device-arbitration state (from the prior review's Finding 1) are all plausible candidates for a future deadlock if no global lock-ordering discipline is documented.
**Architecture impact:** requires a documented, enforced lock-acquisition order (e.g., "model registry lock is always acquired before OTA state lock, never the reverse") as an explicit engineering policy, ideally checked by a lock-order-verification tool in CI/debug builds, not just a comment convention.
**Implementation impact:** affects how each subsystem's internal locking is designed from the start, not just how they're documented after the fact.
**Performance impact:** N/A directly; a deadlock is a total-failure mode (device hangs), not a performance degradation, which is arguably worse for an always-on product.
**Risk if ignored:** an intermittent, hard-to-reproduce full-system hang under specific timing conditions involving two or more of these subsystems interacting — one of the worst classes of field bug to diagnose post-ship.
**Production examples:** large concurrent systems (database engines, OS kernels) universally document and enforce global lock-ordering disciplines for exactly this reason; tools like Clang's Thread Safety Analysis or runtime lock-order-verification (e.g., patterns similar to the Linux kernel's lockdep) are the standard mitigation.
**References:** General Knowledge.
**Confidence:** General Knowledge.
**Priority:** **Medium-High** — cheap to establish as policy now, expensive to retrofit once several subsystems exist independently.
**ADR required:** Yes — extends, but is distinct from, the priority-inversion/threading-model ADR already recommended.
**Experiment required:** Yes — stress-testing for deadlock under concurrent subsystem activity (e.g., OTA install during a multi-device arbitration event) is Needs Experimentation.
**Estimated engineering effort:** Low-Medium (policy + CI tooling, applied consistently).

---

### 8. No device provisioning / identity / attestation architecture

**Why it matters:** the security appendix (`aura_addendum_v4.md` §8) covers Secure Enclave/Keystore usage for *storing* keys and model-signing verification, but never addresses how a factory-fresh device **acquires** its initial trust anchor (the OTA update-verification public key, and any per-device identity used for the multi-device-arbitration protocol from the prior review) during manufacturing — directly relevant given CoBuild Labs' hardware manufacturing involvement.
**Architecture impact:** requires an explicit provisioning-time architecture: how is the trust anchor injected during manufacturing (e.g., flashed at the factory alongside firmware, vs. fetched on first boot from a provisioning service), and how does the device prove its own authenticity to other devices/services afterward (device attestation) — none of which currently exists as a design.
**Implementation impact:** affects the manufacturing/flashing process itself (a CoBuild Labs operational concern, not just a software one), and determines whether the OTA signing scheme (§6 of `aura_addendum_v4.md`) has a secure root of trust at all, or is only secure assuming the initial key injection was itself secure — an unstated assumption in the current OTA design.
**Performance impact:** N/A.
**Risk if ignored:** the entire OTA-signing security model (already treated as settled in `aura_addendum_v4.md`) has an unaddressed bootstrapping gap — a device with no secure way to receive its first trust anchor cannot actually verify anything, undermining the security work already done unless this is closed.
**Production examples:** standard IoT/embedded manufacturing practice injects per-device keys/certificates during a factory provisioning step (documented practice across ARM's PSA Certified program materials and similar embedded-security industry guidance).
**References:** General Knowledge.
**Confidence:** General Knowledge.
**Priority:** **High** — this is a prerequisite for the OTA security model already recommended elsewhere in the document set to actually hold.
**ADR required:** Yes.
**Experiment required:** No — primarily a process/architecture decision.
**Estimated engineering effort:** Medium (mostly manufacturing-process design, not runtime software).

---

### 9. No local-discovery protocol specified for multi-device arbitration

**Why it matters:** the prior review (`aura_expert_panel_review.md`) identified multi-device arbitration as a missing subsystem and recommended a local (non-cloud) coordination mechanism to preserve AURA's offline positioning — but did not specify the actual discovery/transport protocol, which is itself a distinct, non-trivial architecture decision.
**Architecture impact:** requires choosing among **mDNS/DNS-SD** (standard local-network service discovery, works over existing WiFi infrastructure, no pairing step needed but requires all devices on the same LAN/multicast domain), **BLE** (works without WiFi, lower power, but shorter range and requires an explicit pairing/bonding flow), or **WiFi Direct** (device-to-device without an access point, more complex stack). Each has different implications for the ESP32/Cortex-M tier's power budget (BLE is likely cheapest there) versus the mobile/desktop tier (mDNS is likely simplest there).
**Implementation impact:** this decision determines a real, separate networking-stack integration per platform, not a reuse of the OTA networking stack already scoped.
**Performance impact:** directly determines the achievable arbitration latency (how quickly devices can compare confidence scores before one commits to responding) — relevant against the same real-time expectations as the core detection latency budget.
**Risk if ignored:** without a concrete protocol choice, the multi-device-arbitration ADR recommended previously remains unimplementable.
**Production examples:** mDNS/DNS-SD is the standard choice for the Chromecast/AirPlay/general smart-home local-discovery pattern; BLE is the standard choice for battery-constrained IoT pairing flows (e.g., most BLE-based smart-home sensor onboarding).
**References:** General Knowledge.
**Confidence:** General Knowledge.
**Priority:** **Medium** — depends on the multi-device feature's priority, already flagged as High in the prior review but still contingent on a product decision.
**ADR required:** Yes.
**Experiment required:** Yes — actual arbitration latency achievable over mDNS vs. BLE on real target hardware is Needs Experimentation.
**Estimated engineering effort:** Medium.

---

### 10. No causal tracing/event-ID architecture across the detection cascade for production debugging

**Why it matters:** telemetry-with-privacy design and benchmark dashboards are already scoped (`aura_phase1_audit.md` §11, `aura_addendum_v4.md` §5/§7), but nothing in the document set specifies how a single wake-word event (or a specific false accept/false reject reported by a beta user) can be traced through the pipeline — VAD fired → stage-1 triggered → stage-2 verified/rejected → speaker-verification result — as one causally-linked record, versus disconnected per-stage logs.
**Architecture impact:** requires a lightweight, privacy-preserving **event/correlation ID** generated at VAD-trigger time and propagated through every subsequent pipeline stage's (already privacy-reviewed, aggregate-only) telemetry emission, so a specific detection event's full cascade path can be reconstructed for debugging without ever transmitting raw audio.
**Implementation impact:** every pipeline stage's telemetry-emission code needs to accept and forward this ID — a cross-cutting concern that's cheap to add now and expensive to retrofit once each stage's telemetry is independently implemented.
**Performance impact:** negligible if implemented as a simple integer/UUID tag; must be designed to add zero meaningful latency on the hot path.
**Risk if ignored:** production false-accept/false-reject investigations degrade to guessing which stage caused a given failure, directly undermining the "our own measured, debuggable benchmarks" discipline this entire document set has repeatedly insisted on.
**Production examples:** this is the same pattern as distributed tracing (e.g., OpenTelemetry-style trace/span IDs) applied to an on-device pipeline instead of a network of services — the pattern transfers even though the deployment context differs.
**References:** General Knowledge.
**Confidence:** General Knowledge.
**Priority:** **Medium-High** — directly serves the production-debugging criterion this review is scoped against.
**ADR required:** Yes.
**Experiment required:** No.
**Estimated engineering effort:** Low-Medium (cross-cutting but mechanically simple).

---

### 11. No golden-fixture / deterministic-replay testing architecture

**Why it matters:** the benchmark harness (`aura_addendum_v4.md` §7) specifies *aggregate* metrics (FA/hr, FRR) run continuously in CI, but there is no specified mechanism for **reproducing a single specific failure** deterministically — e.g., replaying the exact audio bytes and exact pipeline configuration that produced a specific missed detection during development, as a permanent regression-test fixture.
**Architecture impact:** requires (a) a "golden fixture" format (a recorded audio clip plus its expected pipeline output, checked into the versioned benchmark corpus already scoped in `aura_addendum_v4.md` §7) and (b) a deterministic-replay mode for the pipeline itself (fixed random seeds where applicable, no wall-clock-dependent behavior in the inference path) so that replaying the same fixture always produces the same result — not guaranteed by default if any part of the pipeline has non-deterministic behavior (e.g., a thread-scheduling-dependent race in the buffer-ownership model from Finding 2).
**Implementation impact:** determinism must be a design constraint on the audio pipeline and inference scheduling from the start, not something asserted after the fact — this connects directly to and constrains Finding 2's backpressure/threading design.
**Performance impact:** N/A to production; directly determines whether CI regressions can be root-caused efficiently or require manual re-investigation each time.
**Risk if ignored:** every specific bug found in the field or in ad hoc testing has to be manually reproduced from scratch instead of becoming a permanent, automatically-checked regression fixture — a direct tax on long-term engineering velocity.
**Production examples:** "golden test" / snapshot-testing patterns are standard practice in production ML systems generally (e.g., fixture-based regression testing is standard in speech/vision pipeline test suites across the industry) — General Knowledge, not a single citable source.
**References:** General Knowledge.
**Confidence:** General Knowledge.
**Priority:** **Medium.**
**ADR required:** Yes — should reference and constrain Finding 2's threading design.
**Experiment required:** No — this is a testing-infrastructure decision, though verifying actual determinism once built is itself a form of testing.
**Estimated engineering effort:** Medium.

---

### 12. No formal backend/runtime plugin interface — the ONNX Runtime/TFLite Micro choice is not abstracted behind a stable internal API

**Why it matters:** the document set recommends specific runtimes (ONNX Runtime + TFLite Micro, with ExecuTorch/NCNN/MNN as evaluation candidates) but never specifies the **internal software interface** the rest of the engine uses to talk to "whichever inference backend is active" — without this, swapping or adding a backend (e.g., adding ExecuTorch support after ONNX Runtime is already integrated) means changing call sites throughout the codebase rather than implementing one new backend module against a stable interface.
**Architecture impact:** requires an `IInferenceBackend` interface (load model, run inference, report memory/timing stats) that the cascade orchestration logic depends on, with ONNX Runtime/TFLite Micro/ExecuTorch each as interchangeable implementations behind it.
**Implementation impact:** this is the concrete mechanism that makes the "evaluate ExecuTorch in parallel" recommendation (already made in `aura_investment_committee_report.md` ADR-002) actually cheap to execute — without it, "evaluate in parallel" implicitly means a second, parallel, throwaway integration effort rather than a clean A/B swap.
**Performance impact:** a well-designed interface adds negligible overhead (one virtual-call boundary per inference invocation, not per-tensor); a poorly designed one (e.g., forcing data-format conversions at the boundary) could reintroduce the copy costs Finding 2 is trying to eliminate.
**Risk if ignored:** every future runtime evaluation or swap becomes a larger, riskier undertaking than necessary — directly undermining the document set's own repeated recommendation to keep runtime options open pending real benchmarking.
**Production examples:** this is the standard "backend abstraction" pattern used by any production ML-serving system that supports multiple inference backends (e.g., how most production inference servers abstract over multiple execution providers/backends behind one internal API rather than hardcoding call sites per backend).
**References:** General Knowledge.
**Confidence:** General Knowledge.
**Priority:** **Medium-High** — directly enables the ADR-002 experimentation plan already committed to elsewhere in the document set.
**ADR required:** Yes.
**Experiment required:** No — this is an interface-design decision, separate from the backend-selection experiments it enables.
**Estimated engineering effort:** Medium.

---

## Summary Table

| # | Finding | Priority | ADR | ADR Category |
|---|---|---|---|---|
| 1 | Platform Abstraction Layer | Critical | Yes | New — foundational |
| 2 | Audio buffer ownership / backpressure | Critical | Yes | New |
| 3 | Heterogeneous mic input (USB/BT/multi-mic/resampling) | High | Yes | New |
| 4 | Model lifecycle / hot-swap architecture | High | Yes | New |
| 5 | Cross-language binding/codegen architecture | High | Yes | New |
| 6 | Build system / monorepo decision | High | Yes | New |
| 7 | Lock hierarchy / deadlock avoidance | Medium-High | Yes | Extends existing threading ADR |
| 8 | Device provisioning / identity / attestation | High | Yes | New — closes OTA security gap |
| 9 | Local-discovery protocol (mDNS/BLE) | Medium | Yes | Implements prior multi-device ADR |
| 10 | Cascade causal tracing / event ID | Medium-High | Yes | New |
| 11 | Golden-fixture / deterministic replay testing | Medium | Yes | Constrains Finding 2 |
| 12 | Backend/runtime plugin interface | Medium-High | Yes | Enables existing ADR-002 |

**Note on completeness:** every layer in the review request not appearing above (inference-runtime tensor-reuse/pinned-memory specifics, NUMA awareness, work-stealing schedulers, connection pooling/retry-backoff for OTA networking, CLI/workspace tooling beyond the binding-generation question, static-analysis/security-scanning CI stages, folder-layout/naming-convention specifics, and multi-vendor hardware-abstraction beyond what Finding 1's PAL already covers) was evaluated and found to be either already addressed at the appropriate level of abstraction by a prior document, or to be an implementation detail *within* one of the twelve architectural decisions above rather than a missing decision in its own right — per this review's own filtering rule, those are not listed separately.
