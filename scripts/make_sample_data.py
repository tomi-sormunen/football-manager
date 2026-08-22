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
import json
import os
import random
import sys
from datetime import datetime, timedelta, timezone

from fpl_common import write_dataset
from model import DEFCON_THRESHOLD, GOAL_PTS
from projections import project_all, write_projections

HISTORY_GWS = 8            # finished GWs simulated into data/history/
CURRENT_GW = HISTORY_GWS   # last finished GW
N_FUTURE_GWS = 8           # upcoming GWs with fixtures for projections
NEXT_GW = CURRENT_GW + 1
RNG = random.Random(42)    # deterministic sample data

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


SHORT = {t[0]: t[2] for t in TEAMS}
STRENGTH = {t[0]: t[3] for t in TEAMS}
ATT = {t[0]: (t[4] + t[5]) / 2 for t in TEAMS}
DFN = {t[0]: (t[6] + t[7]) / 2 for t in TEAMS}
AVG_ATT = sum(ATT.values()) / len(ATT)
AVG_DFN = sum(DFN.values()) / len(DFN)


def latent(row):
    """Turn a roster row's headline numbers into per-match latent rates."""
    (_web, _full, _team, pos, _price, status, _news, _form, _pts, minutes,
     _g, _a, _cs, xg, xa, defcon, _sel, _ep, _cc) = row
    nineties = max(0.5, minutes / 90)
    start_p = {"a": 0.95, "d": 0.6, "i": 0.1, "s": 0.05, "u": 0.05}.get(status, 0.9)
    if minutes < 160 and status == "a":
        start_p = 0.8
    return {
        "pos": pos,
        "xg90": xg / nineties,
        "xa90": xa / nineties,
        "defcon90": defcon / nineties,   # avg defensive-action count per 90
        "start_p": start_p,
    }


def poisson(rng, lam):
    """Knuth's Poisson sampler (small lambdas here)."""
    import math
    l, k, p = math.exp(-lam), 0, 1.0
    while True:
        k += 1
        p *= rng.random()
        if p <= l:
            return k - 1


def build_fixtures():
    """Round-robin-ish fixtures GW1..(HISTORY_GWS+N_FUTURE_GWS)."""
    team_ids = [t[0] for t in TEAMS]
    base = datetime(2026, 6, 20, 14, 0, tzinfo=timezone.utc)
    fixtures = []
    total = HISTORY_GWS + N_FUTURE_GWS
    for g in range(total):
        gw = 1 + g
        rot = team_ids[g % len(team_ids):] + team_ids[:g % len(team_ids)]
        half = len(rot) // 2
        homes, aways = rot[:half], rot[half:][::-1]
        kickoff = base + timedelta(days=7 * g)
        for hteam, ateam in zip(homes, aways):
            fixtures.append({
                "gw": gw, "team_h": hteam, "team_a": ateam,
                "kickoff": kickoff.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "fdr_h": min(5, max(1, STRENGTH[ateam] - 2)),
                "fdr_a": min(5, max(1, STRENGTH[hteam] - 1)),
                "finished": gw <= HISTORY_GWS,
            })
    return fixtures


def team_opp_map(fixtures, gw):
    m = {}
    for fx in fixtures:
        if fx["gw"] != gw:
            continue
        m[fx["team_h"]] = (fx["team_a"], True)
        m[fx["team_a"]] = (fx["team_h"], False)
    return m


