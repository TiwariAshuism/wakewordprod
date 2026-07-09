# AURA as a Wake-Word-Training SaaS

Turn a customer's labelled audio into a **versioned, signed, drop-in wake-word bundle** with one
command. Everything below maps to code that already exists in this repo — no hand-waving.

| Claim | Backed by |
|---|---|
| One-command onboarding | `serve_train.py` |
| Train + calibrate | `train.py` (+ `tools/aura_train.py`, `tools/calibrate.py`) |
| Quality gate (FA/hr, FRR, ECE) | `evaluate.py` |
| Signed, hashed, watermarked deliverable | `tools/bundle.py` -> `dist/<wake>_v<ver>/manifest.json` + `.zip` |
| Drop-in / OTA hot-swap on device | `AuraEngine.initialize()` (SDK), `MainActivity.copyModels()`, `docs/design/aura_stage8_ops.md` (OTA) |

---

## 1. Per-customer flow

```
customer labelled dataset  ─►  serve_train.py  ─►  signed versioned bundle (.zip)  ─►  device
   positive/*.wav                (train+calib+eval+bundle)     dist/<wake>_v<ver>.zip     drop-in OR OTA
   negative/*.wav
```

The whole onboarding is a single command:

```bash
python serve_train.py \
  --wake-word "hey nova" \
  --data /data/acme_dataset \
  --customer acme \
  --license-id ACME-2026-001 \
  --sign-key keys/acme.key         # optional; omit --no-stage2 to keep the verifier cascade
```

`serve_train.py` orchestrates the existing scripts by subprocess (it never edits them):

1. **Synthesize** a temp `config.yaml` from repo defaults, overriding
   `wake_word / dataset_dir / customer / license_id / version / sign_key` (and `stage2.enabled`).
2. **`python train.py`** — trains Stage-1 (always-on detector) and, unless `--no-stage2`, a Stage-2
   verifier cascade; fits confidence calibration; then **bundles** via `tools/bundle.py`.
3. **`python evaluate.py`** — streaming-detector mirror scores held-out, speaker-independent data:
   FA/hr, FRR, ECE/AUROC, operating point.
4. **Report card** — prints wake word, version, recall, FA/hr, FRR, ECE, model sizes, licensing
   status, and the final **deliverable zip path**.

Example report card (from a real run):

```
  Wake word     : hey nova  (slug: hey_nova)
  Version       : 20260709
  Customer      : acme          License id : ACME-2026-001
  Model tag     : hey_nova-20260709-acme
  Recall (stage1): 1.000        FA/hr: 0.000   FRR: 0.0%   ECE: 0.0000
  Model size    : S1 58.6 KB  S2 126.0 KB  Total 184.6 KB
  Signed manifest: yes          Files hashed: 5 (sha256 each)
  DELIVERABLE   : dist/hey_nova_v20260709.zip
```

**Dataset contract** (validated up front with a clear error): `<data>/positive/*.wav` +
`<data>/negative/*.wav`, 16 kHz mono. The split is **speaker-independent** (`tools/aura_data.py`),
so reported recall/FA reflect unseen voices — the numbers you can put in a customer SLA.

**Frontend contract is fixed** (`16kHz/40mel/win400/hop160/100frame`, recorded in the manifest).
Every bundle is interchangeable with any other for the same engine — the customer app never changes
code to accept a new wake word, only the model files.

---

## 2. The deliverable bundle

`tools/bundle.py::build_bundle()` produces, per wake word + version:

```
dist/<wake_word>_v<version>/
  aura.onnx            # Stage-1 (required)
  aura_stage2.onnx     # Stage-2 (only if stage2.enabled)
  silero_vad.onnx      # fixed engine VAD, same for every wake word
  labels.json          # trained labels + calibration block + "model_tag" watermark
  manifest.json        # integrity + provenance + licensing (schema below)
  INTEGRATION.md       # exactly how the customer drops this in
dist/<wake_word>_v<version>.zip   # for delivery / OTA
```

`manifest.json` carries provenance and integrity:

```json
{ "name": "hey_nova", "version": "20260709", "created_utc": "...Z",
  "engine": "AURA", "frontend_contract": "16kHz/40mel/win400/hop160/100frame",
  "target": {"os": "android", "abi": "arm64-v8a"},
  "customer": "acme", "license_id": "ACME-2026-001",
  "files": { "aura.onnx": {"sha256": "...", "bytes": 60012}, ... },
  "metrics": { "recall": 1.0, "calibration_method": "platt", ... },
  "signature": "<hex HMAC-SHA256 over the canonical manifest, or null>" }
```

- **`sha256_file()`** — a per-file hash is **always** written (tamper/corruption detection).
- **`sign_manifest()` / `verify_bundle()`** — HMAC-SHA256 over the canonical manifest (all keys
  except `signature`, sorted, `json.dumps`) using `cfg.sign_key`. `verify_bundle()` re-hashes every
  file and re-checks the signature; ship it in your delivery-acceptance test.
- Python **stdlib only** (`hashlib`, `hmac`, `json`, `zipfile`, `shutil`, `datetime`) — no new deps
  in the training image.

---

## 3. Versioning + OTA hot-swap

**Versioning.** `version = cfg.version` or UTC `YYYYMMDD`. The version is baked into the folder name,
the zip name, the manifest, and the `model_tag` watermark, so a bundle is self-identifying end to end.
Re-onboard the same customer with a new dataset -> new version, same file names inside -> a clean
in-place upgrade.

**Drop-in.** The engine loads a *fixed set of file names* — `AuraEngine.initialize(modelDir)` reads
exactly `MODEL_ASSETS = [aura.onnx, aura_stage2.onnx, silero_vad.onnx, labels.json]`
(`MainActivity.copyModels()`). Because every bundle uses those same names, "installing a new wake
word" = replace four files. Nothing in the app or SDK changes.

