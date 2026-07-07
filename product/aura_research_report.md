# PROJECT AURA — Wake-Word Engine State-of-the-Art Research Report
### Phase 1 Deliverable: Literature Review & Competitive Reverse-Engineering Audit

**Status:** Research-only. No architecture decisions made.
**Confidence tagging used throughout:** `[V]` Verified (publicly documented/peer-reviewed), `[EJ]` Engineering Judgment (informed inference from public evidence), `[H]` Hypothesis (unverified, needs prototyping to confirm).

---

## 0. Executive Summary

Wake-word (keyword-spotting, KWS) detection is a mature but still-evolving field sitting at the intersection of classical DSP, streaming deep learning, and severe embedded-systems constraints. The state of the art has converged on a fairly narrow architectural band — small convolutional/depthwise-separable networks (BC-ResNet family) or lightweight streaming attention models, operating on log-Mel features, quantized to INT8, running in well under 1 MB of weights — not because larger models don't help accuracy, but because the deployment envelope (always-on, <5% CPU, <20 MB RAM, battery-constrained) punishes anything larger disproportionately.

The commercial leaders (Alexa, Google, Siri) differentiate less through model novelty and more through **data scale, multi-stage cascades, personalization, and hardware co-design** (dedicated DSP/NPU wake islands). The open-source ecosystem (Porcupine, openWakeWord, microWakeWord, Precise, Snowboy — discontinued) trades some accuracy and robustness for transparency, customizability, and zero licensing cost, but has real gaps: weak far-field performance, limited multilingual support, small/synthetic training sets, and inconsistent production hardening.

**The realistic opportunity for AURA is not a novel model architecture** — BC-ResNet/TCN-based streaming CNNs are already near-optimal for the constraint envelope `[EJ]`. The differentiable opportunities are in: (1) large-scale, well-augmented, permissively-licensed training data (the single biggest lever competitors control that open source lacks), (2) a genuinely cross-platform runtime (ONNX Runtime + XNNPACK/NNAPI/CoreML/TFLite-Micro under one abstraction), (3) a rigorous two-stage cascade + on-device personalization/speaker-verification pipeline, and (4) benchmarking rigor and tooling that the open-source ecosystem currently lacks entirely.

---

## 1. History of Wake-Word Detection — Technology Evolution

### 1.1 Template Matching Era: DTW (Dynamic Time Warping) `[V]`
**Why developed:** Before statistical models were tractable on embedded hardware, KWS was framed as a template-matching problem: record a reference utterance, align a candidate utterance to it by warping the time axis to minimize distance (typically on MFCC frames), and threshold the total warping cost.

**Strengths:** Needs only one or a few enrollment examples; interpretable; no training infrastructure; works with very limited compute.

**Weaknesses:** Poor generalization across speakers/accents/noise; O(N·M) alignment cost per template; brittle thresholding; no shared statistical structure across a large vocabulary.

**Why replaced:** Once enough labeled data and cheap-enough compute existed, statistical models (HMMs) modeled the *distribution* of acoustic variation instead of comparing to fixed templates, which generalizes far better.

### 1.2 Statistical Era: GMM-HMM `[V]`
**Why developed:** Speech is a sequential process with rich intra-class variability (speaker, rate, noise). Hidden Markov Models capture the temporal/state structure (phoneme sequences), while Gaussian Mixture Models capture the emission distribution of acoustic features per state.

**Strengths:** Principled probabilistic framework; well-understood training (Baum-Welch/EM); can share sub-word units (phonemes) across many keywords; decades of tooling (HTK, Kaldi, Sphinx).

**Weaknesses:** GMMs are poor density estimators for high-dimensional, correlated features; independence assumptions between frames are unrealistic; requires careful feature engineering (MFCC + deltas); scaling accuracy requires large phonetically-labeled corpora.

**Why replaced:** Discriminatively-trained neural networks (DNN-HMM hybrids, then pure neural KWS) directly modeled P(keyword|features) far more accurately than generative GMMs, especially once GPUs made backprop-based training practical at scale (~2012–2014).