def simulate_history(fixtures):
    """Simulate HISTORY_GWS finished gameweeks → {gw: [rows]} + per-player totals."""
    lat = {i + 1: latent(P[i]) for i in range(len(P))}
    pos_by_id = {i + 1: P[i][3] for i in range(len(P))}
    team_by_id = {i + 1: P[i][2] for i in range(len(P))}
    history = {}

    for gw in range(1, HISTORY_GWS + 1):
        opp_map = team_opp_map(fixtures, gw)
        rows = []
        for pid, L in lat.items():
            pos, team = pos_by_id[pid], team_by_id[pid]
            opp, home = opp_map.get(team, (0, True))
            played = RNG.random() < L["start_p"]
            minutes = 0
            if played:
                minutes = 90 if RNG.random() < 0.8 else RNG.randint(60, 88)
            elif RNG.random() < 0.15:
                minutes = RNG.randint(10, 55)     # cameo
            n90 = minutes / 90

            # opponent-adjusted attacking output
            amult = (AVG_DFN / DFN.get(opp, AVG_DFN)) * (1.08 if home else 0.94)
            xg = max(0.0, RNG.gauss(L["xg90"] * n90 * amult, 0.15)) if minutes else 0.0
            xa = max(0.0, RNG.gauss(L["xa90"] * n90 * amult, 0.12)) if minutes else 0.0
            goals = poisson(RNG, xg) if minutes else 0
            assists = poisson(RNG, xa) if minutes else 0
            defcon = int(max(0, RNG.gauss(L["defcon90"] * n90, 2.0))) if minutes else 0

            # goals conceded from strength mismatch
            lam_conc = 1.3 * (ATT.get(opp, AVG_ATT) / AVG_DFN) * (0.9 if home else 1.1)
            gc = poisson(RNG, lam_conc) if minutes else 0
            cs = minutes >= 60 and gc == 0

            pts = 0
            if minutes > 0:
                pts += 2 if minutes >= 60 else 1
            pts += goals * GOAL_PTS.get(pos, 4) + assists * 3
            if cs and pos in ("GKP", "DEF"):
                pts += 4
            elif cs and pos == "MID":
                pts += 1
            if pos in ("GKP", "DEF") and minutes >= 60:
                pts -= gc // 2
            if defcon >= DEFCON_THRESHOLD.get(pos, 12):
                pts += 2
            bonus = RNG.choice([0, 0, 0, 1, 2, 3]) if pts >= 6 else 0
            pts += bonus

            rows.append({
                "id": pid, "pos": pos, "team": team, "opp": opp, "home": home,
                "minutes": minutes, "xg": round(xg, 2), "xa": round(xa, 2),
                "goals": goals, "assists": assists,
                "defcon": defcon, "bonus": bonus, "gc": gc, "pts": max(0, pts),
            })
        history[gw] = rows
    return history


def players_from_history(history):
    """Aggregate simulated history into current-season player rows."""
    agg = {}
    for gw in sorted(history):
        for r in history[gw]:
            a = agg.setdefault(r["id"], {"minutes": 0, "xg": 0.0, "xa": 0.0,
                "goals": 0, "assists": 0, "defcon": 0, "bonus": 0, "cs": 0,
                "pts": 0, "apps": 0, "recent": []})
            a["minutes"] += r["minutes"]
            a["xg"] += r["xg"]
            a["xa"] += r["xa"]
            a["goals"] += r["goals"]
            a["assists"] += r["assists"]
            a["defcon"] += r["defcon"]
            a["bonus"] += r["bonus"]
            a["pts"] += r["pts"]
            if r["minutes"] > 0:
                a["apps"] += 1
            if r["minutes"] >= 60 and r["gc"] == 0 and r["pos"] in ("GKP", "DEF", "MID"):
                a["cs"] += 1
            a["recent"].append(r["pts"])

    players = []
    for i, row in enumerate(P):
        pid = i + 1
        (web, full, team, pos, price, status, news, _form, _pts, _min,
         _g, _a, _cs, _xg, _xa, _dc, sel, _ep, ccev) = row
        a = agg[pid]
        apps = max(1, a["apps"])
        minutes = a["minutes"]
        form = round(sum(a["recent"][-5:]) / min(5, len(a["recent"])), 1)
        players.append({
            "id": pid, "name": full, "web": web, "team": team,
            "team_short": SHORT[team], "pos": pos, "price": price,
            "status": status, "news": news, "form": form, "pts": a["pts"],
            "ppg": round(a["pts"] / apps, 1), "sel": sel, "minutes": minutes,
            "goals": a["goals"], "assists": a["assists"],
            "cs": a["cs"], "xg": round(a["xg"], 1), "xa": round(a["xa"], 1),
            "xgi": round(a["xg"] + a["xa"], 1), "defcon": a["defcon"],
            "defcon_per90": round(a["defcon"] / minutes * 90, 2) if minutes else 0.0,
            "ict": round((a["xg"] + a["xa"]) * 20 + a["defcon"] * 0.3 + form, 1),
            "bonus": a["bonus"], "ep_next": form,
            "cost_change_event": ccev,
            "transfers_in_event": int(max(0, form) * 30000),
            "transfers_out_event": int(max(0, 6 - form) * 12000),
        })
    return players


