# Expected-points model (`xpts-v1`)

The projections behind captaincy, transfers, value and differentials come from a
transparent, opponent-adjusted **expected-points model**. It's deliberately
inspectable rather than a black box, and it's validated by a backtest so we can
tell whether it actually beats naive guessing.

The whole model is one function — [`project_points`](../scripts/model.py) —
which takes a player's accumulated stats "as of now", their position and the
opponent/venue, and returns expected FPL points for one fixture plus a
breakdown. Both the live projections and the backtest call that same function,
so **the model we validate is exactly the model that ships**.

## Inputs

Accumulated per player (from `data/history/` when available, else current-season
totals in `players.json`):

- minutes, appearances, and recent per-GW minutes (for the minutes model)
- expected goals (xG) and expected assists (xA)
- DEFCON hits — matches reaching the position threshold (10 for DEF, 12 for
  MID/FWD)
- bonus points
- team attack/defence strength ratings and the fixture's opponent + venue

## How a projection is built

For one upcoming fixture:

```
expected_points =
      appearance                     # P(play) × (P(60+)×2 + P(<60)×1)
    + goals × goal_points[pos]       # xG/90 (regressed) × mins × opp × venue
    + assists × 3                    # xA/90 (regressed) × mins × opp × venue
    + P(clean sheet) × cs_points[pos]
    + DEFCON_hit_rate × 2
    + expected_bonus
```

Key ideas:

1. **Regression to the mean.** Per-90 rates are pulled toward position priors by
   sample size: `rate = (total + prior·k) / (nineties + k)`. A player with two
   hot games isn't extrapolated to a full season of the same.
2. **Minutes model.** Recent availability + the FPL `status` flag give P(play)
   and expected minutes — this is what down-weights rotation and injury risks.
3. **Opponent & venue adjustment.** Attacking output scales with how leaky the
   opponent is (their defensive rating vs league average) and a home/away bump.
4. **Clean sheets.** A logistic on the *defence-minus-attack* strength gap.
   Its coefficients can be **fitted from history** (`fit_cs`); sensible defaults
   apply until there's enough data.
5. **DEFCON (2025/26).** Modelled as an empirical hit-rate × 2 points, so
   ball-winning defenders and CDMs are valued correctly.
6. **Recent form.** Two gentle, tunable nudges on top of the above:
   - *Player recency* — when building a player's cumulative stats, recent
     gameweeks weigh more (`RECENCY_DECAY`, default 0.9). Crucially this only
     reshapes the *rate*; the effective totals are rescaled back to the player's
     real minutes, so regression-to-mean still uses their true sample size.
   - *Team form* — each club gets a recent attack rating (expected goals *for*
     per match vs league average) and defence rating (goals conceded vs average)
     from the last few gameweeks. These multiply the opponent adjustment
     (`FORM_WEIGHT`) and shift clean-sheet probability (`CS_FORM_WEIGHT`), so an
     in-form attack / leaky defence moves projections — on top of FPL's static
     strength ratings, which already price in much of the season-long picture.

   All three weights are env-overridable (`FM_RECENCY_DECAY`, `FM_FORM_WEIGHT`,
   `FM_CS_FORM_WEIGHT`) and recorded in `projections.json`'s `meta.form`. Setting
   them to `1.0 / 0 / 0` reproduces the pre-form model exactly.

Every term is returned in the `parts` breakdown, which is what the Captains view
draws as bars — so you can always see *why* a player is projected where they are.

## Backtesting

[`scripts/backtest.py`](../scripts/backtest.py) replays finished gameweeks. For
each GW *t* (from the 4th on), it builds each player's inputs from GWs **before**
*t* only, predicts their points for *t* using their real opponent/venue that
week, and compares to what they actually scored. It reports **MAE, RMSE and
correlation** for the model and for two baselines:

- **last** — predict last gameweek's points
- **ppg** — predict the player's mean points so far

A model worth shipping should beat both. Results are written to
`data/backtest.json` and printed in CI.

### Real backtest results

You don't have to wait a season for real numbers:
[`scripts/backfill_history.py`](../scripts/backfill_history.py) converts past
seasons from the open [`vaastav/Fantasy-Premier-League`](https://github.com/vaastav/Fantasy-Premier-League)
dataset into our history schema, and the backtest runs straight over them.

Backtested over **2022-23 + 2023-24** (30,797 player-gameweek samples), each
prediction using only data available *before* that gameweek:

| Predictor | MAE ↓ | RMSE ↓ | Correlation ↑ |
|---|---|---|---|
| **`xpts-v1` model** | **1.76** | **2.61** | **0.377** |
| baseline: last GW's points | 1.86 | 3.31 | 0.284 |
| baseline: season points-per-game | 2.12 | 2.82 | 0.281 |

The model beats both naive baselines on **all three** metrics. Per-player,
per-gameweek FPL scoring is inherently noisy (hauls and blanks), so a
correlation around 0.38 is a solid result rather than a low one — the point is
the consistent edge over guessing, sustained across two full seasons and every
position (MID best at MAE 1.57, DEF hardest at 1.99).

#### On the recent-form weighting

The form/recency nudges were tuned on the **2024-25 + 2025-26** backfill
(30,621 samples). The honest finding: their effect is **small and mixed** —
because FPL's own team ratings already price in much of a team's form.

| Config | MAE ↓ | RMSE ↓ | Correlation ↑ |
|---|---|---|---|
| no form (`1.0 / 0 / 0`) | **1.804** | **2.609** | 0.399 |
| **shipped** (`decay 0.9 / att 0.2 / cs 0.4`) | 1.810 | 2.613 | **0.402** |

Recency alone is essentially neutral; team-form weighting buys a small
**ranking-correlation** gain (0.399 → 0.402) at a tiny cost in absolute error.
For a tool whose job is to *rank* transfer and captain options, correlation is
the more decision-relevant metric, so the gentle defaults are shipped — but they
are deliberately mild and one env var away from off. Dialling them harder
(e.g. `att 0.35 / cs 0.8`) raised correlation no further and hurt MAE more, so
they're kept restrained.

Reproduce it:

```bash
python scripts/backfill_history.py --seasons 2022-23,2023-24 --out data/backfill
python scripts/backtest.py --history data/backfill --out data/backfill/backtest.json
```

The committed `data/backfill/backtest.json` is what the dashboard's "Model
validated" banner reads. The raw per-gameweek snapshots are large and
regenerable, so they're git-ignored; only the small report is committed. The
sample dataset also ships **synthetic** history so the pipeline runs with no
network at all — those numbers only prove the machinery, not accuracy.

## Limitations & next steps

- No explicit penalty/set-piece taker modelling yet (partly captured via xG).
- Bonus (BPS) is a simple rate, not a fitted BPS model.
- Double/blank gameweeks are handled per-fixture but not yet surfaced as a
  planner.
- The clean-sheet fit needs a few hundred GK/DEF match samples before it
  overrides the defaults.

The interface (`project_points`) is stable, so any of these can be improved
without touching the frontend or the data contract. See
[`FEATURES.md`](FEATURES.md#roadmap) for where this sits on the roadmap.
