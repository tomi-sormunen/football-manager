# Infrastructure for a genuinely backtested model

*"If we wanted to build a genuinely backtested model with historical gameweek
data, what infrastructure would that require? Are there costs, or free
options?"*

Short answer: **you can build and run a genuinely backtested FPL model for £0**,
staying entirely on free tiers, and only start paying if you later want a
live per-user backend or very large ML workloads. Here's the full picture.

## What "genuinely backtested" actually needs

1. **Historical data** — several seasons of per-gameweek, per-player data
   (points, minutes, xG/xA, opponent, venue, price, ownership).
2. **A place to store it** — that grows sensibly over time.
3. **Compute** — to build features, fit the model, and replay past gameweeks.
4. **A scheduler** — to refresh data and re-run automatically.
5. **Evaluation tracking** — to compare model versions honestly over time.
6. **Hosting** — to serve the results (already solved: GitHub Pages).

Each has a free option. The table at the bottom summarises.

## 1. Historical data — where it comes from (all free)

The single biggest question. Our current pipeline (`build_history.py`) only
accumulates history **going forward** from when you turn it on. To backtest
*now* you need past seasons, and there are free sources:

- **Community datasets** — the best-known is the open
  [`vaastav/Fantasy-Premier-League`](https://github.com/vaastav/Fantasy-Premier-League)
  GitHub repo: cleaned per-gameweek, per-player CSVs going back to 2016/17.
  Free, no key. A one-off `backfill_history.py` can convert these into our
  `data/history/` schema.
- **The official FPL API** — `element-summary/{id}` gives per-match history for
  the *current* season; `event/{gw}/live` gives a whole GW in one call (what we
  already use). Free, no key, just be polite with request rate.
- **xG/underlying stats** — Understat and FBref (StatsBomb data) have free xG
  history; scraping has ToS/rate considerations, so prefer the community dataset
  which already folds much of this in.

None of these cost money. The work is *ETL* (transform them into one schema),
not procurement.

## 2. Storage — options as the data grows

A full season of per-player, per-GW rows is small — a few MB. Even 10 seasons is
tens of MB. So:

- **Committed files in the repo (current approach)** — JSON/CSV/**Parquet** in
  `data/`. Free, versioned, zero infra. Parquet keeps it compact. Good to
  ~hundreds of MB. This is all this project needs for a long time.
- **SQLite committed in the repo** — a single `.sqlite` file queried in CI or
  in the browser (via `sql.js`/DuckDB-Wasm). Free, still no server. Nice once
  you want ad-hoc queries.
- **A free-tier hosted database** — only if you outgrow files or want a live
  API to read it:
  [Supabase](https://supabase.com) (free Postgres, ~500MB),
  [Neon](https://neon.tech) (free Postgres, autosuspend),
  [Turso](https://turso.tech) (free libSQL/SQLite, generous row limits),
  [Cloudflare D1](https://developers.cloudflare.com/d1/) (free SQLite tier).
  All have free tiers that comfortably fit this data.

**Recommendation:** stay on committed Parquet/SQLite until you specifically need
a live queryable backend. Watch repo size only if you commit raw data every run
(store *derived* snapshots, and consider Git LFS or a separate data branch if it
ever balloons).

## 3. Compute — training and backtesting

- **GitHub Actions runners** — 2 vCPU / 7 GB, up to 6h per job. Ample for
  feature building, our logistic fit, the backtest, and even gradient-boosted
  trees (XGBoost/LightGBM) over 10 seasons of FPL-sized data (~hundreds of
  thousands of rows). **Free**: unlimited minutes for public repos; 2,000
  min/month for private (this pipeline uses a minute or two per run).
- **Google Colab (free tier)** — for interactive model development / heavier
  experiments, including a free GPU if you ever go neural. Free.
- **Your own laptop** — the model and backtest here run in well under a second
  on sample data; real data is still small.

You do **not** need a paid GPU or a cluster for an FPL model. The data is small;
the intelligence is in the features, not the FLOPs.

## 4. Scheduling — already free

GitHub Actions `cron` (what `pages.yml` uses) triggers refresh + retrain +
backtest on a schedule. Free. No separate scheduler, no server to keep alive.

## 5. Evaluation tracking

- **Commit `data/backtest.json` each run** (we do this) — a versioned, diffable
  record of accuracy over time. Free, zero infra.
- **Weights & Biases / MLflow** — a free tier of W&B, or self-hosted MLflow, if
  you want dashboards comparing model versions. Optional; only worth it once you
  have several competing models.

## 6. When you'd actually spend money

Everything above is free. You'd reach for paid infrastructure only for:

- **A live per-user backend** — e.g. fetching a manager's squad by team ID on
  demand (the FPL API blocks browsers via CORS). Solve it free first with
  serverless: [Cloudflare Workers](https://workers.cloudflare.com) (100k
  req/day free), Vercel / Netlify / Deno Deploy free functions, or an AWS Lambda
  free tier. A tiny proxy/function is free at this scale; you only pay at high
  traffic.
- **Very large historical/ML workloads** — many seasons across many leagues,
  heavy hyperparameter sweeps. Then a small cloud VM or managed DB (a few £/month)
  or paid CI minutes might help. Not needed for a single-league planning tool.
- **Premium data feeds** — live odds, richer event data (Opta/StatsBomb
  commercial). Nice-to-have, not required; the free xG sources are good.

## Recommended path for this project

1. **Now (free):** backfill `data/history/` from the community dataset, keep
   accumulating live snapshots via Actions, store as Parquet/SQLite in-repo,
   train + backtest in CI, commit `backtest.json`, serve on Pages. This is a
   genuinely backtested model at zero cost.
2. **If/when personalised squad import is wanted:** add a free serverless proxy
   (Cloudflare Workers) for the per-user FPL calls; the model stays in CI.
3. **Only if you outgrow files:** move history to a free-tier hosted DB.

## Cost summary

| Need | Free option | When you'd pay |
|---|---|---|
| Historical data | Community dataset + FPL API | Never (commercial feeds optional) |
| Storage | Parquet/SQLite in repo; free-tier Postgres/Turso/D1 | Huge multi-league data |
| Compute (train/backtest) | GitHub Actions; Colab | Large ML sweeps / GPU |
| Scheduling | GitHub Actions cron | — |
| Eval tracking | Commit `backtest.json`; W&B free tier | Team dashboards |
| App hosting | GitHub Pages | — |
| Live per-user API | Cloudflare Workers / serverless free tiers | High traffic |

**Bottom line:** the free stack (GitHub Actions + committed data + a community
backfill + serverless when needed) is enough to build, backtest, retrain and
serve a real FPL model indefinitely for a personal/mini-league tool. Paid
infrastructure is a scaling choice, not a requirement.
