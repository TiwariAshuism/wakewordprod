#!/usr/bin/env python3
"""Loader for the synthetic 'hey aura' wake-word dataset (dataset/hey_aura/{positives,negatives}).

Same filename grammar as tools/heym_data.py:
  positives/us_gtts-encom_tts_hey-aura_s100.wav      -> label 1, accent=us, speaker=gtts-encom
  negatives/neg_bn_espeak-bn_tts_alexa_p30-w120.wav  -> label 0, accent=bn, speaker=espeak-bn
field0 = accent, field1 = engine-voice ("speaker"); negatives are prefixed neg_.

Because this data is TTS-only (no real speakers), a speaker-held-out split is meaningless.
Instead the eval split is ACCENT-INDEPENDENT: a fixed set of whole accents (~15% of clips) is
held out and NEVER seen in training, so held-out recall / per-clip FAR reflect unseen accents.
"""
import os
import numpy as np
from scipy.io import wavfile

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "dataset", "hey_aura")

# Accent-independent eval: hold out these whole accents (~14.5% of all 8581 clips:
# 210 positives + 1034 negatives). None of these accents appear in the train split.
#   en-gb-scotland  80 pos + 512 neg
#   en-gb-x-gbclan  80 pos + 512 neg
#   us              25 pos +  10 neg
#   uk              25 pos +   0 neg
TEST_ACCENTS = {"en-gb-scotland", "en-gb-x-gbclan", "us", "uk"}


def _base(fname):
    return fname[4:] if fname.startswith("neg_") else fname  # strip neg_


def _accent(fname):
    return _base(fname).split("_")[0]                          # field 0


def _speaker(fname):
    p = _base(fname).split("_")
    return p[1] if len(p) > 1 else "?"                         # field 1 (engine-voice)


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
    """Yield (path, label, speaker, accent) for split in {'train','test'}.
    test == clip's accent is in TEST_ACCENTS (accent-independent held-out eval)."""
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


def summary():
    from collections import Counter
    for split in ("train", "test"):
        labs, spk, acc = Counter(), Counter(), Counter()
        for _, l, s, a in items(split):
            labs[l] += 1
            spk[s] += 1
            acc[a] += 1
        print(f"[{split}] pos={labs[1]} neg={labs[0]} accents={dict(sorted(acc.items()))}")


if __name__ == "__main__":
    summary()
