#!/usr/bin/env python3
"""Generate a realistic *sample* dataset matching the live schema, so the site
renders before the first live data refresh runs in CI.

This is illustrative data (clearly marked ``source: "sample"`` in meta.json) —
prices, form and ownership are plausible but not live. The GitHub Action
overwrites these files with real data from the FPL API.

Usage:  python scripts/make_sample_data.py [--out data]
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta, timezone

from fpl_common import write_dataset

CURRENT_GW = 2
N_FUTURE_GWS = 8

# --- Clubs: (id, name, short, strength, att_h, att_a, def_h, def_a) ---------
TEAMS = [
    (1, "Arsenal", "ARS", 5, 1350, 1330, 1330, 1310),
    (2, "Aston Villa", "AVL", 4, 1180, 1150, 1160, 1140),
    (3, "Bournemouth", "BOU", 3, 1090, 1060, 1080, 1050),
    (4, "Brentford", "BRE", 3, 1110, 1070, 1090, 1050),
    (5, "Brighton", "BHA", 3, 1150, 1120, 1120, 1090),
    (6, "Chelsea", "CHE", 4, 1250, 1220, 1230, 1200),
    (7, "Crystal Palace", "CRY", 3, 1130, 1100, 1150, 1120),
    (8, "Everton", "EVE", 3, 1090, 1060, 1120, 1090),
    (9, "Fulham", "FUL", 3, 1100, 1070, 1100, 1070),
    (10, "Liverpool", "LIV", 5, 1360, 1340, 1320, 1300),
    (11, "Man City", "MCI", 5, 1370, 1350, 1310, 1290),
    (12, "Man Utd", "MUN", 4, 1200, 1170, 1180, 1150),
    (13, "Newcastle", "NEW", 4, 1240, 1210, 1220, 1190),
    (14, "Nott'm Forest", "NFO", 3, 1120, 1090, 1170, 1140),
    (15, "Tottenham", "TOT", 4, 1230, 1200, 1180, 1150),
    (16, "West Ham", "WHU", 3, 1120, 1090, 1090, 1060),
    (17, "Wolves", "WOL", 3, 1080, 1050, 1070, 1040),
    (18, "Brighton B", "BRB", 2, 1020, 1000, 1010, 990),
    (19, "Leeds", "LEE", 2, 1040, 1010, 1030, 1000),
    (20, "Sunderland", "SUN", 2, 1030, 1000, 1020, 990),
]

# --- Players -----------------------------------------------------------------
# (web, full, team_id, pos, price, status, news, form, pts, minutes, goals,
#  assists, cs, xg, xa, defcon_total, sel, ep_next, cost_change_event)
P = [
    # Forwards
    ("Haaland", "Erling Haaland", 11, "FWD", 14.2, "a", "", 8.5, 20, 180, 3, 0, 1, 2.6, 0.3, 3, 58.2, 8.1, 2),
    ("Isak", "Alexander Isak", 13, "FWD", 10.6, "a", "", 6.0, 12, 165, 1, 1, 0, 1.4, 0.6, 2, 24.5, 6.4, 1),
    ("Watkins", "Ollie Watkins", 2, "FWD", 9.0, "a", "", 5.5, 11, 178, 1, 1, 0, 1.2, 0.7, 4, 18.7, 5.8, 0),
    ("Wood", "Chris Wood", 14, "FWD", 7.4, "a", "", 4.5, 9, 180, 1, 0, 0, 0.9, 0.2, 2, 12.3, 4.6, 1),
    ("Cunha", "Matheus Cunha", 12, "FWD", 6.9, "d", "Knock - 75% chance", 4.0, 8, 150, 1, 1, 0, 1.0, 0.8, 5, 9.1, 4.1, -1),
    ("Mateta", "Jean-Philippe Mateta", 7, "FWD", 7.6, "a", "", 5.0, 10, 172, 1, 1, 0, 1.1, 0.4, 3, 11.8, 5.0, 0),

    # Midfielders
    ("Salah", "Mohamed Salah", 10, "MID", 14.6, "a", "", 9.0, 22, 180, 2, 2, 1, 1.8, 1.3, 6, 46.1, 8.6, 1),
    ("Palmer", "Cole Palmer", 6, "MID", 10.4, "a", "", 7.0, 16, 180, 2, 1, 1, 1.5, 1.1, 8, 33.4, 7.0, 1),
    ("Saka", "Bukayo Saka", 1, "MID", 10.1, "a", "", 6.5, 15, 174, 1, 2, 1, 1.3, 1.5, 7, 28.9, 6.9, 0),
    ("M.Salah", "Mohamed Salah 2", 15, "MID", 9.6, "a", "", 6.8, 15, 180, 2, 1, 0, 1.4, 0.9, 5, 21.2, 6.5, 1),
    ("Semenyo", "Antoine Semenyo", 3, "MID", 7.3, "a", "", 6.2, 14, 180, 2, 1, 0, 1.1, 0.7, 14, 19.4, 5.9, 2),
    ("Rogers", "Morgan Rogers", 2, "MID", 6.9, "a", "", 5.5, 12, 176, 1, 1, 0, 0.8, 1.0, 11, 14.0, 5.2, 1),
    ("Gakpo", "Cody Gakpo", 10, "MID", 7.6, "a", "", 5.0, 11, 150, 1, 1, 1, 0.9, 0.6, 4, 12.6, 5.0, 0),
    ("Mbeumo", "Bryan Mbeumo", 12, "MID", 8.1, "a", "", 5.8, 13, 180, 2, 0, 0, 1.2, 0.5, 9, 16.7, 5.7, 0),
    ("Caicedo", "Moisés Caicedo", 6, "MID", 5.3, "a", "", 4.2, 10, 180, 0, 0, 1, 0.1, 0.3, 22, 8.9, 4.0, 1),
    ("Gravenberch", "Ryan Gravenberch", 10, "MID", 5.6, "a", "", 4.8, 11, 180, 0, 1, 1, 0.2, 0.4, 19, 11.5, 4.3, 1),
    ("Rice", "Declan Rice", 1, "MID", 6.6, "a", "", 4.5, 10, 180, 0, 1, 1, 0.4, 0.6, 17, 9.3, 4.4, 0),

    # Defenders (incl. DEFCON-friendly picks)
    ("Gabriel", "Gabriel Magalhães", 1, "DEF", 6.3, "a", "", 6.0, 14, 180, 1, 0, 2, 0.5, 0.1, 13, 22.7, 5.4, 1),
    ("Saliba", "William Saliba", 1, "DEF", 6.1, "a", "", 5.2, 12, 180, 0, 0, 2, 0.1, 0.1, 15, 14.1, 5.0, 0),
    ("VvD", "Virgil van Dijk", 10, "DEF", 6.5, "a", "", 5.5, 13, 180, 1, 0, 1, 0.4, 0.2, 12, 16.8, 5.1, 0),
    ("Gabriel M", "Gabriel dos Santos", 13, "DEF", 5.9, "a", "", 5.0, 12, 180, 0, 1, 1, 0.2, 0.5, 16, 12.0, 4.8, 1),
    ("Muñoz", "Daniel Muñoz", 7, "DEF", 5.6, "a", "", 5.8, 13, 180, 1, 1, 1, 0.4, 0.6, 18, 15.5, 5.0, 1),
    ("Milenković", "Nikola Milenković", 14, "DEF", 5.2, "a", "", 5.4, 12, 180, 1, 0, 1, 0.3, 0.1, 21, 13.3, 4.7, 1),
    ("Andersen", "Joachim Andersen", 9, "DEF", 4.6, "a", "", 4.6, 10, 180, 0, 0, 1, 0.1, 0.1, 24, 9.8, 4.1, 0),
    ("Hall", "Lewis Hall", 13, "DEF", 5.4, "a", "", 5.6, 12, 180, 0, 2, 1, 0.2, 0.7, 14, 17.2, 4.9, 1),
    ("Kerkez", "Milos Kerkez", 10, "DEF", 5.5, "a", "", 4.8, 11, 165, 0, 1, 1, 0.3, 0.5, 12, 11.1, 4.5, 0),
    ("Aina", "Ola Aina", 14, "DEF", 5.0, "d", "Hamstring - 50%", 4.0, 9, 150, 0, 0, 1, 0.1, 0.2, 20, 6.7, 3.6, -1),
    ("Burn", "Dan Burn", 13, "DEF", 4.5, "a", "", 4.4, 10, 180, 1, 0, 1, 0.2, 0.1, 23, 8.4, 4.0, 0),

    # Goalkeepers
    ("Raya", "David Raya", 1, "GKP", 5.6, "a", "", 5.5, 13, 180, 0, 0, 2, 0.0, 0.0, 0, 18.9, 4.9, 0),
    ("Sánchez", "Robert Sánchez", 6, "GKP", 5.0, "a", "", 4.8, 11, 180, 0, 0, 1, 0.0, 0.0, 0, 12.3, 4.4, 1),
    ("Pickford", "Jordan Pickford", 8, "GKP", 5.4, "a", "", 5.0, 12, 180, 0, 0, 1, 0.0, 0.0, 0, 14.6, 4.6, 0),
    ("Petrović", "Đorđe Petrović", 3, "GKP", 4.6, "a", "", 4.6, 11, 180, 0, 0, 1, 0.0, 0.0, 0, 9.5, 4.2, 1),
    ("Verbruggen", "Bart Verbruggen", 5, "GKP", 4.7, "a", "", 4.2, 9, 180, 0, 0, 1, 0.0, 0.0, 0, 7.2, 3.9, 0),
]


def build_players():
    players = []
    for (web, full, team, pos, price, status, news, form, pts, minutes,
         goals, assists, cs, xg, xa, defcon, sel, ep_next, ccev) in P:
        xgi = round(xg + xa, 2)
        defcon_per90 = round(defcon / minutes * 90, 2) if minutes else 0.0
        games = max(1, minutes // 90)
        players.append({
            "id": len(players) + 1,
            "name": full,
            "web": web,
            "team": team,
            "team_short": next(t[2] for t in TEAMS if t[0] == team),
            "pos": pos,
            "price": price,
            "status": status,
            "news": news,
            "form": form,
            "pts": pts,
            "ppg": round(pts / games, 1),
            "sel": sel,
            "minutes": minutes,
            "goals": goals,
            "assists": assists,
            "cs": cs,
            "xg": xg,
            "xa": xa,
            "xgi": xgi,
            "defcon": defcon,
            "defcon_per90": defcon_per90,
            "ict": round((goals * 3 + assists * 2 + defcon * 0.3) * 2.2 + form, 1),
            "bonus": max(0, round((pts - minutes / 90 * 2) * 0.2)),
            "ep_next": ep_next,
            "cost_change_event": ccev,
            "transfers_in_event": int(max(0, form) * 30000),
            "transfers_out_event": int(max(0, 6 - form) * 12000),
        })
    return players


def build_fixtures():
    """Round-robin-ish fixtures with FDR derived from opponent strength."""
    team_ids = [t[0] for t in TEAMS]
    strength = {t[0]: t[3] for t in TEAMS}
    base = datetime(2026, 8, 22, 14, 0, tzinfo=timezone.utc)
    fixtures = []
    for g in range(N_FUTURE_GWS):
        gw = CURRENT_GW + g
        # simple rotating pairing so every team plays once per GW
        rot = team_ids[g:] + team_ids[:g]
        half = len(rot) // 2
        homes, aways = rot[:half], rot[half:][::-1]
        kickoff = base + timedelta(days=7 * g)
        for h, a in zip(homes, aways):
            # FDR 1(easy)–5(hard) from opponent strength, +/- for venue
            fdr_h = min(5, max(1, strength[a] - 2))
            fdr_a = min(5, max(1, strength[h] - 1))
            fixtures.append({
                "gw": gw,
                "team_h": h,
                "team_a": a,
                "kickoff": kickoff.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "fdr_h": fdr_h,
                "fdr_a": fdr_a,
                "finished": gw < CURRENT_GW,
            })
    return fixtures


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="data")
    args = ap.parse_args(argv)

    teams = [{
        "id": i, "name": n, "short": s, "strength": st,
        "att_home": ah, "att_away": aa, "def_home": dh, "def_away": da,
    } for (i, n, s, st, ah, aa, dh, da) in TEAMS]

    next_deadline = datetime(2026, 8, 28, 18, 30, tzinfo=timezone.utc)
    meta = {
        "source": "sample",
        "season": "2025/26",
        "current_gw": CURRENT_GW,
        "next_gw": CURRENT_GW + 1,
        "next_deadline_utc": next_deadline.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "scoring": {
            "squad_squadsize": 15, "squad_total_spend": 100.0,
            "squad_team_limit": 3, "transfers_cost": 4, "transfers_limit": 5,
        },
    }
    write_dataset(args.out, meta=meta, teams=teams, players=build_players(),
                  fixtures=build_fixtures())
    return 0


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    raise SystemExit(main())
