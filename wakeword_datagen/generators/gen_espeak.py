#!/usr/bin/env python3
"""espeak-ng (NON-AI, classic formant synthesis) wake-word generator.

Grid: espeak_accents x espeak_pitches x espeak_speeds_wpm, over every positive/negative
phrase. Emits 16 kHz mono s16 WAV into output/{positives,negatives}. Idempotent.

Usage: python gen_espeak.py [--limit N]
"""
import argparse
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import genlib  # noqa: E402

ENGINE = "espeak"
# espeak-ng on Windows (as installed for this project).
ESPEAK_BIN = os.environ.get("ESPEAK_BIN", r"C:\Program Files\eSpeak NG\espeak-ng.exe")


def available():
    for cand in (ESPEAK_BIN, "espeak-ng", "espeak"):
        try:
            subprocess.run([cand, "--version"], capture_output=True, check=True)
            return cand
        except Exception:
            continue
    return None


def _synth(binpath, text, accent, pitch, wpm, out_wav):
    """espeak-ng -> raw wav, then ffmpeg -> 16 kHz mono s16."""
    fd, raw = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    try:
        r = subprocess.run(
            [binpath, "-v", accent, "-p", str(pitch), "-s", str(wpm), "-w", raw, text],
            capture_output=True,
        )
        if r.returncode != 0 or not os.path.exists(raw) or os.path.getsize(raw) < 44:
            return False
        return genlib.ffmpeg_to_16k(raw, out_wav)
    finally:
        if os.path.exists(raw):
            os.remove(raw)


def generate(limit=None):
    binpath = available()
    if not binpath:
        return {"engine": ENGINE, "available": False, "made": 0, "skipped": 0,
                "failed": 0, "reason": "espeak-ng binary not found"}
    genlib.ensure_dirs()
    p = genlib.load_phrases()
    accents = p["espeak_accents"]
    pitches = p["espeak_pitches"]
    wpms = p["espeak_speeds_wpm"]
    jobs = []  # (text, negative, accent, pitch, wpm)
    for negative, texts in ((False, p["positives"]), (True, genlib.neg_phrases(p))):
        for accent in accents:
            for pitch in pitches:
                for wpm in wpms:
                    for text in texts:
                        jobs.append((text, negative, accent, pitch, wpm))
    if limit:
        pos = [j for j in jobs if not j[1]][:limit]
        neg = [j for j in jobs if j[1]][:limit]
        jobs = pos + neg
    made = skipped = failed = 0
    for text, negative, accent, pitch, wpm in jobs:
        variant = f"p{pitch}-w{wpm}"
        out = genlib.out_path(accent, ENGINE, accent, text, variant, negative)
        if os.path.exists(out):
            skipped += 1
            continue
        if _synth(binpath, text, accent, pitch, wpm, out):
            made += 1
        else:
            failed += 1
    return {"engine": ENGINE, "available": True, "made": made,
            "skipped": skipped, "failed": failed}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None,
                    help="max NEW clips per category (positives / negatives) for a smoke")
    args = ap.parse_args()
    print(generate(limit=args.limit))


if __name__ == "__main__":
    main()
