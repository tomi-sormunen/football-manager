#!/usr/bin/env python3
"""Backfill past-season history from the open community FPL dataset.

Converts one or more seasons from vaastav/Fantasy-Premier-League into our
data/history schema, so the backtest has *real* multi-season data immediately
(rather than only the current season accumulating going forward).

Source (free, no key): https://github.com/vaastav/Fantasy-Premier-League
For each season it reads teams.csv, players_raw.csv and gws/merged_gw.csv and
writes:
    <out>/<season>/gwNN.json     one snapshot per gameweek (history rows)
    <out>/<season>/teams.json    that season's clubs + strength ratings

Then point the backtest at a season:
    python scripts/backtest.py --history data/backfill/2023-24 \
        --teams data/backfill/2023-24/teams.json

Note: expected goals/assists exist from 2020-21 on; the 2025/26 DEFCON stat
only exists for that season. Missing fields backfill as 0 and the model falls
back to its priors — the pipeline still runs for every season.

Usage:  python scripts/backfill_history.py --seasons 2022-23,2023-24 [--out data/backfill]
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import os
import sys
import urllib.request

BASE = "https://raw.githubusercontent.com/vaastav/Fantasy-Premier-League/master/data"
HEADERS = {"User-Agent": "football-manager/1.0 (backfill)"}
ELEMENT_TYPE = {"1": "GKP", "2": "DEF", "3": "MID", "4": "FWD"}
POS_TEXT = {"GK": "GKP", "GKP": "GKP", "DEF": "DEF", "MID": "MID", "FWD": "FWD"}


def _get_text(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=120) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _rows(text):
    return list(csv.DictReader(io.StringIO(text)))


def _i(v, d=0):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return d


def _f(v, d=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


def build_teams(teams_csv):
    teams, name_to_id = [], {}
    for t in teams_csv:
        tid = _i(t["id"])
        teams.append({
            "id": tid, "name": t["name"], "short": t.get("short_name", ""),
            "strength": _i(t.get("strength"), 3),
            "att_home": _i(t.get("strength_attack_home")),
            "att_away": _i(t.get("strength_attack_away")),
            "def_home": _i(t.get("strength_defence_home")),
            "def_away": _i(t.get("strength_defence_away")),
        })
        name_to_id[t["name"]] = tid
    return teams, name_to_id


def backfill_season(season, out_dir):
    base = f"{BASE}/{season}"
    teams_csv = _rows(_get_text(f"{base}/teams.csv"))
    players_csv = _rows(_get_text(f"{base}/players_raw.csv"))
    merged = _rows(_get_text(f"{base}/gws/merged_gw.csv"))

    teams, name_to_id = build_teams(teams_csv)
    team_by_element = {_i(p["id"]): _i(p["team"]) for p in players_csv}
    type_by_element = {_i(p["id"]): ELEMENT_TYPE.get(str(p["element_type"]), "MID")
                       for p in players_csv}

    by_gw = {}
    for r in merged:
        gw = _i(r.get("GW") or r.get("round"))
        if gw <= 0:
            continue
        pid = _i(r.get("element"))
        pos = POS_TEXT.get((r.get("position") or "").upper()) or type_by_element.get(pid, "MID")
        team = team_by_element.get(pid) or name_to_id.get(r.get("team"), 0)
        by_gw.setdefault(gw, []).append({
            "id": pid, "pos": pos, "team": team,
            "opp": _i(r.get("opponent_team")),
            "home": str(r.get("was_home")).lower() in ("true", "1"),
            "minutes": _i(r.get("minutes")),
            "xg": _f(r.get("expected_goals")),
            "xa": _f(r.get("expected_assists")),
            "goals": _i(r.get("goals_scored")),
            "assists": _i(r.get("assists")),
            "defcon": _i(r.get("defensive_contribution")),   # 0 pre-2025/26
            "bonus": _i(r.get("bonus")),
            "gc": _i(r.get("goals_conceded")),
            "pts": _i(r.get("total_points")),
        })

    season_dir = os.path.join(out_dir, season)
    os.makedirs(season_dir, exist_ok=True)
    with open(os.path.join(season_dir, "teams.json"), "w", encoding="utf-8") as fh:
        json.dump(teams, fh, ensure_ascii=False, separators=(",", ":"))
        fh.write("\n")
    for gw, rows in sorted(by_gw.items()):
        with open(os.path.join(season_dir, f"gw{gw:02d}.json"), "w", encoding="utf-8") as fh:
            json.dump(rows, fh, ensure_ascii=False, separators=(",", ":"))
            fh.write("\n")

    total_rows = sum(len(v) for v in by_gw.values())
    print(f"  {season}: {len(by_gw)} GWs, {total_rows} player-GW rows, "
          f"{len(teams)} teams → {season_dir}/")
    return len(by_gw)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seasons", default="2023-24",
                    help="comma-separated, e.g. 2021-22,2022-23,2023-24")
    ap.add_argument("--out", default="data/backfill")
    args = ap.parse_args(argv)

    seasons = [s.strip() for s in args.seasons.split(",") if s.strip()]
    print(f"Backfilling {len(seasons)} season(s) from the community dataset…")
    ok = 0
    for s in seasons:
        try:
            backfill_season(s, args.out)
            ok += 1
        except Exception as exc:  # noqa: BLE001
            print(f"  {s}: FAILED — {exc}", file=sys.stderr)
    print(f"Done: {ok}/{len(seasons)} seasons backfilled into {args.out}/")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
