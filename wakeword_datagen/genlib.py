#!/usr/bin/env python3
"""Shared helpers for the multi-engine wake-word TTS generation framework.

All engines emit 16 kHz mono s16 WAV into output/{positives,negatives}, named so
tools/heym_data.py can parse them:

  positives/  {accent}_{engine}-{voice}_tts_{phrase-slug}_{variant}.wav      -> label 1
  negatives/  neg_{accent}_{engine}-{voice}_tts_{phrase-slug}_{variant}.wav  -> label 0

heym_data.py splits the (neg_-stripped) name on "_" and reads:
  parts[0] = accent   parts[1] = engine-voice ("speaker")
so field 0 and field 1 must never contain an internal underscore. We slugify every
field with hyphens as the only intra-field separator; "_" is reserved as the field
delimiter. Extra trailing underscore-fields (variant, aug tag) are harmless to the loader.
"""
import json
import os
import re
import subprocess

import numpy as np
from scipy.io import wavfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
PHRASES_JSON = os.path.join(HERE, "phrases.json")
OUT_POS = os.path.join(HERE, "output", "positives")
OUT_NEG = os.path.join(HERE, "output", "negatives")
PIPER_DIR = os.path.join(HERE, "models", "piper")
# SpeechCommands _background_noise_ lives here (parent repo .data).
NOISE_ROOT = os.path.join(REPO, ".data", "SpeechCommands", "speech_commands_v0.02")
SR = 16000


def load_phrases():
    with open(PHRASES_JSON, encoding="utf-8") as f:
        return json.load(f)


def ensure_dirs():
    os.makedirs(OUT_POS, exist_ok=True)
    os.makedirs(OUT_NEG, exist_ok=True)


def slug(s):
    """Lowercase, collapse any run of non-alphanumerics to a single hyphen. No underscores."""
    s = str(s).strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-") or "x"


def _fname(accent, engine, voice, phrase_text, variant, negative):
    field_accent = slug(accent)
    field_speaker = slug(f"{engine}-{voice}")
    field_phrase = slug(phrase_text)
    field_variant = slug(variant)
    name = f"{field_accent}_{field_speaker}_tts_{field_phrase}_{field_variant}.wav"
    return ("neg_" + name) if negative else name


def out_path(accent, engine, voice, phrase_text, variant, negative):
    d = OUT_NEG if negative else OUT_POS
    return os.path.join(d, _fname(accent, engine, voice, phrase_text, variant, negative))


def have_ffmpeg():
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
        return True
    except Exception:
        return False


def ffmpeg_to_16k(src, dst):
    """Convert any audio file to 16 kHz mono s16 WAV. Returns True on success."""
    try:
        r = subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", src,
             "-ar", str(SR), "-ac", "1", "-c:a", "pcm_s16le", dst],
            capture_output=True,
        )
        return r.returncode == 0 and os.path.exists(dst) and os.path.getsize(dst) > 44
    except Exception:
        return False


def ffmpeg_atempo(src, dst, tempo):
    """Convert + apply speed (atempo) to 16 kHz mono s16 WAV. Returns True on success."""
    try:
        r = subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", src,
             "-filter:a", f"atempo={tempo:.4f}",
             "-ar", str(SR), "-ac", "1", "-c:a", "pcm_s16le", dst],
            capture_output=True,
        )
        return r.returncode == 0 and os.path.exists(dst) and os.path.getsize(dst) > 44
    except Exception:
        return False


def write_wav_16k(x, dst):
    """Write a float32/64 [-1,1] mono array as 16 kHz s16 WAV (assumes x already at SR)."""
    x = np.asarray(x, dtype=np.float64)
    if x.ndim > 1:
        x = x[:, 0]
    x = np.clip(x, -1.0, 1.0)
    wavfile.write(dst, SR, (x * 32767.0).astype(np.int16))


def read_wav(path):
    sr, data = wavfile.read(path)
    x = data.astype(np.float64)
    if data.dtype == np.int16:
        x /= 32768.0
    elif np.max(np.abs(x)) > 1.0:
        x /= 32768.0
    if x.ndim > 1:
        x = x[:, 0]
    return sr, x


def neg_phrases(phrases):
    """All negatives = hard_negatives + generic_negatives (both -> output/negatives)."""
    return list(phrases.get("hard_negatives", [])) + list(phrases.get("generic_negatives", []))
