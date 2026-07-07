#!/usr/bin/env python3
"""Generate the deterministic golden fixture for the AURA v0 pipeline test.

This synthesizes a placeholder "marvin"-like utterance: 0.5 s silence, a ~0.6 s
energetic amplitude-modulated multi-tone burst (stands in for the spoken word),
then 0.5 s silence. It is NOT a real recording of the word "marvin" — it is a
deterministic, reproducible stimulus so the golden test asserts an exact cascade
outcome (Stage 7 §14 / ADR-GoldenTest). Flagged as a placeholder in REPORT.md.

Deterministic: fixed seed, no randomness that varies run to run.
"""
import json
import math
import os
import struct
import wave

SR = 16000
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "benchmarks", "corpus", "positive")
WAV = os.path.join(OUT_DIR, "marvin_clean_en_us_001.wav")
META = os.path.join(OUT_DIR, "marvin_clean_en_us_001.json")


def synth():
    samples = []
    # 0.3 s silence
    samples += [0] * int(0.3 * SR)
    # 1.5 s burst: two formant-like tones, amplitude-modulated, to look speech-ish.
    # Short (30 ms) cosine fades with a flat, sustained high-energy middle so the 1 s
    # detection window fills well within continuous speech AND several inference
    # windows (hop 10 frames) land inside the utterance to satisfy the posterior
    # smoothing (M consecutive windows) — realistic for a spoken keyword.
    n = int(1.5 * SR)
    fade = int(0.03 * SR)
    for i in range(n):
        t = i / SR
        if i < fade:
            env = 0.5 * (1 - math.cos(math.pi * i / fade))
        elif i > n - fade:
            env = 0.5 * (1 - math.cos(math.pi * (n - i) / fade))
        else:
            env = 1.0
        am = 0.7 + 0.3 * math.sin(2 * math.pi * 6.0 * t)            # 6 Hz syllabic AM
        s = (math.sin(2 * math.pi * 320.0 * t) + 0.6 * math.sin(2 * math.pi * 1100.0 * t))
        samples.append(int(max(-1.0, min(1.0, 0.35 * env * am * s)) * 32767))
    # 0.3 s silence
    samples += [0] * int(0.3 * SR)
    return samples


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    samples = synth()
    with wave.open(WAV, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(b"".join(struct.pack("<h", s) for s in samples))
    meta = {
        "expected_outcome": "Confirmed",
        "expected_events": 1,
        "wake_word": "marvin",
        "source": "synthetic-placeholder (tools/gen_golden_fixture.py)",
        "provenance": "generated, NOT a real recording — placeholder stimulus",
        "accent": "n/a (synthetic)",
        "language": "en-US (nominal)",
        "sample_rate": SR,
        "duration_s": round(len(samples) / SR, 3),
        "note": "Placeholder fixture for the v0 vertical slice; replace with a real "
                "labelled recording once the AURA-trained model exists.",
    }
    with open(META, "w") as f:
        json.dump(meta, f, indent=2)
    print(f"wrote {WAV} ({len(samples)} samples) and {META}")


if __name__ == "__main__":
    main()
