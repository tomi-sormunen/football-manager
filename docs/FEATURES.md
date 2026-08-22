# Feature Research & Roadmap

This document captures the research behind what an FPL planning tool should do,
maps each idea to how (and whether) we implement it under the "GitHub Pages
first" constraint, and lays out a phased roadmap.

## Where the ideas come from

Synthesised from the established FPL tool landscape and community discussion
(r/FantasyPL and the mainstream planners/assistants):

- **myFPL** — data-driven transfer suggestions, squad optimiser, captain picks,
  transfer grading, chip-aware planning, live points.
- **Fantasy Football Scout / Premier Fantasy Tools** — season-long planner
  across all 38 GWs (transfers, rotation, chip strategy), fixture ticker.
- **OneFPL** — live dashboard, mini-league table, transfer planner, player
  comparison lab, projections + differentials, price-change market, fixtures.
- **FPL Tactics / Fine Line** — plan transfers weeks ahead, compare players,
  find differentials, expected-points-based captain picks, no signup.

**Common denominator across all of them** (i.e. table-stakes features):

1. Fixture Difficulty Ratings (FDR) ticker — plan rotation & chips.
2. Player explorer with value metrics (points-per-million, form).
3. Captain / vice-captain picker driven by projected points, not gut.
4. Transfer planner with price-change tracking and hit (-4) awareness.
5. Player comparison.
6. Differential finder (low ownership, high projected return).
7. Chip strategy planning (double gameweeks, blanks, bench boost timing).
8. Your-team import (via FPL team ID) for personalised advice.

**2025/26-specific:** the new **Defensive Contributions (DEFCON)** scoring
rewards CBs and defensive midfielders. Good tooling now surfaces a **DEFCON
hit-rate** (share of matches a player hit the 10/12 threshold) so it can be
weighed alongside attacking returns. We treat this as a first-class metric.

### Sources
- <https://myfpl.co/>
- <https://onefpl.com/tools>
- <https://www.premierfantasytools.com/fpl-planner-intro/>
- <https://fpltactics.com/>
- <https://www.getfineline.app/fpl-tools>
- FPL API guide — <https://medium.com/@frenzelts/fantasy-premier-league-api-endpoints-a-detailed-guide-acbd5598eb19>
- DEFCON explainer — <https://www.premierleague.com/en/news/4361991/whats-new-in-202526-fantasy-defensive-contributions>

## The core design constraint

GitHub Pages serves **static files only** — there is no server we control. The
official FPL API also does **not** send CORS headers, so the browser cannot call
it directly from `*.github.io`.

**Our answer:** a scheduled **GitHub Action** acts as the backend. It calls the
FPL API on GitHub's runners (no CORS in server-to-server calls), transforms the
response into small JSON files, and commits them to `data/`. The static site
then reads those files **same-origin**. All analysis (projections, value,
captaincy, transfer targets) runs **client-side** in the browser from that data.

See [`ARCHITECTURE.md`](ARCHITECTURE.md) for the full data flow.

## Projected points — our transparent heuristic

We deliberately start with an **explainable** projection rather than a black
box. Per player, per upcoming fixture:

```
proj = minutes_factor × ( base_form
                          + attack_expectation(xGI, fixture ease, venue)
                          + defcon_expectation(hit_rate, position)
                          + clean_sheet_expectation(team defence, fixture) )
```

- **minutes_factor** — down-weights rotation risks and flagged/injured players
  (uses `status` + recent minutes).
- **base_form** — the player's current form (avg points over recent GWs).
- **attack_expectation** — expected goal involvement scaled by how easy the
  opponent is (from FDR / team strength) and home/away.
- **defcon_expectation** — DEFCON hit-rate × 2 pts, by position threshold.
- **clean_sheet_expectation** — for GK/DEF (and a little for MID), from the
  opponent's attacking strength.

Captaincy = projected points for the single next fixture, ranked. Every number
in the UI can be traced back to these inputs — no unexplained magic. The model
is intended to be **swapped/improved** over time (see roadmap Phase 3).

## Roadmap

### Phase 1 — Foundation (this initial version) ✅
- Repo structure, docs (rules + architecture), data pipeline script.
- GitHub Action to refresh data on a schedule; Pages deploy workflow.
- Static SPA that loads committed data and offers:
  - **Dashboard** — current GW, deadline countdown, top captain picks, top
    value picks, price-change watch.
  - **Players** — sortable/filterable explorer with value & DEFCON metrics.
  - **Fixtures (FDR)** — colour-coded ticker for the next N gameweeks.
  - **Captains** — ranked picks with the reasoning breakdown.
  - **Transfers** — best-value / in-form targets by position, flag warnings.
  - **Differentials** — high projection, sub-10% ownership.
- Sample dataset committed so the site works before the first Action run.

### Phase 2 — Personalisation
- Import your squad by **FPL team ID** (fetched by the Action to avoid CORS, or
  a manual paste), then tailor transfer/captain advice to your 15 and budget.
- Free-transfer & bank tracking; hit (-4) break-even calculator.
- Mini-league table view.

### Phase 3 — Smarter projections  🚧 in progress
- ✅ **Opponent-adjusted expected-points model** (`xpts-v1`) with a minutes
  model, regressed per-90 rates, a fitted clean-sheet logistic and a DEFCON
  hit-rate — replacing the heuristic where available, with the heuristic kept as
  a fallback. See [`MODEL.md`](MODEL.md).
- ✅ **Per-gameweek history snapshots** (`data/history/`) via `build_history.py`,
  accumulating the training/backtest set over the season.
- ✅ **Backtest harness** (`backtest.py`) comparing the model against naive
  baselines (MAE / RMSE / correlation), reported to `data/backtest.json`.
- ⬜ **Backfill history** from a public multi-season dataset so real backtest
  numbers exist immediately (see [`INFRASTRUCTURE.md`](INFRASTRUCTURE.md)).
- ⬜ Upgrade `xpts-v1` toward a gradient-boosted model once history is deep.
- ⬜ Multi-week transfer **planner** (plan several GWs ahead, compare paths).
- ⬜ Chip-timing optimiser using double/blank gameweek detection.

### Phase 4 — Optimisation & polish
- Squad optimiser (best XI / best 15 under £100m and the 3-per-club limit) via
  a linear/greedy solver in the browser.
- Automated captaincy & transfer "what-if" simulation.
- Notifications ahead of deadlines.

## Explicitly out of scope (for now)
- Making transfers *for* you (the official API has no public write access;
  changes must be made on the FPL site).
- Anything requiring login/secrets in the static site (kept server-side in the
  Action if ever needed).
