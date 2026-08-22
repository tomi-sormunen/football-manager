#!/usr/bin/env python3
"""Snapshot finished gameweeks into data/history/ for the model & backtest.

For each finished gameweek not already saved, fetch the FPL "live" endpoint
(one call per gameweek — returns every player's stats for that GW) and join it
with fixtures to record the opponent and venue. Writes data/history/gwNN.json.

Runs inside the GitHub Action; stdlib only. Idempotent — existing snapshots are
skipped, so history accumulates over the season.

Usage:  python scripts/build_history.py [--out data/history]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request

API = "https://fantasy.premierleague.com/api"
HEADERS = {"User-Agent": "football-manager/1.0 (+github pages planning tool)"}
POS_MAP = {1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"}


def _get(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.load(resp)


def _f(v, d=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


def team_opponents(fixtures, gw):
    """team_id -> (opp_id, is_home) for a gameweek (first fixture if a DGW)."""
    m = {}
    for fx in fixtures:
        if fx.get("event") != gw:
            continue
        m.setdefault(fx["team_h"], (fx["team_a"], True))
        m.setdefault(fx["team_a"], (fx["team_h"], False))
    return m


def snapshot_gw(gw, live, bootstrap, fixtures):
    pos = {e["id"]: POS_MAP.get(e["element_type"], "MID") for e in bootstrap["elements"]}
    team = {e["id"]: e["team"] for e in bootstrap["elements"]}
    opp = team_opponents(fixtures, gw)
    rows = []
    for el in live["elements"]:
        pid = el["id"]
        s = el.get("stats", {})
        tid = team.get(pid)
        o = opp.get(tid, (0, True))
        rows.append({
            "id": pid,
            "pos": pos.get(pid, "MID"),
            "team": tid,
            "opp": o[0],
            "home": o[1],
            "minutes": int(s.get("minutes", 0)),
            "xg": _f(s.get("expected_goals")),
            "xa": _f(s.get("expected_assists")),
            "defcon": int(s.get("defensive_contribution", 0)),
            "bonus": int(s.get("bonus", 0)),
            "gc": int(s.get("goals_conceded", 0)),
            "pts": int(s.get("total_points", 0)),
        })
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="data/history")
    args = ap.parse_args(argv)
    os.makedirs(args.out, exist_ok=True)

    try:
        bootstrap = _get(f"{API}/bootstrap-static/")
        fixtures = _get(f"{API}/fixtures/")
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR fetching FPL API: {exc}", file=sys.stderr)
        return 1

    finished = [ev["id"] for ev in bootstrap["events"] if ev.get("finished")]
    written = 0
    for gw in finished:
        path = os.path.join(args.out, f"gw{gw:02d}.json")
        if os.path.exists(path):
            continue
        try:
            live = _get(f"{API}/event/{gw}/live/")
        except Exception as exc:  # noqa: BLE001
            print(f"WARN could not fetch GW{gw} live: {exc}", file=sys.stderr)
            continue
        rows = snapshot_gw(gw, live, bootstrap, fixtures)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(rows, fh, ensure_ascii=False, separators=(",", ":"))
            fh.write("\n")
        written += 1
        print(f"Wrote {path} ({len(rows)} players)")

    print(f"History up to date: {len(finished)} finished GWs, {written} newly written.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
