#!/usr/bin/env python3
"""Speech Commands v2 reader that loads WAVs directly with scipy (bypasses
torchaudio's TorchCodec/FFmpeg backend, which isn't installed). Uses the dataset's
official testing_list.txt / validation_list.txt to split; everything else is
training. Skips _background_noise_ (not a labelled word)."""
import os
import numpy as np
from scipy.io import wavfile

V2 = "speech_commands_v0.02"


def find_root(data_dir):
    for cand in (os.path.join(data_dir, "SpeechCommands", V2), os.path.join(data_dir, V2)):
        if os.path.isdir(cand):
            return cand
    raise FileNotFoundError(f"Speech Commands not found under {data_dir}")


def _load_list(root, fname):
    path = os.path.join(root, fname)
    with open(path) as f:
        return set(line.strip().replace("\\", "/") for line in f if line.strip())


def iter_clips(root, subset, shuffle_seed=0):
    """Yield (samples_float64 [-1,1], label) for subset in {training,testing,validation}."""
    testing = _load_list(root, "testing_list.txt")
    validation = _load_list(root, "validation_list.txt")
    labels = sorted(d for d in os.listdir(root)
                    if os.path.isdir(os.path.join(root, d)) and d != "_background_noise_")
    items = []
    for label in labels:
        ldir = os.path.join(root, label)
        for fn in os.listdir(ldir):
            if not fn.endswith(".wav"):
                continue
            rel = f"{label}/{fn}"
            in_test = rel in testing
            in_val = rel in validation
            if subset == "training" and (in_test or in_val):
                continue
            if subset == "testing" and not in_test:
                continue
            if subset == "validation" and not in_val:
                continue
            items.append((os.path.join(ldir, fn), label))
    rng = np.random.RandomState(shuffle_seed)
    rng.shuffle(items)
    for path, label in items:
        try:
            sr, data = wavfile.read(path)
        except Exception:
            continue
        if data.dtype == np.int16:
            x = data.astype(np.float64) / 32768.0
        else:
            x = data.astype(np.float64)
            if np.max(np.abs(x)) > 1.0:
                x = x / 32768.0
        if x.ndim > 1:
            x = x[:, 0]
        yield x, label
