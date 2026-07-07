# USB-C Microphone Recommendation for Wake-Word Capture (Realme 8, Android)

**Use case:** always-on wake-word capture + testing, physically plugged into a Realme 8 (USB-C).
**Goal:** clean, representative audio for a wake-word model — not "pretty" YouTube audio.

---

## TL;DR — Top Pick

**RODE VideoMic Me-C** (~$79 / ₹6,500) — a proper cardioid condenser that connects over native USB-C digital audio (UAC), is class-compliant on Android, and delivers clean, *lightly-processed* speech. Best all-round balance of near-field quality, Android compatibility, and "no black-box DSP fighting your model."

If budget is tight, the **fallback top value pick** is the **MAONO AU-100 / any UAC USB-C lavalier** (~$15–20).

---

## The single most important principle for wake-word audio

**You want the mic's captured audio to match what the model will see in production, and you want to control preprocessing yourself.**

- Wake-word / keyword-spotting pipelines do their *own* front-end: VAD, gain control, sometimes noise suppression or beamforming. Baking heavy DSP into the mic **before** your code sees the samples causes **training/inference feature mismatch** — a documented pitfall in KWS research (see Domain-Aware Training, arXiv:2005.03633).
- So: prefer a mic whose output is **as raw as reasonably possible**. Aggressive hardware AGC, "denoise" and beamforming can *help* human listening but can *hurt* a small-footprint wake-word model if the same processing isn't present (identically) at both train and inference time.
- Collect your training data through **the same signal chain the deployed device will use.** If the Realme 8's own built-in mic + Android AudioRecord path is the deployment target, a fancy external mic can actually make your dataset *less* representative.

---

## AGC / Beamforming: help or hurt? (direct answer)

| Feature | Verdict for wake-word | Why |
|---|---|---|
| **Hardware AGC** | Usually **hurts** for data collection | Non-stationary gain changes the amplitude envelope non-deterministically; hard to reproduce at inference. Prefer fixed/manual gain. If you can't disable it, at least keep it identical for train + test. |
| **Beamforming (mic array)** | **Helps far-field, but only if replicated at inference** | Directional gain toward the speaker dramatically improves far-field SNR. But a beamformed single channel is a *processed* signal — your production device must run the same beamformer, or the model sees a different distribution. |
| **Hardware noise suppression / "denoise"** | **Hurts** unless matched | NS introduces non-linear spectral artifacts. A model trained on NS'd audio degrades on raw audio and vice-versa. |
| **Raw / flat mic (no DSP)** | **Best default** | You own the preprocessing; you can add/remove/augment it in software consistently. |

**Rule of thumb:** for *training-data generation*, favor clean & flat. For *far-field deployment*, use an array **and** run its beamformer/NS at inference too, then collect data through that same array so train == inference.

---

## Near-field vs Far-field tradeoff

- **Near-field (holding/close to phone, <0.5 m):** any decent cardioid lavalier or the VideoMic Me-C is plenty. High SNR, little reverb. A mic **array is overkill** and its beamforming/NS may only add mismatch risk.
- **Far-field (across the room, 2–5 m):** SNR and reverberation dominate. Here a **4-mic array with beamforming + AEC** (ReSpeaker-class) genuinely helps — but note it's built for SBC/PC (Raspberry Pi/Jetson), **not** phones, and pushes you toward matched-preprocessing discipline.
- Realme 8 "always-on plugged-in" scenario is realistically **near/mid-field** — a wired cardioid condenser or lavalier is the sweet spot.

---

## Sample rate

