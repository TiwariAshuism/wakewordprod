# Speaker Verification Plan — Tier C (`core/speaker/`)

Plan for the optional speaker-verification (SV) module, per SAS §3.12 and ADR-005 (SAS §19,
"Speaker verification architecture + anti-spoofing gate"). Grounded in
`product/aura_sas.md`, `product/aura_investment_committee_report.md` (ADR-005, Risk Matrix,
Go/No-Go), and `product/aura_phase1_audit.md` §12 (Security Review).

**Governing constraint (ADR-005):** the *architecture* is **Accepted** (ECAPA-TDNN); the *ship
gate* is **Deferred** pending an ASVspoof-methodology anti-spoofing evaluation. Investment
Committee No-Go is explicit: *"Marketing speaker verification as a security feature — blocked on
ADR-005's anti-spoofing evaluation."* Everything below is scoped so engineering can build the
mechanism without tripping that gate.

---

## 1. Architecture

- **Embedding model:** ECAPA-TDNN-derived small embedding network (Desplanques et al.,
  Interspeech 2020 — Res2Net + SE blocks, channel/context attention pooling, multi-layer feature
  aggregation), trained with **AAM-softmax on VoxCeleb**. GE2E/d-vector LSTM is the documented
  fallback (ADR-005 option 2) if ECAPA-TDNN proves too heavy for a target device class.
- **Runtime:** loaded through `core/runtime/` on the **Speaker model slot** — an independent
  `ModelManager` slot with its own hot-swap/mmap lifecycle (SAS §3.13), parallel to Stage-1 and
  Stage-2. Reuses the ADR-002 backend (ONNX Runtime / TFLite Micro); no bespoke inference path.
- **Verify operation:** compute the utterance embedding, cosine-compare against the enrolled
  template(s), threshold → accept/reject. Emits a `SpeakerRejected` / verified outcome carrying
  the CorrelationId established at `VadTriggered` (SAS §12 tracing).
- **Type-safety:** telemetry/log record types have no field capable of holding a raw embedding
  vector (SAS §22 privacy rule) — embeddings never leave the module in a loggable form.

## 2. Placement in the cascade

SV runs **last**, only after Stage-2 confirms (SAS §7.3):

```
VAD gate → Stage-1 → Stage-2 → SpeakerVerifying (only if enabled + past ADR gate) → DetectionConfirmed
```

- Internal-only API, invoked by `core/detect/` **only after Stage-2 verification succeeds**
  (SAS §3.12). Never runs speculatively — it is the most expensive stage and gates the rarest event.
- **Thread ownership: Inference thread** (SAS §3.11 thread map — `runtime/`, `detect/`, `speaker/`
  are High-priority, soft-real-time; heap alloc and blocking I/O forbidden on the steady-state path).
- In multi-device arbitration, the losing device suppresses Stage-2/SV compute (SAS §7.9).

## 3. Enrollment / verify flow (on-device)

- Core engine exposes only the `enroll()` / `verify()` primitives; **enrollment UX lives at the
  SDK layer** (SAS §3.12). The `IWakeWordEngine` surface already reserves
  `enrollSpeaker(const SpeakerEnrollmentRequest&)` — today a stub returning `kUnimplemented`
  ("out of scope for v0", `core/engine/WakeWordEngine.cpp:103`). `ModelSlot::kSpeaker` and the
  `kSpeakerRejected` cascade outcome are likewise reserved but unreached in v0.
- **Enroll:** user-initiated, distinct lifecycle event. Capture N enrollment utterances → embed →
  aggregate to a template → persist. All on-device; no cloud enrollment path (external
  identity-provider integration is explicitly out of scope, SAS §3.20).
- **Verify:** single-shot embedding + threshold at cascade tail. No network I/O.

## 4. Template storage

- `core/speaker/` **owns** the enrolled-speaker embedding templates, persisted via `core/security/`
  **hardware-backed storage where available** (platform Keystore / Keychain / secure enclave;
  SAS §3.12, §3.19). Phase1-audit §12 flags on-device weights/templates as extractable unless
  deliberately protected — Keystore-backed encryption at rest is the mitigation.
- Enrollment data is **DPDP/CCPA-relevant personal data**: ADR-Legal-DPDP is **Deferred pending
  legal review**. Retention, deletion, and export of templates must be settled with legal before
  any enrollment ships to real users.

## 5. ⚠️ ADR-005 anti-spoofing go/no-go gate (CRITICAL)

**SV is a personalization convenience, NOT a security boundary, until this gate clears.**

- **Gate:** an explicit anti-spoofing evaluation against **ASVspoof** challenge methodology
  covering **replay, synthetic-speech / voice-cloning (XTTS, VoiceCraft), and voice-conversion**
  attacks (phase1-audit §12; ADR-005 rationale). ASVspoof and AAM-/one-class-softmax countermeasure
  losses are Verified as the standard literature here.
- **Highest security-risk item in the project:** shipping SV without this evaluation and calling
  it "security" is the #1 risk in the Investment Committee Risk Matrix (High severity). The
  Go/No-Go explicitly No-Go's marketing SV as security until the eval completes.
- **Related unmitigated attack classes** to document, not silently ignore (phase1-audit §12):
  ultrasonic/DolphinAttack, adversarial audio, model extraction.
- **Owner:** Security Architect + ML Architect (joint). Output is a binding go/no-go decision, not
  a recommendation (Investment Committee Priority Fix #2).

## 6. Compile-time gating

The whole module is gated behind **`AURA_ENABLE_SPEAKER_VERIFICATION`** (default **off**). When
off: no Speaker model slot allocation, `SpeakerVerifying` state unreachable, `enrollSpeaker()`
returns `kUnimplemented`, and no marketing/API surface implies verification. The flag stays off in
shipping builds until §5 clears — the gate is enforced at build time, not by policy alone.

## 7. Phasing — build vs. blocked-on-data/legal

| Phase | Engineering can build (no external dependency) | Blocked on data / legal |
|---|---|---|
| **P0 — scaffold** | `core/speaker/` module behind the compile flag; `IModelLoader` Speaker slot; `enroll()`/`verify()` primitives + cascade `SpeakerVerifying` state wired; Keystore-backed template store via `security/`; golden-fixture determinism harness. | — |
| **P1 — prototype** (SAS Phase 2a) | Integrate an off-the-shelf ECAPA-TDNN embedding (e.g. SpeechBrain) to exercise the pipeline end-to-end on device; measure latency/RAM on the Inference thread per tier. | Needs **VoxCeleb** license for any AURA-trained/fine-tuned model; needs licensing review (VoxCeleb terms — Priority Fix #4). |
| **P2 — security gate** (SAS Phase 2b named checkpoint) | Build the ASVspoof evaluation harness (replay/clone/voice-conversion test sets). | Needs **anti-spoofing eval data** + the **joint Security/ML go/no-go decision** (ADR-005). SV cannot proceed to Phase 2c until this clears. Also gates on DPDP/CCPA legal review of enrollment data. |
| **P3 — ship decision** | Flip `AURA_ENABLE_SPEAKER_VERIFICATION` only for build classes that passed P2; wire SDK enrollment UX. | Marketing framing (personalization vs. security) is a legal/product call, **not** engineering's — contingent on P2 outcome. |

**Recommendation of record (Investment Committee §14, Open Question):** default to shipping v1
**without** SV (ADR-005 option 3 / SAS Tier-C sequencing) unless the anti-spoofing evaluation can
realistically complete inside the Phase 2a/2b window. Build the mechanism; keep the flag off; do
not market it as security until the gate is green.
