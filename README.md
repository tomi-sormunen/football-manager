# ⚽ FPL Manager

A data-backed planning aid for your **Fantasy Premier League** team — fixture
difficulty, captain picks, transfer targets, value analysis and differentials —
running as a static web app you can host **for free on GitHub Pages**.

> Not affiliated with the Premier League or FPL. Uses the public FPL API.

## What it does

| View | What you get |
|---|---|
| **Dashboard** | Current gameweek, deadline countdown, top captain & value picks, price movers, a sell/watch list. |
| **My Team** | Import your squad by FPL team ID: your XI/bench on a pitch with captain/vice, bank & value, projected GW total, injury alerts, and suggested transfers (5-GW gain, budget- and club-limit-aware, with −4 hit break-even). |
| **Players** | Sortable, filterable explorer — price, form, points-per-£m, xGI, **DEFCON per 90** (the new 2025/26 defensive scoring), ownership, and a projection over the next 5 GWs. |
| **Fixtures** | Colour-coded Fixture Difficulty Ratings (FDR) ticker for the next 6 gameweeks, sorted by easiest run. |
| **Captains** | Ranked captaincy picks with a transparent breakdown (appearance / attack / clean sheet / DEFCON). |
| **Transfers** | Best projected targets by position and budget, plus players to consider selling — with a reminder of the −4 hit maths. |
| **Differentials** | Low-ownership (<10%) players with a strong projection, for climbing mini-leagues. |

Recommendations are driven by an **opponent-adjusted expected-points model**
(`xpts-v1`) computed in the GitHub Action, with a transparent client-side
heuristic as a fallback. The model is deliberately **explainable** (every
projection comes with a breakdown) and is **backtested** against past gameweeks
so we can tell it beats naive guessing — see [`docs/MODEL.md`](docs/MODEL.md).

## How it works (the clever bit)

GitHub Pages only serves static files, and the FPL API doesn't allow browsers to
call it directly (no CORS). So:

1. A scheduled **GitHub Action** calls the FPL API from GitHub's servers,
   transforms it into small JSON files, and commits them to [`data/`](data/).
2. The static site reads those files **same-origin** and does all the analysis
   client-side.

No server, no database, no build step. Full detail in
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Quick start

### Run it locally
```bash
python scripts/make_sample_data.py     # generate sample data into data/
python -m http.server 8000             # then open http://localhost:8000
```
The site ships with a built-in **sample dataset** so it works immediately. The
Action replaces it with live data.

### Deploy to GitHub Pages
1. Push this repo to GitHub (merge to your default branch).
2. **Settings → Pages → Build and deployment → Source: “GitHub Actions”.**
3. The [`pages.yml`](.github/workflows/pages.yml) workflow deploys the site and,
   on a schedule, refreshes the data. Trigger the first run from the **Actions**
   tab (“Update data & deploy to Pages” → *Run workflow*).

No secrets or tokens required — it uses the built-in `GITHUB_TOKEN`.

### Load your own team (My Team)
Set your **FPL team ID** (the number in your Points-page URL,
`.../entry/<ID>/event/...`) in [`config.json`](config.json), or as an
`FPL_TEAM_ID` repository variable. The Action fetches your squad server-side and
commits `data/entry.json` (the FPL API can't be called from the browser — CORS).
For a live team-id box that loads *any* manager on the fly, point
`config.json`'s `entry_proxy` at a transparent proxy that forwards to the FPL API
(a Cloudflare Worker or a Supabase Edge Function) — see
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md#personalised-squad-my-team).

## Repository layout
```
index.html            SPA entry point
assets/css, assets/js  styles + app (data loader, analysis engine, views, router)
data/                 committed JSON, refreshed by the Action
  history/            per-gameweek snapshots (training / backtest set)
  projections.json    model output · backtest.json (accuracy report)
config.json           your FPL team ID + optional live-input proxy URL
scripts/              fetch_fpl_data.py · fetch_entry.py · build_history.py
                      backfill_history.py · model.py · projections.py
                      backtest.py · make_sample_data.py
docs/                 RULES · FEATURES · ARCHITECTURE · MODEL · INFRASTRUCTURE
.github/workflows/    pages.yml (history → data → projections → backtest → deploy)
                      backfill.yml (manual: backfill past seasons → backtest)
```

## Docs
- [`docs/RULES.md`](docs/RULES.md) — the FPL rules, structured (squad, transfers, chips, scoring incl. DEFCON).
- [`docs/MODEL.md`](docs/MODEL.md) — the expected-points model and how it's backtested.
- [`docs/FEATURES.md`](docs/FEATURES.md) — feature research and the roadmap.
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — data flow, the data contract, and internals.
- [`docs/INFRASTRUCTURE.md`](docs/INFRASTRUCTURE.md) — what a backtested model needs, and the (free) options.

## Roadmap (short version)
- **Done:** the views above; the opponent-adjusted expected-points model (`xpts-v1`) with per-GW history snapshots, a backtest harness, and a **backfill from a public multi-season dataset** — `xpts-v1` beats naive baselines on real 2022-24 data ([`docs/MODEL.md`](docs/MODEL.md)).
- **Next:** the **My Team** view — import your squad by FPL team ID for personalised captain & transfer advice (done); free-transfer count tracking and a mini-league view still to come.
- **Later:** a gradient-boosted model, a multi-week transfer & chip planner, and a squad optimiser.

### Get real backtest numbers now
```bash
python scripts/backfill_history.py --seasons 2022-23,2023-24 --out data/backfill
python scripts/backtest.py --history data/backfill --out data/backfill/backtest.json
```
Or run the **“Backfill history & backtest”** GitHub Action. The dashboard shows a
“Model validated” banner from the result.

See [`docs/FEATURES.md`](docs/FEATURES.md#roadmap) for the full plan.