**OTA hot-swap.** The bundle *is* the OTA payload. Per `docs/design/aura_stage8_ops.md` (§3, §1) the
platform already supports:
- push a signed model image (full or binary-delta against the installed version),
- **staged / canary rollout** with version pinning per device or fleet segment,
- **hot-swap** the running model — the engine tolerates a transient double-residency during swap
  (Stage 7 §5), so detection stays live across the update; roll back to the previous signed bundle
  if a canary regresses.

The manifest's `version` + `signature` are exactly the fields the OTA channel needs to decide
eligibility and to verify the payload before it touches the device.

---

## 4. Per-bundle licensing

Every bundle is individually attributable and verifiable:

- **`license_id`** — the customer's entitlement id, embedded in the signed manifest.
- **`signature`** — HMAC over the manifest; a bundle that isn't signed by *your* key won't verify.
  Rotate keys per the additive rotation policy in `aura_stage8_ops.md` §7.
- **`model_tag` watermark** — `<wake_word>-<version>[-<customer>]` written into `labels.json`, so a
  leaked model file is traceable to the customer and build even outside the manifest.

Acceptance / anti-piracy check (one call):

```python
import sys; sys.path.insert(0, "tools"); import bundle
assert bundle.verify_bundle("dist/hey_nova_v20260709")   # re-hashes files + checks signature
```

Gate delivery, OTA admission, and (optionally) on-device load on this passing.

---

## 5. REST API sketch (managed offering)

Wrap `serve_train.py` behind a job queue; the CLI already returns everything the API needs.

```
POST /v1/train
  headers: Authorization: Bearer <customer-key>
  body (multipart): wake_word="hey nova", dataset=<zip of positive/ + negative/>,
                    license_id?, no_stage2?
  -> 202 { "job_id": "job_abc123", "status": "queued" }

GET /v1/jobs/{job_id}
  -> 200 { "status": "running|succeeded|failed",
           "report_card": { "recall":..., "fa_per_hr":..., "frr":..., "ece":..., "size_kb":... } }
        # report_card is the same block serve_train.py prints, parsed from evaluate.py

GET /v1/bundle/{job_id}
  -> 200 application/zip  (the signed dist/<wake>_v<ver>.zip; 402 if license/quota unmet)

GET /v1/bundle/{job_id}/manifest   -> the manifest.json (integrity + provenance, no model bytes)
```

Worker per job: unzip dataset -> run `serve_train.py --wake-word ... --data ... --sign-key <server key>`
-> on exit 0, publish `dist/<wake>_v<ver>.zip` to object storage keyed by `job_id`, index the
manifest. The signing key lives **server-side only** (HSM-backed per §7 of the ops doc); customers
never see it, they only receive verifiable signed bundles.

---

## 6. Security + privacy (customer audio)

- **Ephemeral training data.** Customer WAVs are inputs only; delete the dataset and the temp
  config after a successful job (`serve_train.py` already removes its temp config; the worker should
  purge the unzipped dataset on completion). Retain only the *derived* bundle, never raw audio,
  unless the contract says otherwise.
- **Tenant isolation.** One job = one temp config + one `dist/_work/<slug>` output dir; nothing is
  shared across customers. Run workers in per-job sandboxes.
- **No audio leaves the loop.** Training + calibration + evaluation are fully offline/local (ONNX +
  numpy); there is no third-party inference call in the path.
- **Integrity + provenance by construction.** sha256 per file + signed manifest + `model_tag`
  watermark make every delivered artifact tamper-evident and traceable.
- **On-device privacy** is inherited from the engine: detection is on-device, and telemetry is
  opt-in/offline-tolerant (`aura_stage8_ops.md` §Telemetry) — a device that never phones home still
  works.

---

## 7. Build-vs-managed + pricing

**Two ways to consume the exact same bundle format:**

| | Build (self-host) | Managed (hosted) |
|---|---|---|
| Who runs training | Customer runs `serve_train.py` in their CI | We run it behind the REST API (§5) |
| Signing key | Their key | Our HSM-backed key; they get verifiable bundles |
| Delivery | They keep the `.zip` | Pull from `GET /v1/bundle/{id}` / we push OTA |
| Updates | They re-run + redeploy | We OTA hot-swap (§3) |
| Best for | Data-residency / air-gapped | Fastest time-to-wake-word |

**Packaging (illustrative):**

- **Starter** — 1 wake word, self-host (`serve_train.py`), community support. Per-wake-word one-time.
- **Pro** — managed API, N wake words, versioned bundles + signed manifests, email support. Monthly
  per wake word + per re-train.
- **Enterprise** — OTA hot-swap + staged rollout + version pinning, per-customer signing keys +
  watermarking, custom FA/FRR SLA (backed by `evaluate.py` numbers), on-prem worker option.
  Platform fee + per-device OTA + per-retrain.

Natural metering hooks, all already emitted: **per training job** (an API call / `serve_train.py`
run), **per wake word** (a bundle), **per re-train** (a new `version`), **per device** (OTA
installs, keyed by manifest `version` + `license_id`).

---

### TL;DR
A customer sends labelled audio; `serve_train.py` runs `train.py` + `evaluate.py`, and
`tools/bundle.py` emits a signed, hashed, watermarked, versioned bundle. They drop four files into
`assets/models/` (or we OTA hot-swap them). Licensing, integrity, and traceability are all carried in
`manifest.json` + the `model_tag` watermark — every claim here is one `verify_bundle()` or one
report card away from being checked.
