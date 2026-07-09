#!/usr/bin/env python3
"""Deployable model bundle + integrity for the AURA wake-word engine.

Packages the trained artifacts (Stage-1 ONNX, optional Stage-2 ONNX, the fixed Silero
VAD engine, and the calibrated labels.json) into a single, delivery-ready folder + zip
with a signed manifest and per-file SHA-256 integrity.

Public API (single source of truth — see the SHARED BUNDLE SPEC):
    build_bundle(output_dir, wake_word, cfg, metrics=None, dist_root="dist")
                                                    -> (bundle_dir, zip_path)
    sha256_file(path)                    -> hex digest of a file
    sign_manifest(manifest_dict, key_bytes) -> hex HMAC-SHA256 of the canonical manifest
    verify_bundle(bundle_dir)            -> bool (per-file sha256 + optional signature)

Stdlib only (hashlib, hmac, json, zipfile, shutil, datetime, os) — no new deps.
"""
import datetime
import hashlib
import hmac
import json
import os
import shutil
import zipfile

# --------------------------------------------------------------------------- constants
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
# Where the fixed VAD engine ships from (same file for every wake word).
SILERO_SRC = os.path.join(
    REPO, "apps", "android", "src", "main", "assets", "models", "silero_vad.onnx")
FRONTEND_CONTRACT = "16kHz/40mel/win400/hop160/100frame"


