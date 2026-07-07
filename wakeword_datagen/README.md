# wakeword_datagen — Multi-Engine "hey aura" Data-Generation Suite

> **Active wake word: "hey aura"** (superseded the earlier "hey m"). The pipeline, engines,
> filename grammar and `heym_data`-style parsing are unchanged; only the target phrase moved.
> Staged into `dataset/hey_aura/` (loader: `tools/heyaura_data.py`, a one-line ROOT tweak
> over `tools/heym_data.py`).
>
> **Final generated counts (on disk, staged to `dataset/hey_aura/`):**
> **1 209 positives + 7 372 negatives = 8 581 clips** (~140.6 min / 2.34 h of audio).
> Per engine: espeak 8 292 · sapi 222 · gtts 60 · piper 7 (all four engines functional).
> **Augmentation multiplier used: aug-k = 4 (×5 = 1 clean + 4 `-aug*` variants)** — applied
> to the piper subset in this run; the espeak/sapi/gtts bulk is still clean and can be topped
> up by re-running the augmentation pass.

Master guide for generating synthetic wake-word training audio for the **"hey aura"** model.
This suite renders the wake word and its confusable near-misses through **multiple TTS
engines × accents × speeds × pitches**, then runs every clip through the *same*
augmentation front-end used at training time. Output is drop-in compatible with
`tools/heym_data.py` / `tools/heym_train.py`.

> **Read this first — the honest caveat (see §6):** synthetic TTS alone is **not enough**
> to ship a wake-word model. It is for **bootstrapping** and **hard-negative coverage**.
> It **must** be mixed with **real recordings** of the target user's voice through the real
> mic/channel, or the model will fail on real audio (the *synthetic-to-real gap*).

---

## 1. What this folder is + structure

A self-contained, idempotent, gracefully-degrading generator. Every engine writes
16 kHz mono int16 WAV into `output/{positives,negatives}` with filenames that
`tools/heym_data.py` can parse (`{accent}_{engine}-{voice}_tts_{phrase}_{variant}.wav`;
negatives are prefixed `neg_`). Re-running skips files already on disk.

```
wakeword_datagen/
├── README.md              ← this file
├── BEST_PRACTICES.md      ← sourced KWS data recipe (ratios, hard negatives, the gap)
├── MIC_RECOMMENDATION.md  ← USB-C mic pick for real-audio capture on Android
├── run_all.py             ← orchestrator: runs every engine + augmentation, prints counts
├── genlib.py              ← shared helpers (paths, ffmpeg→16k, WAV I/O, phrase loading)
├── augment.py             ← augmentation pass (reuses tools/aura_augment.py)
├── phrases.json           ← phrase lists + accent/speed/pitch grids
├── generators/
│   ├── gen_espeak.py      ← espeak-ng   (classic / NON-AI)
│   ├── gen_sapi.py        ← Windows SAPI (classic / NON-AI, via pyttsx3)
│   ├── gen_gtts.py        ← Google TTS  (AI / neural, online)
│   └── gen_piper.py       ← Piper       (AI / neural, offline)
├── models/piper/          ← auto-downloaded Piper ONNX voices (lessac en-US, alan en-GB)
├── noise/                 ← (optional local noise; augmentation also uses SpeechCommands)
└── output/
    ├── positives/         ← label 1  ("hey m" and its spelling variants)
    └── negatives/         ← label 0  (hard-negative confusables + generic speech)
```

Companion tool (writes straight into `dataset/hey_m/`, not `output/`):
`tools/sarvam_tts_gen.py` — **Sarvam AI (Bulbul)** neural TTS for Indian-language accent gaps
(Marathi, Bengali, Hinglish, Malayalam/Tamil/Telugu/Kannada). India-only; cannot make
en-US/en-GB/en-AU. Run separately with an API key.

---

## 2. The TTS engines — AI (neural) vs without-AI (classic)

The suite deliberately mixes **two fundamentally different classes of synthesizer**. This
is not redundancy — each class leaves a different acoustic fingerprint, and training across
both prevents the model from overfitting to any one vocoder's artifacts (a documented
KWS pitfall — see BEST_PRACTICES.md §3, "single-TTS-engine overfitting").

