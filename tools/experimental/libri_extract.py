#!/usr/bin/env python3
"""Extract isolated keyword clips from LibriSpeech (OpenSLR 12) via forced alignment, to
build a real-speech KWS dataset for validating the AURA engine.

Uses torchaudio's MMS_FA CTC forced aligner to get word-level timestamps in each utterance,
then cuts the target word (padded to ~1 s, 16 kHz mono) as a positive, and other words as
negatives. Filenames encode the LibriSpeech speaker id (spk{ID}_...) so training can do a
strict speaker-independent split.

Usage:
  python tools/libri_extract.py                      # auto-pick the best frequent word
  python tools/libri_extract.py --word something --max-pos 2500 --max-neg 7500
"""
import argparse
import collections
import os
import re
import sys

import numpy as np
import torch

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", ".data", "LibriSpeech")
OUT_ROOT = os.path.join(HERE, "..", "dataset")
SR = 16000
CLIP = SR  # ~1 s
PAD = int(0.12 * SR)

# ~3+ syllable distinctive candidates (auto-pick chooses the most frequent that qualifies)
CANDIDATES = ["something", "everything", "beautiful", "wonderful", "together", "remember",
              "important", "morning", "children", "himself", "without", "general", "family",
              "another", "however", "national", "afternoon", "different", "certainly"]


def iter_utts(splits):
    for sp in splits:
        root = os.path.join(DATA, sp)
        if not os.path.isdir(root):
            continue
        for spk in os.listdir(root):
            spdir = os.path.join(root, spk)
            if not os.path.isdir(spdir):
                continue
            for ch in os.listdir(spdir):
                chdir = os.path.join(spdir, ch)
                trans = os.path.join(chdir, f"{spk}-{ch}.trans.txt")
                if not os.path.isfile(trans):
                    continue
                for line in open(trans, encoding="utf-8"):
                    uid, _, text = line.strip().partition(" ")
                    flac = os.path.join(chdir, uid + ".flac")
                    if os.path.isfile(flac):
                        yield spk, flac, text.lower()


def pick_word(splits):
    freq = collections.Counter()
    spk = collections.defaultdict(set)
    for s, _, text in iter_utts(splits):
        for w in set(re.findall(r"[a-z]+", text)):
            if w in CANDIDATES:
                freq[w] += 1
                spk[w].add(s)
    ranked = sorted(CANDIDATES, key=lambda w: (len(spk[w]) >= 100, freq[w]), reverse=True)
    best = ranked[0]
    print("word frequencies (utts / speakers):",
          {w: (freq[w], len(spk[w])) for w in ranked[:6]})
    return best


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--word", default=None)
    ap.add_argument("--splits", nargs="+", default=["train-clean-100", "dev-clean", "test-clean"])
    ap.add_argument("--max-pos", type=int, default=2500)
    ap.add_argument("--max-neg", type=int, default=7500)
    ap.add_argument("--max-utts", type=int, default=4000, help="cap utterances aligned (CPU time)")
    args = ap.parse_args()
    import torchaudio

    splits = [s for s in args.splits if os.path.isdir(os.path.join(DATA, s))]
    print("splits present:", splits)
    word = args.word or pick_word(splits)
    print("target keyword:", word)

    bundle = torchaudio.pipelines.MMS_FA
    model = bundle.get_model()
    tokenizer = bundle.get_tokenizer()
    aligner = bundle.get_aligner()
    dict_ = bundle.get_dict()

    def clean(w):
        return "".join(c for c in w if c in dict_)

    outp = os.path.join(OUT_ROOT, f"libri_{word}")
    pos_dir = os.path.join(outp, "positives"); neg_dir = os.path.join(outp, "negatives")
    os.makedirs(pos_dir, exist_ok=True); os.makedirs(neg_dir, exist_ok=True)

    npos = nneg = naligned = 0
    pos_spk = set()
    # gather utterances that contain the word first (positives), interleave to spread speakers
    utts = [(s, f, t) for (s, f, t) in iter_utts(splits) if word in re.findall(r"[a-z]+", t)]
    print(f"utterances containing '{word}': {len(utts)}")
    for spk, flac, text in utts:
        if npos >= args.max_pos or naligned >= args.max_utts:
            break
        words = [clean(w) for w in re.findall(r"[a-z]+", text)]
        words = [w for w in words if w]
        if word not in words:
            continue
        try:
            import soundfile as sf
            data, sr = sf.read(flac, dtype="float32")  # torchaudio.load needs torchcodec in 2.11
            if data.ndim > 1:
                data = data[:, 0]
            wav = torch.from_numpy(data).unsqueeze(0)
            if sr != SR:
                wav = torchaudio.functional.resample(wav, sr, SR)
            with torch.inference_mode():
                emission, _ = model(wav)
            spans = aligner(emission[0], tokenizer(words))
        except Exception:
            continue
        naligned += 1
        ratio = wav.size(1) / emission.size(1)
        x = wav[0].numpy()
        for i, w in enumerate(words):
            fs = int(spans[i][0].start * ratio); fe = int(spans[i][-1].end * ratio)
            seg = _center_clip(x, fs, fe)
            if w == word and npos < args.max_pos:
                _save(os.path.join(pos_dir, f"spk{spk}_libri_{word}_{npos}.wav"), seg)
                npos += 1; pos_spk.add(spk)
            elif w != word and nneg < args.max_neg and (nneg % 3 == 0):
                _save(os.path.join(neg_dir, f"neg_spk{spk}_libri_{w}_{nneg}.wav"), seg)
                nneg += 1
        if naligned % 200 == 0:
            print(f"  aligned {naligned} utts -> pos {npos} neg {nneg} spk {len(pos_spk)}")
    print(f"DONE word={word} pos={npos} neg={nneg} pos_speakers={len(pos_spk)} -> {outp}")


def _center_clip(x, fs, fe):
    fs = max(0, fs - PAD); fe = min(len(x), fe + PAD)
    seg = x[fs:fe]
    if len(seg) >= CLIP:
        off = (len(seg) - CLIP) // 2
        return seg[off:off + CLIP]
    out = np.zeros(CLIP, np.float32); out[:len(seg)] = seg
    return out


def _save(path, seg):
    from scipy.io import wavfile
    wavfile.write(path, SR, (np.clip(seg, -1, 1) * 32767).astype(np.int16))


if __name__ == "__main__":
    sys.exit(main())
