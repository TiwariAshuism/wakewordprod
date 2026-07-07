# AURA KWS — Architecture Head-to-Head (robustness sprint)

Same augmented + stabilized training pipeline, same 13-class task, same front-end. Metrics on the held-out Speech Commands test split (marvin TP / non-marvin FP at softmax threshold 0.5). `noisy` = one augmentation pass (noise/reverb/speed) on the same test clips.

| arch | params | marvin F1 (clean) | clean TP@.5 | clean FP@.5 | noisy TP@.5 | noisy FP@.5 |
|---|---|---|---|---|---|---|
| dscnn **(winner)** | 15053 | 0.921 | 0.831 | 0.002 | 0.805 | 0.000 |
| cnn | 32317 | 0.853 | 0.692 | 0.001 | 0.631 | 0.001 |
| bcresnet | 8077 | 0.813 | 0.692 | 0.004 | 0.610 | 0.003 |

**Winner: `dscnn`** - selected by highest noisy TP@0.5 with FP <= 0.1 on both splits (tie-break: fewer params). Exported as the shipped `kws_marvin.onnx`. Placeholder weights (Speech Commands), not the AURA-trained model.

## Before / after vs the v1 baseline (host DET sweep, `tools/verify_kws_host.py`)

The v1 model was the un-augmented, bouncy-trained CNN. The sprint winner (dscnn) at the
same operating points:

| operating point | v1 baseline (clean) | v2 dscnn (clean) | v2 dscnn (NOISY: noise/reverb/speed) |
|---|---|---|---|
| marvin TP @ 0.6 | 47.7% | **77.4%** | **70.3%** |
| marvin TP @ 0.5 | 55.9% | **83.1%** | **77.4%** |
| non-marvin FP @ 0.5 | 0.7% | 0.0% | 0.3% |
| silence FP | 0.0% | 0.0% | 0.0% |

**+30 points** of clean true-positive at the same 0% false-accept, and — the point of the
sprint — **~70–77% recall retained under noise/reverb** where the baseline was never even
evaluated (and, being clean-only trained, would degrade sharply). The default
`DetectConfig.stage1Threshold` was moved 0.6 → **0.5** (chosen from this curve: big TP gain
at still-~0% FP). Layered on top: **posterior smoothing** (`stage1ConsecutiveWindows`, M-of-N
positive windows) makes the *decision* robust to transient-noise single-window spikes,
independent of the model.

### Levers applied (all algorithm-only)
Waveform augmentation (noise @ SNR curriculum, synthetic-RIR reverb, speed ±15%, gain,
time-shift) + online SpecAugment; cosine-LR + warmup + label-smoothing + early-stop on
marvin-F1 (stable vs the old 0.33↔0.64 bounce); dedicated `_silence_` class + hard-negative
`_unknown_`; DS-CNN / BC-ResNet / CNN head-to-head. Front-end unchanged (numpy==C++
alignment preserved), so no on-device front-end change was needed.