### Without AI — classic / rule-based synthesis
| Engine | File | How it works | Acoustic character |
|---|---|---|---|
| **espeak-ng** | `gen_espeak.py` | **Formant synthesis** — rules generate formants directly, no training data, no neural net. | Buzzy, robotic, extremely controllable. Huge accent + pitch + rate range for near-zero cost. The workhorse of this suite. |
| **Windows SAPI** | `gen_sapi.py` | **Concatenative / classic** Microsoft voices (David, Zira, Hazel…) via `pyttsx3`. | Older-generation, "assistant-ish" timbre distinct from both espeak and neural voices. |

### With AI — neural TTS
| Engine | File | How it works | Acoustic character |
|---|---|---|---|
| **Piper** | `gen_piper.py` | **Neural (VITS)**, runs **offline** from downloaded ONNX voices. | Natural, human-like prosody. Offline = unlimited free volume. |
| **gTTS** | `gen_gtts.py` | **Google's neural TTS**, **online** (one MP3 per phrase; speed variants derived locally via ffmpeg). | Very natural, Google-voice timbre. Rate-limited/network-bound. |
| **Sarvam** (separate) | `tools/sarvam_tts_gen.py` | **Neural (Bulbul)**, Indian-language voices. | Fills Indic accent gaps. India-only. |

**Why mix both classes:** neural engines give realism (prosody, coarticulation) but a
narrow set of voice "fingerprints"; classic engines give cheap, massive coverage of pitch,
speed, and accent axes with a totally different spectral signature. A model trained on the
union learns the *word*, not a synthesizer. Classic espeak also cheaply produces the exotic
Indic accents (`hi, ta, te, bn, mr`) that anchor the confusable space for "hey m".

---

## 3. How to generate (`run_all.py` + flags)

`run_all.py` runs **all four `output/` engines** (espeak → sapi → gtts → piper), then the
augmentation pass, and prints a per-engine WAV count. It requires **ffmpeg on PATH** (every
engine converts to 16 kHz through it) and is fully **idempotent** — safe to re-run; it only
fills in missing files.

```bash
# Full generation + augmentation (the real run)
python wakeword_datagen/run_all.py

# SMOKE TEST — <=3 new clips per engine per category, tiny augmentation
python wakeword_datagen/run_all.py --limit 3

# Generators only, skip augmentation
python wakeword_datagen/run_all.py --no-augment

# More augmented variants per clean clip (default aug_k = 2)
python wakeword_datagen/run_all.py --aug-k 4

# Cap clips fed to augmentation (smoke)
python wakeword_datagen/run_all.py --aug-limit 100
```

| Flag | Default | Effect |
|---|---|---|
| `--limit N` | none (all) | Max **new** clips per engine per category. Use for smoke tests. |
| `--no-augment` | off | Run TTS engines only; skip the augmentation pass. |
| `--aug-k K` | `2` | Augmented variants generated per clean clip. |
| `--aug-limit N` | = `--limit` | Cap clean clips fed into augmentation. |

Engines can also be run individually, e.g. `python generators/gen_espeak.py --limit 5`.
A missing/broken engine (no espeak binary, gTTS offline, Piper download fails, non-Windows
SAPI) is **logged and skipped** — the rest continue.

**Augmentation** (`augment.py`) reuses `tools/aura_augment.py` so the augmentation *matches
the training front-end exactly*: additive background noise on an **SNR curriculum
{20, 10, 5, 0} dB**, synthetic far-field reverb, speed perturbation, gain jitter, time-shift.
Noise is drawn from the SpeechCommands `_background_noise_` corpus if present, else
synthesized white/pink/brown noise. Each clean clip yields K variants tagged `-aug{n}`
(so they are never re-augmented). Seeded and reproducible.

---

## 4. The variant matrix produced

Every engine sweeps its own grid (from `phrases.json`) over **7 positive phrases** and
**22 negative phrases** (12 hard-negative confusables + 10 generic negatives).

