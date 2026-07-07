#!/usr/bin/env python3
"""Windows SAPI voices via pyttsx3 (NON-AI). Each installed voice x a couple of speaking
rates, over every phrase. Emits 16 kHz mono s16 WAV. Idempotent.

pyttsx3's SAPI driver is finicky about save_to_file in a loop, so we re-create the engine
per clip (slower but reliable). Off Windows / no voices -> reported unavailable.

Usage: python gen_sapi.py [--limit N]
"""
import argparse
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import genlib  # noqa: E402

ENGINE = "sapi"
# SAPI default rate is ~200 wpm; sample a slow / normal / fast triple.
RATES = [150, 200, 250]


def _import():
    try:
        import pyttsx3  # noqa
        return pyttsx3
    except Exception:
        return None


def list_voices():
    pyttsx3 = _import()
    if pyttsx3 is None:
        return None, []
    try:
        eng = pyttsx3.init()
        voices = eng.getProperty("voices")
        try:
            eng.stop()
        except Exception:
            pass
        out = []
        for v in voices:
            vid = v.id
            name = getattr(v, "name", None) or vid.split("\\")[-1]
            out.append((vid, name))
        return pyttsx3, out
    except Exception:
        return pyttsx3, []


def _voice_accent(name):
    n = name.lower()
    for tag in ("en-us", "en-gb", "en-in", "en-au"):
        if tag.replace("-", "") in n.replace("-", "").replace(" ", ""):
            return tag
    if "united states" in n or "david" in n or "zira" in n or "mark" in n:
        return "en-us"
    if "united kingdom" in n or "hazel" in n or "george" in n:
        return "en-gb"
    if "india" in n or "heera" in n or "ravi" in n:
        return "en-in"
    return "sapi"


def _synth(pyttsx3, vid, rate, text, out_wav):
    fd, raw = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    try:
        eng = pyttsx3.init()
        eng.setProperty("voice", vid)
        eng.setProperty("rate", rate)
        eng.save_to_file(text, raw)
        eng.runAndWait()
        try:
            eng.stop()
        except Exception:
            pass
        if not os.path.exists(raw) or os.path.getsize(raw) < 44:
            return False
        return genlib.ffmpeg_to_16k(raw, out_wav)
    except Exception:
        return False
    finally:
        if os.path.exists(raw):
            os.remove(raw)


def generate(limit=None):
    pyttsx3, voices = list_voices()
    if pyttsx3 is None:
        return {"engine": ENGINE, "available": False, "made": 0, "skipped": 0,
                "failed": 0, "reason": "pyttsx3 not installed"}
    if not voices:
        return {"engine": ENGINE, "available": False, "made": 0, "skipped": 0,
                "failed": 0, "reason": "no SAPI voices found (non-Windows or none installed)"}
    genlib.ensure_dirs()
    p = genlib.load_phrases()
    jobs = []  # (text, negative, vid, name, rate)
    for negative, texts in ((False, p["positives"]), (True, genlib.neg_phrases(p))):
        for vid, name in voices:
            for rate in RATES:
                for text in texts:
                    jobs.append((text, negative, vid, name, rate))
    if limit:
        pos = [j for j in jobs if not j[1]][:limit]
        neg = [j for j in jobs if j[1]][:limit]
        jobs = pos + neg
    made = skipped = failed = 0
    for text, negative, vid, name, rate in jobs:
        accent = _voice_accent(name)
        variant = f"r{rate}"
        out = genlib.out_path(accent, ENGINE, name, text, variant, negative)
        if os.path.exists(out):
            skipped += 1
            continue
        if _synth(pyttsx3, vid, rate, text, out):
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
