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

from model import Cumulative, League, clamp, fit_cs, project_points

HORIZON = 6

# Recency + form knobs (env-overridable so they can be A/B'd on the backtest).
# Per-gameweek decay applied to a player's stats when building cumulatives:
# 1.0 = every gameweek counts equally; <1 = recent gameweeks weigh more.
RECENCY_DECAY = float(os.environ.get("FM_RECENCY_DECAY", "0.9"))
# How many recent gameweeks feed a team's recent-form rating.
FORM_RECENT_N = int(os.environ.get("FM_FORM_RECENT_N", "5"))


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


def build_cumulative(history, upto_gw, pos_by_id, decay=None):
    """Accumulate each player's inputs from all history GWs < upto_gw.

    Rate inputs (xG, xA, bonus, DEFCON hits) are **recency-weighted**: a recent
    gameweek counts `1/decay` times more than the one before it. To keep the
    regression-to-mean honest, weights only reshape the *rate* — the effective
    totals are rescaled back to the player's real minutes, so a hot player over
    few games is still regressed by their true sample size. `decay=1.0`
    reproduces the old equal-weight behaviour exactly.
    """
    if decay is None:
        decay = RECENCY_DECAY
    cum = {}
    wacc = {}   # pid -> [w·minutes, w·xg, w·xa, w·bonus, w·defcon_hit]
    gws = sorted(g for g in history if g < upto_gw)
    n_gw = len(gws)
    latest = gws[-1] if gws else 0
    for gw in gws:
        w = decay ** (latest - gw)
        for r in history[gw]:
            pid = r["id"]
            c = cum.get(pid)
            if c is None:
                c = cum[pid] = Cumulative()
                wacc[pid] = [0.0, 0.0, 0.0, 0.0, 0.0]
            mins = r.get("minutes", 0)
            c.minutes += mins                      # raw totals (real sample size)
            if mins > 0:
                c.appearances += 1
            c.recent_minutes.append(mins)
            pos = pos_by_id.get(pid, r.get("pos", "MID"))
            thr = DEFCON_THRESHOLD.get(pos, 12)
            hit = 1.0 if r.get("defcon", 0) >= thr else 0.0
            a = wacc[pid]
            a[0] += w * mins
            a[1] += w * r.get("xg", 0.0)
            a[2] += w * r.get("xa", 0.0)
            a[3] += w * r.get("bonus", 0)
            a[4] += w * hit
    for pid, c in cum.items():
        c.gws_elapsed = n_gw
        wmin, wxg, wxa, wbonus, wdef = wacc[pid]
        if wmin > 0 and c.minutes > 0:
            scale = c.minutes / wmin               # rate → effective total on real minutes
            c.xg = wxg * scale
            c.xa = wxa * scale
            c.bonus = wbonus * scale
            c.defcon_hits = wdef * scale
    return cum


def team_form(history, teams, recent_n=None):
    """Recent attack/defence form per team as multipliers around 1.0.

    Attack form = recent expected goals *for* per match vs the league average
    (>1 = scoring more than average lately). Defence form = league-average goals
    conceded / this team's recent goals conceded per match (>1 = meaner than
    average lately). Returns ({}, {}) — neutral — when history is too thin.
    """
    if recent_n is None:
        recent_n = FORM_RECENT_N
    per = {}   # team -> {gw: (xg_for, goals_against)}
    for gw, rows in history.items():
        agg = {}
        for r in rows:
            t = r["team"]
            a = agg.setdefault(t, [0.0, 0])
            a[0] += r.get("xg", 0.0)
            a[1] = max(a[1], r.get("gc", 0))       # team goals conceded that match
        for t, (xgf, ga) in agg.items():
            per.setdefault(t, {})[gw] = (xgf, ga)

    att_raw, dfn_raw = {}, {}
    for t, byg in per.items():
        gws = sorted(byg)[-recent_n:]
        if len(gws) < 2:                           # too few matches to trust
            continue
        att_raw[t] = sum(byg[g][0] for g in gws) / len(gws)
        dfn_raw[t] = sum(byg[g][1] for g in gws) / len(gws)
    if len(att_raw) < 6:                           # not enough teams with data
        return {}, {}

    avg_att = sum(att_raw.values()) / len(att_raw) or 1.0
    avg_ga = sum(dfn_raw.values()) / len(dfn_raw) or 1.0
    att_form, dfn_form = {}, {}
    for t in att_raw:
        att_form[t] = clamp(att_raw[t] / avg_att, 0.6, 1.6)
        dfn_form[t] = clamp(avg_ga / max(dfn_raw[t], 0.3), 0.6, 1.6)
    return att_form, dfn_form


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
        league.att_form, league.dfn_form = team_form(history, teams)
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
    from model import FORM_WEIGHT, CS_FORM_WEIGHT
    return {
        "meta": {
            "model": "xpts-v1",
            "horizon": horizon,
            "from_gw": next_gw,
            "history_gws": len(history) if history else 0,
            "cs_coeffs": {"bias": round(league.cs_bias, 3),
                          "slope": round(league.cs_slope, 3),
                          "home": round(league.cs_home, 3)},
            "form": {"recency_decay": RECENCY_DECAY, "att_weight": FORM_WEIGHT,
                     "cs_weight": CS_FORM_WEIGHT, "teams_rated": len(league.att_form)},
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