**16 kHz is sufficient** and is the standard for wake-word / KWS models (speech energy is well under 8 kHz; 16 kHz Nyquist = 8 kHz covers it). Android USB audio officially supports 8/11.025/12/16/22.05/24/32/44.1/48 kHz. Most USB-C mics enumerate at 48 kHz — just capture at 48 k and **downsample to 16 k in software** (cleaner than trusting the mic's internal rate switching), or request 16 k directly via `AudioRecord`.

---

## Android USB-Audio (UAC) compatibility caveats — READ before buying

1. **Must be UAC class-compliant.** Android natively supports USB Audio Class devices. Analog-TRRS mics via a USB-C dongle also work but add a DAC in the path.
2. **UAC1 vs UAC2:** Android supports both, but some cheap receivers default to UAC1 (limited rates) or misbehave. UAC2 is safer for full rate support.
3. **Cheap cables kill it:** many USB-C cables omit the D+/D- data lines — mic shows as "charging only" / not detected. Use the mic's own cable or a known data-capable one.
4. **Realme/ColorOS quirk:** some Android skins gate USB audio input behind **Developer Options → "USB audio routing" / "Disable USB audio routing"** toggles. Check these if input isn't detected.
5. **Quick compliance test:** plug in with a tool like **AudioTool** (Android). If it shows a "USB Audio Device" with selectable sample rates → compliant and will record. If it only charges / shows nothing → it won't capture.
6. **Simultaneous charge + record:** a bare USB-C mic occupies the only port. For always-on you may want a USB-C hub/splitter with PD passthrough — verify the hub passes UAC.

---

## Ranked Shortlist

### (a) Simple USB-C lavalier / clip mics — *best default for near-field data*
| Rank | Mic | ~Price | Why | Android/UAC note |
|---|---|---|---|---|
| 1 | **Sennheiser Profile / XS Lav USB-C** | $50–60 (₹4–5k) | Neutral, flat, reliable — minimal DSP, ideal raw capture | Class-compliant USB-C, plug-and-play |
| 2 | **MAONO AU-100 / generic UAC USB-C lav** | $15–20 (₹1.2–1.6k) | Cheap, omnidirectional, "flat enough," great for bulk data collection | Verify UAC + data cable; most work on Android |
| 3 | **Z ZAFFIRO / NPTCL USB-C lapel** | $12–18 | Budget omni clip, decent for near-field | Some add hardware "denoise" — prefer non-denoise SKU |

> Avoid lav mics that heavily advertise "AI noise cancelling / ENC" if you want raw training data.

### (b) USB-C mini shotgun / condenser — *best near-field quality + directionality*
| Rank | Mic | ~Price | Why | Android/UAC note |
|---|---|---|---|---|
| 1 | **RODE VideoMic Me-C** ⭐ | $79 (₹6.5k) | Cardioid condenser, native USB-C digital, clean lightly-processed output, headphone monitor jack | Purpose-built for USB-C Android; class-compliant |
| 2 | **RODE VideoMic Me-C+** | ~$99 | Newer, better capsule/monitoring | Android + iOS USB-C |

### (c) Hardware noise-cancel / mic ARRAY / far-field — *only for across-room deployment*
| Rank | Mic | ~Price | Why | Android/UAC note |
|---|---|---|---|---|
| 1 | **Seeed ReSpeaker USB 4-Mic Array (XVF3000 v2)** | ~$70–80 | 4-mic array, beamforming, AEC, DoA, NS, VAD — real far-field (up to ~5 m). The classic "voice-assistant" front end | **UAC on PC/Raspberry Pi/Jetson; NOT phone-friendly.** Best paired with an SBC, not the Realme 8 |
| 2 | **ReSpeaker XVF3800 4-Mic Array** | ~$90–100 | Newer XMOS, 360° far-field, AGC/beamforming/de-reverb | Same caveat — SBC/PC target |
| — | ReSpeaker 2-Mics / Lite | ~$10–15 | Cheap array for experiments | HAT/I2S, needs a Pi |

> Arrays give you *processed* audio. Only worthwhile if you (i) deploy far-field and (ii) run the same beamformer at inference. For a phone-plugged near-field use case, they add cost + mismatch risk.

---

## Recommendation for THIS project (Realme 8, plugged-in, wake-word datagen)

1. **Buy the RODE VideoMic Me-C** as the primary — clean, directional, guaranteed Android USB-C compatibility. ⭐ **Top pick.**
2. **Also grab a $15 UAC USB-C lavalier** to capture "cheap/consumer mic" variation — real wake-word robustness comes from *diverse* mics, not one perfect mic.
3. **Capture at 48 kHz, downsample to 16 kHz in software.** Keep any hardware AGC/NS **off or constant**, and do gain/VAD/augmentation yourself so train == inference.
4. Skip the ReSpeaker arrays **unless** you pivot to a true across-the-room, SBC-hosted deployment.

---

### Sources
- Engadget — best mobile microphones 2026: https://www.engadget.com/computing/accessories/best-mobile-microphones-for-recording-with-a-phone-154536629.html
- SYNCO — best wireless lav for Android: https://www.syncoaudio.com/blogs/news/best-wireless-lavalier-microphone-for-android
- B&H — RODE VideoMic Me-C (USB-C Android shotgun): https://www.bhphotovideo.com/c/product/1632902-REG/rode_videomic_me_c_directional_microphone.html
- Android AOSP — USB digital audio (supported sample rates / UAC): https://source.android.com/docs/core/audio/usb
- Alibaba Electronics — USB-C mic Android compatibility/UAC1 vs UAC2, cable/data-line caveats: https://electronics.alibaba.com/question/wireless-lavalier-mic-for-android-setup,-compatibility-real-world-tips
- Seeed Studio — ReSpeaker USB 4-Mic Array (beamforming/AEC/DoA/far-field): https://www.seeedstudio.com/ReSpeaker-USB-Mic-Array-p-4247.html
- Seeed Studio — ReSpeaker XVF3800 far-field array: https://wiki.seeedstudio.com/respeaker_xvf3800_introduction/
- Domain-Aware Training for Far-field Small-footprint Keyword Spotting (arXiv:2005.03633): https://arxiv.org/pdf/2005.03633