def build_sample_entry():
    """A plausible 15-man squad (2-5-5-3) picked from the sample roster."""
    # (element_id, slot). Slots 1-11 start (1=GK), 12-15 bench (12=backup GK).
    starters = [
        (29, 1),                                   # Raya (GK)
        (18, 2), (20, 3), (22, 4), (23, 5),        # Gabriel, VvD, Muñoz, Milenković
        (7, 6), (8, 7), (9, 8), (11, 9),           # Salah, Palmer, Saka, Semenyo
        (1, 10), (3, 11),                          # Haaland, Watkins
    ]
    bench = [(32, 12), (15, 13), (27, 14), (4, 15)]  # Petrović, Caicedo, Aina, Wood
    picks = []
    for eid, slot in starters + bench:
        picks.append({
            "element": eid, "slot": slot,
            "is_captain": eid == 7,                # Salah (C)
            "is_vice": eid == 1,                   # Haaland (VC)
            "multiplier": (2 if eid == 7 else (0 if slot >= 12 else 1)),
        })
    return {
        "id": 9155976, "manager": "Sample Manager", "team_name": "Sample FC",
        "event": CURRENT_GW, "overall_points": 512, "overall_rank": 850000,
        "gw_points": 61, "bank": 1.5, "squad_value": 100.8,
        "event_transfers": 1, "event_transfers_cost": 0,
        "picks": picks, "source": "sample",
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="data")
    args = ap.parse_args(argv)

    teams = [{
        "id": i, "name": n, "short": s, "strength": st,
        "att_home": ah, "att_away": aa, "def_home": dh, "def_away": da,
    } for (i, n, s, st, ah, aa, dh, da) in TEAMS]

    fixtures = build_fixtures()
    history = simulate_history(fixtures)

    # write history snapshots
    hist_dir = os.path.join(args.out, "history")
    os.makedirs(hist_dir, exist_ok=True)
    for gw, rows in history.items():
        with open(os.path.join(hist_dir, f"gw{gw:02d}.json"), "w", encoding="utf-8") as fh:
            json.dump(rows, fh, ensure_ascii=False, separators=(",", ":"))
            fh.write("\n")

    players = players_from_history(history)

    next_deadline = datetime(2026, 8, 21, 18, 30, tzinfo=timezone.utc)
    meta = {
        "source": "sample", "season": "2025/26",
        "current_gw": CURRENT_GW, "next_gw": NEXT_GW,
        "next_deadline_utc": next_deadline.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "scoring": {"squad_squadsize": 15, "squad_total_spend": 100.0,
                    "squad_team_limit": 3, "transfers_cost": 4, "transfers_limit": 5},
    }
    write_dataset(args.out, meta=meta, teams=teams, players=players, fixtures=fixtures)

    # model projections from the simulated history
    projections = project_all(players, teams, fixtures, meta, history)
    write_projections(args.out, projections)

    # sample squad so the "My Team" view renders without the FPL API
    with open(os.path.join(args.out, "entry.json"), "w", encoding="utf-8") as fh:
        json.dump(build_sample_entry(), fh, ensure_ascii=False, separators=(",", ":"))
        fh.write("\n")
    print("Wrote sample data/entry.json (My Team)")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    raise SystemExit(main())
