"""Build data/projections.json from the model + history.

Turns accumulated history (and, as a fallback, current-season totals) into
expected points for each player over the next N gameweeks, writing an
explainable projection the frontend can consume. Shared helpers here
(`load_history`, `build_cumulative`, `league_from`) are also used by the
backtest so the two always agree.
"""
from __future__ import annotations

import glob
import json
import os

from model import Cumulative, League, fit_cs, project_points

HORIZON = 6


# ---- history loading --------------------------------------------------------

def load_history(history_dir):
    """Load data/history/gw*.json → {gw: [rows]}, sorted by gameweek.

    Each row: {id, pos, team, opp, home, minutes, xg, xa, defcon, bonus,
    gc, pts}. `defcon` is the match's defensive-action tally (a "hit" is
    compared against the position threshold when building cumulatives).
    """
    out = {}
    for path in sorted(glob.glob(os.path.join(history_dir, "gw*.json"))):
        try:
            gw = int(os.path.basename(path)[2:].split(".")[0])
        except ValueError:
            continue
        with open(path, encoding="utf-8") as fh:
            out[gw] = json.load(fh)
    return dict(sorted(out.items()))


from model import DEFCON_THRESHOLD


def build_cumulative(history, upto_gw, pos_by_id):
    """Accumulate each player's inputs from all history GWs < upto_gw."""
    cum = {}
    gws = [g for g in history if g < upto_gw]
    n_gw = len(gws)
    for gw in gws:
        for r in history[gw]:
            pid = r["id"]
            c = cum.get(pid)
            if c is None:
                c = cum[pid] = Cumulative()
            mins = r.get("minutes", 0)
            c.minutes += mins
            c.xg += r.get("xg", 0.0)
            c.xa += r.get("xa", 0.0)
            c.bonus += r.get("bonus", 0)
            if mins > 0:
                c.appearances += 1
            pos = pos_by_id.get(pid, r.get("pos", "MID"))
            thr = DEFCON_THRESHOLD.get(pos, 12)
            if r.get("defcon", 0) >= thr:
                c.defcon_hits += 1
            c.recent_minutes.append(mins)
    for c in cum.values():
        c.gws_elapsed = n_gw
    return cum


def cumulative_from_season(players, current_gw):
    """Fallback when there is little/no history: build cumulatives from the
    current-season totals already in players.json."""
    cum = {}
    for p in players:
        c = Cumulative()
        c.minutes = p.get("minutes", 0)
        c.xg = p.get("xg", 0.0)
        c.xa = p.get("xa", 0.0)
        c.bonus = p.get("bonus", 0)
        c.appearances = max(1, round(c.minutes / 90)) if c.minutes else 0
        c.gws_elapsed = max(1, current_gw)
        thr = DEFCON_THRESHOLD.get(p["pos"], 12)
        # season defcon_per90 → approx share of matches hitting the threshold
        per90 = p.get("defcon_per90", 0.0)
        c.defcon_hits = c.appearances * min(1.0, per90 / thr) if thr < 99 else 0
        cum[p["id"]] = c
    return cum


# ---- league (with fitted clean-sheet coefficients) --------------------------

def league_from(teams, history=None):
    league = League.from_teams(teams)
    if history:
        samples = []
        for gw, rows in history.items():
            for r in rows:
                if r.get("minutes", 0) <= 0 or r.get("pos") not in ("GKP", "DEF"):
                    continue
                d = league.dfn.get(r["team"], league.avg_dfn)
                a = league.att.get(r["opp"], league.avg_att)
                scale = (league.avg_dfn + league.avg_att) / 2 or 1.0
                gap = (d - a) / scale
                samples.append((gap, r.get("home", True), r.get("gc", 1) == 0))
        fit_cs(league, samples)
    return league


# ---- upcoming fixtures ------------------------------------------------------

def upcoming_by_team(fixtures, from_gw, horizon):
    """team_id -> [(gw, opp_id, home)] for the next `horizon` gameweeks."""
    out = {}
    for fx in sorted(fixtures, key=lambda f: f["gw"]):
        if fx["gw"] < from_gw or fx["gw"] >= from_gw + horizon:
            continue
        out.setdefault(fx["team_h"], []).append((fx["gw"], fx["team_a"], True))
        out.setdefault(fx["team_a"], []).append((fx["gw"], fx["team_h"], False))
    return out


# ---- main projection --------------------------------------------------------

def project_all(players, teams, fixtures, meta, history, horizon=HORIZON):
    next_gw = meta["next_gw"]
    pos_by_id = {p["id"]: p["pos"] for p in players}
    status_by_id = {p["id"]: p.get("status", "a") for p in players}

    # Guard against history that doesn't represent the current player pool
    # (e.g. leftover sample snapshots on a live dataset, or a season rollover):
    # if few of today's players appear in it, ignore it and use season totals.
    if history:
        current_ids = {p["id"] for p in players}
        hist_ids = {r["id"] for rows in history.values() for r in rows}
        overlap = len(current_ids & hist_ids) / max(1, len(current_ids))
        if overlap < 0.5:
            print(f"WARN history covers only {overlap:.0%} of current players — "
                  "ignoring it as unrepresentative; using current-season totals.")
            history = {}

    league = league_from(teams, history)
    if history:
        cum = build_cumulative(history, next_gw, pos_by_id)
    else:
        cum = cumulative_from_season(players, meta["current_gw"])

    fixtures_by_team = upcoming_by_team(fixtures, next_gw, horizon)

    result = {}
    for p in players:
        pid = p["id"]
        c = cum.get(pid) or Cumulative()
        by_gw = []
        for (gw, opp, home) in fixtures_by_team.get(p["team"], []):
            proj = project_points(c, p["pos"], p["team"], opp, home, league,
                                  status_by_id.get(pid, "a"))
            proj["gw"] = gw
            proj["opp"] = opp
            proj["home"] = home
            by_gw.append(proj)
        total5 = round(sum(x["exp"] for x in by_gw), 2)
        result[pid] = {
            "next": by_gw[0]["exp"] if by_gw else 0.0,
            "next_parts": by_gw[0]["parts"] if by_gw else None,
            "next_detail": by_gw[0]["detail"] if by_gw else None,
            "sum": total5,
            "by_gw": [{"gw": x["gw"], "exp": x["exp"]} for x in by_gw],
        }
    return {
        "meta": {
            "model": "xpts-v1",
            "horizon": horizon,
            "from_gw": next_gw,
            "history_gws": len(history) if history else 0,
            "cs_coeffs": {"bias": round(league.cs_bias, 3),
                          "slope": round(league.cs_slope, 3),
                          "home": round(league.cs_home, 3)},
        },
        "players": result,
    }


def write_projections(outdir, projections):
    os.makedirs(outdir, exist_ok=True)
    path = os.path.join(outdir, "projections.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(projections, fh, ensure_ascii=False, separators=(",", ":"))
        fh.write("\n")
    n = len(projections.get("players", {}))
    print(f"Wrote projections for {n} players "
          f"(model={projections['meta']['model']}, "
          f"history_gws={projections['meta']['history_gws']}) to {path}")
