#!/usr/bin/env python3
"""Piper (AI, OFFLINE neural TTS) wake-word generator. Uses the downloaded en_US / en_GB
voices in models/piper. Speed variants map phrases.json 'speeds' to piper --length-scale
(length_scale = 1/speed: >1 slower, <1 faster). 16 kHz mono s16 WAV out. Idempotent.

Voices auto-download from https://huggingface.co/rhasspy/piper-voices if missing; a failed
download is logged and that voice is skipped (framework degrades gracefully).

Usage: python gen_piper.py [--limit N]
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import genlib  # noqa: E402

ENGINE = "piper"
HF = "https://huggingface.co/rhasspy/piper-voices/resolve/main"
# (short-name, accent-tag, hf-relative-path-without-extension)
# Many en_US + en_GB neural voices at medium quality (danny only ships at 'low').
# A failed/absent download is logged and skipped, so the list can be aspirational.
VOICES = [
    # --- en_US ---
    ("amy", "en-us", "en/en_US/amy/medium/en_US-amy-medium"),
    ("danny", "en-us", "en/en_US/danny/low/en_US-danny-low"),
    ("joe", "en-us", "en/en_US/joe/medium/en_US-joe-medium"),
    ("kusal", "en-us", "en/en_US/kusal/medium/en_US-kusal-medium"),
    ("lessac", "en-us", "en/en_US/lessac/medium/en_US-lessac-medium"),
    ("ryan", "en-us", "en/en_US/ryan/medium/en_US-ryan-medium"),
    ("kristin", "en-us", "en/en_US/kristin/medium/en_US-kristin-medium"),
    ("hfcmale", "en-us", "en/en_US/hfc_male/medium/en_US-hfc_male-medium"),
    ("hfcfemale", "en-us", "en/en_US/hfc_female/medium/en_US-hfc_female-medium"),
    # --- en_GB ---
    ("alan", "en-gb", "en/en_GB/alan/medium/en_GB-alan-medium"),
    ("alba", "en-gb", "en/en_GB/alba/medium/en_GB-alba-medium"),
    ("cori", "en-gb", "en/en_GB/cori/medium/en_GB-cori-medium"),
    ("jenny", "en-gb", "en/en_GB/jenny_dioco/medium/en_GB-jenny_dioco-medium"),
    ("northern", "en-gb", "en/en_GB/northern_english_male/medium/en_GB-northern_english_male-medium"),
    ("semaine", "en-gb", "en/en_GB/semaine/medium/en_GB-semaine-medium"),
]


def _download(rel, dst):
    try:
        urllib.request.urlretrieve(f"{HF}/{rel}", dst)
        return os.path.exists(dst) and os.path.getsize(dst) > 1024
    except Exception:
        return False


def ensure_voices():
    """Return list of (name, accent, onnx_path). Downloads missing voices; logs failures."""
    os.makedirs(genlib.PIPER_DIR, exist_ok=True)
    ready = []
    for name, accent, rel in VOICES:
        onnx = os.path.join(genlib.PIPER_DIR, os.path.basename(rel) + ".onnx")
        cfg = onnx + ".json"
        if not (os.path.exists(onnx) and os.path.exists(cfg)):
            print(f"  [piper] downloading voice {name} ({accent}) ...")
            ok = _download(rel + ".onnx", onnx) and _download(rel + ".onnx.json", cfg)
            if not ok:
                print(f"  [piper] FAILED to download {name}; skipping")
                continue
        ready.append((name, accent, onnx))
    return ready


def piper_available():
    try:
        subprocess.run([sys.executable, "-m", "piper", "--help"],
                       capture_output=True, check=True)
        return True
    except Exception:
        return False


def _synth(onnx, length_scale, text, out_wav):
    fd, raw = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    try:
        r = subprocess.run(
            [sys.executable, "-m", "piper", "-m", onnx,
             "--length-scale", f"{length_scale:.4f}", "-f", raw],
            input=text.encode("utf-8"), capture_output=True,
        )
        if r.returncode != 0 or not os.path.exists(raw) or os.path.getsize(raw) < 44:
            return False
        return genlib.ffmpeg_to_16k(raw, out_wav)
    finally:
        if os.path.exists(raw):
            os.remove(raw)


def generate(limit=None):
    if not piper_available():
        return {"engine": ENGINE, "available": False, "made": 0, "skipped": 0,
                "failed": 0, "reason": "piper package not installed"}
    voices = ensure_voices()
    if not voices:
        return {"engine": ENGINE, "available": False, "made": 0, "skipped": 0,
                "failed": 0, "reason": "no piper voices available (download failed?)"}
    genlib.ensure_dirs()
    p = genlib.load_phrases()
    speeds = p["speeds"]
    jobs = []  # (text, negative, name, accent, onnx, speed)
    for negative, texts in ((False, p["positives"]), (True, genlib.neg_phrases(p))):
        for name, accent, onnx in voices:
            for spd in speeds:
                for text in texts:
                    jobs.append((text, negative, name, accent, onnx, spd))
    if limit:
        pos = [j for j in jobs if not j[1]][:limit]
        neg = [j for j in jobs if j[1]][:limit]
        jobs = pos + neg
    made = skipped = failed = 0
    for text, negative, name, accent, onnx, spd in jobs:
        ls = 1.0 / spd
        variant = f"ls{ls:.2f}"
        out = genlib.out_path(accent, ENGINE, name, text, variant, negative)
        if os.path.exists(out):
            skipped += 1
            continue
        if _synth(onnx, ls, text, out):
            made += 1
        else:
            failed += 1
    return {"engine": ENGINE, "available": True, "made": made,
            "skipped": skipped, "failed": failed, "voices": len(voices)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()
    print(generate(limit=args.limit))


if __name__ == "__main__":
    main()
