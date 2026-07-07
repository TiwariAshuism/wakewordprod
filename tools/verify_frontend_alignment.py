#!/usr/bin/env python3
"""Prove tools/aura_frontend.py (numpy, used for training) matches the on-device C++
front-end (dump_frontend). Feeds the same WAV through both and reports max abs diff
per log-Mel value. This is the M3-risk alignment gate: the model is trained on numpy
features, so they must equal what core/features produces at inference."""
import subprocess
import sys
import numpy as np
import aura_frontend as fe
import wave

WAV = "benchmarks/corpus/positive/marvin_clean_en_us_001.wav"
DUMP = sys.argv[1] if len(sys.argv) > 1 else None  # path to compiled dump_frontend exe


def read_wav(path):
    with wave.open(path, "rb") as w:
        n = w.getnframes()
        raw = w.readframes(n)
    x = np.frombuffer(raw, dtype="<i2").astype(np.float64) / 32768.0
    return x


def main():
    if not DUMP:
        print("usage: verify_frontend_alignment.py <dump_frontend_exe>", file=sys.stderr)
        return 2
    # C++ frames
    out = subprocess.run([DUMP, WAV], capture_output=True, text=True, check=True)
    cpp = np.array([[float(v) for v in line.split(",")]
                    for line in out.stdout.strip().splitlines()], dtype=np.float64)
    # numpy frames (DSP + log-Mel, no pad/truncate — raw streaming)
    x = read_wav(WAV)
    npy = fe.log_mel(fe.apply_dsp(x)).astype(np.float64)

    n = min(len(cpp), len(npy))
    cpp, npy = cpp[:n], npy[:n]
    diff = np.abs(cpp - npy)
    print(f"frames: cpp={len(out.stdout.strip().splitlines())} numpy={len(npy)} compared={n}")
    print(f"max abs diff  = {diff.max():.5f}")
    print(f"mean abs diff = {diff.mean():.5f}")
    ok = diff.max() < 0.05
    print("ALIGNMENT:", "OK (numpy == C++ within tol)" if ok else "MISMATCH")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
