#!/usr/bin/env python3
"""Confidence calibration for the shipped 'hey aura' wake-word models (Plan Part A).

Fits and MEASURES calibration for the shipped Stage-1 (aura.onnx) and Stage-2
(aura_stage2.onnx) models, then writes the winning params into the model's
labels.json 'calibration' block and a before/after report.

Pipeline (identical to the on-device / benchmark path):
  wav -> tools/aura_frontend.features() (DSP + log-Mel, [100,40]) -> onnxruntime -> logits[2]
  target-class softmax posterior computed EXACTLY like benchmarks/harness/bench_kws.py:81-83
      z = z - z.max(); e = exp(z); p = (e / e.sum())[target_index]

Held-out data comes from tools/aura_data.py (accent-independent test split). Report rule 2:
we split the held-out accents in HALF — one half CALIBRATES (fits a,b / T), the other half
is the EVAL set (all before/after ECE/MCE/Brier/AUROC are measured on the eval half, which is
also the FA/hr eval set). The two halves share NO accent, so fit and eval never overlap.

Two methods:
  * Platt  (primary):  p = sigmoid(a*z + b),  z = target-class logit   (binary decision)
  * Temperature (comparison): softmax(logits / T),  T fit by minimizing NLL

Winner = lowest eval ECE (10-bin) that does NOT degrade eval AUROC. The block schema is fixed:
  {"calibration":{"method":"platt"|"temperature"|"none",
                  "stage1":{"a":..,"b":..,"temperature":..},
                  "stage2":{"a":..,"b":..,"temperature":..}}}
Each stage always carries BOTH the Platt (a,b) and the temperature; `method` selects which the
consumer applies. Missing/absent calibration -> identity (a=1, b=0, T=1, method=none).

Run:  python tools/calibrate.py
"""
import argparse
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import aura_frontend as fe
import aura_data

ASSET = os.path.join(HERE, "..", "apps", "android", "src", "main", "assets", "models")
DASH = os.path.join(HERE, "..", "benchmarks", "dashboards")

# ---- Report rule 2: split the held-out accents in half (disjoint fit vs eval) ----
# aura_data.TEST_ACCENTS = {en-gb-scotland, en-gb-x-gbclan, uk, us}
CALIB_ACCENTS = {"en-gb-scotland", "uk"}   # ~105 pos + 512 neg  -> fits a,b / T
EVAL_ACCENTS = {"en-gb-x-gbclan", "us"}    # ~105 pos + 522 neg  -> before/after metrics (FA/hr eval set)


# ---------------------------------------------------------------- math helpers
def softmax_rows(Z):
    Z = Z - Z.max(axis=1, keepdims=True)
    E = np.exp(Z)
    return E / E.sum(axis=1, keepdims=True)


def sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))


def uncal_posterior(Z, target):
    """Target-class softmax posterior, exactly like bench_kws.py:81-83 (per row)."""
    return softmax_rows(Z)[:, target]


def platt_posterior(Z, target, a, b):
    return sigmoid(a * Z[:, target] + b)


def temp_posterior(Z, target, T):
    return softmax_rows(Z / T)[:, target]


# ---------------------------------------------------------------- fitting
def fit_platt(Z, y, target):
    """Fit p = sigmoid(a*z + b) on the target logit by minimizing binary NLL."""
    from scipy.optimize import minimize
    z = Z[:, target].astype(np.float64)
    yy = y.astype(np.float64)
    eps = 1e-12

    def nll(theta):
        a, b = theta
        p = np.clip(sigmoid(a * z + b), eps, 1 - eps)
        return -np.mean(yy * np.log(p) + (1 - yy) * np.log(1 - p))

    res = minimize(nll, np.array([1.0, 0.0]), method="L-BFGS-B")
    a, b = float(res.x[0]), float(res.x[1])
    return a, b


def fit_temperature(Z, y):
    """Temperature scaling: minimize multi-class NLL of softmax(logits/T). Returns T>0."""
    from scipy.optimize import minimize_scalar
    Zd = Z.astype(np.float64)
    idx = np.arange(len(y))
    eps = 1e-12

    def nll(logT):
        T = np.exp(logT)
        P = softmax_rows(Zd / T)
        p = np.clip(P[idx, y], eps, 1 - eps)
        return -np.mean(np.log(p))

    res = minimize_scalar(nll, bounds=(np.log(0.05), np.log(20.0)), method="bounded")
    return float(np.exp(res.x))


