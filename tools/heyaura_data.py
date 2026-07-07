#!/usr/bin/env python3
"""Loader/check for the 'hey aura' wake-word dataset (dataset/hey_aura/{positives,negatives}).

Identical filename grammar to heym_data.py — the ONLY tweak needed for hey_aura is ROOT:
field 0 = accent, field 1 = engine-voice ("speaker"); negatives are prefixed neg_.
e.g.  positives/us_gtts-encom_tts_hey-aura_s100.wav          -> label 1, accent=us,  spk=gtts-encom
      negatives/neg_bn_espeak-bn_tts_alexa_p30-w120.wav      -> label 0, accent=bn,  spk=espeak-bn

Run directly to print pos/neg + per-accent + per-engine counts.
"""
import os
from collections import Counter

# The one-line difference from tools/heym_data.py:
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "dataset", "hey_aura")
TEST_SPEAKERS = {"vijay", "ritu", "rohan"}  # none appear in synthetic data -> all land in train


def _base(fn):
    return fn[4:] if fn.startswith("neg_") else fn


def _accent(fn):
    return _base(fn).split("_")[0]


def _speaker(fn):
    p = _base(fn).split("_")
    return p[1] if len(p) > 1 else "?"


def _engine(fn):
    return _speaker(fn).split("-")[0]


def items():
    for sub, label in (("positives", 1), ("negatives", 0)):
        d = os.path.join(ROOT, sub)
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            if fn.endswith(".wav"):
                yield os.path.join(d, fn), label, _speaker(fn), _accent(fn), _engine(fn)


def summary():
    labs, acc, eng = Counter(), Counter(), Counter()
    for _, l, s, a, e in items():
        labs[l] += 1
        acc[a] += 1
        eng[e] += 1
    print(f"pos={labs[1]} neg={labs[0]} total={sum(labs.values())}")
    print("by accent:", dict(sorted(acc.items())))
    print("by engine:", dict(sorted(eng.items())))


if __name__ == "__main__":
    summary()
