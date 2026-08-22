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
