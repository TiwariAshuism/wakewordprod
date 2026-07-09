#!/usr/bin/env python3
"""Easy wake-word TRAINING entry point — one config, one command.

    python train.py                 # uses ./config.yaml
    python train.py --config my.yaml

Reads config.yaml, loads datasets/<wake_word>/{positive,negative} with a speaker-independent
split (tools/aura_data.py), trains Stage-1 (+ optional Stage-2) via tools/aura_train.py,
exports ONNX + labels.json into output_dir, and optionally fits confidence calibration
(tools/calibrate.py). See TRAINING.md.
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.join(HERE, "tools")


# --------------------------------------------------------------------------- config
def load_config(path):
    """Read the YAML config. Uses pyyaml if available, else a tiny indent-aware parser that
    supports the flat scalars + the one nested block (`stage2:`) this config uses."""
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    try:
        import yaml
        return yaml.safe_load(text)
    except Exception:
        return _mini_yaml(text)


def _coerce(v):
    s = v.strip()
    if s == "" or s.startswith("#"):
        return None
    s = s.split(" #", 1)[0].strip()  # strip trailing inline comment
    if s.lower() in ("true", "false"):
        return s.lower() == "true"
    if s.lower() in ("null", "none", "~"):
        return None
    try:
        return int(s)
    except ValueError:
        pass
    try:
        return float(s)
    except ValueError:
        pass
    return s.strip('"').strip("'")


def _mini_yaml(text):
    """Minimal fallback parser: `key: value` lines + a single level of nesting (2-space
    indent). Enough for this config; ignores comments/blank lines."""
    root, cur = {}, None
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        key, _, val = line.strip().partition(":")
        key = key.strip()
        if indent == 0:
            if val.strip() == "":
                cur = {}
                root[key] = cur
            else:
                root[key] = _coerce(val)
                cur = None
        else:
            if cur is not None:
                cur[key] = _coerce(val)
    return root


# --------------------------------------------------------------------------- calibration
def _run_calibration(labels_path, stages, target, dataset_dir, wake_word):
    """Fit + write a calibration block into labels.json using the held-out (speaker-
    independent) test split. Reuses tools/calibrate.py primitives. `stages` = list of
    (stage_name, onnx_path)."""
    import numpy as np
    import onnxruntime as ort
    import aura_frontend as fe
    import aura_data
    import calibrate as cal

    def collect(sess, in_name):
        Z, y = [], []
        for path, label, spk, acc in aura_data.items("test", dataset_dir=dataset_dir,
                                                      wake_word=wake_word):
            x = aura_data.read_wav(path)
            feat = fe.features(x, apply_dsp_chain=True, frames=fe.WINDOW_FRAMES)[None].astype(np.float32)
            Z.append(sess.run(None, {in_name: feat})[0][0]); y.append(int(label))
        return np.asarray(Z, np.float64), np.asarray(y, np.int64)

    block = {"method": "none", "stage1": {"a": 1.0, "b": 0.0, "temperature": 1.0},
             "stage2": {"a": 1.0, "b": 0.0, "temperature": 1.0}}
    per_stage_ece, summaries = {}, []
    for stage_name, onnx_path in stages:
        sess = ort.InferenceSession(onnx_path, providers=["CPUExecutionProvider"])
        in_name = sess.get_inputs()[0].name
        Z, y = collect(sess, in_name)
        if len(y) < 4 or (y == 1).sum() == 0 or (y == 0).sum() == 0:
            print(f"  ! calibration: too few held-out clips for {stage_name}; leaving identity")
            continue
        # deterministic half/half split for fit vs eval
        idx = np.arange(len(y)); fit = idx % 2 == 0; ev = ~fit
        if y[fit].sum() == 0 or y[ev].sum() == 0:  # keep both halves non-degenerate
            fit, ev = idx < len(y) // 2, idx >= len(y) // 2
        a, b = cal.fit_platt(Z[fit], y[fit], target)
        T = cal.fit_temperature(Z[fit], y[fit])
        m_none = cal.all_metrics(cal.uncal_posterior(Z[ev], target), y[ev])
        m_platt = cal.all_metrics(cal.platt_posterior(Z[ev], target, a, b), y[ev])
        m_temp = cal.all_metrics(cal.temp_posterior(Z[ev], target, T), y[ev])
        block[stage_name] = {"a": round(a, 6), "b": round(b, 6), "temperature": round(T, 6)}
        per_stage_ece[stage_name] = {"none": m_none["ece"], "platt": m_platt["ece"],
                                     "temperature": m_temp["ece"]}
        summaries.append(f"{stage_name}: ECE none={m_none['ece']:.4f} "
                         f"platt={m_platt['ece']:.4f} temp={m_temp['ece']:.4f}")

    # global method = lowest summed eval ECE across stages
    if per_stage_ece:
        totals = {mth: sum(s[mth] for s in per_stage_ece.values())
                  for mth in ("none", "platt", "temperature")}
        block["method"] = min(totals, key=totals.get)
    with open(labels_path, "r", encoding="utf-8") as f:
        labels = json.load(f)
    labels["calibration"] = block
    with open(labels_path, "w", encoding="utf-8") as f:
        json.dump(labels, f, indent=2); f.write("\n")
    for s in summaries:
        print("  " + s)
    print(f"  calibration method chosen: {block['method']}  -> {labels_path}")


# --------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(
        description="Train a wake-word model from a single config.yaml.")
    ap.add_argument("--config", default=os.path.join(HERE, "config.yaml"),
                    help="path to config.yaml (default: ./config.yaml)")
    args = ap.parse_args()

    if not os.path.exists(args.config):
        sys.exit(f"config not found: {args.config}")
    cfg = load_config(args.config)
    wake_word = cfg.get("wake_word", "hey_aura")
    dataset_dir = os.path.join(HERE, cfg.get("dataset_dir", f"datasets/{wake_word}"))
    output_dir = os.path.join(HERE, cfg.get("output_dir", "models"))
    epochs = int(cfg.get("epochs", 25))
    arch = cfg.get("arch", "dscnn")
    stage2_cfg = cfg.get("stage2") or {}
    stage2_on = bool(stage2_cfg.get("enabled", False))
    stage2_arch = stage2_cfg.get("arch", "cnn")
    do_calibrate = bool(cfg.get("calibrate", False))

    # tools/ on path (heavy imports live here — deferred until after --help).
    sys.path.insert(0, TOOLS)
    import aura_train

    if not os.path.isdir(dataset_dir):
        sys.exit(f"dataset_dir not found: {dataset_dir}\n"
                 f"Create {dataset_dir}/positive/*.wav and {dataset_dir}/negative/*.wav "
                 f"(see datasets/README.md).")

    print(f"wake_word={wake_word}  dataset_dir={dataset_dir}  output_dir={output_dir}")
    os.makedirs(output_dir, exist_ok=True)

    # Shared, arch-independent feature cache lives in output_dir.
    cache = os.path.join(output_dir, f"{wake_word}_features.npz")
    Xtr, ytr, Xte, yte = aura_train.prepare_features(
        dataset_dir=dataset_dir, wake_word=wake_word, cache_path=cache)
    import numpy as np
    print(f"features: train={Xtr.shape} test={Xte.shape} "
          f"pos_tr={int(ytr.sum())} neg_tr={int((ytr == 0).sum())} "
          f"pos_te={int(yte.sum())} neg_te={int((yte == 0).sum())}")
    if len(ytr) == 0 or ytr.sum() == 0:
        sys.exit("no positive training clips found — check datasets/<wake_word>/positive/*.wav")

    labels = {"wake_word": wake_word, "num_classes": 2, "target_index": 1,
              "labels": ["not_wake", wake_word], "sample_rate": int(cfg.get("sample_rate", 16000))}
    stage_paths = []

    # ---- Stage 1 ----
    print(f"[stage1/{arch}] training {epochs} epochs ...")
    model1, m1 = aura_train.train_arch(arch, Xtr, ytr, Xte, yte, epochs=epochs)
    s1_onnx = os.path.join(output_dir, f"{wake_word}.onnx")
    aura_train.export_onnx(model1, s1_onnx)
    m1["onnx"] = os.path.basename(s1_onnx)
    m1["size_kb"] = round(os.path.getsize(s1_onnx) / 1024, 1)
    labels["stage1"] = m1
    stage_paths.append(("stage1", s1_onnx))
    print(f"[stage1/{arch}] F1={m1['f1']:.3f} recall={m1['recall']:.3f} "
          f"per-clip-FAR={m1['per_clip_far']:.3f} size={m1['size_kb']}KB -> {s1_onnx}")

    # ---- Stage 2 (optional cascade verifier) ----
    if stage2_on:
        print(f"[stage2/{stage2_arch}] training {epochs} epochs ...")
        model2, m2 = aura_train.train_arch(stage2_arch, Xtr, ytr, Xte, yte, epochs=epochs)
        s2_onnx = os.path.join(output_dir, f"{wake_word}_stage2.onnx")
        aura_train.export_onnx(model2, s2_onnx)
        m2["onnx"] = os.path.basename(s2_onnx)
        m2["size_kb"] = round(os.path.getsize(s2_onnx) / 1024, 1)
        labels["stage2"] = m2
        stage_paths.append(("stage2", s2_onnx))
        print(f"[stage2/{stage2_arch}] F1={m2['f1']:.3f} recall={m2['recall']:.3f} "
              f"per-clip-FAR={m2['per_clip_far']:.3f} size={m2['size_kb']}KB -> {s2_onnx}")
    else:
        labels["stage2"] = None

    labels_path = os.path.join(output_dir, "labels.json")
    with open(labels_path, "w", encoding="utf-8") as f:
        json.dump(labels, f, indent=2); f.write("\n")

    # ---- Optional calibration ----
    if do_calibrate:
        print("[calibrate] fitting confidence calibration on held-out split ...")
        try:
            _run_calibration(labels_path, stage_paths, labels["target_index"],
                             dataset_dir, wake_word)
        except Exception as e:
            print(f"  ! calibration skipped ({type(e).__name__}: {e})")

    print("\nartifacts:")
    print(f"  stage1 : {s1_onnx}")
    if stage2_on:
        print(f"  stage2 : {os.path.join(output_dir, wake_word + '_stage2.onnx')}")
    print(f"  labels : {labels_path}")
    print(f"  cache  : {cache}")
    print(f"\nNext: python evaluate.py --config {os.path.relpath(args.config, HERE)}")


if __name__ == "__main__":
    main()