### 1.3 Keyword/Filler HMM and Garbage Modeling `[V]`
A KWS-specific refinement of GMM-HMM: build an explicit HMM for the keyword and a "filler"/"garbage" model for everything else, then compute a likelihood ratio. This is the direct conceptual ancestor of the modern "keyword score vs. background score" framing still used today (including in Porcupine's public description of its own approach `[EJ]` based on marketing/technical blog claims — not independently verified).

### 1.4 Discriminative Neural KWS: CNN (Sainath & Parada 2015, "Deep KWS") `[V]`
**Why developed:** Google's 2015 "Convolutional Neural Networks for Small-footprint Keyword Spotting" (Sainath & Parada) reframed KWS as a straightforward supervised classification problem over fixed-size log-Mel spectrogram windows, discarding the sequential HMM decoder entirely in favor of a small CNN that directly outputs a keyword/non-keyword posterior per frame, smoothed over a sliding window.

**Strengths:** Massively smaller footprint than HMM decoders (no WFST/lattice); trains end-to-end; no phonetic dictionary needed; became the template nearly every subsequent small-footprint KWS paper builds on.

**Weaknesses:** Fixed-size input window limits temporal context; convolution alone doesn't model long-range temporal dependencies well; sliding-window smoothing adds latency and is a heuristic bolted onto the classifier rather than a learned decision function.

**Why replaced/extended:** Recurrent and temporal-convolutional variants were added to capture longer temporal context without blowing up parameter count.

### 1.5 CRNN / LSTM / GRU Era `[V]`
**Why developed:** Pure CNNs process fixed windows; recurrent layers (LSTM/GRU) or CRNNs (CNN feature extractor + RNN temporal aggregator) let the network integrate information across the whole utterance and maintain a running "state," which is a more natural fit for streaming detection (you can feed one frame at a time and keep a hidden state instead of buffering a full window).

**Strengths:** True streaming inference (O(1) per-frame compute update); better handling of variable-length keyword duration; improved accuracy on longer/multi-syllable wake words.

**Weaknesses:** LSTM/GRU are harder to quantize well (gating nonlinearities, cell-state dynamic range); sequential recurrence limits some hardware parallelism; vanishing-gradient issues for very long contexts (less relevant at KWS context lengths, but non-zero).

### 1.6 Temporal Convolutional Networks (TCN) `[V]`
**Why developed:** TCNs (dilated causal convolutions) give large receptive fields without recurrence, are trivially parallelizable during training, and — critically — are much easier to quantize and to implement as streaming operators (cache a small ring buffer of past activations per layer) than RNNs.

**Strengths:** Causal by construction (good for real-time streaming); stable training; excellent latency/accuracy trade-off; quantization-friendly.

**Weaknesses:** Effective receptive field is fixed by depth/dilation schedule at design time (less adaptive than attention); can need more layers than an RNN for equivalent long-range context.

### 1.7 BC-ResNet (Broadcasted Residual Learning) `[V]`
**Why developed:** Kim et al. (Qualcomm AI Research), "Broadcasted Residual Learning for Efficient Keyword Spotting" (Interspeech 2021), introduced BC-ResNet specifically to close the gap between full 2D-convolution accuracy and 1D-temporal-convolution efficiency by factorizing frequency and temporal processing and "broadcasting" a frequency-averaged residual back across the time axis.

**Strengths:** State-of-the-art accuracy/parameter trade-off on Google Speech Commands at the time of publication; explicitly designed for the embedded KWS constraint envelope; became a reference architecture cited by many subsequent papers and reportedly used as a baseline/component in several commercial and open-source systems `[EJ]`.

**Weaknesses:** Still a from-scratch supervised architecture — doesn't leverage large-scale self-supervised pretraining; frequency-averaging is a strong inductive bias that can lose fine-grained spectral detail relevant for very similar-sounding confusable phrases.

### 1.8 Streaming Transformers / Conformer `[V]`
**Why developed:** Transformers dominate ASR/NLP due to attention's ability to model arbitrary long-range dependencies. Streaming variants (chunked attention, causal masking, limited look-ahead) and Conformer (convolution + attention hybrid, originally from Gulati et al. 2020 for ASR) were adapted to KWS to capture context that convolution-only models miss.

**Strengths:** Strong accuracy, especially on harder/longer/multi-word wake phrases; attention gives adaptive, content-dependent context aggregation.

**Weaknesses:** Attention is inherently more compute/memory-hungry per parameter than convolution; naive self-attention is O(n²) in sequence length, requiring chunking/caching tricks for streaming; quantization of softmax/attention is less mature than for convolution; generally considered **overkill for single-word wake detection** and more relevant to longer custom phrases or joint KWS+ASR front-ends `[EJ]`.

### 1.9 TinyML-Specific Models `[V]`
A pragmatic, non-academic-novelty trend: rather than inventing new architectures, projects like **microWakeWord** and TFLite-Micro reference models focus on aggressively shrinking known-good architectures (small CNN/TCN, ~10–30K parameters) to fit ARM Cortex-M0/M4-class MCUs with tens-of-KB RAM budgets, prioritizing engineering discipline (fixed-point math, static memory allocation, streaming operator kernels) over model novelty.

### 1.10 Self-Supervised Speech Embeddings (wav2vec 2.0, HuBERT, WavLM) `[V]`
**Why developed:** Large-scale self-supervised pretraining on unlabeled speech (masked prediction, contrastive objectives) produces general-purpose acoustic representations that transfer well to many downstream tasks with little labeled data — appealing for KWS because labeled wake-word data (especially for *custom* user-defined wake words) is scarce.

**Strengths:** Strong few-shot/low-resource performance; a single pretrained encoder can support many downstream tasks (KWS, speaker ID, ASR); active area for "train your own wake word from 5 examples" products.

**Weaknesses:** The encoders themselves (wav2vec2/HuBERT base: ~95M params) are far too large to run directly on an always-on mobile/embedded budget; practical use requires either (a) distilling into a tiny student network, or (b) running the heavy encoder only server-side/cloud for enrollment, then deploying a small distilled detector on-device. This is an active research/engineering gap rather than a solved problem `[EJ]`.

### 1.11 Why Each Generation Replaced the Previous (Summary Table)

| Generation | Key Limitation Solved | New Limitation Introduced |
|---|---|---|
| DTW | No statistical generalization | O(N·M) cost, brittle templates |
| GMM-HMM | No discriminative training | Poor density estimation in high-D space |
| CNN (Sainath) | HMM decoder complexity | Fixed-window, no true streaming state |
| CRNN/LSTM/GRU | No temporal integration | Quantization/parallelism difficulty |
| TCN | RNN quantization/parallelism issues | Fixed receptive field at design time |
| BC-ResNet | 2D-conv cost vs. accuracy trade-off | Still fully supervised, from-scratch |
| Streaming Transformer/Conformer | Limited long-range context | Compute/memory cost, quantization immaturity |
| TinyML variants | MCU deployability | Accuracy ceiling vs. larger models |
| Self-supervised embeddings | Low-resource/custom KW data | Encoder too large for on-device inference |

---

## 2. Commercial & Open-Source Systems — Reverse-Engineering Audit

**Methodological note:** None of these companies publish full production architectures. What follows synthesizes patents, engineering blog posts, conference talks, and credible third-party analysis, explicitly separated from inference. Where a company has published no public technical detail, this is stated rather than filled in with guesses.

### 2.1 Amazon Alexa
- **Architecture (public):** Alexa's published research (Amazon Science blog, Interspeech/ICASSP papers under "Alexa wake word") describes a **multi-stage cascade**: a small always-on DSP-resident first-stage detector with very low compute, feeding a second-stage, more accurate on-SoC verifier before the device streams audio to the cloud `[V]`.
- **Neural network:** Amazon has published on CNN and, more recently, on **contextual/personalized wake-word models** and neural network compression for the on-device stage `[V, per Amazon Science publications]`.
- **Hardware:** Devices with far-field arrays use **beamforming + AEC** for the multi-microphone Echo line; DSP-resident first-stage detection is standard in industry to keep the main SoC asleep `[EJ, standard industry pattern, not all specifics confirmed per-SKU]`.
- **Dataset:** Not published in detail — has access to enormous scale via Alexa device telemetry (with user consent/opt-in mechanisms), an advantage no open-source project can replicate `[EJ]`.
- **Known weaknesses (from public complaints, Reddit r/amazonecho, press coverage):** False triggers from TV/media audio; accent-related false-reject disparities have been publicly studied and are a documented fairness/robustness issue in the wider KWS literature, and Alexa is frequently cited as an example in that discussion `[EJ, community/press sourced]`.

### 2.2 Google Assistant / "Hey Google"
- **Architecture:** Google's published KWS research (Sainath & Parada 2015 origin, plus later papers on "multi-word" and "personalized" wake-word models) underlies "Hey Google" / "OK Google" detection `[V]`.
- **Personalization:** Google has published on speaker-adaptive/personalized wake-word models to reduce false accepts from other people's voices or devices `[V]`.
- **Hardware acceleration:** Pixel devices use a dedicated always-on DSP (documented in Pixel hardware teardowns/marketing as part of the "Pixel Neural Core"/always-on compute path in some generations) to run first-stage detection without waking the AP `[EJ, based on public hardware marketing, exact model not disclosed]`.
- **Known weaknesses:** Documented accidental activations from phonetically similar phrases in ambient TV/media (widely reported in tech press); multilingual wake-word support has historically lagged single-language coverage `[EJ]`.

### 2.3 Apple Siri ("Hey Siri")
- **Architecture:** Apple has published a detailed engineering blog post ("Hey Siri: An On-device DNN-powered Voice Trigger for Apple's Personal Assistant") describing a **two-pass detection**: a small always-on DSP-resident detector (very low power, on the Always-On Processor) that triggers a larger, more accurate main-processor DNN to confirm `[V]`.
- **Personalization:** Apple's blog describes explicit speaker-adaptation via the enrollment process ("Hey Siri" training flow) `[V]`.
- **Known weaknesses:** Third-party teardown/security research communities have occasionally reported on-device trigger-phrase confusability; Apple has not published quantitative FA/FR numbers publicly.

### 2.4 Picovoice Porcupine `[V + EJ]`
- **Architecture (from Picovoice's own public docs/blog):** Porcupine is marketed as using a proprietary lightweight neural network with an emphasis on cross-platform portability (single C runtime, bindings for many languages) and small model size (custom wake-word models are reportedly a few hundred KB) `[V, per Picovoice public docs]`. Exact architecture (layer types, parameter count) is **not publicly disclosed** — it's closed-source/proprietary.
- **Strengths (community-reported, GitHub/HN/Reddit):** Very low false-accept rate reputation; good cross-platform SDK coverage (the most polished multi-platform commercial-grade SDK in this space); simple custom wake-word training via their console.
- **Weaknesses:** Commercial licensing costs at scale; closed model weights (no on-prem full customization beyond their training console); community complaints about pricing changes over time (visible in GitHub issues/Reddit r/homeassistant threads) `[EJ, community-sourced, not independently verified figures]`.

### 2.5 DaVoice
- Much less public technical documentation is available than for Porcupine. Publicly marketed as a wake-word/voice-AI SDK vendor competing on customization and multilingual support. **Insufficient public information exists to reverse-engineer architecture, dataset, or benchmarks with confidence** — flagging this explicitly rather than speculating `[H — data insufficient]`.

### 2.6 LiveKit Wake-Word
- LiveKit's wake-word functionality (as part of its real-time voice-agent stack) is a relatively recent addition and, per LiveKit's own public docs/blog, is built by **integrating existing open models (e.g., openWakeWord) into their agent pipeline** rather than a from-scratch proprietary detector `[EJ, based on LiveKit public documentation describing openWakeWord integration]`.

### 2.7 openWakeWord `[V — open source, code is public ground truth]`
- **Architecture:** Uses pre-trained audio embedding models (Google's `speech_embedding` model, itself a small CNN) feeding lightweight classifier heads (dense/small models) trained per-wake-word, largely on **synthetically generated (TTS) positive examples plus real negative/background audio**, augmented with room-impulse-response convolution and background noise mixing.
- **Strengths:** Fully open weights and training pipeline; synthetic-data-first approach means new wake words can be added without collecting real human recordings; active community (Home Assistant ecosystem integration).
- **Weaknesses (from GitHub issues):** Accuracy is noticeably behind Porcupine/commercial systems for challenging acoustic conditions; synthetic-only training data creates a real-vs-synthetic domain gap that shows up as elevated false-reject rates for some voices/accents (documented in GitHub issue discussions) `[V, GitHub issue content]`.

### 2.8 microWakeWord `[V]`
- **Architecture:** Purpose-built for ESP32-class MCUs within the Home Assistant / ESPHome ecosystem; small streaming CNN/TCN-style model, INT8 quantized, TFLite-Micro runtime.
- **Strengths:** Genuinely runs on ESP32-S3 with acceptable latency and tiny memory footprint; fully open, MCU-first design rather than mobile-first-then-shrunk.
- **Weaknesses:** Smaller community and slower model-quality iteration than the mobile-first projects; limited to relatively short/simple wake phrases for reliable MCU performance `[EJ]`.

### 2.9 Mycroft Precise / Snowboy / Rhasspy `[V, mostly historical]`
- **Precise:** GRU-based, open-source, part of the now largely inactive Mycroft project (Mycroft AI ceased operations in 2023, well-documented in press coverage). Codebase still used/forked by hobbyists.
- **Snowboy (Kitt.AI):** Historically popular, **officially discontinued/deprecated** by its maintainers years ago; still referenced in old tutorials but not a living project. Architecture details were never fully open (closed-source model training).
- **Rhasspy:** An open-source voice-assistant framework (not itself a novel KWS model) that historically integrated Precise/Snowboy/Porcupine as pluggable wake-word backends — an aggregator, not a from-scratch detector.

### 2.10 Home Assistant Voice / Assist
- Home Assistant's voice pipeline (Assist) explicitly supports **openWakeWord, microWakeWord, and Porcupine** as pluggable backends `[V, per Home Assistant public documentation]` rather than shipping a single proprietary model — a useful precedent for AURA: **the ecosystem already treats wake-word as a swappable component behind a common interface**, which validates a "runtime abstraction first" strategy.

### 2.11 Cross-System Comparison Table

| System | Open/Closed | Architecture (public detail) | Multi-stage cascade | Personalization | Multilingual | Confidence |
|---|---|---|---|---|---|---|
| Alexa | Closed | CNN + compression, cloud-assisted | Yes (DSP → SoC → cloud) | Yes (documented) | Yes | V/EJ mix |
| Google Assistant | Closed | CNN-derived, personalized variants | Yes (DSP → AP) | Yes (documented) | Partial | V/EJ mix |
| Siri | Closed | DNN, two-pass | Yes (AOP → main DNN) | Yes (documented) | Partial | V (blog) |
| Porcupine | Closed weights, open SDK | Proprietary lightweight NN | Unknown | Limited (per-user models via console) | Yes | EJ |
| DaVoice | Closed | Unknown | Unknown | Unknown | Claimed | H |
| LiveKit | Open (integrates openWakeWord) | Inherits openWakeWord | No (single-stage typical) | No | Depends on model used | EJ |
| openWakeWord | Fully open | Embedding + classifier head | No | No | Limited | V |
| microWakeWord | Fully open | Small streaming CNN/TCN | No | No | Limited | V |
| Precise/Snowboy/Rhasspy | Open (mostly inactive) | GRU / undisclosed / aggregator | No | No | Limited | V (historical) |

---

## 3. Research Paper Survey (Representative, Not Exhaustive)

For each: motivation → architecture → dataset → loss → results → limitations → lesson for AURA. (Numeric results below are as reported in each paper on its own eval set — not directly comparable across papers due to differing datasets/protocols; treat cross-paper comparisons as directional, not exact `[V for individual results, EJ for cross-paper comparison]`.)

**3.1 Sainath & Parada, "Convolutional Neural Networks for Small-footprint Keyword Spotting" (Interspeech 2015).**
Motivation: replace HMM-based KWS with a simpler, smaller discriminative model. Architecture: small CNN over log-Mel frames with max-pooling in frequency. Dataset: proprietary "OK Google" data. Loss: cross-entropy. Result: outperformed DNN and HMM baselines at similar or smaller size. Limitation: fixed-window, needs external smoothing heuristic for streaming decisions. Lesson for AURA: the CNN-on-log-Mel baseline remains a legitimate, well-understood starting point for any new KWS effort and a useful sanity-check model before investing in more complex streaming architectures.

**3.2 Kim, Chang, Lee, Sung (Qualcomm), "Broadcasted Residual Learning for Efficient Keyword Spotting" (Interspeech 2021).**
Motivation: close the accuracy gap between 2D and 1D convolution at low parameter counts. Architecture: BC-ResNet, factorized frequency/temporal residual blocks with broadcasting. Dataset: Google Speech Commands v1/v2. Loss: cross-entropy. Result: state-of-the-art accuracy/parameter trade-off reported at publication time on Speech Commands. Limitation: frequency-averaging is a strong prior that may not suit all keyword acoustics (e.g., tonal languages, sibilant-heavy phrases). Lesson for AURA: BC-ResNet variants are a strong default architecture family to prototype first, especially for mobile CPU/NEON deployment.

**3.3 Rybakov et al. (Google), "Streaming Keyword Spotting on Mobile Devices" (Interspeech 2020).**
Motivation: formalize streaming-model design (state caching, causal convolution) for on-device KWS, comparing several architectures (CNN, CRNN, DS-CNN, TCN, etc.) under a unified streaming-latency framework. Dataset: Google Speech Commands. Result: provides one of the more genuinely comparable multi-architecture benchmarking studies in the field. Limitation: single dataset, English-only. Lesson for AURA: adopt this paper's streaming-inference formalism (explicit state buffers per layer, ring-buffer causal convolution) as the reference design pattern for AURA's C++ runtime.

**3.4 Gulati et al. (Google), "Conformer: Convolution-augmented Transformer for Speech Recognition" (Interspeech 2020).**
Motivation: combine convolution's local feature extraction with self-attention's global context modeling, originally for ASR (later adapted by others to KWS). Architecture: interleaved conv/attention/feed-forward blocks. Result: strong WER improvements in ASR. Limitation: designed for ASR-scale compute, not directly embedded-KWS-sized; adapting to always-on wake detection requires heavy shrinking. Lesson for AURA: Conformer-style blocks are a candidate for a "second-stage verifier" model (which can tolerate more compute, since it only runs after a first-stage trigger) rather than the always-on first stage.

**3.5 Warden (Google), "Speech Commands: A Dataset for Limited-Vocabulary Speech Recognition" (2018, arXiv).**
Motivation: create a standard open benchmark for small-footprint KWS research (previously everyone used private data, making comparison impossible). Result: became the de facto academic benchmark; nearly every paper above evaluates on it. Limitation: it is now widely acknowledged in the community that Speech Commands is **too easy and too narrow** (clean audio, limited noise conditions, single-word commands, mostly English/US speakers) to represent real-world always-on performance `[V — well-documented critique]`. Lesson for AURA: do not rely on Speech Commands as a proxy for production readiness; it's useful for architecture ablation but insufficient for FA/hour and cross-accent robustness claims.

**3.6 Self-supervised transfer papers (wav2vec 2.0 — Baevski et al. 2020; HuBERT — Hsu et al. 2021).**
Motivation: learn general acoustic representations from unlabeled speech to reduce labeled-data requirements downstream. Result: strong transfer performance across many speech tasks including few-shot keyword classification demonstrated in follow-up work. Limitation: base encoders (~95M+ params) are far too large for always-on embedded deployment; distillation to a usable size is a research problem in itself, not yet a solved, published, drop-in recipe for KWS specifically `[EJ]`. Lesson for AURA: highest strategic value here is in the **custom-wake-word enrollment pipeline** (few-shot from a handful of user recordings), potentially using a heavy embedding model server-side/at training time only, with a distilled tiny model shipped to device — not for the always-on runtime itself.

**3.7 Hard-negative / confusable-phrase papers (multiple, e.g., work on "similar-sounding wake word rejection").**
Motivation: real-world false accepts are dominated by phonetically similar phrases ("Hey Sirilla," "Aleksa," TV dialogue), not random noise. Common finding across this literature: explicit hard-negative mining against a large corpus of confusable phrases materially reduces FA rate versus random-negative training `[V — recurring, consistent finding across multiple independent papers]`. Lesson for AURA: treat hard-negative mining (using ASR output on large unlabeled audio corpora to surface phonetically close non-keyword segments) as a first-class, non-optional part of the training pipeline, not an afterthought.

---

*(Continued in Part 2: DSP foundations, model architecture comparison, datasets, augmentation, training techniques, runtime engineering, benchmarking methodology, open-source gap analysis, and AURA roadmap.)*

---

## 4. DSP Foundations

### 4.1 STFT / FFT
The Short-Time Fourier Transform slices audio into overlapping frames (typically 20–30 ms, 10 ms hop for speech) and applies an FFT to each to get a time-frequency representation. **Mathematical intuition:** the FFT decomposes a frame into a sum of sinusoids at discrete frequencies; overlapping frames trade time resolution for frequency resolution (Heisenberg-like uncertainty trade-off — narrower frames give better time localization but coarser frequency bins, and vice versa). **Edge-device trade-off:** FFT size directly drives per-frame compute; a 25ms/16kHz frame is typically zero-padded to a power-of-two FFT size (e.g., 512) for efficient radix-2 FFT implementations — this is one of the first, cheapest wins for MCU-class DSP (fixed-point FFT libraries like CMSIS-DSP are standard `[V]`).

### 4.2 Window Functions
Applying a window (Hamming, Hann, Blackman) before the FFT reduces spectral leakage caused by the implicit rectangular windowing of framing. **Trade-off:** Hann/Hamming are cheap and standard for speech; more complex windows (Blackman-Harris) give better sidelobe suppression at slightly higher compute and wider mainlobe (worse frequency resolution) — rarely worth it for KWS given already-coarse Mel binning downstream.

### 4.3 Mel Filterbanks / Log-Mel / MFCC
Mel filterbanks warp the linear FFT frequency axis to the psychoacoustic Mel scale (denser bins at low frequencies where human/speech-relevant energy concentrates), then sum FFT bin energies into ~20–40 filterbank bins. **Log-Mel** takes the log of these energies (compresses dynamic range, matches loudness perception, and is what nearly all modern neural KWS models consume directly as input — CNNs learn better from log-Mel than raw FFT magnitude). **MFCC** additionally applies a DCT to decorrelate the log-Mel bins into cepstral coefficients — this was essential for GMM-HMM systems (which assume diagonal-covariance Gaussians and need decorrelated features) but is **largely unnecessary for CNN/CRNN models**, which can learn correlations across Mel bins directly via convolution; most modern KWS papers use log-Mel, not MFCC `[V — common practice, explicitly discussed in multiple KWS papers]`.

### 4.4 PCAN (Per-Channel Energy Normalization)
PCAN is an alternative to simple log compression that applies an adaptive gain per frequency channel based on a running estimate of that channel's energy, effectively doing automatic gain control *per Mel bin*. Used notably in Google's speech front-end research as a log-Mel alternative that is more robust to loud transient noise. **Trade-off:** more robust to varying loudness/background noise than plain log-Mel, at the cost of extra state (leaky integrator per channel) and tuning parameters (time constants, gain exponents).

### 4.5 AGC (Automatic Gain Control)
Normalizes overall input level so the detector sees a consistent amplitude range regardless of how loud/soft or near/far the speaker is. **Edge trade-off:** simple AGC (single time-constant leaky-integrator gain) is cheap and standard; overly aggressive AGC can amplify noise floor during silence, which can increase false accepts if not paired with a VAD gate.

### 4.6 AEC (Acoustic Echo Cancellation)
Removes the device's own played-back audio (e.g., music, TTS response) from the microphone signal using an adaptive filter (commonly NLMS or Kalman-filter-based) referenced against the known playback signal. **Critical for smart speakers** (which must detect "Alexa, stop" while playing music) — without AEC, self-playback dominates the mic signal and wake-word detection on barge-in becomes unreliable. **Edge trade-off:** adaptive filter length must cover the acoustic path delay (room echo + speaker/output pipeline latency); longer filters are more effective but costlier — a classic real-time DSP engineering trade-off, well covered in Kitzz/HealthWatch-adjacent DSP work Ashu has previously built (Pan-Tompkins/Kalman-filter ANC context is directly analogous).

### 4.7 Noise Suppression
Spectral subtraction, Wiener filtering, or modern neural noise suppression (RNNoise-style small RNN models) reduce stationary background noise before feature extraction. **Trade-off:** aggressive suppression can also suppress speech harmonics relevant to keyword discrimination — over-suppression is a documented failure mode that can *increase* false rejects even while reducing perceived "noisiness" `[EJ]`.

### 4.8 Beamforming / Far-Field Speech
Multi-microphone arrays combine signals with per-microphone delay/gain weighting (fixed beamforming like delay-and-sum, or adaptive like MVDR/GSC) to spatially focus on the speaker's direction and suppress off-axis noise/interference. **Essential for smart-speaker-class far-field performance** (Alexa/Google Home use multi-mic arrays specifically for this). **Edge trade-off:** requires ≥2 synchronized microphones and non-trivial DSP (direction-of-arrival estimation, adaptive weight updates) — infeasible on single-mic phones/wearables, which instead rely more heavily on close-talk assumptions and neural noise robustness.

### 4.9 Voice Activity Detection (VAD)
A cheap classifier (energy-threshold, GMM, or tiny neural network) that decides whether a frame contains speech at all, used to **gate** the more expensive wake-word model so it only runs during speech segments — a major power-saving technique for always-on detection. **This is exactly the "VAD gating" stage** already present in the "Hey M" pipeline's design (per prior project context) and is standard practice across essentially every commercial always-on system `[V — universally documented pattern]`.

### 4.10 Confidence Summary for Section 4
All DSP techniques above are `[V]` — standard, decades-old, textbook signal processing (Oppenheim & Schafer level material) with well-documented adaptations for speech and for embedded deployment; the main open engineering judgment `[EJ]` is *which combination and parameterization* is optimal for AURA's specific hardware targets, which requires empirical benchmarking, not literature review alone.

---

## 5. Model Architecture Comparison

| Architecture | Typical Params (KWS-sized) | Streaming-native | Quantization friendliness | Mobile CPU fit | MCU fit | Notes |
|---|---|---|---|---|---|---|
| Small CNN (Sainath-style) | 50K–250K | No (needs windowing) | Good | Excellent | Good | Simple baseline, still competitive |
| DS-CNN (depthwise-separable) | 30K–150K | Partial | Good | Excellent | Excellent | Standard MobileNet-style factorization |
| ResNet (full 2D conv) | 200K–1M+ | No | Good | Good | Poor | Heavier than needed for KWS |
| BC-ResNet | 10K–200K (scalable family: BC-ResNet-1 to -8) | Yes (with causal variant) | Good | Excellent | Good | Best accuracy/size trade-off reported in literature `[V]` |
| MobileNet/EfficientNet (adapted) | 300K–3M | No | Good | Good | Poor | Generally oversized for single-keyword KWS; more relevant if doing joint tasks |
| TCN | 50K–300K | Yes (native) | Very good | Excellent | Good | Strong latency control via dilation schedule |
| CRNN (CNN+GRU/LSTM) | 100K–500K | Yes (via RNN state) | Moderate (RNN quant harder) | Good | Fair | Good context modeling, trickier INT8 story |
| Transformer (streaming) | 500K–5M+ | Yes, with chunking | Immature | Fair | Poor | Likely overkill for single wake word `[EJ]` |
| Tiny/Streaming Conformer | 200K–2M | Yes, with chunking | Immature | Fair | Poor | Better suited to second-stage verification or multi-word phrases |

**FLOPs/latency note:** For a 1-second audio window at 16kHz with typical 40-dim log-Mel features and 10ms hop (100 frames), a well-designed BC-ResNet or DS-CNN variant in the 50–100K parameter range typically runs in the low single-digit milliseconds per inference on a modern mobile CPU core, comfortably meeting the <100ms latency target with large headroom for the rest of the pipeline (DSP front-end, VAD, cascade second stage) `[EJ — order-of-magnitude estimate based on published parameter/latency figures in the cited papers, not a measured AURA figure]`. Actual figures must be measured per target device/runtime, not assumed from paper-reported numbers on different hardware.

**Recommendation pattern (consistent across Rybakov et al. and BC-ResNet lineage):** first-stage always-on detector should be the smallest model in this table that meets the accuracy bar (DS-CNN or small BC-ResNet variant); second-stage verifier can afford a larger CRNN/BC-ResNet-8/small-Conformer since it only runs after a trigger, dramatically reducing average power cost.

---

## 6. Dataset Landscape

| Dataset | License | Content | Strength | Weakness for KWS |
|---|---|---|---|---|
| Google Speech Commands v2 | CC-BY 4.0 | 35 short command words, ~105K clips | Standard benchmark, easy to use | Too clean/easy; narrow vocabulary; mostly US English `[V — documented critique]` |
| LibriSpeech | CC-BY 4.0 | ~1000h read English audiobooks | Large, clean, well-segmented | Reading-style speech, not conversational/command-style; limited noise diversity |
| Common Voice (Mozilla) | CC0 | Crowdsourced multilingual speech | Huge language coverage, permissive license | Variable recording quality; uneven per-language volume |
| VoxCeleb | Custom (research use) | Celebrity interview audio, speaker ID focus | Great for speaker verification component | Not phonetically balanced for KWS; license restrictions for commercial use need checking |
| FLEURS | CC-BY 4.0 | Multilingual (~100 languages) parallel speech | Strong multilingual benchmark | Small per-language volume, read speech |
| AudioSet | CC-BY 4.0 (labels); audio via YouTube ToS | Huge general-audio event dataset | Excellent negative/background noise source | YouTube-sourced audio has usage/redistribution caveats to check carefully |
| MUSAN | CC-BY 4.0 | Music/speech/noise for augmentation | Purpose-built for augmentation | Relatively small compared to AudioSet |
| ESC-50 | CC-BY-NC | Environmental sound classification | Good categorized noise negatives | Non-commercial license restricts direct commercial use — **legal flag** |
| DNS Challenge datasets | CC-BY 4.0 (Microsoft) | Noise + RIR for denoising research | Purpose-built noisy/clean pairs, includes RIRs | Focused on ASR/denoising, not KWS-labeled |
| LibriTTS | CC-BY 4.0 | Multi-speaker TTS-oriented derivative of LibriSpeech | Good for synthetic positive-example generation via TTS | Same speech-style limitations as LibriSpeech |

**Key strategic point:** No existing public dataset is purpose-built, large-scale, and permissively licensed for wake-word-specific positive examples across many custom phrases and languages. This is consistent with why every open-source project (openWakeWord in particular) leans heavily on **TTS-synthesized positives** rather than real recordings — and is the single clearest "moat" commercial players have via proprietary device telemetry `[EJ]`. **Legal note:** ESC-50's CC-BY-NC license and AudioSet's YouTube-sourced audio both need explicit legal review before any commercial redistribution or embedding of derived data into a commercial AURA product — flagging as a risk item, not making a legal determination here.

---

## 7. Data Augmentation Techniques

- **Speed perturbation** (±10–20%): cheap, well-established ASR/KWS augmentation, simulates speaking-rate variation. `[V]`
- **Pitch shift:** simulates speaker/vocal-tract variation; less universally used than speed perturbation in KWS papers, more common in singing/music tasks — moderate evidence of benefit for KWS specifically `[EJ]`.
- **RIR convolution:** convolving clean speech with measured/simulated room impulse responses to simulate reverberant far-field conditions — one of the most impactful augmentations for far-field robustness, used extensively in DNS Challenge-adjacent and Alexa/Google far-field research `[V]`.
- **Background noise mixing:** additively mixing MUSAN/AudioSet noise at controlled SNR ranges — standard and essential; SNR curriculum (easy-to-hard) is a common refinement.
- **SpecAugment (time/frequency masking):** randomly masking blocks of time frames and/or frequency bins in the log-Mel spectrogram during training — originally for ASR (Park et al. 2019), now standard across nearly all modern speech models including KWS, cheap and consistently effective `[V]`.
- **Reverberation** — see RIR convolution above; sometimes treated separately when using parametric/simulated reverb rather than measured RIRs.
- **Clipping simulation:** simulates cheap/overloaded microphone hardware clipping — relevant for low-cost embedded/IoT microphones (directly relevant to ESP32-based hardware work).
- **Codec simulation:** simulates lossy codec artifacts (e.g., Bluetooth/AMR/Opus at low bitrate) for devices that process audio post-codec — relevant if AURA ever needs to support Bluetooth-mic scenarios.
- **Microphone/device simulation:** convolving with measured frequency responses of cheap MEMS mics vs. studio mics to reduce train/deployment mic mismatch — an under-discussed but practically important augmentation for exactly the kind of custom ESP32-S3 hardware AURA/Kitzz-adjacent work involves.

**Confidence:** all of the above are `[V]`, standard in the literature; the open research question is the **optimal augmentation schedule/curriculum weighting** for a specific target hardware mix, which is empirical, not something the literature settles definitively.

---

## 8. Training Techniques

- **Curriculum learning:** starting training on easier examples (clean, high-SNR) and progressively introducing harder ones (noisy, low-SNR, confusable negatives) — shown in multiple KWS/ASR papers to improve convergence and final robustness versus random-order training `[V]`.
- **Hard-negative mining:** as discussed in section 3.7, actively surfacing phonetically-confusable non-keyword segments (via ASR decoding of large unlabeled corpora) and prioritizing them in training — one of the highest-leverage, most consistently reported techniques for reducing real-world false-accept rate `[V]`.
- **Knowledge distillation:** training a small "student" KWS model to match the output distribution of a larger "teacher" model (or a self-supervised embedding-based classifier) — directly relevant to bridging the self-supervised-embedding-too-large problem from section 1.10/3.6.
- **Self-supervised learning / contrastive learning / metric learning:** relevant primarily for the speaker-verification component (metric learning with triplet/contrastive losses is the standard approach for speaker embeddings, e.g., d-vector/x-vector style systems) rather than the core wake-word detector itself.
- **Transfer learning:** initializing from a model pretrained on a large multi-keyword or general audio-event dataset before fine-tuning on a specific custom wake word — directly relevant to a "train your own wake word from few examples" product feature.
- **Multi-task learning:** jointly training wake-word detection with auxiliary tasks (e.g., VAD, speaker ID) sharing a backbone — can improve data efficiency but adds training/engineering complexity.
- **Temperature scaling / Platt scaling:** post-hoc calibration methods to make model output scores better reflect true probabilities/confidence — useful for setting principled, comparable thresholds across the cascade stages rather than ad hoc per-model thresholds.
- **Focal loss vs. BCE:** for the heavily class-imbalanced keyword-vs-everything-else problem (positives are extremely rare relative to negatives in real always-on audio), focal loss (down-weighting easy negatives) is a documented, reasonable alternative to plain binary cross-entropy, though the improvement magnitude is dataset-dependent and not universally reported as dramatic `[EJ]`.
- **CTC / RNN-T:** relevant mainly if AURA moves toward joint wake-word+short-command spotting (sequence-to-sequence style) rather than pure binary/multi-class trigger detection — likely out of scope for a pure wake-word engine but relevant if the product roadmap extends toward "wake word + command" (e.g., "Hey M, turn off the lights").

---

## 9. Runtime Engineering

| Runtime/Backend | Platforms | Strengths | Weaknesses |
|---|---|---|---|
| TensorFlow Lite | Android, iOS, embedded (via TFLite Micro) | Mature quantization tooling, NNAPI/CoreML delegates, huge community | Larger runtime footprint than TFLite Micro; Google-centric roadmap |
| TensorFlow Lite Micro | MCU (Cortex-M, ESP32) | No dynamic memory allocation, tiny footprint, designed for exactly this use case | Limited operator set, more manual model-conversion friction |
| ONNX Runtime (+ Mobile/Web variants) | Cross-platform (Android/iOS/Linux/Windows/macOS/Wasm) | True single-format cross-platform story, active EP (execution provider) ecosystem (XNNPACK, NNAPI, CoreML, QNN) | MCU support far less mature than TFLite Micro |
| CoreML | iOS/macOS only | Best-in-class Apple Neural Engine utilization | Apple-only, no cross-platform story |
| NNAPI | Android only | Access to vendor NPU/DSP acceleration on supporting devices | Fragmented vendor support/quality across Android OEMs — a well-documented pain point in the Android ML community |
| XNNPACK | Cross-platform CPU backend (used by both TFLite and ONNX Runtime) | Excellent quantized CPU kernel performance, NEON/SIMD optimized | CPU-only (no NPU acceleration itself) |
| QNN (Qualcomm Neural Network SDK) | Qualcomm Hexagon DSP/NPU | Significant power/latency advantage on Snapdragon devices for the always-on first stage | Vendor-locked to Qualcomm silicon |
| ARM NEON / SIMD | ARM CPUs broadly | Free, broad-reach acceleration without vendor lock-in | Doesn't match dedicated NPU/DSP power efficiency for true always-on use |
| WebAssembly SIMD | Browser/Wasm runtimes | Enables the "AURA in the browser" / web-agent use case | Meaningfully slower than native; less relevant for true always-on power-constrained deployment, more relevant for demo/dev-tool contexts |

**Recommendation pattern:** a single **ONNX Runtime-based core** with platform-specific execution providers (XNNPACK as universal CPU fallback, NNAPI on Android where reliable, CoreML on Apple, QNN opportunistically on Qualcomm hardware) gives the broadest genuine cross-platform coverage described in the project goal, while a **separate TFLite-Micro build path** is still very likely necessary for the ESP32/Cortex-M targets, since ONNX Runtime's embedded-MCU story is currently much less mature than TFLite Micro's `[EJ — based on current tooling maturity, subject to change over time]`.

---

## 10. Benchmarking Methodology (Proposed Framework for AURA)

A rigorous KWS benchmark suite should report, at minimum:

1. **False Accepts per Hour (FA/hr):** measured on a large corpus of continuous non-keyword audio (ideally including TV/media/podcast audio, since that's the dominant real-world false-accept source per section 3.7) — not just a held-out test split of the training distribution.
2. **False Rejection Rate (FRR) at a fixed FA/hr operating point:** FRR alone or FA alone is close to meaningless without pairing them — always report as a paired operating point or full curve.
3. **ROC and DET curves:** DET (Detection Error Tradeoff, log-log FA vs. FR) is the standard in the speaker/keyword verification literature and is more discriminating at the low-error-rate operating points relevant to production systems than a linear ROC curve.
4. **Precision/Recall** as a secondary, easier-to-communicate framing for non-specialist stakeholders, but not a substitute for FA/hr + DET.
5. **Latency:** wall-clock time from end-of-keyword-utterance to trigger event, measured on-device on representative hardware, not on a development workstation.
6. **CPU usage:** both peak (during active inference) and average (over long always-on operation, factoring in VAD-gated duty cycling).
7. **RAM:** both static (model weights + buffers) and dynamic peak (during inference) — critical for the <20MB mobile target and the far tighter MCU budgets.
8. **Battery impact:** measured as device battery drain rate (mAh/hour) under continuous always-on operation — the metric that ultimately matters to end users and is directly downstream of CPU/duty-cycle numbers above.
9. **Thermal behavior:** sustained-load thermal throttling checks — relevant because always-on inference, even if individually cheap, runs continuously for hours and can trigger throttling on some mobile SoCs under sustained load if not duty-cycled properly via VAD gating.
10. **Continuous streaming stability:** multi-hour soak tests checking for memory leaks, numerical drift (especially relevant for adaptive AGC/PCAN running state), and crash-freedom — this category is the one most commonly *missing* from academic papers (which evaluate on fixed test sets) and most necessary for a production engine.

**Gap identified:** the academic literature is strong on (1)-(4) and essentially silent on (5)-(10), which are exactly the categories that separate a research prototype from a production wake-word engine — this is a genuine opportunity area for AURA's engineering rigor to differentiate from open-source alternatives, which also generally lack (5)-(10) reporting in their public repos `[V — verified by absence in reviewed repos' documentation]`.

---

## 11. Open-Source Ecosystem Audit — Consolidated Findings

**Architectural strengths observed:**
- openWakeWord's pluggable-model, embedding-based design is a genuinely reusable pattern (embedding model once, cheap per-keyword classifier heads) worth adopting.
- microWakeWord's MCU-first discipline (static memory, TFLite Micro from day one rather than shrinking a mobile model after the fact) avoids a common failure mode of designing mobile-first and struggling to retrofit MCU support.
- Home Assistant's pluggable-backend architecture validates a runtime-abstraction-first approach.

**Architectural weaknesses / common bugs (from GitHub issues across these projects):**
- Real-vs-synthetic training data domain gap causing elevated false-reject rates for underrepresented voices/accents (recurring openWakeWord issue theme).
- Sparse or absent multi-hour soak-testing / memory-leak reports in any of the reviewed open-source repos.
- Limited or no far-field/beamforming integration in any fully open-source project reviewed — this remains commercial-system territory.
- Multilingual wake-word support is thin across the board in open source; most effort concentrates on English.
- No open-source project reviewed publishes DET curves or FA/hr-calibrated benchmarks in their documentation — benchmarking rigor is a consistent, structural gap across the entire open-source ecosystem, not a project-specific failing.

**Missing features / community requests (recurring themes across GitHub issues/Reddit/Home Assistant community forums):**
- Reliable multi-wake-word concurrent detection without proportional CPU cost increase.
- Better documentation/tooling for training genuinely custom wake words from a handful of real (non-synthetic) recordings.
- Cross-platform SDK parity (most open projects are strongest on Linux/Python, weaker on iOS/Flutter/React Native — the exact gap AURA's target platform list would need to fill).


---

## 12. Gap Analysis — Where Existing Systems Fall Short

| Gap | Commercial systems | Open-source systems | Opportunity for AURA |
|---|---|---|---|
| Cross-platform SDK parity (Android/iOS/Flutter/RN/Linux/Windows/macOS/Pi/ESP32/Cortex-M/Wasm in one coherent SDK) | Fragmented per-vendor, no vendor covers this full list | Fragmented per-project, no single project covers this full list | **Largest concrete opportunity** — a genuinely unified runtime abstraction is not solved by anyone today `[EJ]` |
| Multilingual, well-augmented, permissively-licensed training data | Strong (proprietary telemetry) | Weak (synthetic-heavy, English-centric) | Investment in a licensed/ethically-sourced multilingual data pipeline is the highest-leverage, hardest-to-copy differentiator |
| Rigorous, published benchmarking (FA/hr, DET, soak testing) | Not published externally | Not published/measured internally either | Publishing rigorous, reproducible benchmarks would be a credible trust/marketing differentiator versus the entire field |
| Far-field / beamforming support | Strong (multi-mic hardware co-design) | Essentially absent | Realistic only if AURA also engages in reference hardware design (aligns with CoBuild Labs hardware capability) |
| Custom wake-word training from few real (non-TTS) examples | Limited (Porcupine's console is TTS/proprietary-pipeline based per public docs) | Weak (openWakeWord is synthetic-only by default) | A genuinely good few-shot-from-real-audio enrollment flow (leveraging distilled self-supervised embeddings) is a differentiator with real research risk attached |
| Multi-stage cascade with speaker verification, cleanly packaged for third-party developers | Exists internally, not exposed as a general-purpose SDK | Absent | Packaging a documented, configurable 2-stage-cascade + optional speaker-verification SDK is achievable with known techniques, mainly an integration/engineering effort rather than research risk |

---

## 13. Prioritized Innovation List for AURA (Realistic, Not Aspirational)

1. **Unified cross-platform runtime abstraction** (ONNX Runtime core + TFLite-Micro MCU path behind one API) — engineering-heavy, research-light, highest near-term ROI.
2. **Rigorous benchmarking suite and public methodology** (FA/hr on real media audio, DET curves, soak tests) — differentiates on trust with near-zero research risk.
3. **Hard-negative-mining data pipeline** using ASR-decoded large unlabeled corpora — well-precedented technique, mainly a data-engineering investment.
4. **Two-stage cascade + optional speaker verification, packaged as a clean SDK feature** — known techniques (per Alexa/Siri public architecture descriptions), main risk is engineering integration complexity, not research novelty.
5. **BC-ResNet-family first-stage model + optionally larger CRNN/small-Conformer second-stage verifier** — architecture choice is low-research-risk given strong published precedent.
6. **Multilingual data investment** (Common Voice + FLEURS + licensed/synthetic augmentation) — high effort, high differentiation, moderate risk (data quality variance across languages).
7. **Few-shot custom-wake-word-from-real-audio training** using distilled self-supervised embeddings — **highest research risk** item on this list; treat as an R&D spike with a clear go/no-go checkpoint rather than a committed roadmap item.
8. **Reference far-field hardware design** (multi-mic array + beamforming reference board) — realistic only in combination with CoBuild Labs' hardware capability; largest capital/time investment on this list.

---

## 14. Risk Assessment

**Technical risks:**
- Cross-platform runtime unification is more of an integration/maintenance burden than a research risk, but the burden is real and ongoing (every OS/SDK update is a potential regression surface).
- Few-shot custom-wake-word-from-real-audio (item 7 above) has genuine unsolved-research characteristics — no publicly documented drop-in recipe exists today; budget for it as R&D with uncertain timeline, not a fixed-scope feature.

**Research risks:**
- Public benchmarks (Speech Commands, etc.) are known to be poor proxies for production performance (section 3.5) — any internal go/no-go decision based only on academic-benchmark accuracy risks false confidence; production-representative test sets (with real noise/media audio, not synthetic) must be built independently.

**Legal risks:**
- Dataset licensing must be reviewed carefully before commercial use: ESC-50 (CC-BY-NC) is not commercially usable as-is; AudioSet's YouTube-sourced audio has redistribution caveats; VoxCeleb has research-use-oriented terms. None of this is a legal opinion — engage counsel before any commercial data pipeline decision.
- Patents: Amazon, Google, and Apple all hold wake-word-related patents (multi-stage cascade, personalization, specific DSP techniques) based on their public patent filings; a formal freedom-to-operate review is warranted before committing to specific architectural choices that closely mirror described patented techniques, particularly around personalized/adaptive wake-word models and specific multi-mic beamforming methods.

**Engineering risks:**
- Always-on power/thermal budgets are unforgiving; a model that benchmarks well on accuracy but fails the <5% CPU / <20MB RAM / battery-drain targets in real multi-hour soak testing is a shipped-product failure even if it's an academic success — this must be tested continuously through development, not only at the end.

---

## 15. Recommended Roadmap for Phase 2

**Phase 2a — Foundational Prototyping (research-validation focus):**
- Stand up an internal, production-representative benchmark corpus (real media/TV audio negatives, multi-accent positives) since no adequate public dataset exists (section 3.5/12).
- Prototype BC-ResNet-family first-stage model on this corpus; measure FA/hr and DET, not just Speech Commands accuracy.
- Prototype the ONNX Runtime + XNNPACK path on one mobile platform (Android) and one MCU (ESP32-S3) in parallel to surface cross-platform runtime friction early, rather than late.

**Phase 2b — Cascade and Robustness:**
- Add second-stage verifier model and measure end-to-end FA/hr improvement versus single-stage.
- Integrate hard-negative mining pipeline against a large unlabeled audio corpus.
- Run first multi-hour soak test and thermal/battery measurement pass on real target hardware.

**Phase 2c — Differentiation Features (higher risk, sequenced after core validation):**
- R&D spike (time-boxed) on few-shot custom-wake-word-from-real-audio enrollment.
- Multilingual data pipeline expansion beyond English.
- Legal review of dataset licensing and patent landscape before committing to final architecture/feature set for commercial release.

**Explicit non-goal for Phase 2:** do not attempt far-field/beamforming hardware co-design until the software-only cross-platform + cascade + benchmarking foundation (2a/2b) is validated — sequencing risk reduction before the highest-capital-cost item is a deliberate recommendation, not an oversight.

---

## Appendix: Confidence Legend Recap
- `[V]` — Verified against publicly available, citable sources (papers, official engineering blogs, official documentation, or directly inspectable open-source code).
- `[EJ]` — Engineering Judgment: a reasonable inference from public evidence, industry norms, or the cited sources, but not itself directly documented.
- `[H]` — Hypothesis: insufficient public information exists to make a confident claim; flagged explicitly rather than filled in.

**Note on scope:** This document prioritizes accuracy and clearly-labeled uncertainty over exhaustive length. Several subsections (notably the full literature survey in Section 3 and the commercial reverse-engineering in Section 2) could be expanded significantly further with additional targeted research passes — flag any specific area below for a deeper follow-up pass rather than treating this as final.
