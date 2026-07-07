# Dataset Card — `dataset/hey_m` ("hey m" wake word)

AURA-collected wake-word corpus for the real **"hey m"** model (`MODEL_CARD.md`). This card is
an honest inventory of what the data is and is not. Loader/inspector: `tools/heym_data.py`
(`python tools/heym_data.py` prints the live split summary).

## Composition
- **Recorded clips:** **2,095 positives / 1,430 negatives.**
- **Synthetic clips:** **28 Sarvam-TTS clips** (22 positive / 6 negative) — see below.
- **On-disk total:** 2,117 positive / 1,436 negative `.wav` files under
  `dataset/hey_m/{positives,negatives}`.
- **Format:** 16 kHz mono int16 PCM (matches the AURA front-end contract).
- **Speakers:** **23 recorded human speakers** (20 in train + 3 held out) plus 3 synthetic TTS
  voices — i.e. 20+ distinct speakers. Filenames encode `accent_speaker_phrase_style`.

## Split — speaker-independent
Speakers `ritu`, `rohan`, `vijay` are held out for test; everyone else is train. Because the
split is by speaker, all evaluation metrics reflect **unseen voices** (the number that matters
for the wake-word gates). Test set: 369 positives / 114 negatives across the 3 held-out speakers.

## Accent / locale tags
Live accent tags (train / test counts, from `tools/heym_data.py`):

| Accent | Train | Test | Notes |
|---|---|---|---|
| en-IN | 1430 | 331 | **Dominant** |
| hi-IN | 319 | 52 | |
| te-IN | 184 | 32 | |
| ta-IN | 151 | 47 | |
| kn-IN | 129 | 21 | |
| ml-IN | 39 | 0 | |
| bn-IN | 9 | 0 | mostly synthetic |
| mr-IN | 9 | 0 | mostly synthetic |
| `prod` / `real` (untagged locale) | 800 | 0 | production/real captures without a locale tag |

**Data is en-IN-dominant.** The four V1 English accents **en-US / en-GB / en-AU are absent**, as
are large samples of mr-IN / bn-IN. Cross-accent robustness for those is unmeasured — closing
this is `MULTILINGUAL_PLAN.md`.

## Negatives (incl. hard negatives)
Negatives combine real captures with a broadened pool used for the FA-reduction round:
- **Hard confusables:** near-miss phrases (e.g. `hey man`, other `hey_*` / phonetically close
  utterances) recorded and then **2× augmented** (noise / reverb / speed).
- **Broad negatives:** Speech-Commands words, ambient noise, hum, TV, and silence buckets.
These exist to push down false accepts and confusable false-fires; see `HEYM_FA_REDUCTION.md`.

## Synthetic clips (Sarvam-TTS) — train-only
- **28 clips** (22 positive / 6 negative), generated with Sarvam TTS across 3 voices
  (`abhilash`, `anushka`, `vidya`).
- **Train-only:** none of the synthetic voices are in the held-out test speaker set, so they do
  **not** contaminate speaker-independent evaluation.
- **Short:** mean ~**0.36 s** (range 0.26–0.57 s) — much shorter than the recorded positives
  (mean ~2.0 s), so they add lexical/pronunciation variety, not realistic timing.
- **India accents only:** bn-IN (7), mr-IN (7), hi-IN (2), ml-IN (2), ta-IN (2), te-IN (2) on the
  positive side. **en-US / en-GB / en-AU are absent** from the synthetic set as well.

## Known limitations / bias
- **en-IN-dominant; V1 English accents (en-US/GB/AU) absent** — the single largest data gap.
- **Small synthetic set** (28 clips, short, India-only) — a variety supplement, not a substitute
  for real multi-accent recordings.
- **No 20+ hour real negative corpus** — the corpus is far too short to *measure* FA/hr at the
  ≤ 0.05 resolution the ship gate needs (media/TV/podcast licensing is the open requirement).
- **No far-field / real-room parity** beyond the augmentation applied to negatives.
- Licensing of any externally-sourced negatives (Speech-Commands is CC-BY-4.0) remains a formal
  review gate before any redistribution.

### References
- `MODEL_CARD.md` — the model trained on this data.
- `HEYM_RESULTS.md` / `HEYM_FA_REDUCTION.md` — how the data was used and evaluated.
- `MULTILINGUAL_PLAN.md` — plan to close the accent/locale gap.
