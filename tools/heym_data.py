#!/usr/bin/env python3
"""Loader for the placed 'hey m' wake-word dataset (dataset/hey_m/{positives,negatives}).

Filenames encode accent/speaker/phrase/style, e.g.
  positives/en-IN_aditya_heyy_m_normal_nat.wav        -> label 1 (wake word)
  negatives/neg_en-IN_aditya_hey_man_fast.wav         -> label 0 (incl. hard negatives)
16 kHz mono int16 (matches the AURA front-end). Split is SPEAKER-INDEPENDENT — a fixed set
of held-out speakers forms the test set, so FA/FR reflect unseen voices (the number that
matters for the hard requirements)."""
import os
import numpy as np
from scipy.io import wavfile

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "dataset", "hey_m")
# Held out for speaker-independent evaluation (never seen in training).
TEST_SPEAKERS = {"vijay", "ritu", "rohan"}


def _speaker(fname):
    base = fname[4:] if fname.startswith("neg_") else fname  # strip neg_
    parts = base.split("_")
    return parts[1] if len(parts) > 1 else "?"   # [accent, speaker, ...]


def _accent(fname):
    base = fname[4:] if fname.startswith("neg_") else fname
    return base.split("_")[0]                     # en-IN, ...


def read_wav(path):
    sr, data = wavfile.read(path)
    x = data.astype(np.float64)
    if data.dtype == np.int16:
        x /= 32768.0
    elif np.max(np.abs(x)) > 1.0:
        x /= 32768.0
    if x.ndim > 1:
        x = x[:, 0]
    return x


def items(split):
    """Yield (path, label, speaker, accent) for split in {'train','test'}."""
    for sub, label in (("positives", 1), ("negatives", 0)):
        d = os.path.join(ROOT, sub)
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            if not fn.endswith(".wav"):
                continue
            spk = _speaker(fn)
            is_test = spk in TEST_SPEAKERS
            if (split == "test") != is_test:
                continue
            yield os.path.join(d, fn), label, spk, _accent(fn)


def summary():
    from collections import Counter
    for split in ("train", "test"):
        labs = Counter()
        spk = Counter()
        acc = Counter()
        for _, l, s, a in items(split):
            labs[l] += 1
            spk[s] += 1
            acc[a] += 1
        print(f"[{split}] pos={labs[1]} neg={labs[0]} speakers={dict(spk)} accents={dict(acc)}")


if __name__ == "__main__":
    summary()
