# ⚽ FPL Manager

A data-backed planning aid for your **Fantasy Premier League** team — fixture
difficulty, captain picks, transfer targets, value analysis and differentials —
running as a static web app you can host **for free on GitHub Pages**.

> Not affiliated with the Premier League or FPL. Uses the public FPL API.

## What it does

| View | What you get |
|---|---|
| **Dashboard** | Current gameweek, deadline countdown, top captain & value picks, price movers, a sell/watch list. |
| **Players** | Sortable, filterable explorer — price, form, points-per-£m, xGI, **DEFCON per 90** (the new 2025/26 defensive scoring), ownership, and a projection over the next 5 GWs. |
| **Fixtures** | Colour-coded Fixture Difficulty Ratings (FDR) ticker for the next 6 gameweeks, sorted by easiest run. |
| **Captains** | Ranked captaincy picks with a transparent breakdown (appearance / attack / clean sheet / DEFCON). |
| **Transfers** | Best projected targets by position and budget, plus players to consider selling — with a reminder of the −4 hit maths. |
| **Differentials** | Low-ownership (<10%) players with a strong projection, for climbing mini-leagues. |

All recommendations are computed **in your browser** from data refreshed by a
GitHub Action. The projection is a deliberately **explainable heuristic** — see
[`docs/FEATURES.md`](docs/FEATURES.md) — not a black box, so you can always see
*why* a player is suggested.

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

## Repository layout
```
index.html            SPA entry point
assets/css, assets/js  styles + app (data loader, analysis engine, views, router)
data/                 committed JSON, refreshed by the Action
scripts/              fetch_fpl_data.py (live) · make_sample_data.py (sample)
docs/                 RULES.md · FEATURES.md · ARCHITECTURE.md
.github/workflows/    pages.yml (refresh data + deploy)
```

## Docs
- [`docs/RULES.md`](docs/RULES.md) — the FPL rules, structured (squad, transfers, chips, scoring incl. DEFCON).
- [`docs/FEATURES.md`](docs/FEATURES.md) — feature research, the projection model, and the roadmap.
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — data flow, the data contract, and analysis internals.

## Roadmap (short version)
- **Now:** the views above, on live data.
- **Next:** import your own squad by FPL team ID for personalised advice; free-transfer/hit break-even calculator; mini-league view.
- **Later:** a fitted expected-points model backtested on history, a multi-week transfer & chip planner, and a squad optimiser.

See [`docs/FEATURES.md`](docs/FEATURES.md#roadmap) for the full plan.
