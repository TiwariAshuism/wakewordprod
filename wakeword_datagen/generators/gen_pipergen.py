#!/usr/bin/env python3
"""Piper *sample-generator* (rhasspy/piper-sample-generator, MIT) wake-word generator.

Distinct from gen_piper.py (which drives ordinary Piper voices): this uses the LibriTTS-R
medium multi-speaker *generator* checkpoint, which blends up to 904 real speaker embeddings
via SLERP (--slerp-weights) for huge voice diversity. English only.

Runs INSIDE the isolated venv wakeword_datagen/venvs/pipergen (torch/torchaudio/piper-tts)
so it never touches the main training environment's torch. Self-contained: no genlib import
(genlib needs scipy, absent here). Resamples 22.05 kHz -> 16 kHz mono s16 in-process with
torchaudio (no per-file ffmpeg spawn). Idempotent: skips clips already present.

Output naming (parsed by tools/aura_data.py: field0=accent, field1=engine-voice):
  positives/  en-us_pipergen-libritts_tts_{phrase-slug}_v0001.wav       -> label 1
  negatives/  neg_en-us_pipergen-libritts_tts_{phrase-slug}_v0001.wav   -> label 0
"""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import wave

import numpy as np
import torch
import torchaudio

HERE = os.path.dirname(os.path.abspath(__file__))
DATAGEN = os.path.dirname(HERE)
REPO_PSG = os.path.join(DATAGEN, "piper-sample-generator")
MODEL = os.path.join(REPO_PSG, "models", "en-us-libritts-high.pt")
PHRASES_JSON = os.path.join(DATAGEN, "phrases.json")
OUT_POS = os.path.join(DATAGEN, "output", "positives")
OUT_NEG = os.path.join(DATAGEN, "output", "negatives")
VENV_PY = os.path.join(DATAGEN, "venvs", "pipergen", "Scripts", "python.exe")

ENGINE = "pipergen"
VOICE = "libritts"
ACCENT = "en-us"        # LibriTTS-R is U.S. English
SR = 16000

# Diversity knobs (cycled per sample by the generator).
SLERP_WEIGHTS = ["0.2", "0.35", "0.5", "0.65", "0.8"]
LENGTH_SCALES = ["0.8", "0.9", "1.0", "1.1", "1.25"]
MAX_SPEAKERS = "800"


def slug(s):
    s = str(s).strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-") or "x"


def fname(phrase, idx, negative):
    name = f"{ACCENT}_{ENGINE}-{VOICE}_tts_{slug(phrase)}_v{idx:04d}.wav"
    return ("neg_" + name) if negative else name


def resample_write(src_wav, dst_wav):
    """Read 22.05 kHz s16 mono WAV -> 16 kHz s16 mono WAV. Trims to avoid empty clips."""
    w = wave.open(src_wav, "rb")
    sr, n, ch = w.getframerate(), w.getnframes(), w.getnchannels()
    raw = w.readframes(n)
    w.close()
    x = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if ch > 1:
        x = x.reshape(-1, ch)[:, 0]
    if x.size < 2:
        return False
    t = torch.from_numpy(x).unsqueeze(0)
    if sr != SR:
        t = torchaudio.functional.resample(t, sr, SR)
    r = np.clip(t.squeeze(0).numpy(), -1.0, 1.0)
    if r.size < 2:
        return False
    i16 = (r * 32767.0).astype(np.int16)
    o = wave.open(dst_wav, "wb")
    o.setframerate(SR)
    o.setsampwidth(2)
    o.setnchannels(1)
    o.writeframes(i16.tobytes())
    o.close()
    return os.path.getsize(dst_wav) > 44


def gen_phrase(phrase, count, negative):
    """Generate `count` clips for one phrase. Idempotent per (phrase, idx)."""
    out_dir = OUT_NEG if negative else OUT_POS
    os.makedirs(out_dir, exist_ok=True)

    targets = [os.path.join(out_dir, fname(phrase, i, negative)) for i in range(count)]
    missing = [i for i, p in enumerate(targets) if not os.path.exists(p)]
    if not missing:
        return 0, count, 0  # made, skipped, failed

    made = failed = 0
    with tempfile.TemporaryDirectory() as tmp:
        cmd = [
            VENV_PY, "-m", "piper_sample_generator", phrase,
            "--model", MODEL,
            "--max-samples", str(count),
            "--max-speakers", MAX_SPEAKERS,
            "--slerp-weights", *SLERP_WEIGHTS,
            "--length-scales", *LENGTH_SCALES,
            "--output-dir", tmp,
        ]
        r = subprocess.run(cmd, cwd=REPO_PSG, capture_output=True, text=True)
        if r.returncode != 0:
            sys.stderr.write(f"[pipergen] FAILED '{phrase}': {r.stderr[-400:]}\n")
            return 0, count - len(missing), len(missing)
        for i in missing:
            raw = os.path.join(tmp, f"{i}.wav")
            if os.path.exists(raw) and resample_write(raw, targets[i]):
                made += 1
            else:
                failed += 1
    return made, count - len(missing), failed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pos-per-phrase", type=int, default=300)
    ap.add_argument("--neg-per-phrase", type=int, default=120)
    args = ap.parse_args()

    with open(PHRASES_JSON, encoding="utf-8") as f:
        p = json.load(f)
    positives = p["positives"]
    negatives = list(p.get("hard_negatives", [])) + list(p.get("generic_negatives", []))

    tot = {"made": 0, "skipped": 0, "failed": 0}
    for label, phrases, per, neg in (
        ("POS", positives, args.pos_per_phrase, False),
        ("NEG", negatives, args.neg_per_phrase, True),
    ):
        for phrase in phrases:
            m, s, f = gen_phrase(phrase, per, neg)
            tot["made"] += m
            tot["skipped"] += s
            tot["failed"] += f
            print(f"  [{label}] {phrase!r:30} made={m} skip={s} fail={f}", flush=True)

    print(json.dumps({"engine": ENGINE, **tot}))


if __name__ == "__main__":
    main()
