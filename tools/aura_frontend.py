#!/usr/bin/env python3
"""AURA front-end, ported to numpy to EXACTLY mirror the on-device C++ path.

This is the M3-risk fix (v0 REPORT.md): the model must be trained on the same
features the engine produces at inference. On device the signal flows
capture -> DSP(AGC -> AEC(no-op) -> NS) -> log-Mel, block-streamed in 160-sample
(10 ms) blocks. This module reproduces that byte-for-byte in intent:

  - AGC  mirrors core/dsp/DspChain.cpp AgcStage   (per-block, adaptive gain)
  - NS   mirrors core/dsp/DspChain.cpp NsStage    (1-pole HP + soft noise gate)
  - log-Mel mirrors core/features/LogMelExtractor.cpp
    (Hann-400 symmetric, FFT 512, |X|^2, HTK mel 40 [20,8000], natural log,
     win 400 / hop 160, center=False)

Both tools/train_kws_model.py and tools/verify_kws_host.py import this, so the
trained weights and the host verification use the identical front-end the device
uses. tools/dump_frontend_check verifies numpy≈C++ on a test signal.
"""
import numpy as np

SR = 16000
WIN = 400
HOP = 160
FFT = 512
N_MELS = 40
FMIN = 20.0
FMAX = 8000.0
BLOCK = 160          # capture block used for DSP streaming (config.audio.captureFrames)
WINDOW_FRAMES = 100  # DetectConfig.stage1WindowFrames


def _hann(n):
    i = np.arange(n, dtype=np.float64)
    return 0.5 * (1.0 - np.cos(2.0 * np.pi * i / (n - 1)))  # symmetric, matches C++


_HANN = _hann(WIN)


def _hz_to_mel(hz):
    return 2595.0 * np.log10(1.0 + hz / 700.0)


def _mel_to_hz(mel):
    return 700.0 * (10.0 ** (mel / 2595.0) - 1.0)


def _mel_filterbank():
    n_bins = FFT // 2 + 1
    mel_min, mel_max = _hz_to_mel(FMIN), _hz_to_mel(FMAX)
    edges_hz = _mel_to_hz(mel_min + (mel_max - mel_min) * np.arange(N_MELS + 2) / (N_MELS + 1))
    hz_to_bin = lambda hz: hz * FFT / SR
    fb = np.zeros((N_MELS, n_bins), dtype=np.float64)
    for m in range(N_MELS):
        lo, ctr, hi = hz_to_bin(edges_hz[m]), hz_to_bin(edges_hz[m + 1]), hz_to_bin(edges_hz[m + 2])
        b_lo = max(0, int(np.floor(lo)))
        b_hi = min(n_bins - 1, int(np.ceil(hi)))
        for k in range(b_lo, b_hi + 1):
            w = 0.0
            if lo <= k <= ctr and ctr > lo:
                w = (k - lo) / (ctr - lo)
            elif ctr < k <= hi and hi > ctr:
                w = (hi - k) / (hi - ctr)
            fb[m, k] = max(0.0, w)
    return fb


_FB = _mel_filterbank()


def apply_dsp(x):
    """Block-streamed AGC -> AEC(no-op) -> NS, mirroring DspChain.cpp. Vectorized but
    numerically identical (verified by tools/verify_frontend_alignment.py). State
    evolves across 160-sample blocks exactly as the engine does."""
    from scipy.signal import lfilter
    x = np.asarray(x, dtype=np.float64).copy()
    # --- AGC (per-block adaptive gain; scalar update, vectorized scale) ---
    gain = 1.0
    for start in range(0, len(x), BLOCK):
        blk = x[start:start + BLOCK]
        if blk.size == 0:
            continue
        rms = np.sqrt(np.mean(blk * blk))
        if rms > 1e-5:
            desired = 0.1 / rms
            gain += 0.05 * (desired - gain)
            gain = min(20.0, max(0.1, gain))
        x[start:start + BLOCK] = np.clip(blk * gain, -1.0, 1.0)
    # --- NS 1-pole high-pass: y[n] = 0.97*(y[n-1] + x[n] - x[n-1]) over whole signal
    #     (continuous state == per-block streaming, since the HP is causal/linear) ---
    hp = lfilter([0.97, -0.97], [1.0, -0.97], x)
    # --- NS soft noise gate (per-block, applied to HP output) ---
    noise_floor = 1e-4
    for start in range(0, len(hp), BLOCK):
        blk = hp[start:start + BLOCK]
        if blk.size == 0:
            continue
        rms2 = np.sqrt(np.mean(blk * blk))
        noise_floor += 0.01 * (rms2 - noise_floor)
        if rms2 < noise_floor * 1.5:
            hp[start:start + BLOCK] = blk * 0.5
    return hp


def log_mel(x):
    """Streaming log-Mel (win 400 / hop 160, center=False). Returns [T, 40] float32.
    Vectorized; identical to the per-frame C++ path."""
    x = np.asarray(x, dtype=np.float64)
    if len(x) < WIN:
        return np.zeros((0, N_MELS), dtype=np.float32)
    sw = np.lib.stride_tricks.sliding_window_view(x, WIN)[::HOP]  # [F, 400]
    windowed = sw * _HANN                                          # broadcast Hann
    padded = np.zeros((windowed.shape[0], FFT), dtype=np.float64)
    padded[:, :WIN] = windowed
    spec = np.fft.rfft(padded, n=FFT, axis=1)                      # [F, 257]
    power = spec.real ** 2 + spec.imag ** 2
    mel = power @ _FB.T                                            # [F, 40]
    return np.log(mel + 1e-6).astype(np.float32)


def features(x, apply_dsp_chain=True, frames=WINDOW_FRAMES):
    """Full front-end: (optional DSP) -> log-Mel -> pad/truncate to `frames` -> [frames, 40]."""
    if apply_dsp_chain:
        x = apply_dsp(x)
    m = log_mel(x)  # [T, 40]
    out = np.zeros((frames, N_MELS), dtype=np.float32)
    t = min(len(m), frames)
    if t > 0:
        out[:t] = m[:t]
    if len(m) < frames and len(m) > 0:
        # pad by repeating the log of the noise floor (silence), matching a quiet tail
        out[len(m):] = np.log(1e-6)
    return out  # [frames, 40]