- **Positives:** `hey m, hey em, heyy m, hai m, hey mm, hey. m, he m` (spelling variants
  that steer each synthesizer's pronunciation toward the target).
- **Hard negatives:** `hello, mango, hello mango, hey man, hey ma, hey mom, hey am, hey Sam,
  hey ma'am, hey there, a m, hey n`.
- **Generic negatives:** `okay google, good morning, what time is it, turn on the light,
  play music, yes, no, stop, how are you, thank you`.

### Clean-clip grid per engine
| Engine | Grid | Per phrase | Positives (×7) | Negatives (×22) |
|---|---|---|---|---|
| **espeak** | 9 accents × 3 pitches (35/50/65) × 3 wpm (130/160/190) = 81 | 81 | **567** | **1 782** |
| **gtts** | 7 accents × 3 speeds (0.85/1.0/1.15) = 21 | 21 | **147** | **462** |
| **piper** | 2 voices × 3 speeds = 6 | 6 | **42** | **132** |
| **sapi** | (installed voices V) × 3 rates (150/200/250) | 3V | **21V** | **66V** |

**Accent axes** — espeak: `en-us, en-gb, en-gb-x-rp, en-gb-scotland, hi, ta, te, bn, mr`;
gtts: `en/US, en/UK, en/IN, en/AU, hi, ta, te`; piper: `en-US (lessac), en-GB (alan)`;
sapi: inferred from each installed Windows voice.

### Augmentation multiplier
With `--aug-k K`, total files = clean × (1 + K). Default `K=2` → **×3**; standalone
`augment.py` default `K=4` → **×5**.

### Full-run scale (clean, before augmentation)
espeak 2 349 + gtts 609 + piper 174 + sapi (~63 pos / ~198 neg at 3 voices) ≈ **3 100–3 400
clean clips**, i.e. roughly **~9–10k** after default `aug-k=2`.

### Actual on-disk snapshot (generation in progress)
As of the last check the full run was **still generating** (espeak done first — it is by far
the largest grid — with gtts/piper/sapi and the augmentation pass still to complete):

| | positives | negatives |
|---|---|---|
| espeak (clean) | ~492 | ~979 |
| gtts / piper / sapi | trickling in | trickling in |
| augmented (`-aug*`) | just starting | just starting |
| **on disk total** | **~507** | **~991** |

The earlier `--limit 3` smoke test passed end-to-end (real 16 kHz mono int16 WAVs in both
folders; 24 positives / 18 negatives after augmentation) and a second run made 0 / skipped
all → **idempotency confirmed**. Re-run `run_all.py` any time to top up to the full matrix.

---

## 5. How to feed it into training

The filenames are **`heym_data`-compatible** by construction, so placing them is a copy:

```bash
# Copy generated clips into the training dataset
cp wakeword_datagen/output/positives/* dataset/hey_m/positives/
cp wakeword_datagen/output/negatives/* dataset/hey_m/negatives/

# (optional) sanity-check what the loader now sees — pos/neg/speaker/accent counts
python tools/heym_data.py

# Retrain the wake-word model (speaker-independent split)
python tools/heym_train.py
```

Notes:
- `heym_data.py` splits on `_`: **field 0 = accent**, **field 1 = engine-voice ("speaker")**.
  The generator slugifies every field with hyphens so `_` is only ever the delimiter.
- The split is **speaker-independent** — held-out speakers (`vijay, ritu, rohan`) form the
  test set, so FA/FR are always measured on **unseen voices**. All synthetic clips are
  "speakers" the test set never contains, so they land in **train only** — exactly right:
  **train on synthetic, evaluate on real.**
- `heym_train.py` already augments the **hard negatives most** (they are FA-critical for a
  short, confusable word), on top of this suite's augmentation.

---

## 6. CRITICAL honest caveat — synthetic TTS is NOT enough

From **BEST_PRACTICES.md** (fully sourced there):

- **Pure-synthetic training under-performs on real microphones.** TTS is too clean and too
  uniform in prosody, channel, and noise. This *synthetic-to-real gap* is a distribution
  shift, not just a noise level.
- **Amazon (ICASSP 2021):** carefully **mixing TTS with real human speech** gave the best
  single-keyword detection — cutting DET-curve AUC by **>11%** vs baseline. The lesson is
  **mix, don't replace.**
- **"hey m" is only ~3 phonemes** — intrinsically confusable with "hey", "hey man", "hey
  mom", "aim", "ma'am", "hey Em". For this word, **hard negatives + real enrollment audio
  are the single most important part of the recipe**, not the synthetic positives.

**So use this suite for what it is good at:**
1. **Bootstrapping** — get a first model off the ground before you have thousands of human
   recordings.
2. **Hard-negative coverage** — cheaply enumerate and render the huge confusable space
   ("hey man/mom/ma'am/Sam", "mango", "aim", bare "hey") that a short wake word demands.

**Then close the gap with real audio you must collect:**
- **1 000–5 000 real "hey m" recordings** (≥ ~20–50 per enrolled user), diverse humans,
  through **real mics and rooms**.
- A **real-speech eval set** (real positives + real confusables + real background) for
  DET/ROC and for setting the operating threshold. **Never tune the threshold on synthetic
  audio.**
- **Continuously mined real false-activations** from staging/shadow logs — the highest-value
  data you can collect post-launch; retrain on it every cycle.

Recommended positives mix: **50k–200k multi-engine/multi-accent synthetic "hey m"** *plus*
**1k–5k real human recordings** — never 100% synthetic. Hard negatives: **50k–150k synthetic
confusables at ~1:1 with positives**, plus continuously-mined real false-activations.

---

## 7. See also

- **`BEST_PRACTICES.md`** — the full, sourced KWS data recipe: positive/negative ratios,
  hard-negative construction (GraphemeAug, LLM-Synth4KWS), the augmentation chain, speaker/
  accent diversity, and the target data recipe for "hey m".
- **`MIC_RECOMMENDATION.md`** — which USB-C mic to buy for capturing the **real** audio that
  §6 says you cannot skip, on Android, without baking in black-box DSP that would create a
  train/inference mismatch.

**Mic top pick: RODE VideoMic Me-C (~$79 / ₹6,500)** — a clean cardioid condenser with
native, class-compliant USB-C digital audio that Just Works on Android, giving
lightly-processed (not black-box-DSP'd) speech so real recordings match what the model sees
at inference. Pair it with a cheap (~$15) UAC USB-C lavalier to add "consumer mic" variety —
robustness comes from *diverse* mics, not one perfect one. Capture at 48 kHz, downsample to
16 kHz in software, and keep any hardware AGC/noise-suppression off or constant.

---

## 8. Multi-engine expansion (2026-07-08)

Six additional TTS engines were trialed on top of the original
espeak / gTTS / SAPI / piper set. All clips are 16 kHz mono PCM_16 and were
merged into `dataset/hey_aura/{positives,negatives}`.

**Worked (3 of 6) — 5,878 new clips added:**

| Engine | License | Positives | Negatives | Total |
|---|---|---:|---:|---:|
| piper-sg (`pipergen-libritts`, Rhasspy Piper / LibriTTS) | MIT | 1,500 | 890 | 2,390 |
| Kokoro-82M (`hexgrad/Kokoro-82M`, ran via CPU fallback) | Apache-2.0 | 960 | 2,048 | 3,008 |
| indic-tts (`indictts`, AI4Bharat Indic-TTS) | MIT (AI4Bharat) | 60 | 420 | 480 |

**Failed (3 of 6) — 0 clips:**

| Engine | License | Reason |
|---|---|---|
| Parler-TTS | Apache-2.0 | Engine installed/ran, but no model weights obtained → 0 clips |
| Bark (Suno) | MIT | Torch install did not finish in time → generation not reached |
| IndicF5 (AI4Bharat) | CC-BY-4.0 (gated) | Install worked, model download blocked by HF gating → 0 clips |

Kokoro adds strong multi-accent English (af/am/bf/bm/hf/hm voice families) and
piper-sg contributes the bulk of the `en-us` positives; indic-tts adds native
Hindi coverage. Parler / Bark / IndicF5 can be revisited once weights are
obtained (Bark just needs the torch build to complete; IndicF5 needs HF gated-repo access).
