#!/usr/bin/env python3
"""Generate synthetic 'hey m' wake-word audio via the Sarvam AI TTS API (Bulbul), to fill the
Indian-language accent gaps (Marathi, Bengali, Hinglish/Hindi, boost Malayalam/Tamil/Telugu/
Kannada). Idempotent: skips any (lang, voice, phrase, pace) clip already on disk.

IMPORTANT (honest scope):
  - Sarvam is INDIA-only TTS. It CANNOT produce en-US / en-GB / en-AU (your V1 accent gap).
  - TTS is a BOOTSTRAP, not real speech: few voices per language, no real mic/channel/distance.
    Synthetic clips go to TRAIN ONLY; the held-out REAL speakers stay the test set, so FR/FA are
    always measured on real voices. Retrain + re-eval will show if this actually helps.

Key: put it in .data/sarvam_key.txt (gitignored) or env SARVAM_API_KEY. Never printed.
Output: 16 kHz mono int16 WAV into dataset/hey_m/{positives,negatives}, named so heym_data.py
picks them up (accent = lang tag, speaker = sarvam voice, marked 'sarvamtts').

Usage:
  python tools/sarvam_tts_gen.py --dry-run        # show plan + count, no API calls, no key needed
  python tools/sarvam_tts_gen.py                  # generate missing clips (needs key)
  python tools/sarvam_tts_gen.py --max 50         # cap number of new clips this run
"""
import argparse
import base64
import io
import json
import os
import sys
import time
import urllib.request

import numpy as np
from scipy.io import wavfile
from scipy.signal import resample_poly

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..", "dataset", "hey_m")
DATA = os.path.join(HERE, "..", ".data")
ENDPOINT = "https://api.sarvam.ai/text-to-speech"
SR = 16000

# BUDGET-OPTIMIZED plan (only ~40 Sarvam credits). Spend where value is highest:
#   1) MISSING languages (completely absent from the dataset) — positives first.
#   2) BOOST languages (present but thin / roadmap V2-V3) — a couple positives each.
#   3) A few confusable negatives, missing-languages first.
MISSING = ["mr-IN", "bn-IN"]                       # not in the data at all
BOOST = ["ml-IN", "hi-IN", "ta-IN", "te-IN"]       # thin / Hinglish / V3
V3 = ["anushka", "abhilash", "vidya"]              # 2F + 1M for some speaker diversity
POS2 = ["hey m", "heyy m"]
NEG2 = ["hey man", "hey google"]
PACES = {"normal": 1.0, "fast": 1.25}


def plan():
    """Yield (kind, lang, voice, text, pace, out_path) in PRIORITY order (highest value first),
    so a small --max still spreads across the missing languages. ~30 items total."""
    def pos(lang, voice, text, pace_name):
        fn = f"{lang}_{voice}_sarvamtts_{_slug(text)}_{pace_name}.wav"
        return ("pos", lang, voice, text, pace_name, os.path.join(ROOT, "positives", fn))

    def neg(lang, voice, text):
        fn = f"neg_{lang}_{voice}_sarvamtts_{_slug(text)}.wav"
        return ("neg", lang, voice, text, "normal", os.path.join(ROOT, "negatives", fn))

    # A) MISSING positives — 2 langs x 3 voices x 2 phrases = 12  (highest value)
    for lang in MISSING:
        for v in V3:
            for txt in POS2:
                yield pos(lang, v, txt, "normal")
    # B) BOOST positives — 4 langs x 2 voices x 1 phrase = 8
    for lang in BOOST:
        for v in V3[:2]:
            yield pos(lang, v, "hey m", "normal")
    # C) MISSING confusable negatives — 2 langs x 1 voice x 2 = 4
    for lang in MISSING:
        for txt in NEG2:
            yield neg(lang, V3[0], txt)
    # D) BOOST negatives — 2 langs x 1 = 2
    for lang in BOOST[:2]:
        yield neg(lang, V3[0], "hey man")
    # E) MISSING fast-pace positives (if budget remains) — 2
    for lang in MISSING:
        yield pos(lang, V3[0], "hey m", "fast")


def load_key():
    k = os.environ.get("SARVAM_API_KEY")
    if k:
        return k.strip()
    f = os.path.join(DATA, "sarvam_key.txt")
    if os.path.isfile(f):
        return open(f).read().strip()
    return None


def _slug(s):
    return s.replace(" ", "_")


def synth(key, text, lang, voice, pace):
    body = json.dumps({
        "inputs": [text], "target_language_code": lang, "speaker": voice,
        "pitch": 0, "pace": pace, "loudness": 1.0,
        "speech_sample_rate": SR, "enable_preprocessing": True, "model": "bulbul:v2",
    }).encode()
    req = urllib.request.Request(ENDPOINT, data=body, method="POST",
                                 headers={"api-subscription-key": key, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        payload = json.loads(r.read())
    wav_b64 = payload["audios"][0]
    sr, data = wavfile.read(io.BytesIO(base64.b64decode(wav_b64)))
    x = data.astype(np.float32)
    if data.dtype == np.int16:
        x /= 32768.0
    if x.ndim > 1:
        x = x[:, 0]
    if sr != SR:
        from math import gcd
        g = gcd(int(sr), SR)
        x = resample_poly(x, SR // g, int(sr) // g)
    return np.clip(x, -1, 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--max", type=int, default=0, help="cap new clips this run (0 = no cap)")
    ap.add_argument("--sleep", type=float, default=0.2, help="pause between API calls")
    args = ap.parse_args()

    todo = [p for p in plan() if not os.path.exists(p[5])]
    exists = sum(1 for _ in plan()) - len(todo)
    npos = sum(1 for t in todo if t[0] == "pos"); nneg = len(todo) - npos
    print(f"total planned={sum(1 for _ in plan())}  already-on-disk(skip)={exists}  "
          f"to-generate={len(todo)} (pos={npos}, neg={nneg})")
    print(f"missing-langs={MISSING}  boost-langs={BOOST}  voices={V3}")
    if args.dry_run:
        by_lang = {}
        for t in todo:
            by_lang[t[1]] = by_lang.get(t[1], 0) + 1
        print("to-generate by language:", by_lang)
        print("(dry-run: no API calls, no key needed)")
        return 0

    key = load_key()
    if not key:
        print("ERROR: no key. Put it in .data/sarvam_key.txt or set SARVAM_API_KEY.", file=sys.stderr)
        return 2

    os.makedirs(os.path.join(ROOT, "positives"), exist_ok=True)
    os.makedirs(os.path.join(ROOT, "negatives"), exist_ok=True)
    made = fail = 0
    for kind, lang, voice, txt, pace_name, out in todo:
        if args.max and made >= args.max:
            print(f"hit --max {args.max}; stopping (rest will generate on next run).")
            break
        try:
            x = synth(key, txt, lang, voice, PACES[pace_name])
            wavfile.write(out, SR, (x * 32767).astype(np.int16))
            made += 1
            if made % 25 == 0:
                print(f"  ...{made} generated")
        except Exception as e:
            fail += 1
            msg = str(e)[:120]
            if fail <= 10:
                print(f"  FAIL {lang}/{voice}/{txt}: {msg}")
        time.sleep(args.sleep)
    print(f"done: generated={made} failed={fail} (skipped {exists} existing). "
          f"Synthetic clips are TRAIN-only (real held-out speakers remain the test set).")
    print("Next: rm .data/heym_feat2.npz && retrain + re-eval to measure if it helps FR.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
