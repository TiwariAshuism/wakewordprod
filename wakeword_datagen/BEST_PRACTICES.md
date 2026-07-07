# Wake-Word / KWS Training-Data Best Practices — "hey m"

Actionable, sourced guidance for building a production custom-wake-word dataset. Target model: **"hey m"**.

---

## 0. Design caveat for "hey m" (read first)

"hey m" is **phonetically very short** (~3 phonemes: /h eɪ ɛ m/). Picovoice explicitly warns that a good wake word should contain **at least ~6 phonemes and diverse sounds**; short phrases have poor discriminability and high false-accept rates because there is little acoustic material to separate them from ordinary speech. See [Picovoice — Creating a Custom Wake Word](https://picovoice.ai/blog/console-tutorial-custom-wake-word/) and [Porcupine FAQ](https://picovoice.ai/docs/faq/porcupine/).

**Implication:** "hey m" will be intrinsically confusable with "hey", "hey man", "hey Em/M", "hey mom", "hey Amy", "aim", "ma'am", etc. **Hard negatives are not optional here — they are the single most important part of the recipe.** If product allows, prefer a longer phrase (e.g. "hey Milo"); if "hey m" is fixed, over-invest in hard negatives and per-user/real enrollment audio.

---

## 1. Positives vs negatives — how much of each

Real production pipelines are **massively negative-heavy**. The deployment reality is that the wake word is spoken a few times a day but the mic hears hours of non-wake speech, so the training distribution must reflect that.

- **openWakeWord** ("hey jarvis" reference model): **~200,000 synthetic positive clips** vs **~31,000 hours of negatives** (ACAV100M noise/music/speech, Common Voice, podcasts, Free Music Archive, plus reverberated copies and adversarial near-miss synthetics). Source: [openWakeWord hey_jarvis model card](https://github.com/dscripka/openWakeWord/blob/main/docs/models/hey_jarvis.md).
- The negative pool dwarfs positives by **orders of magnitude in duration**. Do not aim for a "balanced" 1:1 set — that under-represents the false-accept surface and yields a trigger-happy model.
- Class imbalance during optimization is handled by **loss weighting / sampling**, not by shrinking the negative corpus.

**Rule of thumb:** thousands–hundreds-of-thousands of positive clips; **hundreds to thousands of hours** of general negatives; and a dedicated, curated hard-negative set (below).

---

## 2. Hard negatives (confusables) — the highest-leverage component

Hard negatives are utterances **acoustically close to the wake word but that must NOT trigger** (e.g. for "hey m": "hey man", "hey mom", "mango", "hey Amy", "ma'am", "aim", "hey", "Emma"). Without them the model learns a lazy boundary and fires on near-misses.

- Google/DeepMind's **GraphemeAug** (Interspeech 2025) systematically synthesizes hard negatives by grapheme-level edits (insert/delete/substitute) of the wake phrase, then TTS-renders them. Result: large **false-accept reductions** while holding the true-accept rate roughly constant, and it composes with standard augmentation. Best results come from **mixing synthetic hard negatives with real ones** — synthetics complement, don't replace, real data. Source: [GraphemeAug, arXiv 2505.14814](https://arxiv.org/pdf/2505.14814) / [ISCA archive](https://www.isca-archive.org/interspeech_2025/zhang25h_interspeech.pdf).
- **LLM-Synth4KWS** (Interspeech 2025) uses an LLM to enumerate confusable phrases, then multi-speaker TTS to render them — a scalable recipe for the confusable set. Source: [arXiv 2505.22995](https://arxiv.org/pdf/2505.22995).
- openWakeWord bakes in **adversarial phonetically-similar synthetics** (e.g. "hey jealous" for "hey jarvis") and a second-stage **verifier** trained on manually collected false-activations. Source: [hey_jarvis model card](https://github.com/dscripka/openWakeWord/blob/main/docs/models/hey_jarvis.md).

**Construction recipe for "hey m" hard negatives:**
1. Generate confusables by edit-distance/grapheme edits and phonetic neighbors: `hey man, hey men, hey mom, hey ma, hey Em, hey Amy, hey Emma, hey hem, hey / hey you, hey now, mango, ma'am, aim, name, they, may, embed…`
2. Render each via **many TTS voices** (multi-speaker/multi-accent) with the same augmentation as positives.
3. **Mine real false activations** from live/staging logs and shadow deployments; feed them back every retrain (hard-negative mining loop). This is the most valuable data you can collect post-launch.

---

## 3. Synthetic TTS data — effective, but mind the synthetic-to-real gap

Synthetic TTS is the standard way to bootstrap KWS when you can't record thousands of humans saying "hey m", and it works — but **pure-synthetic training under-performs on real microphones** (the *synthetic-to-real gap*: TTS is too clean/uniform in prosody, channel, and noise).

- Amazon (Werchniak et al., **ICASSP 2021**): **carefully mixing TTS audio with real human speech** gave the best single-keyword detection, cutting DET-curve AUC by **>11%** vs baseline. Takeaway: **mix, don't replace**. Source: [Amazon Science — Exploring the application of synthetic audio in training keyword spotters](https://www.amazon.science/publications/exploring-the-application-of-synthetic-audio-in-training-keyword-spotters).
- openWakeWord trains positives from **100% synthetic** but only works because of **heavy augmentation (RIR reverb + noise mixing)** to close the realism gap, plus enormous real negative corpora. Source: [hey_jarvis model card](https://github.com/dscripka/openWakeWord/blob/main/docs/models/hey_jarvis.md).
- The gap is well-documented across speech tasks and is a distributional shift, not just noise. Source: [Task Arithmetic can Mitigate Synthetic-to-Real Gap in ASR, arXiv 2406.02925](https://arxiv.org/pdf/2406.02925).

**Pitfalls to avoid:**
- **Single-TTS-engine overfitting** — the model learns the vocoder's fingerprint, not the word. Use **multiple TTS engines + many speaker embeddings + embedding mixtures** to invent novel voices (openWakeWord uses NVIDIA WaveGlow/LibriTTS **and** VITS/VCTK).
- **Too-clean audio** — always pass synthetics through the real-world augmentation chain (§4).
- **No real speech at all** — collect at least a **real enrollment/eval set** of humans saying "hey m" (see §6). Even 20–50 real samples per user materially improves detection per openWakeWord guidance.

---

## 4. Augmentation chain (apply to positives AND hard negatives)

Grounded in openWakeWord's pipeline and standard KWS practice:

| Augmentation | Setting / curriculum | Source |
|---|---|---|
| **Additive noise (SNR curriculum)** | Mix speech/music/noise at **0 to 20 dB SNR**; sample across the range so the model sees clean → very noisy. Sources: FSD50k, ACAV100M, Free Music Archive, DEMAND, MUSAN. | [openWakeWord model card](https://github.com/dscripka/openWakeWord/blob/main/docs/models/hey_jarvis.md) |
| **Reverberation (RIR)** | Convolve with **simulated + real room impulse responses** (openWakeWord uses BIRD; MIT/SLR28 RIRs also common). | [openWakeWord model card](https://github.com/dscripka/openWakeWord/blob/main/docs/models/hey_jarvis.md) |
| **SpecAugment** | Time + frequency masking on the mel/log-mel features: **F=10 (freq mask), T=50 (time mask), 2 masks each**. | [SpecAugment, arXiv 1904.08779](https://arxiv.org/abs/1904.08779); KWS usage per survey results |
| **Speed / tempo & pitch** | ±5–15% speed perturbation and small pitch shifts to cover speaking-rate and vocal-tract variation. | Standard ASR/KWS augmentation (Ko et al., speed perturbation) |
| **Gain / volume** | Random gain to simulate distance-from-mic and AGC. | openWakeWord pipeline |
| **Channel / codec** (optional) | Band-limiting, device mic IRs, µ-law/Opus round-trips to match target hardware. | Deployment-matching practice |

Guidance: **apply augmentation on-the-fly per epoch** (fresh noise/RIR/SpecAugment draw each time) so the model never memorizes a fixed augmented copy — GraphemeAug makes the same point for regenerating negatives each epoch.

---

## 5. Speaker / accent diversity

KWS must generalize across accent, gender, age, pitch, and stress. Bake diversity into both synthetic and real data.

- **Multi-speaker, multi-accent TTS**: use many speaker embeddings and mixtures across engines (LibriTTS, VCTK cover diverse English speakers/accents). [openWakeWord model card](https://github.com/dscripka/openWakeWord/blob/main/docs/models/hey_jarvis.md).
- **Real diversity anchor**: MLCommons **Multilingual Spoken Words Corpus** — 23.4M 1-sec keyword clips, 50 languages, thousands of speakers/accents per language — is an explicit resource for building accent-robust KWS and a large real-speech negative/keyword pool. Sources: [MLCommons dataset page](https://mlcommons.org/datasets/multilingual-spoken-words/), [announcement](https://mlcommons.org/2021/12/multilingual-spoken-words-corpus-50-languages-and-over-23-million-audio-keyword-examples/).
- **Common Voice** and podcast corpora supply real, accent-varied negative speech (used directly by openWakeWord).
- Target: cover **male/female/child, ≥5–10 English accent families** (US, UK, Indian, Australian, African, SE-Asian, etc.), across pitch and speaking rate. For "hey m" specifically, oversample accents where the vowel/nasal realization drifts toward confusables.

---

## 6. Target data recipe for "hey m"

A pragmatic production starting point (scale up as false-accept data arrives). Ratios matter more than absolute counts.

### Positives
| Source | Clips | Notes |
|---|---|---|
| Synthetic TTS "hey m" | **50,000–200,000** | **≥3 TTS engines**, hundreds of speaker embeddings + mixtures, multi-accent. On-the-fly aug (§4). |
| **Real "hey m" recordings** | **1,000–5,000** (min ~20–50 per enrolled user) | Diverse humans + real mics/rooms. **Do not skip** — closes synthetic-to-real gap and anchors eval. |

### Hard negatives (confusables) — over-invest for this short word
| Source | Clips | Notes |
|---|---|---|
| Synthetic confusables (grapheme-edit / LLM-enumerated) | **50,000–150,000** | "hey man/mom/ma/Amy/Emma/Em", "mango", "ma'am", "aim", bare "hey", etc. Multi-voice, augmented, regenerated per epoch. |
| **Mined real false-activations** | **grow continuously** | From staging/shadow logs. Highest-value data post-launch; retrain on it every cycle. |

### General (easy) negatives
| Source | Amount | Notes |
|---|---|---|
| General speech (Common Voice, podcasts, MSWC) | **500–3,000+ hours** | Broad accent/language coverage. |
| Noise / music (FSD50k, ACAV100M, FMA, MUSAN) | **500–1,000+ hours** | Also serves as the noise-mixing pool for augmentation. |
| Reverberated copies of the above | derived | Via RIR convolution. |

### Ratios & handling
- **Positives : hard-negatives ≈ 1 : 1** (roughly matched; for a short/confusable word bias toward *more* hard negatives).
- **General negatives ≫ positives** — hundreds-to-thousands of hours vs thousands-to-hundreds-of-thousands of clips; handle imbalance via **loss weighting / negative sub-sampling**, never by shrinking the negative pool.
- **Every positive and hard negative passes the full augmentation chain (§4), redrawn each epoch.**
- Hold out a **real-speech eval set** (real positives + real confusables + real background) for DET/ROC and to set the operating threshold — never tune the threshold on synthetic audio alone.

---

## Sources
- [openWakeWord — "hey jarvis" model card (data recipe, RIR/noise/SNR, adversarial negatives, verifier)](https://github.com/dscripka/openWakeWord/blob/main/docs/models/hey_jarvis.md)
- [openWakeWord repo](https://github.com/dscripka/openWakeWord)
- [Picovoice — Creating a Custom Wake Word](https://picovoice.ai/blog/console-tutorial-custom-wake-word/) · [Porcupine FAQ (phoneme guidance)](https://picovoice.ai/docs/faq/porcupine/)
- [GraphemeAug — synthesized hard negatives (Interspeech 2025), arXiv 2505.14814](https://arxiv.org/pdf/2505.14814) · [ISCA archive](https://www.isca-archive.org/interspeech_2025/zhang25h_interspeech.pdf)
- [LLM-Synth4KWS — confusable data synthesis (Interspeech 2025), arXiv 2505.22995](https://arxiv.org/pdf/2505.22995)
- [Amazon (Werchniak et al., ICASSP 2021) — synthetic audio for keyword spotters (mix TTS+real, >11% DET-AUC gain)](https://www.amazon.science/publications/exploring-the-application-of-synthetic-audio-in-training-keyword-spotters)
- [Task Arithmetic can Mitigate Synthetic-to-Real Gap in ASR, arXiv 2406.02925](https://arxiv.org/pdf/2406.02925)
- [SpecAugment, arXiv 1904.08779](https://arxiv.org/abs/1904.08779)
- [MLCommons Multilingual Spoken Words Corpus](https://mlcommons.org/datasets/multilingual-spoken-words/) · [announcement](https://mlcommons.org/2021/12/multilingual-spoken-words-corpus-50-languages-and-over-23-million-audio-keyword-examples/)
