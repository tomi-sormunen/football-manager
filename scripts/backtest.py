#!/usr/bin/env python3
"""Backtest the expected-points model against actual gameweek outcomes.

For each finished gameweek t (from the 4th onward, so there is some history),
we build each player's cumulative inputs from GWs < t *only*, predict their
points for GW t using their real opponent/venue that week, and compare to the
points they actually scored. We report MAE / RMSE / correlation for the model
and for two naive baselines:

  * last     — predict last gameweek's points
  * ppg      — predict the player's mean points so far

A model worth shipping should beat both. Results are written to
data/backtest.json and printed.

Usage:  python scripts/backtest.py [--history data/history] [--teams data/teams.json]
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys

from model import Cumulative, project_points
from projections import build_cumulative, league_from, load_history

MIN_GW = 4          # need a few GWs of history before predicting
MIN_PRIOR_MINS = 45  # only score players with some prior evidence


def _metrics(pairs):
    """pairs: list of (pred, actual) → dict of MAE/RMSE/corr/n."""
    n = len(pairs)
    if n == 0:
        return {"n": 0, "mae": None, "rmse": None, "corr": None}
    errs = [p - a for p, a in pairs]
    mae = sum(abs(e) for e in errs) / n
    rmse = math.sqrt(sum(e * e for e in errs) / n)
    mp = sum(p for p, _ in pairs) / n
    ma = sum(a for _, a in pairs) / n
    cov = sum((p - mp) * (a - ma) for p, a in pairs)
    vp = math.sqrt(sum((p - mp) ** 2 for p, _ in pairs))
    va = math.sqrt(sum((a - ma) ** 2 for _, a in pairs))
    corr = cov / (vp * va) if vp > 0 and va > 0 else None
    return {"n": n, "mae": round(mae, 3), "rmse": round(rmse, 3),
            "corr": round(corr, 3) if corr is not None else None}


def _evaluate_season(history, teams, acc):
    """Evaluate one season's history, appending (pred, actual) pairs into `acc`.

    Running baselines reset per season (player ids are only unique within a
    season in the community dataset), but the pooled pairs give overall metrics.
    """
    gws = sorted(history)
    pos_by_id = {}
    for gw in gws:
        for r in history[gw]:
            pos_by_id.setdefault(r["id"], r.get("pos", "MID"))

    pts_sum, apps, last_pts = {}, {}, {}   # running per-player totals (this season)
    evaluated = []

    for t in gws:
        if t >= MIN_GW:
            league = league_from(teams, {g: history[g] for g in gws if g < t})
            cum = build_cumulative(history, t, pos_by_id)
            evaluated.append(t)

            for r in history[t]:
                pid = r["id"]
                c = cum.get(pid)
                if c is None or c.minutes < MIN_PRIOR_MINS:
                    continue
                pos = pos_by_id.get(pid, "MID")
                actual = r.get("pts", 0)
                pred = project_points(c, pos, r["team"], r["opp"],
                                      r.get("home", True), league, "a")["exp"]
                ppg = pts_sum.get(pid, 0) / apps[pid] if apps.get(pid) else 0.0

                acc["model"].append((pred, actual))
                acc["last"].append((last_pts.get(pid, ppg), actual))
                acc["ppg"].append((ppg, actual))
                acc["by_pos"].setdefault(pos, []).append((pred, actual))

        for r in history[t]:               # advance running totals
            pid = r["id"]
            last_pts[pid] = r.get("pts", 0)
            if r.get("minutes", 0) > 0:
                pts_sum[pid] = pts_sum.get(pid, 0) + r.get("pts", 0)
                apps[pid] = apps.get(pid, 0) + 1

    return evaluated


def run_backtest(datasets):
    """datasets: list of (label, history, teams). Returns a pooled report."""
    acc = {"model": [], "last": [], "ppg": [], "by_pos": {}}
    seasons = {}
    for label, history, teams in datasets:
        seasons[label] = _evaluate_season(history, teams, acc)
    return {
        "model": _metrics(acc["model"]),
        "baseline_last": _metrics(acc["last"]),
        "baseline_ppg": _metrics(acc["ppg"]),
        "by_position": {pos: _metrics(p) for pos, p in sorted(acc["by_pos"].items())},
        "seasons": {k: {"gws_evaluated": v} for k, v in seasons.items()},
    }


def discover_datasets(path, teams_fallback):
    """Yield (label, history, teams) from `path`.

    If `path` holds gwNN.json directly it's one dataset; otherwise each immediate
    subdirectory containing gwNN.json is a dataset. teams.json in the dataset dir
    is preferred, else `teams_fallback`.
    """
    def load_teams(dirpath):
        local = os.path.join(dirpath, "teams.json")
        src = local if os.path.exists(local) else teams_fallback
        with open(src, encoding="utf-8") as fh:
            return json.load(fh)

    direct = load_history(path)
    if direct:
        return [(os.path.basename(path.rstrip("/")) or "history", direct, load_teams(path))]

    out = []
    for name in sorted(os.listdir(path)):
        sub = os.path.join(path, name)
        if os.path.isdir(sub) and load_history(sub):
            out.append((name, load_history(sub), load_teams(sub)))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--history", default="data/history")
    ap.add_argument("--teams", default="data/teams.json")
    ap.add_argument("--out", default="data/backtest.json")
    args = ap.parse_args(argv)

    if not os.path.exists(args.history):
        print(f"No history at {args.history} — run build_history.py, "
              "backfill_history.py, or make_sample_data.py first.", file=sys.stderr)
        return 1
    datasets = discover_datasets(args.history, args.teams)
    if not datasets:
        print(f"No gameweek snapshots found under {args.history}.", file=sys.stderr)
        return 1

    report = run_backtest(datasets)
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=0)
        fh.write("\n")

    m, bl, bp = report["model"], report["baseline_last"], report["baseline_ppg"]
    labels = ", ".join(report["seasons"].keys())
    print(f"Backtest over [{labels}] — {m['n']} player-GW samples")
    print(f"  model         MAE {m['mae']}  RMSE {m['rmse']}  corr {m['corr']}")
    print(f"  baseline last MAE {bl['mae']}  RMSE {bl['rmse']}  corr {bl['corr']}")
    print(f"  baseline ppg  MAE {bp['mae']}  RMSE {bp['rmse']}  corr {bp['corr']}")
    if m["mae"] is not None and bl["mae"] is not None:
        print(f"  → model beats 'last' MAE by {bl['mae'] - m['mae']:+.3f}, "
              f"'ppg' MAE by {bp['mae'] - m['mae']:+.3f} pts/player/GW")
    for pos, met in report["by_position"].items():
        print(f"    {pos}: MAE {met['mae']} (n={met['n']})")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    raise SystemExit(main())
