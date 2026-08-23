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
import urllib.error
import urllib.request

API = "https://fantasy.premierleague.com/api"
# The FPL API rejects some non-browser user agents; use a browser-like one.
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (compatible; football-manager/1.0; "
                   "+https://github.com/tomi-sormunen/football-manager)"),
    "Accept": "application/json",
}


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


def fetch_picks_with_fallback(team_id, start_event):
    """Return (picks_resp, event). A GW's picks are only public AFTER its
    deadline, so if the current GW isn't available yet we walk back to the most
    recent gameweek that is (the last team you saved). Returns (None, None) if
    no gameweek has public picks yet (true pre-season)."""
    for ev in range(start_event, 0, -1):
        url = f"{API}/entry/{team_id}/event/{ev}/picks/"
        try:
            return _get(url), ev
        except urllib.error.HTTPError as e:
            if e.code == 404:
                print(f"  GW{ev} picks not public yet ({e.code}); trying earlier…",
                      file=sys.stderr)
                continue
            raise
    return None, None


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--entry", default=None)
    ap.add_argument("--out", default="data")
    args = ap.parse_args(argv)

    team_id = resolve_team_id(args.entry, args.out)

    entry_url = f"{API}/entry/{team_id}/"
    try:
        entry = _get(entry_url)
    except urllib.error.HTTPError as e:
        print(f"ERROR GET {entry_url} → HTTP {e.code} {e.reason}. "
              "Check the team id (the number in your FPL Points-page URL: "
              ".../entry/<ID>/event/...).", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR GET {entry_url} → {exc}", file=sys.stderr)
        return 1

    start_event = pick_event(entry, args.out)
    print(f"entry {team_id}: current_event={entry.get('current_event')}, "
          f"starting picks lookup at GW{start_event}", file=sys.stderr)

    picks_resp, event = fetch_picks_with_fallback(team_id, start_event)
    if picks_resp is None:
        print(f"No public picks for entry {team_id} yet — a gameweek's squad is "
              "only exposed by the public API after that gameweek's deadline. "
              "It will populate automatically once the deadline passes.",
              file=sys.stderr)
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
