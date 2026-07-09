#!/usr/bin/env python3
"""Wake-word dataset loader.

Two modes, selected by whether a `dataset_dir` is passed to `items()`:

1. GENERALIZED (the easy training flow — `train.py` / `evaluate.py`):
   Pass `dataset_dir=datasets/<wakeword>` and it loads
       datasets/<wakeword>/positive/*.wav   -> label 1 (wake word)
       datasets/<wakeword>/negative/*.wav   -> label 0 (everything else)
   16 kHz mono. The split is SPEAKER-INDEPENDENT: a deterministic ~15% of the distinct
   speakers is held out and NEVER seen in training, so held-out recall / per-clip FAR
   reflect unseen voices. "Speaker" is parsed from the filename when it follows the
   `accent_speaker_...` grammar (see tools/heym_data.py); otherwise the whole file stem is
   treated as its own speaker, which still yields a reproducible, leakage-free split.

2. LEGACY (default, `dataset_dir=None`): the original synthetic 'hey aura' dataset at
   dataset/hey_aura/{positives,negatives} with an ACCENT-independent split (TEST_ACCENTS).
   Preserved unchanged so tools/aura_train.py and tools/calibrate.py keep working when called
   without a dataset_dir.
"""
import hashlib
import os

import numpy as np
from scipy.io import wavfile

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "dataset", "hey_aura")

# ---- Legacy accent-independent eval: hold out these whole accents (~14.5% of clips). ----
# None of these accents appear in the legacy train split.
TEST_ACCENTS = {"en-gb-scotland", "en-gb-x-gbclan", "us", "uk"}

# Generalized speaker-independent split: a speaker lands in the test set when a stable hash
# of its name falls in the bottom TEST_SPEAKER_PCT percent. Deterministic across runs/OSes.
TEST_SPEAKER_PCT = 15


def _base(fname):
    return fname[4:] if fname.startswith("neg_") else fname  # strip neg_


def _accent(fname):
    return _base(fname).split("_")[0]                          # field 0


def _speaker(fname):
    p = _base(fname).split("_")
    return p[1] if len(p) > 1 else "?"                         # field 1 (engine-voice)


def _speaker_key(fname):
    """Speaker id for the speaker-independent split. Uses the `accent_speaker_...` grammar
    when present (field 1); otherwise the file stem (minus a `neg_` prefix) is its own key."""
    base = _base(fname)
    stem = os.path.splitext(base)[0]
    parts = stem.split("_")
    return parts[1] if len(parts) >= 2 else stem


def _is_test_speaker(spk, test_pct=TEST_SPEAKER_PCT):
    h = int(hashlib.md5(spk.encode("utf-8")).hexdigest(), 16) % 100
    return h < test_pct


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


def _legacy_items(split):
    """Original dataset/hey_aura loader (accent-independent split via TEST_ACCENTS)."""
    for sub, label in (("positives", 1), ("negatives", 0)):
        d = os.path.join(ROOT, sub)
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            if not fn.endswith(".wav"):
                continue
            acc = _accent(fn)
            is_test = acc in TEST_ACCENTS
            if (split == "test") != is_test:
                continue
            yield os.path.join(d, fn), label, _speaker(fn), acc


def items(split, dataset_dir=None, wake_word=None, test_pct=TEST_SPEAKER_PCT):
    """Yield (path, label, speaker, accent) for split in {'train','test'}.

    dataset_dir=None  -> legacy dataset/hey_aura (accent-independent split).
    dataset_dir set   -> datasets/<wakeword>/{positive,negative}/*.wav with a
                         speaker-independent split (test == speaker held out)."""
    if dataset_dir is None:
        yield from _legacy_items(split)
        return
    for sub, label in (("positive", 1), ("negative", 0)):
        d = os.path.join(dataset_dir, sub)
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            if not fn.endswith(".wav"):
                continue
            spk = _speaker_key(fn)
            is_test = _is_test_speaker(spk, test_pct)
            if (split == "test") != is_test:
                continue
            yield os.path.join(d, fn), label, spk, _accent(fn)


def summary(dataset_dir=None, wake_word=None):
    from collections import Counter
    for split in ("train", "test"):
        labs, spk, acc = Counter(), Counter(), Counter()
        for _, l, s, a in items(split, dataset_dir=dataset_dir, wake_word=wake_word):
            labs[l] += 1
            spk[s] += 1
            acc[a] += 1
        print(f"[{split}] pos={labs[1]} neg={labs[0]} n_speakers={len(spk)} "
              f"accents={dict(sorted(acc.items()))}")


if __name__ == "__main__":
    summary()
