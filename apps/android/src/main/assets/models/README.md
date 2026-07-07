# Placeholder model assets

The reference app expects two ONNX models here at build/run time:

| File | What it is | License | How to obtain |
|---|---|---|---|
| `silero_vad.onnx` | Silero VAD (voice activity detection) | MIT | Download from the [snakers4/silero-vad](https://github.com/snakers4/silero-vad) repo (`files/silero_vad.onnx`). |
| `kws_marvin.onnx` | **Placeholder** keyword-spotting model that fires on "marvin" | (source-dependent) | Generate/convert with `python tools/convert_kws_model.py` — see that script for the exact source model and the front-end contract it documents. |

**These are NOT the AURA-trained model** (which does not exist yet — the research
track produces it later). `kws_marvin.onnx` is a stand-in so the pipeline is
exercised end-to-end. See the repo `REPORT.md` "Placeholders" section.

The models are git-ignored (binary). CI / a developer must place them here before
`:apps:android:assembleDebug` packages the APK. The app degrades gracefully (shows
an "init failed" status) if they are missing rather than crashing.

**Feature front-end must match** `kws_marvin.onnx`'s training front-end
(16 kHz, 25 ms/10 ms, 40 log-Mel) — this alignment is configured in
`core/config/Config.h` (`FeatureConfig`) and is the single biggest integration
risk for the placeholder (Stage 7 M3). `tools/convert_kws_model.py` prints the
exact front-end it assumes.
