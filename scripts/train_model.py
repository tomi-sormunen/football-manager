#!/usr/bin/env python3
"""Train the gradient-boosted model (xpts-v2) and export it to a portable JSON.

Trains a scikit-learn GradientBoostingRegressor that stacks on xpts-v1 (its
features are v1's components + recent-form signals — see features.py), then
exports the trees to data/model_v2.json for the dependency-free live predictor
(gbm.py). Reports an honest, leakage-free comparison against v1 by holding out
the most recent season.

Usage (needs scikit-learn):
    python scripts/train_model.py --history data/backfill --out data/model_v2.json
where <history> holds one subdirectory of gwNN.json per season (as produced by
backfill_history.py).
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys

from features import FEATURES, build_examples
from projections import build_cumulative, league_from
from backtest import discover_datasets   # (label, history, teams) tuples


def _metrics(pred, actual):
    n = len(actual)
    if not n:
        return {"n": 0}
    err = [p - a for p, a in zip(pred, actual)]
    mae = sum(abs(e) for e in err) / n
    rmse = math.sqrt(sum(e * e for e in err) / n)
    mp, ma = sum(pred) / n, sum(actual) / n
    cov = sum((p - mp) * (a - ma) for p, a in zip(pred, actual))
    vp = math.sqrt(sum((p - mp) ** 2 for p in pred))
    va = math.sqrt(sum((a - ma) ** 2 for a in actual))
    corr = cov / (vp * va) if vp > 0 and va > 0 else 0.0
    return {"n": n, "mae": round(mae, 3), "rmse": round(rmse, 3), "corr": round(corr, 3)}


def export_model(gbr, features):
    """Serialise a fitted GradientBoostingRegressor to plain JSON trees."""
    trees = []
    for stage in gbr.estimators_:
        t = stage[0].tree_
        trees.append({
            "left": [int(x) for x in t.children_left],
            "right": [int(x) for x in t.children_right],
            "feature": [int(x) for x in t.feature],
            "threshold": [round(float(x), 5) for x in t.threshold],
            "value": [round(float(v[0][0]), 5) for v in t.value],
        })
    return {
        "model": "xpts-v2",
        "features": features,
        "init": round(float(gbr.init_.constant_.ravel()[0]), 5),
        "learning_rate": float(gbr.learning_rate),
        "trees": trees,
    }


def train(X, y, seed=0):
    from sklearn.ensemble import GradientBoostingRegressor
    gbr = GradientBoostingRegressor(
        n_estimators=200, max_depth=3, learning_rate=0.05,
        subsample=0.8, min_samples_leaf=60, random_state=seed)
    gbr.fit(X, y)
    return gbr


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--history", default="data/backfill",
                    help="dir of season subdirs (from backfill_history.py)")
    ap.add_argument("--teams", default="data/teams.json")
    ap.add_argument("--out", default="data/model_v2.json")
    args = ap.parse_args(argv)

    datasets = discover_datasets(args.history, args.teams)
    if len(datasets) < 2:
        print("Need >=2 seasons (one held out for validation). "
              "Run backfill_history.py for several seasons first.", file=sys.stderr)
        return 1
    datasets.sort(key=lambda d: d[0])                 # by season label
    print(f"Seasons: {[d[0] for d in datasets]}")

    # Build examples per season.
    ex = {}
    for label, history, teams in datasets:
        X, y, _ = build_examples(history, teams, league_from, build_cumulative)
        ex[label] = (X, y)
        print(f"  {label}: {len(y)} training rows")

    # Leakage-free validation: hold out the most recent season.
    val_label = datasets[-1][0]
    Xtr = [r for lbl in ex if lbl != val_label for r in ex[lbl][0]]
    ytr = [v for lbl in ex if lbl != val_label for v in ex[lbl][1]]
    Xval, yval = ex[val_label]

    print(f"Training on {len(ytr)} rows, validating on {val_label} ({len(yval)} rows)…")
    gbr = train(Xtr, ytr)

    v1_idx = FEATURES.index("v1_exp")
    v1_val = [row[v1_idx] for row in Xval]
    v2_val = list(gbr.predict(Xval))
    m1, m2 = _metrics(v1_val, yval), _metrics(v2_val, yval)
    print(f"  held-out {val_label}:  v1  MAE {m1['mae']}  RMSE {m1['rmse']}  corr {m1['corr']}")
    print(f"                        v2  MAE {m2['mae']}  RMSE {m2['rmse']}  corr {m2['corr']}")
    print(f"  → v2 vs v1: MAE {m2['mae'] - m1['mae']:+.3f}, corr {m2['corr'] - m1['corr']:+.3f}")

    # Ship a model trained on ALL seasons (max data), exporting the portable JSON.
    Xall = [r for lbl in ex for r in ex[lbl][0]]
    yall = [v for lbl in ex for v in ex[lbl][1]]
    final = train(Xall, yall)
    model = export_model(final, FEATURES)
    model["trained_on"] = [d[0] for d in datasets]
    model["validation"] = {"season": val_label, "v1": m1, "v2": m2}
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(model, fh, separators=(",", ":"))
        fh.write("\n")
    size_kb = os.path.getsize(args.out) // 1024
    print(f"Wrote {args.out} ({len(model['trees'])} trees, {size_kb} KB, "
          f"trained on {len(yall)} rows).")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    raise SystemExit(main())
