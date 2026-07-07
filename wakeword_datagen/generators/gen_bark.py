#!/usr/bin/env python3
"""Bark (suno-ai, MIT) generative TTS -> wake-word clips. GPU-preferred, SLOW on CPU.

Runs from an ISOLATED venv (wakeword_datagen/venvs/bark) so it never touches the main
env's torch. Emits 16 kHz mono s16 WAV into output/{positives,negatives} using the shared
genlib filename grammar so tools/aura_data.py can parse accent/speaker.

Because Bark is slow on CPU this is a MODEST diversity proof, not a full sweep:
  * uses SUNO_USE_SMALL_MODELS to be tractable on CPU
  * a few v2/en_speaker_* presets
  * a wall-clock budget (--minutes) and a hard clip cap (--max-clips); it stops cleanly
  * idempotent: existing files are skipped, so re-running resumes

Usage: python gen_bark.py [--minutes 40] [--max-clips 30]
"""
import argparse
import os
import sys
import tempfile
import time

# Bark env knobs MUST be set before importing bark.
os.environ.setdefault("SUNO_USE_SMALL_MODELS", "1")
os.environ.setdefault("SUNO_OFFLOAD_CPU", "0")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import genlib  # noqa: E402

ENGINE = "bark"
ACCENT = "en"  # Bark en_speaker presets; not in aura_data TEST_ACCENTS -> all land in train

# A few presets for speaker diversity (male/female mix).
SPEAKERS = ["v2/en_speaker_1", "v2/en_speaker_6", "v2/en_speaker_9"]

# Modest phrase selection (dedup of near-identical spellings).
POS_PHRASES = ["hey aura", "heyy aura", "hai aura", "hey aurah"]
NEG_PHRASES = ["aura", "hey Dora", "hey Cora", "hey Nora", "hey Laura", "hey Aurora"]


def _voice_tag(speaker):
    # slug("bark-v2/en_speaker_6") -> "bark-v2-en-speaker-6"; keep only the speaker part for voice
    return speaker  # genlib.slug will hyphenate it; engine prefix added by _fname


def _jobs():
    """Yield (negative, phrase, speaker, variant, out_path)."""
    for negative, phrases in ((False, POS_PHRASES), (True, NEG_PHRASES)):
        for phrase in phrases:
            for speaker in SPEAKERS:
                variant = "t0"
                out = genlib.out_path(ACCENT, ENGINE, _voice_tag(speaker), phrase, variant, negative)
                yield negative, phrase, speaker, variant, out


def generate(minutes=40.0, max_clips=30):
    genlib.ensure_dirs()

    try:
        from bark import SAMPLE_RATE, generate_audio, preload_models
        from scipy.io import wavfile
        import numpy as np
    except Exception as e:
        return {"engine": ENGINE, "available": False, "made": 0, "skipped": 0,
                "failed": 0, "reason": f"import failed: {e}"}

    jobs = list(_jobs())
    todo = [j for j in jobs if not os.path.exists(j[4])]
    skipped = len(jobs) - len(todo)
    if not todo:
        return {"engine": ENGINE, "available": True, "made": 0, "skipped": skipped,
                "failed": 0, "reason": "all target files already exist"}

    t_load = time.time()
    try:
        preload_models()
    except Exception as e:
        return {"engine": ENGINE, "available": False, "made": 0, "skipped": skipped,
                "failed": 0, "reason": f"preload_models failed (model download?): {e}"}
    load_s = time.time() - t_load
    print(f"[bark] models loaded in {load_s:.0f}s", flush=True)

    deadline = time.time() + minutes * 60.0
    made = failed = 0
    voices_used = set()
    for i, (negative, phrase, speaker, variant, out) in enumerate(todo):
        if made >= max_clips:
            print(f"[bark] hit max-clips={max_clips}, stopping", flush=True)
            break
        if time.time() > deadline:
            print(f"[bark] hit time budget ({minutes} min), stopping", flush=True)
            break
        t0 = time.time()
        try:
            audio = generate_audio(phrase, history_prompt=speaker, silent=True)
            fd, tmp = tempfile.mkstemp(suffix=".wav")
            os.close(fd)
            try:
                wavfile.write(tmp, SAMPLE_RATE, np.asarray(audio, dtype=np.float32))
                ok = genlib.ffmpeg_to_16k(tmp, out)
            finally:
                if os.path.exists(tmp):
                    os.remove(tmp)
            if ok:
                made += 1
                voices_used.add(speaker)
                dt = time.time() - t0
                lbl = "neg" if negative else "pos"
                print(f"[bark] {made}/{len(todo)} {lbl} '{phrase}' {speaker} {dt:.0f}s -> {os.path.basename(out)}", flush=True)
            else:
                failed += 1
                print(f"[bark] ffmpeg failed for '{phrase}' {speaker}", flush=True)
        except Exception as e:
            failed += 1
            print(f"[bark] gen failed '{phrase}' {speaker}: {e}", flush=True)

    return {"engine": ENGINE, "available": True, "made": made, "skipped": skipped,
            "failed": failed, "voices_used": sorted(voices_used),
            "model_load_s": round(load_s, 1)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=float, default=40.0)
    ap.add_argument("--max-clips", type=int, default=30)
    args = ap.parse_args()
    print(generate(minutes=args.minutes, max_clips=args.max_clips))


if __name__ == "__main__":
    main()