# --------------------------------------------------------------------------- integrity
def sha256_file(path):
    """Return the hex SHA-256 digest of a file, read in chunks."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _canonical_manifest_bytes(manifest_dict):
    """Deterministic bytes for signing/verifying: every key EXCEPT "signature",
    sorted keys, compact separators."""
    payload = {k: v for k, v in manifest_dict.items() if k != "signature"}
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sign_manifest(manifest_dict, key_bytes):
    """Hex HMAC-SHA256 of the canonical manifest (all keys except "signature")."""
    return hmac.new(key_bytes, _canonical_manifest_bytes(manifest_dict),
                    hashlib.sha256).hexdigest()


def verify_bundle(bundle_dir):
    """Recompute every file's SHA-256 against manifest.json and (if a signature and a
    co-located key are available) verify the HMAC signature. Returns True iff everything
    matches. Never raises for an ordinary bad bundle — returns False instead."""
    manifest_path = os.path.join(bundle_dir, "manifest.json")
    if not os.path.isfile(manifest_path):
        return False
    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
    except (OSError, ValueError):
        return False

    files = manifest.get("files") or {}
    if not files:
        return False
    for fname, meta in files.items():
        fpath = os.path.join(bundle_dir, fname)
        if not os.path.isfile(fpath):
            return False
        if sha256_file(fpath) != meta.get("sha256"):
            return False
        if os.path.getsize(fpath) != meta.get("bytes"):
            return False

    # Signature is optional. If present, verify it against a key file next to the
    # bundle (sign_key.bin) when one was captured; otherwise treat presence of a valid
    # self-consistent signature field as unverifiable-but-not-failing is NOT safe, so we
    # only pass signature verification when we can recompute it.
    sig = manifest.get("signature")
    if sig:
        key = _load_verify_key(bundle_dir)
        if key is not None:
            expected = sign_manifest(manifest, key)
            if not hmac.compare_digest(expected, sig):
                return False
    return True


def _load_verify_key(bundle_dir):
    """Best-effort: a bundle may ship a copy of the signing key for local verification
    at <bundle_dir>/.sign_key. Absent by default (keys are secret); returns None then."""
    kp = os.path.join(bundle_dir, ".sign_key")
    if os.path.isfile(kp):
        with open(kp, "rb") as f:
            return f.read()
    return None


# --------------------------------------------------------------------------- build
def _version(cfg):
    v = cfg.get("version")
    if v not in (None, ""):
        return str(v)
    return datetime.datetime.utcnow().strftime("%Y%m%d")


def _read_key_bytes(sign_key_path):
    """Load the signing key file (relative paths resolve against repo root). Returns
    bytes, or None if not configured / missing (WARN, don't crash)."""
    if not sign_key_path:
        return None
    p = sign_key_path
    if not os.path.isabs(p):
        p = os.path.join(REPO, p)
    if not os.path.isfile(p):
        print(f"  ! bundle: sign_key not found at {p}; shipping UNSIGNED bundle")
        return None
    with open(p, "rb") as f:
        key = f.read()
    if not key:
        print(f"  ! bundle: sign_key at {p} is empty; shipping UNSIGNED bundle")
        return None
    return key


def _integration_md(wake_word, version, files, engine_version, customer, license_id,
                    signed, silero_present):
    """Customer-facing drop-in note, generated per bundle."""
    lines = []
    lines.append(f"# AURA integration — {wake_word} (v{version})")
    lines.append("")
    lines.append("This bundle contains a complete, ready-to-ship AURA wake-word model set.")
    lines.append("")
    lines.append("## Drop-in")
    lines.append("")
    lines.append("Copy every file in this folder (except `manifest.json` and this note)")
    lines.append("into your app's model assets directory:")
    lines.append("")
    lines.append("```")
    lines.append("apps/android/src/main/assets/models/")
    lines.append("```")
    lines.append("")
    lines.append("These filenames already match the app's `MODEL_ASSETS` list, so the AURA")
    lines.append("SDK's `copyModels()` picks them up automatically — rebuild the app and you")
    lines.append("are done. Nothing else to change.")
    lines.append("")
    lines.append("Files to copy:")
    lines.append("")
    for fname in sorted(files):
        if fname in ("manifest.json", "INTEGRATION.md"):
            continue
        lines.append(f"- `{fname}`")
    if not silero_present:
        lines.append("")
        lines.append("> WARNING: `silero_vad.onnx` was not found at build time and is NOT")
        lines.append("> included. Add the fixed Silero VAD engine to this folder before")
        lines.append("> shipping — it is the same file for every wake word.")
    lines.append("")
    lines.append("## Engine / SDK target")
    lines.append("")
    lines.append(f"- Engine: **AURA** ({engine_version})")
    lines.append(f"- Front-end contract: `{FRONTEND_CONTRACT}`")
    lines.append("- Target: android / arm64-v8a")
    if customer:
        lines.append(f"- Licensed to: **{customer}**"
                     + (f" (license `{license_id}`)" if license_id else ""))
    lines.append("")
    lines.append("## Integrity (SHA-256)")
    lines.append("")
    lines.append("Verify each delivered file against these digests (also in `manifest.json`):")
    lines.append("")
    for fname in sorted(files):
        lines.append(f"- `{fname}`  \n  `{files[fname]['sha256']}`")
    lines.append("")
    if signed:
        lines.append("The `manifest.json` is signed (HMAC-SHA256); verify with the AURA")
        lines.append("tooling before deployment.")
    else:
        lines.append("This bundle is unsigned (no signing key was configured at build time).")
    lines.append("")
    return "\n".join(lines)


def build_bundle(output_dir, wake_word, cfg, metrics=None, dist_root="dist"):
    """Assemble the deployable bundle folder + zip. Returns (bundle_dir, zip_path).

    output_dir : where train.py wrote aura.onnx / aura_stage2.onnx / labels.json
    wake_word  : e.g. "hey_aura"
    cfg        : loaded config dict (optional version/customer/license_id/sign_key)
    metrics    : optional best-effort metrics dict (ece_stage1/recall/fa_per_hr/...)
    dist_root  : delivery root (created if missing)
    """
    cfg = cfg or {}
    version = _version(cfg)
    customer = cfg.get("customer") or None
    license_id = cfg.get("license_id") or None
    key_bytes = _read_key_bytes(cfg.get("sign_key"))
    engine_version = str(cfg.get("engine_version") or "engine v1")

    # Resolve dist root (relative -> repo root) and create it.
    if not os.path.isabs(dist_root):
        dist_root = os.path.join(REPO, dist_root)
    os.makedirs(dist_root, exist_ok=True)

    bundle_name = f"{wake_word}_v{version}"
    bundle_dir = os.path.join(dist_root, bundle_name)
    if os.path.exists(bundle_dir):
        shutil.rmtree(bundle_dir)
    os.makedirs(bundle_dir)

    # ---- collect files ----
    # Stage-1 ONNX (required). train.py writes it as <wake_word>.onnx; ship as aura.onnx.
    s1_src = os.path.join(output_dir, f"{wake_word}.onnx")
    if not os.path.isfile(s1_src):
        alt = os.path.join(output_dir, "aura.onnx")
        if os.path.isfile(alt):
            s1_src = alt
        else:
            raise FileNotFoundError(
                f"bundle: Stage-1 ONNX not found (looked for {s1_src} and {alt})")
    shutil.copy2(s1_src, os.path.join(bundle_dir, "aura.onnx"))

    notes = []

    # Stage-2 ONNX (only if enabled AND present).
    stage2_cfg = cfg.get("stage2") or {}
    stage2_on = bool(stage2_cfg.get("enabled", False))
    if stage2_on:
        s2_src = os.path.join(output_dir, f"{wake_word}_stage2.onnx")
        if not os.path.isfile(s2_src):
            s2_src = os.path.join(output_dir, "aura_stage2.onnx")
        if os.path.isfile(s2_src):
            shutil.copy2(s2_src, os.path.join(bundle_dir, "aura_stage2.onnx"))
        else:
            print("  ! bundle: stage2 enabled but no *_stage2.onnx found; skipping")
            notes.append("stage2 enabled in config but Stage-2 ONNX was missing at build")

    # Fixed Silero VAD engine (same file for every wake word).
    silero_present = os.path.isfile(SILERO_SRC)
    if silero_present:
        shutil.copy2(SILERO_SRC, os.path.join(bundle_dir, "silero_vad.onnx"))
    else:
        print(f"  ! bundle: silero_vad.onnx not found at {SILERO_SRC}; "
              f"customer must add it before shipping")
        notes.append("silero_vad.onnx missing at build — add the fixed VAD engine "
                     "(same file for all wake words) before shipping")

    # labels.json with calibration block + watermark model_tag.
    labels_src = os.path.join(output_dir, "labels.json")
    if not os.path.isfile(labels_src):
        raise FileNotFoundError(f"bundle: labels.json not found at {labels_src}")
    with open(labels_src, "r", encoding="utf-8") as f:
        labels = json.load(f)
    model_tag = f"{wake_word}-{version}" + (f"-{customer}" if customer else "")
    labels["model_tag"] = model_tag
    with open(os.path.join(bundle_dir, "labels.json"), "w", encoding="utf-8") as f:
        json.dump(labels, f, indent=2, sort_keys=False)
        f.write("\n")

    # ---- manifest (files hashed AFTER all payload files are in place) ----
    payload_files = [n for n in sorted(os.listdir(bundle_dir))
                     if n not in ("manifest.json", "INTEGRATION.md")]
    files_block = {}
    for n in payload_files:
        p = os.path.join(bundle_dir, n)
        files_block[n] = {"sha256": sha256_file(p), "bytes": os.path.getsize(p)}

    manifest = {
        "name": wake_word,
        "wake_word": cfg.get("wake_word_display") or wake_word,
        "version": version,
        "created_utc": datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
        "engine": "AURA",
        "frontend_contract": FRONTEND_CONTRACT,
        "target": {"os": "android", "abi": "arm64-v8a"},
        "customer": customer,
        "license_id": license_id,
        "model_tag": model_tag,
        "files": files_block,
        "metrics": dict(metrics) if metrics else {},
    }
    if notes:
        manifest["notes"] = notes

    # Signature over the canonical manifest (excludes "signature").
    manifest["signature"] = sign_manifest(manifest, key_bytes) if key_bytes else None

    # ---- INTEGRATION.md (references the just-computed hashes) ----
    integ = _integration_md(wake_word, version, files_block, engine_version,
                            customer, license_id, signed=bool(key_bytes),
                            silero_present=silero_present)
    with open(os.path.join(bundle_dir, "INTEGRATION.md"), "w", encoding="utf-8",
              newline="\n") as f:
        f.write(integ)

    # INTEGRATION.md is documentation about the payload; include its hash too so the
    # bundle is fully covered. Re-open manifest add is unnecessary — add it now, then
    # re-sign so the signature still matches what verify_bundle checks.
    integ_path = os.path.join(bundle_dir, "INTEGRATION.md")
    files_block["INTEGRATION.md"] = {"sha256": sha256_file(integ_path),
                                     "bytes": os.path.getsize(integ_path)}
    manifest["files"] = files_block
    manifest["signature"] = sign_manifest(manifest, key_bytes) if key_bytes else None

    # ---- write manifest.json (pretty) ----
    manifest_path = os.path.join(bundle_dir, "manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, sort_keys=False)
        f.write("\n")

    # ---- zip the folder for delivery ----
    zip_path = os.path.join(dist_root, bundle_name + ".zip")
    if os.path.exists(zip_path):
        os.remove(zip_path)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _dirs, fnames in os.walk(bundle_dir):
            for fn in fnames:
                fp = os.path.join(root, fn)
                arc = os.path.join(bundle_name, os.path.relpath(fp, bundle_dir))
                zf.write(fp, arc)

    return bundle_dir, zip_path
