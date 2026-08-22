#!/usr/bin/env python3
"""Fetch data from the official Fantasy Premier League API and write the slim
dataset the static site consumes into ``data/``.

Runs inside a GitHub Action (see ``.github/workflows/update-data.yml``) where
the FPL API is reachable server-to-server (CORS does not apply). Uses only the
Python standard library so the Action needs no ``pip install``.

Endpoints used (all public, read-only):
  * https://fantasy.premierleague.com/api/bootstrap-static/  (players, teams, GWs)
  * https://fantasy.premierleague.com/api/fixtures/          (fixtures + FDR)

Usage:  python scripts/fetch_fpl_data.py [--out data]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request

from fpl_common import write_dataset
from projections import load_history, project_all, write_projections

API = "https://fantasy.premierleague.com/api"
HEADERS = {"User-Agent": "football-manager/1.0 (+github pages planning tool)"}

POS_MAP = {1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"}


def _get(url: str):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.load(resp)


def _f(value, default=0.0):
    """Parse FPL's stringy numbers safely."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _i(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def transform(bootstrap: dict, fixtures_raw: list):
    teams_raw = bootstrap["teams"]
    team_by_id = {t["id"]: t for t in teams_raw}

    teams = [{
        "id": t["id"],
        "name": t["name"],
        "short": t["short_name"],
        "strength": _i(t.get("strength"), 3),
        "att_home": _i(t.get("strength_attack_home")),
        "att_away": _i(t.get("strength_attack_away")),
        "def_home": _i(t.get("strength_defence_home")),
        "def_away": _i(t.get("strength_defence_away")),
    } for t in teams_raw]

    players = []
    for e in bootstrap["elements"]:
        minutes = _i(e.get("minutes"))
        # FPL exposes a per-match "defensive contribution" tally; older seasons
        # may not have it, so fall back to 0 and derive a per-90 rate.
        defcon = _i(e.get("defensive_contribution"))
        defcon_per90 = round(defcon / minutes * 90, 2) if minutes else 0.0
        team = team_by_id.get(e["team"], {})
        players.append({
            "id": e["id"],
            "name": f"{e.get('first_name', '')} {e.get('second_name', '')}".strip(),
            "web": e.get("web_name", ""),
            "team": e["team"],
            "team_short": team.get("short_name", ""),
            "pos": POS_MAP.get(e["element_type"], "MID"),
            "price": round(_i(e.get("now_cost")) / 10.0, 1),
            "status": e.get("status", "a"),
            "news": e.get("news", "") or "",
            "form": _f(e.get("form")),
            "pts": _i(e.get("total_points")),
            "ppg": _f(e.get("points_per_game")),
            "sel": _f(e.get("selected_by_percent")),
            "minutes": minutes,
            "goals": _i(e.get("goals_scored")),
            "assists": _i(e.get("assists")),
            "cs": _i(e.get("clean_sheets")),
            "xg": _f(e.get("expected_goals")),
            "xa": _f(e.get("expected_assists")),
            "xgi": _f(e.get("expected_goal_involvements")),
            "defcon": defcon,
            "defcon_per90": defcon_per90,
            "ict": _f(e.get("ict_index")),
            "bonus": _i(e.get("bonus")),
            "ep_next": _f(e.get("ep_next")),
            "cost_change_event": _i(e.get("cost_change_event")),
            "transfers_in_event": _i(e.get("transfers_in_event")),
            "transfers_out_event": _i(e.get("transfers_out_event")),
        })

    fixtures = []
    for fx in fixtures_raw:
        gw = fx.get("event")
        if gw is None:  # unscheduled fixtures have no gameweek yet
            continue
        fixtures.append({
            "gw": _i(gw),
            "team_h": fx["team_h"],
            "team_a": fx["team_a"],
            "kickoff": fx.get("kickoff_time") or "",
            "fdr_h": _i(fx.get("team_h_difficulty"), 3),
            "fdr_a": _i(fx.get("team_a_difficulty"), 3),
            "finished": bool(fx.get("finished")),
        })

    # Gameweek meta: find current + next from the events list.
    events = bootstrap["events"]
    current = next((ev for ev in events if ev.get("is_current")), None)
    nxt = next((ev for ev in events if ev.get("is_next")), None)
    if current is None:
        current = next((ev for ev in events if not ev.get("finished")), events[0])
    current_gw = current["id"] if current else 1
    next_gw = nxt["id"] if nxt else current_gw + 1
    next_deadline = (nxt or current or {}).get("deadline_time", "")

    # Live scoring values so the app never hard-codes stale numbers.
    gs = bootstrap.get("game_settings", {})
    scoring = {
        "squad_squadsize": gs.get("squad_squadsize", 15),
        "squad_total_spend": gs.get("squad_total_spend", 1000) / 10.0,
        "squad_team_limit": gs.get("squad_team_limit", 3),
        "transfers_cost": gs.get("transfers_cost", 4),
        "transfers_limit": gs.get("transfers_limit", 5),
    }

    meta = {
        "source": "fpl-api",
        "season": _guess_season(events),
        "current_gw": current_gw,
        "next_gw": next_gw,
        "next_deadline_utc": next_deadline,
        "scoring": scoring,
    }
    return meta, teams, players, fixtures


def _guess_season(events):
    for ev in events:
        dt = ev.get("deadline_time", "")
        if len(dt) >= 4 and dt[:4].isdigit():
            start = int(dt[:4])
            # FPL seasons start in Aug; a GW1 in Aug means season start==that year
            return f"{start % 100}/{(start + 1) % 100:02d}"
    return "current"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="data", help="output directory")
    args = ap.parse_args(argv)

    try:
        bootstrap = _get(f"{API}/bootstrap-static/")
        fixtures_raw = _get(f"{API}/fixtures/")
    except Exception as exc:  # noqa: BLE001 - surface a clear CI failure
        print(f"ERROR fetching FPL API: {exc}", file=sys.stderr)
        return 1

    meta, teams, players, fixtures = transform(bootstrap, fixtures_raw)
    write_dataset(args.out, meta=meta, teams=teams, players=players,
                  fixtures=fixtures)

    # Build model projections from any accumulated history (falls back to
    # current-season totals when history is thin). Run build_history.py first
    # in CI so this has the richest history to work with.
    history = load_history(os.path.join(args.out, "history"))
    projections = project_all(players, teams, fixtures, meta, history)
    write_projections(args.out, projections)
    return 0


if __name__ == "__main__":
    # allow running from repo root: python scripts/fetch_fpl_data.py
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    raise SystemExit(main())
