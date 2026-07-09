#!/usr/bin/env python3
"""Cross-device / cross-model calibration consistency (Plan Part A, report rule 3).

Given two models' CALIBRATED target posteriors on a SHARED evaluation set (same clips, same
order) plus the shared labels, report:
  * ECE parity   — |ECE_A - ECE_B| and each ECE (10-bin). Small parity == both devices are
                   equally well-calibrated at the same operating point.
  * Score-distribution divergence — Jensen-Shannon divergence + Population Stability Index
                   between the two posterior histograms. Large divergence == the two devices
                   produce systematically different score distributions (a cross-device drift
                   risk even if each is individually calibrated).

Usable as a library (import `consistency`) or CLI (two .npy/.json posterior files + labels).
"""
import json
import sys
import numpy as np

try:
    from calibrate import ece_mce
except Exception:  # pragma: no cover - allow standalone import
    def ece_mce(p, y, bins=10):
        p = np.asarray(p, np.float64); y = np.asarray(y, np.float64)
        edges = np.linspace(0, 1, bins + 1); N = len(p); ece = mce = 0.0
        for i in range(bins):
            lo, hi = edges[i], edges[i + 1]
            m = (p > lo) & (p <= hi) if i > 0 else (p >= lo) & (p <= hi)
            if not m.any():
                continue
            gap = abs(p[m].mean() - y[m].mean())
            ece += m.sum() / N * gap; mce = max(mce, gap)
        return ece, mce, None


def _hist(p, bins=10):
    h, _ = np.histogram(np.clip(p, 0, 1), bins=bins, range=(0, 1))
    h = h.astype(np.float64)
    return h / max(h.sum(), 1e-12)


def js_divergence(pA, pB, bins=10):
    """Jensen-Shannon divergence (base-2, in [0,1]) between the two posterior histograms."""
    a = _hist(pA, bins); b = _hist(pB, bins)
    m = 0.5 * (a + b)
    def kl(x, y):
        mask = x > 0
        return float(np.sum(x[mask] * np.log2(x[mask] / np.where(y[mask] > 0, y[mask], 1e-12))))
    return 0.5 * kl(a, m) + 0.5 * kl(b, m)


def psi(pA, pB, bins=10):
    """Population Stability Index between the two posterior histograms (A=reference)."""
    a = _hist(pA, bins); b = _hist(pB, bins)
    a = np.clip(a, 1e-6, None); b = np.clip(b, 1e-6, None)
    return float(np.sum((b - a) * np.log(b / a)))


def consistency(pA, pB, y, bins=10):
    """Report ECE parity + score-distribution divergence for two models' calibrated posteriors
    on a shared labeled set. Returns a dict."""
    pA = np.asarray(pA, np.float64); pB = np.asarray(pB, np.float64); y = np.asarray(y)
    if len(pA) != len(pB) or len(pA) != len(y):
        raise ValueError("pA, pB and y must be aligned over the same shared set")
    eceA = ece_mce(pA, y, bins)[0]
    eceB = ece_mce(pB, y, bins)[0]
    return {
        "n": int(len(y)),
        "ece_a": float(eceA), "ece_b": float(eceB),
        "ece_parity": float(abs(eceA - eceB)),
        "js_divergence": float(js_divergence(pA, pB, bins)),
        "psi": float(psi(pA, pB, bins)),
        "mean_a": float(pA.mean()), "mean_b": float(pB.mean()),
        "mean_abs_delta": float(np.mean(np.abs(pA - pB))),
    }


def _load(path):
    if path.endswith(".npy"):
        return np.load(path)
    with open(path) as f:
        return np.asarray(json.load(f), np.float64)


def main():
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("posteriors_a")
    ap.add_argument("posteriors_b")
    ap.add_argument("labels")
    ap.add_argument("--bins", type=int, default=10)
    args = ap.parse_args()
    rep = consistency(_load(args.posteriors_a), _load(args.posteriors_b), _load(args.labels), args.bins)
    print(json.dumps(rep, indent=2))


if __name__ == "__main__":
    main()
