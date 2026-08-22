"""Expected-points model for FPL Manager.

A transparent, opponent-adjusted expected-points model. The single function
``project_points`` is the whole model: given a player's accumulated stats "as of
now", their position, and the opponent/venue, it returns expected FPL points for
one fixture plus an explainable breakdown. Everything else (live projections,
the multi-gameweek horizon, and the backtest) calls this one function, so the
model that is validated by the backtest is exactly the model that ships.

Design choices (documented in docs/MODEL.md):
  * Per-90 attacking rates (xG, xA) are regressed toward position priors by
    sample size, so a player with two good games isn't over-trusted.
  * A minutes model turns recent availability into P(play) and expected minutes.
  * Opponent strength (from the FPL team ratings) scales attack and clean-sheet
    probability; home advantage is applied.
  * Clean-sheet probability uses a logistic on the defence-vs-attack strength
    gap. Its two coefficients can be *fitted* from history (see ``fit_cs``);
    sensible defaults are used until enough history exists.
  * DEFCON (2025/26) is modelled as an empirical hit-rate × 2 pts.

The model is intentionally simple and inspectable rather than a black box; the
backtest measures whether it beats naive baselines and it is meant to be
improved over time behind this same interface.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

# ---- scoring (kept in sync with docs/RULES.md; overridable via meta.scoring) -
GOAL_PTS = {"GKP": 10, "DEF": 6, "MID": 5, "FWD": 4}
CS_PTS = {"GKP": 4, "DEF": 4, "MID": 1, "FWD": 0}
APPEARANCE_60 = 2          # points for 60+ minutes
APPEARANCE_SUB = 1         # points for 1–59 minutes
DEFCON_THRESHOLD = {"GKP": 99, "DEF": 10, "MID": 12, "FWD": 12}
DEFCON_PTS = 2

# ---- position priors for regression-to-mean (per-90) ------------------------
# Weak priors: league-ish averages a player's rate is pulled toward when they
# have few minutes. Units: expected goals / assists per 90.
XG90_PRIOR = {"GKP": 0.0, "DEF": 0.05, "MID": 0.15, "FWD": 0.35}
XA90_PRIOR = {"GKP": 0.0, "DEF": 0.06, "MID": 0.15, "FWD": 0.12}
# Regression strength, in "90s of prior data". Higher = trust the prior longer.
K_RATE = 6.0
# DEFCON hit-rate prior (share of matches hitting the threshold) and strength.
DEFCON_PRIOR = {"GKP": 0.0, "DEF": 0.35, "MID": 0.30, "FWD": 0.10}
K_DEFCON = 5.0
# Bonus points per 90 prior.
BONUS90_PRIOR = 0.25
K_BONUS = 6.0


def clamp(x, lo, hi):
    return max(lo, min(hi, x))


def sigmoid(x):
    return 1.0 / (1.0 + math.exp(-clamp(x, -30, 30)))


@dataclass
class League:
    """League-wide context: team strengths and (optionally fitted) CS coeffs."""
    att: dict            # team_id -> attacking strength (higher = better attack)
    dfn: dict            # team_id -> defensive strength (higher = harder to score on)
    avg_att: float
    avg_dfn: float
    cs_bias: float = -0.10     # logistic intercept
    cs_slope: float = 1.15     # logistic slope on normalised strength gap
    cs_home: float = 0.35      # home-advantage bump (log-odds)

    @classmethod
    def from_teams(cls, teams):
        # Use the mean of home/away attack & defence ratings per team.
        att, dfn = {}, {}
        for t in teams:
            att[t["id"]] = (t["att_home"] + t["att_away"]) / 2 or t.get("strength", 3) * 300
            dfn[t["id"]] = (t["def_home"] + t["def_away"]) / 2 or t.get("strength", 3) * 300
        avg_att = sum(att.values()) / len(att)
        avg_dfn = sum(dfn.values()) / len(dfn)
        return cls(att=att, dfn=dfn, avg_att=avg_att, avg_dfn=avg_dfn)


@dataclass
class Cumulative:
    """A player's accumulated inputs as of the moment we're projecting from."""
    minutes: float = 0.0
    xg: float = 0.0
    xa: float = 0.0
    defcon_hits: float = 0.0   # matches reaching the DEFCON threshold
    bonus: float = 0.0
    appearances: int = 0       # matches with any minutes
    gws_elapsed: int = 0       # gameweeks the player's team has played
    recent_minutes: list = field(default_factory=list)  # last few GWs, newest last


def _rate90(total, minutes, prior, k):
    """Per-90 rate regressed toward a prior by the amount of data (in 90s)."""
    nineties = minutes / 90.0
    return (total + prior * k) / (nineties + k)


def minutes_model(cum: Cumulative, status: str = "a"):
    """Return (p_play, expected_minutes) from recent availability + status."""
    avail = {"a": 1.0, "d": 0.6, "i": 0.05, "s": 0.03, "u": 0.03, "n": 0.03}.get(status, 0.5)
    recent = cum.recent_minutes[-5:]
    if recent:
        p_play = sum(1 for m in recent if m > 0) / len(recent)
        exp_min = sum(recent) / len(recent)
    elif cum.appearances:
        p_play = clamp(cum.appearances / max(1, cum.gws_elapsed), 0, 1)
        exp_min = cum.minutes / cum.appearances
    else:
        p_play, exp_min = 0.5, 60.0
    p_play *= avail
    exp_min = clamp(exp_min * (0.5 + 0.5 * avail), 0, 90)
    return clamp(p_play, 0, 1), exp_min


def fit_cs(league: League, samples):
    """Fit the clean-sheet logistic (bias, slope, home) from history samples.

    samples: iterable of (strength_gap, is_home, kept_clean_sheet:bool). Uses a
    few epochs of plain logistic-regression gradient descent. No-op if there are
    too few samples — the sensible defaults stay in place.
    """
    data = [(g, 1.0 if hm else 0.0, 1.0 if cs else 0.0) for g, hm, cs in samples]
    if len(data) < 200:
        return league
    b, w, h = league.cs_bias, league.cs_slope, league.cs_home
    lr = 0.05
    for _ in range(300):
        gb = gw = gh = 0.0
        for gap, hm, y in data:
            z = b + w * gap + h * hm
            err = sigmoid(z) - y
            gb += err
            gw += err * gap
            gh += err * hm
        n = len(data)
        b -= lr * gb / n
        w -= lr * gw / n
        h -= lr * gh / n
    league.cs_bias, league.cs_slope, league.cs_home = b, w, h
    return league


def cs_probability(league: League, team_id, opp_id, home: bool):
    """P(clean sheet) for `team_id` vs `opp_id`, from the strength gap."""
    d = league.dfn.get(team_id, league.avg_dfn)
    a = league.att.get(opp_id, league.avg_att)
    scale = (league.avg_dfn + league.avg_att) / 2 or 1.0
    gap = (d - a) / scale                     # >0 => our defence outweighs their attack
    z = league.cs_bias + league.cs_slope * gap + league.cs_home * (1 if home else 0)
    return clamp(sigmoid(z), 0.02, 0.85)


def _attack_multiplier(league: League, opp_id, home: bool):
    """Scale attacking output by how leaky the opponent is + home advantage."""
    opp_def = league.dfn.get(opp_id, league.avg_dfn)
    mult = league.avg_dfn / opp_def if opp_def else 1.0   # weak defence => >1
    mult *= 1.08 if home else 0.94
    return clamp(mult, 0.6, 1.6)


def project_points(cum: Cumulative, pos: str, team_id, opp_id, home: bool,
                   league: League, status: str = "a"):
    """Expected FPL points for ONE fixture, with a breakdown. The whole model."""
    p_play, exp_min = minutes_model(cum, status)
    nineties = exp_min / 90.0

    # Appearance points: blended sub/full expectation, gated by P(play).
    p_full = clamp((exp_min - 30) / 60.0, 0, 1)      # rough P(60+ | playing)
    appearance = p_play * (p_full * APPEARANCE_60 + (1 - p_full) * APPEARANCE_SUB)

    # Attacking returns from regressed per-90 rates, opponent-adjusted.
    xg90 = _rate90(cum.xg, cum.minutes, XG90_PRIOR.get(pos, 0.1), K_RATE)
    xa90 = _rate90(cum.xa, cum.minutes, XA90_PRIOR.get(pos, 0.1), K_RATE)
    amult = _attack_multiplier(league, opp_id, home)
    exp_goals = xg90 * nineties * amult * p_play
    exp_assists = xa90 * nineties * amult * p_play
    attack = exp_goals * GOAL_PTS.get(pos, 4) + exp_assists * 3

    # Clean sheet (value only for GKP/DEF and a little for MID).
    p_cs = cs_probability(league, team_id, opp_id, home)
    defence = p_cs * CS_PTS.get(pos, 0) * p_play

    # DEFCON: empirical hit-rate × 2 pts.
    hit_rate = _rate90(cum.defcon_hits, cum.minutes, DEFCON_PRIOR.get(pos, 0.2), K_DEFCON) \
        if pos != "GKP" else 0.0
    # hit_rate here is per-90; treat as per-appearance probability, capped at 1.
    defcon = clamp(hit_rate, 0, 1) * DEFCON_PTS * p_play

    # Bonus, from a regressed per-90 rate.
    bonus90 = _rate90(cum.bonus, cum.minutes, BONUS90_PRIOR, K_BONUS)
    bonus = bonus90 * nineties * p_play

    total = appearance + attack + defence + defcon + bonus
    return {
        "exp": round(total, 2),
        "p_play": round(p_play, 2),
        "exp_min": round(exp_min, 1),
        "parts": {
            "appearance": round(appearance, 2),
            "attack": round(attack, 2),
            "defence": round(defence, 2),
            "defcon": round(defcon, 2),
            "bonus": round(bonus, 2),
        },
        "detail": {
            "xg90": round(xg90, 3), "xa90": round(xa90, 3),
            "p_cs": round(p_cs, 3), "hit_rate": round(clamp(hit_rate, 0, 1), 3),
            "att_mult": round(amult, 3),
        },
    }
