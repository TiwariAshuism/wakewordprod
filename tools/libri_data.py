#!/usr/bin/env python3
"""Loader for the REAL-speech LibriSpeech keyword dataset (dataset/libri_<word>/{positives,negatives}).

Filename grammar (real LibriSpeech speakers):
  positives/spk1089_libri_little_25.wav          -> label 1, speaker=1089, word=little
  negatives/neg_spk1089_libri_the_994.wav        -> label 0, speaker=1089, word=the
The 'spk{ID}' field (field 0 after stripping the neg_ prefix) is the LibriSpeech speaker id.

Because this is REAL speech from many distinct speakers, the eval split is SPEAKER-INDEPENDENT:
a fixed ~20% of the DISTINCT SPEAKERS is held out and NEVER seen in training, so held-out
recall / per-clip FAR reflect UNSEEN REAL VOICES (the number that matters for the wake-word gate).
"""
import os
import re
import numpy as np
from scipy.io import wavfile

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "dataset", "libri_little")

# Fraction of DISTINCT speakers held out for the speaker-independent test split.
HELDOUT_FRAC = 0.20
HELDOUT_SEED = 1337

_SPK_RE = re.compile(r"spk(\d+)")


def _base(fname):
    return fname[4:] if fname.startswith("neg_") else fname  # strip neg_


def _speaker(fname):
    m = _SPK_RE.search(fname)
    return m.group(1) if m else "?"                            # LibriSpeech speaker id


def _word(fname):
    p = _base(fname).split("_")
    # spk{ID}_libri_{word}_{num}.wav  -> word is field index 2
    return p[2] if len(p) > 2 else "?"


def _all_speakers():
    spk = set()
    for sub in ("positives", "negatives"):
        d = os.path.join(ROOT, sub)
        if not os.path.isdir(d):
            continue
        for fn in os.listdir(d):
            if fn.endswith(".wav"):
                spk.add(_speaker(fn))
    return sorted(spk, key=lambda s: (len(s), s))


def heldout_speakers():
    """Deterministic ~20% of DISTINCT speakers reserved for test (never in train)."""
    spk = _all_speakers()
    n_hold = max(1, int(round(len(spk) * HELDOUT_FRAC)))
    rng = np.random.RandomState(HELDOUT_SEED)
    idx = rng.permutation(len(spk))[:n_hold]
    return set(spk[i] for i in sorted(idx))


TEST_SPEAKERS = None  # lazily filled by items()


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
    """Yield (path, label, speaker, word) for split in {'train','test'}.
    test == clip's speaker is in the held-out speaker set (speaker-independent eval)."""
    global TEST_SPEAKERS
    if TEST_SPEAKERS is None:
        TEST_SPEAKERS = heldout_speakers()
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
            yield os.path.join(d, fn), label, spk, _word(fn)


def summary():
    from collections import Counter
    hs = heldout_speakers()
    allspk = _all_speakers()
    print(f"[speakers] total={len(allspk)} heldout={len(hs)} ({sorted(hs, key=lambda s:(len(s),s))})")
    for split in ("train", "test"):
        labs, spk = Counter(), set()
        for _, l, s, w in items(split):
            labs[l] += 1
            spk.add(s)
        print(f"[{split}] pos={labs[1]} neg={labs[0]} clips={labs[1]+labs[0]} speakers={len(spk)}")


if __name__ == "__main__":
    summary()
