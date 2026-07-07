# AURA — Implementation Backlog

What **remains** to implement against `product/`. Completed work is summarized (not tracked) at
the top; everything under "Remaining work" is open. Full analysis in `GAP_ANALYSIS.md`; Tier-D
detail in `TIER_D_COMPLETE.md` / `D2_STREAMING.md` / `HEYM_RESULTS.md` / `HEYM_FA_REDUCTION.md`.

**Status:** `[ ]` todo · `[~]` partial · `[!]` external gate (not code) · **Host?** = doable without the device.

---

## ✅ Completed — no longer tracked

- **Core platform** — M0 build (Gradle/CMake/dep-linter), M1 PAL (Android), M2 audio pipeline
  (ring buffer, DSP, log-Mel, Silero/Energy VAD), M3 `IInferenceBackend`+ORT, common/config/
  scheduler/statemachine/model/engine, SDK JNI + Kotlin `Flow`.
- **Tier A** (Android engine) — Stage-2 cascade, model hot-swap, resampler, ORT EP config,
  lock-order tool, runtime config.
- **Tier B** (prod infra) — benchmark harness, soak/leak, fuzz, integration tests, CI + SBOM +
  model/dataset cards.
- **Tier D host engineering** — D1 INT8 + QAT-vs-PTQ ablation (PTQ retained on merit); D2 causal
  streaming model + C++ `StreamingDetector` (**21.9× always-on compute cut**, host-verified); D5
  TFLite + ExecuTorch artifacts produced; D3 real **"hey m"** model (DS-CNN + Stage-2 cascade;
  FA-reduction **~1193 → 0/hr** in the measurable corpus); D4 Sarvam-TTS multilingual bootstrap.
- **Android APK builds + deploys to a real device** — `:apps:android:assembleDebug` green (JDK 21
  JBR + local SDK/NDK). Fixed 4 device-build bugs: arm64-only `abiFilter`, `ANDROID_STL=c++_shared`
  (Oboe), ORT imported-target wiring (ORT AAR has no Prefab), `posix_memalign` (Android < API 28).
- **56/56 host tests green, lint OK.**

---

## Remaining work

### On-device validation (Realme 8) — the immediate frontier
- `[~]` **APK builds ✅ — install + on-device measurement pending.** The Realme 8 (RMX3085, arm64,
  Android 13) disconnected mid-install; reconnect (data cable + unlock + Allow USB debugging), then:
  - `[ ]` **On-device measurement kit** — `adb`-driven: install → feed test audio → log **latency /
    CPU / RAM / startup / real FRR (Silero VAD)** vs the hard-metrics table (`DEVICE_RUNBOOK.md`).
    **Host-doable now** (device + this build machine present).
  - `[!]` **Battery mAh/hr** — needs a **power rig** (e.g. Monsoon); phone stats are only directional.
  - `[ ]` **APK slimming** — ~76 MB (ORT `.so` for all 4 ABIs); app-level arm64-only `abiFilters` → ~20 MB.

### Tier C — `core/` modules (none started, SAS M5–M6/M8)
- `[ ]` **C1. Telemetry** (`core/telemetry`) — metrics + privacy-preserving upload + full `ILogger`.
  SAS §3.14/§12/§13. **Host? yes.** M.
- `[!]` **C2. Security** (`core/security`) — model/OTA signature verify, Keystore/Enclave keys,
  provisioning + attestation. SAS §3.5/§7.6. Manufacturing dep. H.
- `[ ]` **C3. OTA** (`core/ota`) — model registry, compat checks, staged/canary + rollback, offline
  fallback, flash-wear-aware. SAS §3.15/§7.4. H.
- `[ ]` **C4. Power** (`core/power`) — power state machine; MCU 3-stage analog-gate cascade.
  SAS §3.16/§7.7. Product-decision-gated (battery vs mains). M–H.
- `[ ]` **C5. Discovery** (`core/discovery`) — mDNS/BLE local multi-device arbitration. SAS §3.17/§8.9.
  **Host? yes.** M–H.
- `[!]` **C6. Speaker verification** (`core/speaker`) — ECAPA-TDNN embeddings + enrollment + **ASVspoof
  anti-spoofing gate** (ADR-005). SAS §3.12. Blocked by anti-spoofing eval + VoxCeleb data. H.

### Tier D — remaining (data / device gated)
- `[!]` **D3. Verify the FA/hr gate** — ≤0.05 FA/hr needs a **20+ hr licensed negative corpus**
  (the 16-min corpus only resolves ~4/hr). Then pick the cascade operating point on real data.
- `[ ]` **D3/D4. Accent + language data** — **en-US/GB/AU** positives (Sarvam is India-only) + real
  per-language **test** splits (mr/bn/…) so multilingual gains are measurable; real robustness needs
  real data at volume (MSWC/Common Voice/FLEURS or collection).
- `[~]` **D2. On-device streaming** — wire a **stateful streaming ONNX** into the ORT backend + validate
  on-device latency/power (host side done; see `D2_STREAMING.md`).
- `[~]` **D5. On-MCU** — run the `.tflite` through `TfliteMicroBackend` on an ESP32-S3 / Cortex-M (no MCU here).

### Tier E — external gates & other platforms
- `[!]` **E1. Legal/compliance** — DPDP Act 2023 + Rules 2025, CCPA, dataset-licensing (ESC-50/AudioSet/
  VoxCeleb), patent FTO. **Hard §18 gates.** Not code.
- `[ ]` **E2. Other platforms** — iOS (AVAudioEngine), Linux (ALSA/PipeWire), Windows, macOS, ESP32,
  Cortex-M. ADR-006 tiering. XL.
- `[ ]` **E3. SDK breadth** — `sdk/idl` codegen (replace hand-written JNI) + swift/dart/python bindings. H.

---

## Recommended order

1. **Reconnect the Realme 8 → install the APK → run the on-device measurement kit** (latency / CPU /
   RAM / startup / real FRR). Now unblocked — the build machine + device are both here.
2. **C5 (discovery) + C1 (telemetry)** — host-doable `core/` modules if breadth is wanted.
3. **Your external gates:** 20+ hr corpus (verify FA/hr) · power rig (battery mAh/hr) · en-US/GB/AU +
   real per-language data · legal (E1).
4. **Decision/data-gated:** C2/C4/C6 (security/power/speaker), D5 on-MCU, E2/E3.

Legend of effort: S ≈ <1 day · M ≈ days · H ≈ 1–2 weeks · XL ≈ multi-week/ongoing (rough).
