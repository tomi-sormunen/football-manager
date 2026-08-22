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


def run_backtest(history, teams):
    gws = sorted(history)
    pos_by_id = {}
    for gw in gws:
        for r in history[gw]:
            pos_by_id.setdefault(r["id"], r.get("pos", "MID"))

    model_pairs, last_pairs, ppg_pairs = [], [], []
    by_pos = {}

    # Running per-player totals so the ppg baseline is O(n), not O(n^2).
    pts_sum = {}     # id -> total points in GWs seen so far
    apps = {}        # id -> appearances so far
    last_pts = {}    # id -> points in the most recent GW

    for t in gws:
        if t >= MIN_GW:
            league = league_from(teams, {g: history[g] for g in gws if g < t})
            cum = build_cumulative(history, t, pos_by_id)

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

                model_pairs.append((pred, actual))
                last_pairs.append((last_pts.get(pid, ppg), actual))
                ppg_pairs.append((ppg, actual))
                by_pos.setdefault(pos, []).append((pred, actual))

        # advance running totals with this GW's outcomes
        for r in history[t]:
            pid = r["id"]
            last_pts[pid] = r.get("pts", 0)
            if r.get("minutes", 0) > 0:
                pts_sum[pid] = pts_sum.get(pid, 0) + r.get("pts", 0)
                apps[pid] = apps.get(pid, 0) + 1

    report = {
        "model": _metrics(model_pairs),
        "baseline_last": _metrics(last_pairs),
        "baseline_ppg": _metrics(ppg_pairs),
        "by_position": {pos: _metrics(pairs) for pos, pairs in sorted(by_pos.items())},
        "gws_evaluated": [g for g in gws if g >= MIN_GW],
    }
    return report


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--history", default="data/history")
    ap.add_argument("--teams", default="data/teams.json")
    ap.add_argument("--out", default="data/backtest.json")
    args = ap.parse_args(argv)

    history = load_history(args.history)
    if not history:
        print("No history found — run build_history.py (or make_sample_data.py) first.",
              file=sys.stderr)
        return 1
    with open(args.teams, encoding="utf-8") as fh:
        teams = json.load(fh)

    report = run_backtest(history, teams)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=0)
        fh.write("\n")

    m, bl, bp = report["model"], report["baseline_last"], report["baseline_ppg"]
    print(f"Backtest over {len(report['gws_evaluated'])} GWs, {m['n']} samples")
    print(f"  model         MAE {m['mae']}  RMSE {m['rmse']}  corr {m['corr']}")
    print(f"  baseline last MAE {bl['mae']}  RMSE {bl['rmse']}  corr {bl['corr']}")
    print(f"  baseline ppg  MAE {bp['mae']}  RMSE {bp['rmse']}  corr {bp['corr']}")
    if m["mae"] is not None and bl["mae"] is not None:
        better = bl["mae"] - m["mae"]
        print(f"  → model beats 'last' MAE by {better:+.3f} pts/player/GW")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    raise SystemExit(main())
