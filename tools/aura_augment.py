#!/usr/bin/env python3
"""Waveform-domain augmentation for AURA KWS training robustness. Applied BEFORE
tools/aura_frontend.py features(), so it never touches the on-device front-end
(alignment preserved). Seeded/reproducible.

Augmentations (each applied with a probability): speed perturbation (Ko et al.), gain
jitter, time-shift, synthetic-RIR reverb (far-field), and additive background-noise mixing
at an SNR curriculum. SpecAugment is applied online in the training loop (see
tools/aura_train.py), not here.
"""
import os
import numpy as np
from scipy import signal

SR = 16000


def load_background_noise(root):
    """Load the _background_noise_ clips (long float arrays) for mixing + a silence class."""
    from scipy.io import wavfile
    nd = os.path.join(root, "_background_noise_")
    noises = []
    if not os.path.isdir(nd):
        return noises
    for fn in sorted(os.listdir(nd)):
        if not fn.endswith(".wav"):
            continue
        try:
            _, data = wavfile.read(os.path.join(nd, fn))
        except Exception:
            continue
        x = data.astype(np.float64)
        if x.dtype != np.float64:
            x = x.astype(np.float64)
        if np.max(np.abs(x)) > 1.0:
            x = x / 32768.0
        noises.append(x)
    return noises


def make_rir(rng, sr=SR, rt60=None):
    """Synthetic exponential-decay room impulse response (no external RIR corpus needed)."""
    if rt60 is None:
        rt60 = rng.uniform(0.15, 0.5)  # seconds
    n = int(rt60 * sr)
    if n < 8:
        n = 8
    t = np.arange(n)
    decay = np.exp(-6.9078 * t / n)          # ~ -60 dB over rt60
    rir = rng.standard_normal(n) * decay
    rir[0] = 1.0                              # direct path
    rir /= np.sqrt(np.sum(rir * rir)) + 1e-9  # energy-normalize
    return rir


def _mix_noise(x, noise, rng, snr_db):
    if len(noise) < len(x):
        noise = np.tile(noise, int(np.ceil(len(x) / len(noise))))
    off = rng.randint(0, len(noise) - len(x) + 1)
    seg = noise[off:off + len(x)]
    sp = np.mean(x * x) + 1e-12
    npow = np.mean(seg * seg) + 1e-12
    target = sp / (10.0 ** (snr_db / 10.0))
    seg = seg * np.sqrt(target / npow)
    return x + seg


def silence_clip(noises, rng, length=SR):
    """A ~1 s low-level noise clip for the _silence_ class."""
    if not noises:
        return (rng.standard_normal(length) * 0.001)
    noise = noises[rng.randint(len(noises))]
    if len(noise) < length:
        noise = np.tile(noise, int(np.ceil(length / len(noise))))
    off = rng.randint(0, len(noise) - length + 1)
    seg = noise[off:off + length].copy()
    return seg * rng.uniform(0.05, 0.5)  # attenuated background => "silence/ambient"


def augment(x, noises, rng, snr_choices=(20, 15, 10, 5, 0)):
    """Apply a random subset of waveform augmentations. Length may change (features() pads)."""
    x = np.asarray(x, dtype=np.float64).copy()
    # speed perturbation (resample; changes speed+pitch, standard Ko et al.)
    if rng.random() < 0.5:
        factor = rng.uniform(0.85, 1.15)
        new_len = max(8, int(len(x) / factor))
        x = signal.resample(x, new_len)
    # reverb (far-field)
    if rng.random() < 0.4:
        rir = make_rir(rng)
        x = signal.fftconvolve(x, rir)[:len(x) if len(x) else 1]
    # gain jitter
    if rng.random() < 0.7:
        x = np.clip(x * rng.uniform(0.4, 1.6), -1.0, 1.0)
    # time-shift within a ~1 s frame
    if rng.random() < 0.5:
        shift = rng.randint(-int(0.1 * SR), int(0.1 * SR) + 1)
        x = np.roll(x, shift)
        if shift > 0:
            x[:shift] = 0.0
        elif shift < 0:
            x[shift:] = 0.0
    # additive background noise at a curriculum SNR
    if noises and rng.random() < 0.8:
        snr = float(snr_choices[rng.randint(len(snr_choices))])
        x = _mix_noise(x, noises[rng.randint(len(noises))], rng, snr)
    return np.clip(x, -1.0, 1.0)


def spec_augment(feat, rng, n_time=2, n_freq=2, max_time=12, max_freq=6):
    """Online SpecAugment on a single [T, n_mels] numpy log-Mel frame-stack (train only)."""
    feat = feat.copy()
    T, M = feat.shape
    fill = np.log(1e-6)
    for _ in range(n_time):
        w = rng.randint(0, max_time + 1)
        if w and T - w > 0:
            s = rng.randint(0, T - w)
            feat[s:s + w, :] = fill
    for _ in range(n_freq):
        w = rng.randint(0, max_freq + 1)
        if w and M - w > 0:
            s = rng.randint(0, M - w)
            feat[:, s:s + w] = fill
    return feat
