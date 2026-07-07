#!/usr/bin/env python3
"""Orchestrator for the multi-engine wake-word TTS dataset.

Runs every AVAILABLE engine (espeak-ng, Windows SAPI/pyttsx3, gTTS, Piper) for both
positives and negatives, then augments the clean clips. Idempotent (each engine skips
files already on disk), degrades gracefully (a missing/broken engine is logged and the
rest continue), and prints a per-engine count summary.

Usage:
  python run_all.py                 # full generation + augmentation
  python run_all.py --limit 3       # SMOKE: <=3 new clips per engine per category
  python run_all.py --no-augment    # generators only
  python run_all.py --aug-k 4       # augmented variants per clean clip
"""
import argparse
import os
import sys
import time
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "generators"))

import genlib          # noqa: E402
import gen_espeak      # noqa: E402
import gen_sapi        # noqa: E402
import gen_gtts        # noqa: E402
import gen_piper       # noqa: E402
import augment as aug  # noqa: E402

ENGINES = [
    ("espeak", gen_espeak.generate),
    ("sapi", gen_sapi.generate),
    ("gtts", gen_gtts.generate),
    ("piper", gen_piper.generate),
]


def _engine_of(fn):
    """Recover the engine token from a filename (field 1 = '{engine}-{voice}')."""
    base = fn[4:] if fn.startswith("neg_") else fn
    parts = base.split("_")
    if len(parts) < 2:
        return "?"
    return parts[1].split("-")[0]


def disk_counts():
    pos, neg = Counter(), Counter()
    for d, ctr in ((genlib.OUT_POS, pos), (genlib.OUT_NEG, neg)):
        if not os.path.isdir(d):
            continue
        for fn in os.listdir(d):
            if fn.endswith(".wav"):
                ctr[_engine_of(fn)] += 1
    return pos, neg


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None,
                    help="smoke: max NEW clips per engine per category")
    ap.add_argument("--no-augment", action="store_true")
    ap.add_argument("--aug-k", type=int, default=4, help="augmented variants per clean clip")
    ap.add_argument("--aug-limit", type=int, default=None,
                    help="cap clean clips fed to augmentation (smoke)")
    args = ap.parse_args()

    if not genlib.have_ffmpeg():
        print("FATAL: ffmpeg not found on PATH — every engine needs it to make 16 kHz WAV.")
        return 2

    genlib.ensure_dirs()
    print(f"== wake-word datagen == limit={args.limit} aug_k={args.aug_k}\n")

    results = []
    for name, fn in ENGINES:
        t0 = time.time()
        try:
            r = fn(limit=args.limit)
        except Exception as e:
            r = {"engine": name, "available": False, "made": 0, "skipped": 0,
                 "failed": 0, "reason": f"crashed: {str(e)[:150]}"}
        r["secs"] = round(time.time() - t0, 1)
        results.append(r)
        status = "OK " if r.get("available") else "SKIP"
        line = (f"[{status}] {name:7s} made={r.get('made',0):4d} "
                f"skipped={r.get('skipped',0):4d} failed={r.get('failed',0):4d} "
                f"({r['secs']}s)")
        if r.get("reason"):
            line += f"  -- {r['reason']}"
        print(line)

    # ---- augmentation ----
    aug_res = None
    if not args.no_augment:
        print("\n-- augment --")
        limit = args.aug_limit if args.aug_limit is not None else args.limit
        try:
            aug_res = aug.augment_all(k=args.aug_k, limit=limit)
            print(f"[OK ] augment made={aug_res['made']} skipped={aug_res['skipped']} "
                  f"failed={aug_res['failed']} k={aug_res['k']} "
                  f"noise={aug_res['noise_source']} sources={aug_res['clean_sources']}")
        except Exception as e:
            print(f"[FAIL] augment crashed: {str(e)[:150]}")

    # ---- summary ----
    pos, neg = disk_counts()
    print("\n== per-engine WAV counts on disk ==")
    engines = sorted(set(pos) | set(neg))
    for e in engines:
        print(f"  {e:8s} positives={pos.get(e,0):5d}  negatives={neg.get(e,0):5d}")
    total_pos = sum(pos.values())
    total_neg = sum(neg.values())
    print(f"  {'TOTAL':8s} positives={total_pos:5d}  negatives={total_neg:5d}")

    functional = [r["engine"] for r in results if r.get("available")]
    failed = [(r["engine"], r.get("reason", "")) for r in results if not r.get("available")]
    print(f"\nfunctional engines: {functional if functional else 'NONE'}")
    if failed:
        print("unavailable engines:")
        for e, why in failed:
            print(f"  - {e}: {why}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
