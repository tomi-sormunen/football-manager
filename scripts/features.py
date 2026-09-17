"""Feature extraction for the gradient-boosted model (xpts-v2).

v2 *stacks on v1*: its features are v1's own explainable components (from
``model.project_points``) plus a few raw recent-form signals. This means v2 can
only refine what v1 already computes — it reweights and finds interactions the
hand-built model misses — and it reuses all the existing machinery
(``build_cumulative``, ``league_from``, ``project_points``), so training and the
live pipeline build identical vectors.

``build_examples`` replays history exactly like the backtest, emitting one
(feature-vector, actual-points) pair per player-gameweek — the training set.
"""
from __future__ import annotations

from model import project_points

# Ordered feature names — the JSON model and the live predictor both rely on
# this exact order.
FEATURES = [
    "v1_exp",                                             # v1's projected points
    "appearance", "attack", "defence", "defcon", "bonus",  # v1 component parts
    "p_play", "exp_min", "xg90", "xa90", "p_cs", "hit_rate", "att_mult",  # v1 detail
    "is_gk", "is_def", "is_mid", "is_fwd",               # position one-hot
    "home",
    "opp_def_norm", "team_att_norm",                     # opponent/own strength
    "att_form_team", "dfn_form_team", "att_form_opp", "dfn_form_opp",  # recent form
    "recent_pts_1", "recent_pts_3", "season_ppg",        # the player's own scoring
    "minutes", "appearances", "gws_elapsed",             # sample size / reliability
]


def feature_vector(cum, pos, team, opp, home, league, recent):
    """Build one ordered feature vector. `recent` = {last1, last3, ppg}."""
    proj = project_points(cum, pos, team, opp, home, league, "a")
    d, parts = proj["detail"], proj["parts"]
    avg_att = league.avg_att or 1.0
    avg_dfn = league.avg_dfn or 1.0
    row = {
        "v1_exp": proj["exp"],
        "appearance": parts["appearance"], "attack": parts["attack"],
        "defence": parts["defence"], "defcon": parts["defcon"], "bonus": parts["bonus"],
        "p_play": proj["p_play"], "exp_min": proj["exp_min"],
        "xg90": d["xg90"], "xa90": d["xa90"], "p_cs": d["p_cs"],
        "hit_rate": d["hit_rate"], "att_mult": d["att_mult"],
        "is_gk": 1.0 if pos == "GKP" else 0.0,
        "is_def": 1.0 if pos == "DEF" else 0.0,
        "is_mid": 1.0 if pos == "MID" else 0.0,
        "is_fwd": 1.0 if pos == "FWD" else 0.0,
        "home": 1.0 if home else 0.0,
        "opp_def_norm": league.dfn.get(opp, avg_dfn) / avg_dfn,
        "team_att_norm": league.att.get(team, avg_att) / avg_att,
        "att_form_team": league.att_form.get(team, 1.0),
        "dfn_form_team": league.dfn_form.get(team, 1.0),
        "att_form_opp": league.att_form.get(opp, 1.0),
        "dfn_form_opp": league.dfn_form.get(opp, 1.0),
        "recent_pts_1": recent["last1"], "recent_pts_3": recent["last3"],
        "season_ppg": recent["ppg"],
        "minutes": cum.minutes, "appearances": cum.appearances,
        "gws_elapsed": cum.gws_elapsed,
    }
    return [row[f] for f in FEATURES], proj


def recent_points_maps(history, upto_gw):
    """Per-player recent scoring as of `upto_gw`: last GW points, last-3-appearance
    average, and season points-per-appearance."""
    seq = {}   # pid -> list of (gw, pts) for appearances (minutes>0)
    for gw in sorted(g for g in history if g < upto_gw):
        for r in history[gw]:
            if r.get("minutes", 0) > 0:
                seq.setdefault(r["id"], []).append(r.get("pts", 0))
    out = {}
    for pid, pts in seq.items():
        last1 = pts[-1] if pts else 0.0
        last3 = sum(pts[-3:]) / len(pts[-3:]) if pts else 0.0
        ppg = sum(pts) / len(pts) if pts else 0.0
        out[pid] = {"last1": last1, "last3": last3, "ppg": ppg}
    return out


def build_examples(history, teams, league_from, build_cumulative,
                   min_gw=4, min_prior_mins=45):
    """Replay one season's history → (X, y, groups). `groups` is the GW of each
    row (useful for grouped splits). league_from/build_cumulative are passed in
    to avoid a circular import with projections."""
    gws = sorted(history)
    pos_by_id = {}
    for gw in gws:
        for r in history[gw]:
            pos_by_id.setdefault(r["id"], r.get("pos", "MID"))

    X, y, groups = [], [], []
    for t in gws:
        if t < min_gw:
            continue
        league = league_from(teams, {g: history[g] for g in gws if g < t})
        cum = build_cumulative(history, t, pos_by_id)
        recent = recent_points_maps(history, t)
        for r in history[t]:
            pid = r["id"]
            c = cum.get(pid)
            if c is None or c.minutes < min_prior_mins:
                continue
            pos = pos_by_id.get(pid, "MID")
            rec = recent.get(pid, {"last1": 0.0, "last3": 0.0, "ppg": 0.0})
            vec, _ = feature_vector(c, pos, r["team"], r["opp"],
                                    r.get("home", True), league, rec)
            X.append(vec)
            y.append(r.get("pts", 0))
            groups.append(t)
    return X, y, groups
