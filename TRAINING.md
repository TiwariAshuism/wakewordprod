# Training a wake word — quickstart

Train a custom wake-word model in four steps. Everything is driven by one file:
`config.yaml`.

## 1. Drop your audio in

```
datasets/<wake_word>/positive/*.wav    # clips that SAY the wake word
datasets/<wake_word>/negative/*.wav    # other speech, noise, near-misses
```

16 kHz mono WAV. More negatives = fewer false alarms. See `datasets/README.md` for the
filename convention that gives a clean speaker-independent split.

## 2. Edit `config.yaml`

At minimum set:

```yaml
wake_word: hey_aura
dataset_dir: datasets/hey_aura
```

Every field is commented in `config.yaml` (epochs, architecture, optional Stage-2
cascade, calibration).

## 3. Train

```bash
python train.py
```

Writes to `models/` (or your `output_dir`):

- `<wake_word>.onnx` — Stage-1 detector
- `<wake_word>_stage2.onnx` — optional Stage-2 verifier (if `stage2.enabled: true`)
- `labels.json` — `num_classes` / `target_index` (+ a `calibration` block if enabled)

## 4. Evaluate

```bash
python evaluate.py
```

Runs the streaming-detector mirror on the held-out (unseen-speaker) split and reports
**FA/hr**, **FRR**, and **ECE/MCE** calibration quality, writing
`benchmarks/dashboards/<wake_word>_eval.md`.

## Optional

- **Calibration** — set `calibrate: true` in `config.yaml` to fit Platt/temperature
  scaling on the held-out split and write a `calibration` block into `labels.json`
  (used by `evaluate.py` and the on-device scorer).
- **On-device deploy** — copy `<wake_word>.onnx` (+ `_stage2.onnx`) and `labels.json`
  into the app's model assets. INT8 quantization: see `tools/quant_heym_int8.py`.

## Under the hood (reused tools)

`train.py` / `evaluate.py` are thin wrappers over `tools/`:
`aura_data.py` (loader + speaker-independent split), `aura_frontend.py` (DSP + log-Mel,
mirrors the on-device C++ path), `aura_augment.py`, `kws_models.py` (model zoo),
`aura_train.py` (trainer), `calibrate.py` (ECE/MCE + calibration).
