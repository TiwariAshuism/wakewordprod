#!/usr/bin/env python3
"""Google Translate TTS via gTTS (AI, ONLINE). One MP3 per (accent, phrase); speed
variants are derived locally with ffmpeg atempo (no extra network calls). 16 kHz mono
s16 WAV out. Idempotent, and gentle on the rate limiter (sleep + backoff between calls).

Usage: python gen_gtts.py [--limit N] [--sleep 0.6]
"""
import argparse
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import genlib  # noqa: E402

ENGINE = "gtts"


def _import():
    try:
        from gtts import gTTS  # noqa
        return gTTS
    except Exception:
        return None


def _fetch_mp3(gTTS, text, lang, tld, dst, sleep, retries=3):
    """Download one MP3 with simple exponential backoff on rate-limit / network errors."""
    delay = sleep
    for attempt in range(retries):
        try:
            gTTS(text=text, lang=lang, tld=tld).save(dst)
            time.sleep(sleep)
            return True
        except Exception as e:
            msg = str(e).lower()
            if attempt == retries - 1:
                return False
            # back off harder on throttling
            time.sleep(delay * (4 if ("429" in msg or "too many" in msg) else 2))
            delay *= 2
    return False


def generate(limit=None, sleep=0.6):
    gTTS = _import()
    if gTTS is None:
        return {"engine": ENGINE, "available": False, "made": 0, "skipped": 0,
                "failed": 0, "reason": "gTTS not installed"}
    genlib.ensure_dirs()
    p = genlib.load_phrases()
    accents = p["gtts_accents"]         # [lang, tld, label]
    speeds = p["speeds"]
    jobs = []  # (text, negative, lang, tld, label)
    for negative, texts in ((False, p["positives"]), (True, genlib.neg_phrases(p))):
        for lang, tld, label in accents:
            for text in texts:
                jobs.append((text, negative, lang, tld, label))
    if limit:
        pos = [j for j in jobs if not j[1]][:limit]
        neg = [j for j in jobs if j[1]][:limit]
        jobs = pos + neg

    made = skipped = failed = 0
    net_dead = False
    for text, negative, lang, tld, label in jobs:
        voice = f"{lang}{tld.replace('.', '')}"
        # what outputs would this job produce (one per speed)?
        targets = []
        for spd in speeds:
            variant = f"s{int(round(spd * 100)):03d}"
            targets.append((spd, genlib.out_path(label, ENGINE, voice, text, variant, negative)))
        if all(os.path.exists(t[1]) for t in targets):
            skipped += len(targets)
            continue
        if net_dead:
            failed += sum(1 for _, o in targets if not os.path.exists(o))
            continue
        fd, mp3 = tempfile.mkstemp(suffix=".mp3")
        os.close(fd)
        try:
            if not _fetch_mp3(gTTS, text, lang, tld, mp3, sleep):
                # one hard failure early likely means offline; stop hammering the API
                net_dead = made == 0
                failed += sum(1 for _, o in targets if not os.path.exists(o))
                continue
            for spd, out in targets:
                if os.path.exists(out):
                    skipped += 1
                    continue
                ok = (genlib.ffmpeg_to_16k(mp3, out) if abs(spd - 1.0) < 1e-6
                      else genlib.ffmpeg_atempo(mp3, out, spd))
                made += 1 if ok else 0
                failed += 0 if ok else 1
        finally:
            if os.path.exists(mp3):
                os.remove(mp3)
    res = {"engine": ENGINE, "available": True, "made": made,
           "skipped": skipped, "failed": failed}
    if net_dead and made == 0:
        res["reason"] = "network/gTTS unreachable (offline or rate-limited)"
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--sleep", type=float, default=0.6)
    args = ap.parse_args()
    print(generate(limit=args.limit, sleep=args.sleep))


if __name__ == "__main__":
    main()
