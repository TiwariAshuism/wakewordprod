# "hey m" Wake Word — Results (Executive Summary)

**Date:** 2026-07-07 · **Winner:** `dscnn` (depthwise-separable CNN) · **Shipped as:** `heym.onnx` (float) + `heym_int8.onnx` (INT8)

This run trained a real "hey m" wake-word model head-to-head, selected a winner, quantized it, and measured it speaker-independently. Below is an honest accounting: what the requirements are, what was actually measured here, what is done, and what is still open.

---

## 1. Requirements — MEASURED vs. UNMEASURED-HERE

Hard targets are the ship gate; stretch targets (in parentheses) are the aspiration.

| Requirement | Hard target | Stretch | Measured this run | Status |
|---|---|---|---|---|
| False Accept / hr | ≤ 0.05 | (0.01) | **1192.561 /hr** | **NOT MET** (measured, fails hard) |
| False Reject (miss rate) | ≤ 5% | (2%) | **3.5%** | **MET** (measured) |
| Latency (device inference) | < 100 ms | (60 ms) | 0.107 ms *(host only)* | UNMEASURED-HERE (needs device) |
| Model size | < 500 KB | (200 KB) | **58.6 KB** float / **38.0 KB** INT8 | **MET** (measured) |
| RAM | < 20 MB | (10 MB) | — | UNMEASURED-HERE (needs device) |
| CPU | < 5% | (2%) | — | UNMEASURED-HERE (needs device) |
| Battery | < 10 mAh/hr | (5) | — | UNMEASURED-HERE (needs device) |
| Cold startup | < 1 s | (500 ms) | — | UNMEASURED-HERE (needs device) |
| Streaming frame period | 20–30 ms | (10–20) | — | UNMEASURED-HERE (needs device) |

The five device-bound rows (latency, RAM, CPU, battery, startup, streaming) **cannot be measured on this host** and are deferred to on-device profiling per `DEVICE_RUNBOOK.md`. The 0.107 ms figure is host wall-clock for a single forward pass and is **not** the device latency requirement.

**Bottom line on gates:** the model **passes False-Reject and size**, but **fails the hard False-Accept gate by ~24,000×**. A full M×threshold sweep found **no operating point** that satisfies FA/hr ≤ 0.05 and FRR ≤ 5% simultaneously (the most conservative point tested, M=3/thr=0.95, still gives 57.7 FA/hr while FRR jumps to 63.1%). Details: `benchmarks/dashboards/heym_report.md`.

---

## 2. What is DONE

- **Real "hey m" model trained**, not a stub. Head-to-head between two architectures, evaluated speaker-independent (369 held-out-speaker positive clips; 15.6-min negative corpus):

  | arch | params | speaker-indep F1 | recall | per-clip FAR | size |
  |---|---|---|---|---|---|
  | **dscnn (winner)** | 14,338 | **0.9401** | **0.9783** | 0.3333 | **58.6 KB** |
  | cnn | 31,778 | 0.9286 | 0.9512 | 0.3158 | 126 KB |

- **Winner selection = dscnn.** Both clear the size and recall hard gates. Selection rule is "smallest model that clears recall ≥ 0.95": dscnn is ~2.2× smaller (58.6 vs 126 KB; 14,338 vs 31,778 params) **and** clears recall with more margin (0.9783 vs a marginal 0.9512), and also wins the F1 tie-break it didn't need. cnn's only win (per-clip FAR 0.3158 vs 0.3333) is negligible and doesn't override size-first selection. For an always-on Android wake word, the smaller/faster depthwise-separable CNN is the clear pick.

- **INT8 quantization done and verified to run.** Static PTQ, per-channel QDQ, QInt8 weights+activations, input `input` shape `[1,100,40]`, calibrated on 300 windows from `.data/heym_feat.npz` (`Xtr`). Output shape `(1,2)` confirmed. Size 58.6 KB → **38.0 KB (~35% smaller)**.

- **Files shipped:**
  - Float: `apps/android/src/main/assets/models/heym.onnx`
  - INT8: `apps/android/src/main/assets/models/heym_int8.onnx`

- **Speaker-independent FA/hr + FR measured** on real held-out speakers (not train-on-test).

---

## 3. Honest gaps

1. **False-Accept requirement is not met — and no tested operating point meets it.** This is the headline gap. The FA/hr axis never comes close to 0.05 anywhere in the sweep. The model as-is is not shippable against the hard FA gate.

2. **Data is en-IN-dominant; the four V1 English accents are underrepresented.** Live dataset tags (from `tools/heym_data.py`): en-IN 1430/331, hi-IN 316/52, ta-IN 149/47, te-IN 182/32, kn-IN 129/21, ml-IN 36/0, plus 790 untagged-locale `prod`/`real` clips. **Absent: en-US, en-GB, en-AU** (and mr-IN, bn-IN). The report flags this as a V1 data gap. Mitigation plan: `MULTILINGUAL_PLAN.md`.

3. **All device-bound metrics are unmeasured here** (latency on device, RAM, CPU, battery, cold startup, streaming frame period). They require running on target Android hardware — see `DEVICE_RUNBOOK.md`.

4. **Speaker verification is spec'd but not shipped.** Architecture accepted (SAS §3.12, §7.3 cascade, ADR-005) but the ship gate is deferred. Plan: `SPEAKER_VERIFICATION_PLAN.md`.

---

## 4. Next steps

**To close the False-Accept gap (highest priority):**
- Expand and harden the negative corpus (more hours, more accents, hard negatives / confusable phrases) so the threshold sweep can actually reach FA/hr ≤ 0.05.
- Add a second-stage verifier / multi-frame confirmation and re-run the M×threshold sweep targeting the joint FA/FR constraint.
- Consider retraining with harder negative mining rather than only tuning the operating point (tuning alone did not find a feasible point).

**To close the accent/data gap:**
- Execute `MULTILINGUAL_PLAN.md`: source en-US/en-GB/en-AU (and mr-IN, bn-IN) positive + negative data; re-balance away from en-IN dominance.

**To close the device-metrics gap:**
- Run `DEVICE_RUNBOOK.md` on target hardware to measure latency, RAM, CPU, battery, startup, and streaming frame period against their hard/stretch targets.

**Speaker verification:**
- Follow `SPEAKER_VERIFICATION_PLAN.md` to move ADR-005 from accepted-architecture to a measured ship gate.

---

## 5. What is still needed from the user

1. **A target Android device (or device farm access)** — nothing on the latency/RAM/CPU/battery/startup/streaming row can be answered without it.
2. **A decision on the FA gate:** either (a) fund additional negative/hard-negative data collection so the model can plausibly hit FA/hr ≤ 0.05, or (b) explicitly relax/re-scope the FA target for V1. As measured, V1 does not pass this gate.
3. **English-accent data (en-US/en-GB/en-AU)** or approval to ship V1 as en-IN-first with those accents as a known limitation.
4. **Go/no-go on speaker verification for V1** vs. deferring to V2.

---

### References
- `benchmarks/dashboards/heym_report.md` — full requirements table + M×threshold sweep
- `MULTILINGUAL_PLAN.md` — accent/locale data coverage plan
- `SPEAKER_VERIFICATION_PLAN.md` — ADR-005 speaker-verification plan
- `DEVICE_RUNBOOK.md` — on-device measurement procedure (latency/RAM/CPU/battery/startup)
