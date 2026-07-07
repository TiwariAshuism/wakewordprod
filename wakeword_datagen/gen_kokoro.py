#!/usr/bin/env python3
"""Generate 'hey aura' wake-word clips with Kokoro-82M (kokoro-onnx, CPU).
Outputs 16 kHz mono int16 WAV. Idempotent (skips existing files)."""
import os, re, sys, json, time, subprocess
import numpy as np
from kokoro_onnx import Kokoro

HERE = os.path.dirname(os.path.abspath(__file__))
PHRASES = os.path.join(HERE, "phrases.json")
OUT_POS = os.path.join(HERE, "output", "positives")
OUT_NEG = os.path.join(HERE, "output", "negatives")
MODEL = os.path.join(HERE, "venvs", "kokoro", "kokoro-v1.0.onnx")
VOICES = os.path.join(HERE, "venvs", "kokoro", "voices-v1.0.bin")
os.makedirs(OUT_POS, exist_ok=True)
os.makedirs(OUT_NEG, exist_ok=True)

# voice prefix -> (accent field, kokoro lang)
LANG = {"af": ("af", "en-us"), "am": ("am", "en-us"),
        "bf": ("bf", "en-gb"), "bm": ("bm", "en-gb"),
        "hf": ("hf", "hi"),    "hm": ("hm", "hi")}

# positives: all 5 speeds (maximize). negatives: 2 speeds.
POS_SPEEDS = [0.8, 0.9, 1.0, 1.1, 1.2]
NEG_SPEEDS = [0.9, 1.1]

def slug(i, text):
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return f"{i:02d}-{s}"

def resample_to_wav(samples, sr_in, path):
    raw = np.asarray(samples, dtype=np.float32).tobytes()
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
           "-f", "f32le", "-ar", str(sr_in), "-ac", "1", "-i", "pipe:0",
           "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", path]
    p = subprocess.run(cmd, input=raw, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    if p.returncode != 0:
        raise RuntimeError(p.stderr.decode(errors="ignore")[:300])

def main():
    with open(PHRASES, encoding="utf-8") as f:
        cfg = json.load(f)
    k = Kokoro(MODEL, VOICES)
    voices = [v for v in sorted(k.get_voices()) if v[:2] in LANG]
    print(f"[voices] {len(voices)}: {voices}", flush=True)

    jobs = []  # (outdir, prefix, phrases, speeds)
    jobs.append((OUT_POS, "",    cfg["positives"], POS_SPEEDS))
    negs = cfg["hard_negatives"] + cfg["generic_negatives"]
    jobs.append((OUT_NEG, "neg_", negs, NEG_SPEEDS))

    made = {"pos": 0, "neg": 0}
    skipped = 0
    errors = 0
    t0 = time.time()
    for outdir, prefix, phrases, speeds in jobs:
        key = "neg" if prefix else "pos"
        for i, text in enumerate(phrases):
            sg = slug(i, text)
            for voice in voices:
                accent, lang = LANG[voice[:2]]
                spk = "kokoro-" + voice.replace("_", "")
                for sp in speeds:
                    var = f"s{int(round(sp*100)):03d}"
                    fname = f"{prefix}{accent}_{spk}_tts_{sg}_{var}.wav"
                    path = os.path.join(outdir, fname)
                    if os.path.exists(path):
                        skipped += 1
                        continue
                    try:
                        samples, sr = k.create(text, voice=voice, speed=sp, lang=lang)
                        if samples is None or len(samples) == 0:
                            errors += 1
                            continue
                        resample_to_wav(samples, sr, path)
                        made[key] += 1
                    except Exception as e:
                        errors += 1
                        if errors <= 10:
                            print(f"[err] {fname}: {e}", flush=True)
                    n = made["pos"] + made["neg"]
                    if n and n % 200 == 0:
                        el = time.time() - t0
                        print(f"[prog] made={n} pos={made['pos']} neg={made['neg']} "
                              f"skip={skipped} err={errors} {el:.0f}s "
                              f"({n/el:.1f}/s)", flush=True)
    el = time.time() - t0
    print(f"[DONE] pos={made['pos']} neg={made['neg']} skipped={skipped} "
          f"errors={errors} elapsed={el:.0f}s", flush=True)

if __name__ == "__main__":
    main()
