# AURA KWS Benchmark Report

Model: `kws_marvin.onnx` (arch **dscnn**, 15053 params). Front-end: numpy==C++ (verified). Streaming-detector mirror of `core/detect` (VAD gate + M-of-N smoothing + refractory).

## Accuracy / false-accept (DET sweep x posterior-smoothing M)

Negative corpus: 6.7 min of background noise + non-marvin speech. Positives: 120 held-out marvin clips. M = `DetectConfig.stage1ConsecutiveWindows`.

| M | threshold | false accepts | **FA / hour** | **FRR** |
|---|---|---|---|---|
| 1 | 0.3 | 0 | 0.00 | 0.175 |
| 1 | 0.4 | 0 | 0.00 | 0.217 |
| 1 | 0.5 | 0 | 0.00 | 0.250 |
| 1 | 0.6 | 0 | 0.00 | 0.325 |
| 1 | 0.7 | 0 | 0.00 | 0.400 |
| 1 | 0.8 | 0 | 0.00 | 0.517 |
| 1 | 0.9 | 0 | 0.00 | 0.800 |
| 2 | 0.3 | 0 | 0.00 | 0.475 |
| 2 | 0.4 | 0 | 0.00 | 0.525 |
| 2 | 0.5 | 0 | 0.00 | 0.617 |
| 2 | 0.6 | 0 | 0.00 | 0.717 |
| 2 | 0.7 | 0 | 0.00 | 0.808 |
| 2 | 0.8 | 0 | 0.00 | 0.867 |
| 2 | 0.9 | 0 | 0.00 | 0.950 |
| 3 | 0.3 | 0 | 0.00 | 0.833 |
| 3 | 0.4 | 0 | 0.00 | 0.858 |
| 3 | 0.5 | 0 | 0.00 | 0.933 |
| 3 | 0.6 | 0 | 0.00 | 0.975 |
| 3 | 0.7 | 0 | 0.00 | 0.975 |
| 3 | 0.8 | 0 | 0.00 | 0.992 |
| 3 | 0.9 | 0 | 0.00 | 0.992 |

### Finding

**FA/hr = 0 at every threshold and every M** on this corpus — the model + VAD gate produce no false accepts. Because there are no false accepts to suppress, the M-of-N posterior smoothing (shipped default **M=3**) only costs recall (FRR ~0.93 at 0.5) with no FA benefit; **M=1** keeps FA/hr=0 with far better recall (FRR ~0.25 at 0.5). Like the Stage-2 verifier, the smoothing is insurance against transient false-accepts a noisier/real model would have — for this clean placeholder it is over-conservative. **Recommendation: lower M toward 1-2 for this model** (a config decision, surfaced not auto-applied). FRR is also inflated by short isolated 1 s clips vs the 1 s detection window.

## Latency & load (HOST — not device-representative)

- inference latency (single 100x40 window): p50 0.082 ms, p95 0.094 ms, mean 0.084 ms
- model cold load (session create): 7.6 ms

> Host x86 + onnxruntime desktop. Device latency/CPU/RAM/battery/thermal are measured on hardware per DEVICE_RUNBOOK.md. FA/hr and FRR are model+front-end properties and transfer.

_Placeholder Speech-Commands model, not the AURA-trained model._