# ---------------------------------------------------------------- metrics
def ece_mce(p, y, bins=10):
    """Expected & Maximum Calibration Error over `bins` equal-width confidence bins."""
    p = np.asarray(p, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    edges = np.linspace(0.0, 1.0, bins + 1)
    N = len(p)
    ece = 0.0
    mce = 0.0
    per_bin = []
    for i in range(bins):
        lo, hi = edges[i], edges[i + 1]
        mask = (p > lo) & (p <= hi) if i > 0 else (p >= lo) & (p <= hi)
        cnt = int(mask.sum())
        if cnt == 0:
            per_bin.append((lo, hi, 0, float("nan"), float("nan")))
            continue
        conf = float(p[mask].mean())
        acc = float(y[mask].mean())
        gap = abs(acc - conf)
        ece += cnt / N * gap
        mce = max(mce, gap)
        per_bin.append((lo, hi, cnt, conf, acc))
    return ece, mce, per_bin


def brier(p, y):
    return float(np.mean((np.asarray(p, np.float64) - np.asarray(y, np.float64)) ** 2))


def auroc(p, y):
    """AUROC via the Mann-Whitney U statistic (tie-aware average ranks)."""
    from scipy.stats import rankdata
    p = np.asarray(p, np.float64)
    y = np.asarray(y)
    n_pos = int((y == 1).sum())
    n_neg = int((y == 0).sum())
    if n_pos == 0 or n_neg == 0:
        return float("nan")
    r = rankdata(p)
    return float((r[y == 1].sum() - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg))


def all_metrics(p, y, bins=10):
    ece, mce, per_bin = ece_mce(p, y, bins)
    return {"ece": ece, "mce": mce, "brier": brier(p, y),
            "auroc": auroc(p, y), "per_bin": per_bin}


# ---------------------------------------------------------------- data
def collect_logits(sess, in_name, accents):
    """Score every held-out clip whose accent is in `accents` as a single 100-frame window.
    Returns (Z[N,2] logits, y[N] labels). One (logit, label) per clip."""
    Z, y = [], []
    for path, label, spk, acc in aura_data.items("test"):
        if acc not in accents:
            continue
        x = aura_data.read_wav(path)
        feat = fe.features(x, apply_dsp_chain=True, frames=fe.WINDOW_FRAMES)[None].astype(np.float32)
        z = sess.run(None, {in_name: feat})[0][0]
        Z.append(z)
        y.append(int(label))
    return np.asarray(Z, np.float64), np.asarray(y, np.int64)


# ---------------------------------------------------------------- apply (importable by harnesses)
def load_calibration(path):
    """Load the calibration block from a labels.json. Absent -> identity/none."""
    try:
        with open(path) as f:
            cal = json.load(f).get("calibration")
    except Exception:
        cal = None
    if not cal:
        return {"method": "none", "stage1": {}, "stage2": {}}
    return cal


def apply_calibration(z_vec, cal, stage, target):
    """Apply a calibration block to a raw logits vector -> calibrated target posterior.

    method=temperature: softmax(z / T)[target]
    method=platt:       sigmoid(a * z[target] + b)
    method=none:        plain softmax(z)[target]   (identity)
    """
    z = np.asarray(z_vec, np.float64)
    method = (cal or {}).get("method", "none")
    st = (cal or {}).get(stage, {}) or {}
    if method == "temperature":
        T = st.get("temperature", 1.0) or 1.0
        zz = z / T
    elif method == "platt":
        a = st.get("a", 1.0)
        b = st.get("b", 0.0)
        return float(sigmoid(a * z[target] + b))
    else:
        zz = z
    zz = zz - zz.max()
    e = np.exp(zz)
    return float((e / e.sum())[target])


# ---------------------------------------------------------------- reliability rendering
def reliability_ascii(per_bin, width=40):
    lines = ["  bin        n     conf    acc   gap  reliability(conf=|, acc=#)"]
    for lo, hi, cnt, conf, acc in per_bin:
        if cnt == 0:
            lines.append(f"  {lo:.1f}-{hi:.1f}    0        -      -     -")
            continue
        gap = abs(acc - conf)
        bar = [" "] * width
        ci = min(width - 1, int(conf * width))
        ai = min(width - 1, int(acc * width))
        bar[ci] = "|"
        bar[ai] = "#" if ai != ci else "X"
        lines.append(f"  {lo:.1f}-{hi:.1f}  {cnt:5d}   {conf:.3f}  {acc:.3f}  {gap:.3f}  {''.join(bar)}")
    return "\n".join(lines)


def reliability_png(png_path, curves):
    """curves: list of (label, per_bin). Save a reliability diagram PNG."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as e:
        print(f"(matplotlib unavailable, skipping PNG: {e})")
        return False
    fig, ax = plt.subplots(figsize=(5, 5))
    ax.plot([0, 1], [0, 1], "--", color="gray", lw=1, label="perfect")
    for label, per_bin in curves:
        xs = [(lo + hi) / 2 for lo, hi, c, conf, acc in per_bin if c > 0]
        ys = [acc for lo, hi, c, conf, acc in per_bin if c > 0]
        ax.plot(xs, ys, "-o", ms=4, label=label)
    ax.set_xlabel("confidence (predicted target posterior)")
    ax.set_ylabel("empirical accuracy (target rate)")
    ax.set_title("Reliability diagram")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.legend(loc="upper left", fontsize=8)
    fig.tight_layout()
    fig.savefig(png_path, dpi=110)
    plt.close(fig)
    return True


# ---------------------------------------------------------------- per-model fit+eval
def calibrate_model(sess, in_name, target, stage_name):
    """Fit on CALIB_ACCENTS, measure before/after on EVAL_ACCENTS. Returns a result dict."""
    Zc, yc = collect_logits(sess, in_name, CALIB_ACCENTS)
    Ze, ye = collect_logits(sess, in_name, EVAL_ACCENTS)

    a, b = fit_platt(Zc, yc, target)
    T = fit_temperature(Zc, yc)

    p_none = uncal_posterior(Ze, target)
    p_platt = platt_posterior(Ze, target, a, b)
    p_temp = temp_posterior(Ze, target, T)

    m_none = all_metrics(p_none, ye)
    m_platt = all_metrics(p_platt, ye)
    m_temp = all_metrics(p_temp, ye)

    # Winner: lowest eval ECE that does NOT degrade eval AUROC (vs uncalibrated).
    auroc_floor = m_none["auroc"] - 1e-9
    cands = [("none", m_none), ("platt", m_platt), ("temperature", m_temp)]
    eligible = [(name, m) for name, m in cands
                if np.isnan(m["auroc"]) or m["auroc"] >= auroc_floor]
    if not eligible:
        eligible = cands
    winner = min(eligible, key=lambda nm: nm[1]["ece"])[0]

    return {
        "stage": stage_name, "target": target,
        "n_calib": len(yc), "n_eval": len(ye),
        "pos_eval": int((ye == 1).sum()), "neg_eval": int((ye == 0).sum()),
        "a": a, "b": b, "temperature": T,
        "metrics": {"none": m_none, "platt": m_platt, "temperature": m_temp},
        "posteriors": {"none": p_none, "platt": p_platt, "temperature": p_temp},
        "winner": winner, "y_eval": ye,
    }


# ---------------------------------------------------------------- report
def _mrow(name, m):
    au = "nan" if np.isnan(m["auroc"]) else f"{m['auroc']:.4f}"
    return f"| {name} | {m['ece']:.4f} | {m['mce']:.4f} | {m['brier']:.4f} | {au} |"


def write_report(path, results, chosen_method, png_ok, png_rel):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("# Confidence Calibration Report — 'hey aura'\n\n")
        f.write("Held-out (accent-independent) data split in HALF (report rule 2): "
                f"**calibration accents** = `{sorted(CALIB_ACCENTS)}` (fits a,b / T), "
                f"**eval accents** = `{sorted(EVAL_ACCENTS)}` (before/after metrics; the FA/hr "
                "eval set). The two halves share no accent.\n\n")
        f.write("Target-class softmax posterior computed exactly like "
                "`benchmarks/harness/bench_kws.py:81-83`. Platt = `sigmoid(a*z+b)` on the "
                "target logit (primary); Temperature = `softmax(logits/T)` (comparison). "
                "Winner = lowest 10-bin ECE that does not degrade AUROC.\n\n")
        f.write(f"**Chosen `method` written to labels.json: `{chosen_method}`.**\n\n")
        for r in results:
            f.write(f"## {r['stage']}  (target_index={r['target']})\n\n")
            f.write(f"Calibration clips: {r['n_calib']}  |  Eval clips: {r['n_eval']} "
                    f"(pos={r['pos_eval']}, neg={r['neg_eval']}).  "
                    f"Fitted: Platt a={r['a']:.4f} b={r['b']:.4f}; Temperature T={r['temperature']:.4f}.\n\n")
            f.write("### Before vs after (measured on eval half)\n\n")
            f.write("| method | ECE (10-bin) | MCE | Brier | AUROC |\n|---|---|---|---|---|\n")
            f.write(_mrow("none (before)", r["metrics"]["none"]) + "\n")
            f.write(_mrow("platt", r["metrics"]["platt"]) + "\n")
            f.write(_mrow("temperature", r["metrics"]["temperature"]) + "\n")
            f.write(f"\nStage winner (lowest ECE, AUROC not degraded): **{r['winner']}**.\n\n")
            f.write("### Reliability (eval half, uncalibrated vs winner)\n\n```\n")
            f.write("-- uncalibrated --\n")
            f.write(reliability_ascii(r["metrics"]["none"]["per_bin"]) + "\n\n")
            f.write(f"-- {r['winner']} --\n")
            f.write(reliability_ascii(r["metrics"][r["winner"]]["per_bin"]) + "\n```\n\n")
        if png_ok:
            f.write(f"Reliability diagram (PNG): `{png_rel}`\n\n")
        f.write("_Params written into the model's `labels.json` `calibration` block; each stage "
                "carries both Platt (a,b) and temperature, and `method` selects which applies. "
                "Consumers apply it via `calibrate.apply_calibration` "
                "(bench_kws / heym_eval `--calibration`)._\n")


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--labels", default=os.path.join(ASSET, "labels.json"))
    ap.add_argument("--stage1", default=os.path.join(ASSET, "aura.onnx"))
    ap.add_argument("--stage2", default=os.path.join(ASSET, "aura_stage2.onnx"))
    ap.add_argument("--report", default=os.path.join(DASH, "calibration_report.md"))
    args = ap.parse_args()

    import onnxruntime as ort
    with open(args.labels) as f:
        labels = json.load(f)
    target = int(labels.get("target_index", 1))

    print(f"target_index={target}")
    print(f"calibration accents {sorted(CALIB_ACCENTS)} | eval accents {sorted(EVAL_ACCENTS)}")

    results = []
    for stage_name, path in (("stage1", args.stage1), ("stage2", args.stage2)):
        if not os.path.exists(path):
            print(f"  ! {stage_name} model missing: {path} — skipping")
            continue
        sess = ort.InferenceSession(path, providers=["CPUExecutionProvider"])
        in_name = sess.get_inputs()[0].name
        print(f"scoring {stage_name} ({os.path.basename(path)}) ...")
        r = calibrate_model(sess, in_name, target, stage_name)
        results.append(r)
        mn, mp, mt = r["metrics"]["none"], r["metrics"]["platt"], r["metrics"]["temperature"]
        print(f"  {stage_name}: ECE before={mn['ece']:.4f}  "
              f"platt={mp['ece']:.4f}  temp={mt['ece']:.4f}  -> winner={r['winner']}  "
              f"(a={r['a']:.3f} b={r['b']:.3f} T={r['temperature']:.3f})")

    if not results:
        print("No models scored; aborting.")
        sys.exit(1)

    # Global method (schema has a single `method`): pick the method minimizing summed eval
    # ECE across stages, subject to not degrading AUROC on any stage.
    methods = ["none", "platt", "temperature"]
    def method_ok(mth):
        for r in results:
            au0 = r["metrics"]["none"]["auroc"]
            au = r["metrics"][mth]["auroc"]
            if not (np.isnan(au) or np.isnan(au0)) and au < au0 - 1e-9:
                return False
        return True
    def method_ece(mth):
        return sum(r["metrics"][mth]["ece"] for r in results)
    ok_methods = [m for m in methods if method_ok(m)] or ["none"]
    chosen = min(ok_methods, key=method_ece)
    print(f"global chosen method: {chosen}  (summed eval ECE={method_ece(chosen):.4f})")

    # Reliability PNG (stage1 preferred): uncalibrated vs chosen method
    os.makedirs(DASH, exist_ok=True)
    png_path = os.path.join(DASH, "calibration_reliability.png")
    r0 = results[0]
    curves = [("uncalibrated", r0["metrics"]["none"]["per_bin"]),
              (f"{chosen}", r0["metrics"][chosen if chosen != 'none' else 'none']["per_bin"])]
    png_ok = reliability_png(png_path, curves)

    # Write the calibration block (fixed schema). Each stage carries both Platt + temperature.
    block = {"method": chosen, "stage1": {}, "stage2": {}}
    for r in results:
        block[r["stage"]] = {"a": round(r["a"], 6), "b": round(r["b"], 6),
                             "temperature": round(r["temperature"], 6)}
    # Ensure both stage keys exist even if a model was skipped (identity).
    for st in ("stage1", "stage2"):
        if not block[st]:
            block[st] = {"a": 1.0, "b": 0.0, "temperature": 1.0}
    labels["calibration"] = block
    with open(args.labels, "w", encoding="utf-8") as f:
        json.dump(labels, f, indent=2)
        f.write("\n")
    print(f"wrote calibration block -> {args.labels}")

    write_report(args.report, results, chosen, png_ok, os.path.basename(png_path))
    print(f"wrote report -> {args.report}")

    # Final before/after summary line (what VERIFY expects).
    for r in results:
        before = r["metrics"]["none"]["ece"]
        after = r["metrics"][chosen if chosen != "none" else "none"]["ece"]
        print(f"SUMMARY {r['stage']}: ECE before={before:.4f} after({chosen})={after:.4f} "
              f"AUROC before={r['metrics']['none']['auroc']:.4f} "
              f"after={r['metrics'][chosen if chosen!='none' else 'none']['auroc']:.4f}")


if __name__ == "__main__":
    main()
