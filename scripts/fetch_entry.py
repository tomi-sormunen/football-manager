#!/usr/bin/env python3
"""Fetch a manager's FPL squad and write data/entry.json for personalisation.

The FPL API can't be called from the browser (no CORS), so the Action fetches
the manager's team server-side and commits the result; the static site reads it
same-origin. Public, read-only endpoints:

  * entry/{id}/                      manager summary + current event
  * entry/{id}/event/{gw}/picks/     the 15 picks + bank/value for that GW

Team id resolution: --entry arg → $FPL_TEAM_ID → config.json "fpl_team_id".

Usage:  python scripts/fetch_entry.py [--entry 9155976] [--out data]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request

API = "https://fantasy.premierleague.com/api"
HEADERS = {"User-Agent": "football-manager/1.0 (+github pages planning tool)"}


def _get(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.load(resp)


def resolve_team_id(arg, out_dir):
    if arg:
        return int(arg)
    env = os.environ.get("FPL_TEAM_ID")
    if env and env.strip():
        return int(env)
    for path in ("config.json", os.path.join(out_dir, "..", "config.json")):
        if os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                cfg = json.load(fh)
            if cfg.get("fpl_team_id"):
                return int(cfg["fpl_team_id"])
    raise SystemExit("No team id: pass --entry, set FPL_TEAM_ID, or config.json.")


def pick_event(entry, out_dir):
    ev = entry.get("current_event")
    if ev:
        return ev
    meta_path = os.path.join(out_dir, "meta.json")
    if os.path.exists(meta_path):
        with open(meta_path, encoding="utf-8") as fh:
            return json.load(fh).get("current_gw", 1)
    return 1


def build_entry(team_id, entry, picks_resp, event):
    eh = picks_resp.get("entry_history", {}) or {}
    picks = [{
        "element": p["element"],
        "slot": p["position"],                 # 1..15 (1..11 start, 12..15 bench)
        "is_captain": bool(p.get("is_captain")),
        "is_vice": bool(p.get("is_vice_captain")),
        "multiplier": p.get("multiplier", 1),
    } for p in picks_resp.get("picks", [])]
    return {
        "id": team_id,
        "manager": f"{entry.get('player_first_name', '')} "
                   f"{entry.get('player_last_name', '')}".strip(),
        "team_name": entry.get("name", ""),
        "event": event,
        "overall_points": entry.get("summary_overall_points"),
        "overall_rank": entry.get("summary_overall_rank"),
        "gw_points": eh.get("points"),
        "bank": round(eh.get("bank", 0) / 10.0, 1),
        "squad_value": round(eh.get("value", 0) / 10.0, 1),
        "event_transfers": eh.get("event_transfers"),
        "event_transfers_cost": eh.get("event_transfers_cost"),
        "picks": picks,
        "source": "fpl-api",
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--entry", default=None)
    ap.add_argument("--out", default="data")
    args = ap.parse_args(argv)

    team_id = resolve_team_id(args.entry, args.out)
    try:
        entry = _get(f"{API}/entry/{team_id}/")
        event = pick_event(entry, args.out)
        picks_resp = _get(f"{API}/entry/{team_id}/event/{event}/picks/")
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR fetching entry {team_id}: {exc}", file=sys.stderr)
        return 1

    data = build_entry(team_id, entry, picks_resp, event)
    os.makedirs(args.out, exist_ok=True)
    path = os.path.join(args.out, "entry.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, separators=(",", ":"))
        fh.write("\n")
    print(f"Wrote {path}: {data['manager']} — {data['team_name']} "
          f"(GW{event}, {len(data['picks'])} picks, bank £{data['bank']}m)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
