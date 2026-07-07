#!/usr/bin/env python3
"""Waveform augmentation for the generated TTS clips. Reuses tools/aura_augment.py (the same
augmenter used for AURA KWS training) so augmentation matches the training front-end exactly:
additive background noise at an SNR curriculum {20,10,5,0} dB, synthetic far-field reverb,
speed perturbation, gain jitter, time-shift.

Each clean clip is multiplied into K augmented variants written next to it, with '-aug{n}'
appended to the variant field so heym_data.py still parses accent/speaker and so we never
re-augment an already-augmented file. Idempotent (skips existing). Seeded/reproducible.

Background noise: SpeechCommands _background_noise_ (.data/SpeechCommands/...). If that corpus
is absent we synthesize white/pink/brown noise so SNR mixing still happens.

Usage: python augment.py [--k 4] [--limit N] [--seed 0]
"""
import argparse
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))
import genlib          # noqa: E402
import aura_augment    # noqa: E402  (tools/aura_augment.py)

SNR_CHOICES = (20, 15, 10, 5, 0)


def _synth_noises(rng, n=4, length=genlib.SR * 4):
    """Fallback noise bank (white / pink-ish / brown-ish) if no _background_noise_ corpus."""
    out = []
    for _ in range(n):
        w = rng.standard_normal(length)
        kind = rng.randint(3)
        if kind == 0:                      # white
            x = w
        elif kind == 1:                    # pink-ish (cumulative, mild)
            x = np.cumsum(w) * 0.02
        else:                              # brown-ish
            x = np.cumsum(np.cumsum(w)) * 0.0004
        x = x / (np.max(np.abs(x)) + 1e-9) * 0.3
        out.append(x.astype(np.float64))
    return out


def load_noises(rng):
    noises = aura_augment.load_background_noise(genlib.NOISE_ROOT)
    if noises:
        return noises, f"_background_noise_ ({len(noises)} clips)"
    return _synth_noises(rng), "synthesized (no corpus found)"


def _clean_sources():
    """Yield (dir, filename) for every non-augmented clip already generated."""
    for d in (genlib.OUT_POS, genlib.OUT_NEG):
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            if fn.endswith(".wav") and "-aug" not in fn:
                yield d, fn


def augment_all(k=4, limit=None, seed=0):
    rng = np.random.RandomState(seed)
    noises, src = load_noises(rng)
    sources = list(_clean_sources())
    if limit:
        sources = sources[:limit]
    made = skipped = failed = 0
    for d, fn in sources:
        try:
            sr, x = genlib.read_wav(os.path.join(d, fn))
        except Exception:
            failed += 1
            continue
        stem = fn[:-4]
        for n in range(k):
            out = os.path.join(d, f"{stem}-aug{n}.wav")
            if os.path.exists(out):
                skipped += 1
                continue
            try:
                y = aura_augment.augment(x, noises, rng, snr_choices=SNR_CHOICES)
                genlib.write_wav_16k(y, out)
                made += 1
            except Exception:
                failed += 1
    return {"noise_source": src, "clean_sources": len(sources),
            "made": made, "skipped": skipped, "failed": failed, "k": k}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, default=4, help="augmented variants per clean clip")
    ap.add_argument("--limit", type=int, default=None, help="cap clean source clips (smoke)")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()
    print(augment_all(k=args.k, limit=args.limit, seed=args.seed))


if __name__ == "__main__":
    main()
