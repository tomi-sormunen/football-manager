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
    "pen_taker", "sp_taker",                             # set-piece / penalty duty
    "price_mom", "net_churn",                            # market: price & transfers
]

_NO_MARKET = {"pen": 0, "spo": 0, "price_mom": 0.0, "churn": 0.0}


def _duty(order):
    """Set-piece/penalty order → 1 (primary), 0.5 (backup), 0 (none)."""
    if order == 1:
        return 1.0
    if 1 < order <= 3:
        return 0.5
    return 0.0


def feature_vector(cum, pos, team, opp, home, league, recent, extra=None):
    """Build one ordered feature vector. `recent` = {last1, last3, ppg};
    `extra` = {pen, spo, price_mom, churn} (set-piece duties + market signals)."""
    proj = project_points(cum, pos, team, opp, home, league, "a")
    d, parts = proj["detail"], proj["parts"]
    avg_att = league.avg_att or 1.0
    avg_dfn = league.avg_dfn or 1.0
    ex = extra or _NO_MARKET

    def clamp(x, lo, hi):
        return max(lo, min(hi, x))

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
        "pen_taker": _duty(ex.get("pen", 0)),
        "sp_taker": _duty(ex.get("spo", 0)),
        # realized recent price move (0.1m units) and net-transfer churn as a
        # share of owners — both normalised the same way in training and serving.
        "price_mom": clamp(ex.get("price_mom", 0.0), -5, 5) / 5.0,
        "net_churn": clamp(ex.get("churn", 0.0), -0.5, 0.5) * 2.0,
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


def recent_market_maps(history, upto_gw):
    """Per-player set-piece duty and market momentum as of `upto_gw`:
    latest known penalty/set-piece order, realized price move over the last
    gameweek (0.1m units), and net-transfer churn as a share of owners."""
    seq = {}   # pid -> ordered list of rows (with market fields)
    for gw in sorted(g for g in history if g < upto_gw):
        for r in history[gw]:
            seq.setdefault(r["id"], []).append(r)
    out = {}
    for pid, rows in seq.items():
        last = rows[-1]
        pen = spo = 0
        for r in reversed(rows):                    # latest non-zero duty
            if r.get("pen", 0) and not pen:
                pen = r["pen"]
            if r.get("spo", 0) and not spo:
                spo = r["spo"]
            if pen and spo:
                break
        price_mom = 0.0
        if len(rows) >= 2:
            price_mom = last.get("value", 0) - rows[-2].get("value", 0)
        churn = last.get("tb", 0) / max(1, last.get("sel", 0)) if last.get("sel") else 0.0
        out[pid] = {"pen": pen, "spo": spo, "price_mom": price_mom, "churn": churn}
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
        market = recent_market_maps(history, t)
        for r in history[t]:
            pid = r["id"]
            c = cum.get(pid)
            if c is None or c.minutes < min_prior_mins:
                continue
            pos = pos_by_id.get(pid, "MID")
            rec = recent.get(pid, {"last1": 0.0, "last3": 0.0, "ppg": 0.0})
            vec, _ = feature_vector(c, pos, r["team"], r["opp"],
                                    r.get("home", True), league, rec,
                                    market.get(pid, _NO_MARKET))
            X.append(vec)
            y.append(r.get("pts", 0))
            groups.append(t)
    return X, y, groups
