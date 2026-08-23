# Architecture

## The problem

- **GitHub Pages is static only** — we can't run a server.
- The **official FPL API** (`https://fantasy.premierleague.com/api/…`) does
  **not** send CORS headers, so browser `fetch()` from `*.github.io` is blocked.

## The solution: Actions as the backend

```
                    (scheduled + manual)
  ┌─────────────────────────────────────────┐
  │  GitHub Action: pages.yml (build job)    │
  │  runs fetch_fpl_data.py + fetch_entry.py │
  │                                          │
  │  FPL API  ──►  transform  ──►  data/*.json│
  │  (server-to-server, no CORS)             │
  │                                          │
  │  commits changed JSON back to the repo   │
  └───────────────────┬──────────────────────┘
                      │  push
                      ▼
  ┌──────────────────────────────────────────┐
  │  pages.yml (deploy job) → GitHub Pages     │
  └───────────────────┬──────────────────────┘
                      │
                      ▼
  ┌──────────────────────────────────────────┐
  │  Static site (index.html + assets/js)     │
  │  fetch('data/*.json')  ← same origin ✔    │
  │  all analysis runs client-side            │
  └──────────────────────────────────────────┘
```

The Action calls the FPL API from GitHub's runners (server-to-server, so CORS
is irrelevant), reshapes it into small JSON files, and commits them to `data/`.
The static site reads those files **same-origin** and computes everything
(projections, value, captaincy, transfers) in the browser.

## Repo layout

```
football-manager/
├── index.html              # SPA entry point (loads assets/js/app.js)
├── assets/
│   ├── css/styles.css
│   └── js/
│       ├── app.js          # bootstrap + hash router + view switching
│       ├── data.js         # loads data/*.json, normalises, shared helpers
│       ├── analysis.js     # projections, value, captaincy, transfers, FDR
│       └── views.js        # renders each page (dashboard, players, …)
├── data/                   # committed JSON, refreshed by the Action
│   ├── meta.json           # season, current GW, deadline, source, timestamp
│   ├── teams.json          # clubs + strength ratings
│   ├── players.json        # slim per-player rows (see schema below)
│   ├── fixtures.json       # fixtures with per-side FDR
│   ├── projections.json    # expected-points model output (per player)
│   ├── backtest.json       # model accuracy vs baselines
│   ├── entry.json          # the manager's squad (My Team)
│   └── history/gwNN.json   # per-gameweek snapshots (training/backtest set)
├── config.json             # fpl_team_id + optional entry_proxy
├── scripts/
│   ├── fetch_fpl_data.py   # FPL API → data/*.json + projections (in the Action)
│   ├── fetch_entry.py      # a manager's squad → data/entry.json (in the Action)
│   ├── build_history.py    # snapshot finished GWs → data/history/
│   ├── model.py            # project_points(): the expected-points model
│   ├── projections.py      # history + model → projections.json
│   ├── backtest.py         # replay past GWs, report accuracy
│   └── make_sample_data.py # schema-matching sample dataset (+ synthetic history)
├── docs/                   # RULES.md, FEATURES.md, ARCHITECTURE.md, …
└── .github/workflows/
    ├── pages.yml           # "Update data & deploy to Pages": refresh data
    │                       #   + entry + projections + backtest, then deploy
    └── backfill.yml        # "Backfill history & backtest" (manual)
```

No build step, no framework, no npm install — plain ES-module JavaScript so the
repo *is* the deployable site. This keeps Pages deployment trivial and the
barrier to contributing low. It can be migrated to a framework later without
changing the data contract.

## Data contract

The frontend only ever depends on the shape of `data/*.json` — **not** on the
raw FPL API. Both `fetch_fpl_data.py` (live) and `make_sample_data.py` (sample)
emit exactly this shape, so the UI is identical whether data is live or sample.

### `meta.json`
```json
{
  "generated_utc": "2026-08-22T06:00:00Z",
  "source": "fpl-api",           // or "sample"
  "season": "2025/26",
  "current_gw": 2,
  "next_gw": 3,
  "next_deadline_utc": "2026-08-28T18:30:00Z",
  "scoring": { "...": "live scoring values pulled from the API" }
}
```

### `teams.json` — one row per club
```json
{ "id": 1, "name": "Arsenal", "short": "ARS",
  "strength": 4,
  "att_home": 1300, "att_away": 1310,
  "def_home": 1290, "def_away": 1300 }
```

### `players.json` — one slim row per player
```json
{ "id": 351, "name": "Mohamed Salah", "web": "Salah",
  "team": 12, "team_short": "LIV", "pos": "MID",
  "price": 14.5, "status": "a", "news": "",
  "form": 7.2, "pts": 18, "ppg": 9.0, "sel": 45.3,
  "minutes": 180, "goals": 2, "assists": 1,
  "cs": 1, "xg": 1.4, "xa": 0.8, "xgi": 2.2,
  "defcon": 1, "defcon_per90": 0.5, "ict": 22.5,
  "bonus": 4, "ep_next": 6.5,
  "cost_change_event": 1, "transfers_in_event": 220000,
  "transfers_out_event": 40000 }
```
`pos` is one of `GKP | DEF | MID | FWD`. `status`: `a` available, `d` doubtful,
`i` injured, `s` suspended, `u` unavailable. `price` is in £m.

### `fixtures.json` — one row per fixture
```json
{ "gw": 3, "team_h": 12, "team_a": 1,
  "kickoff": "2026-09-04T19:00:00Z",
  "fdr_h": 3, "fdr_a": 4, "finished": false }
```

## Client-side analysis

All in [`assets/js/analysis.js`](../assets/js/analysis.js), documented inline:

- **FDR ticker** — joins `fixtures` to `teams` for each club's next *N* GWs.
- **Value** — points-per-million and form-per-million.
- **Projection / captaincy** — the transparent heuristic described in
  [`FEATURES.md`](FEATURES.md#projected-points--our-transparent-heuristic).
- **Transfer targets** — best projected/value option per position, availability
  filtered, with warnings for flagged players and price falls.
- **Differentials** — high projection at sub-10% ownership.

## Personalised squad (My Team)

The FPL API blocks browser calls (no CORS), so the manager's own team is loaded
the same way as everything else: the Action runs `fetch_entry.py` server-side and
commits `data/entry.json`, which the site reads same-origin. The team id comes
from the `FPL_TEAM_ID` repository variable, else `config.json`.

`data/entry.json` (one manager's squad):
```json
{ "id": 9155976, "manager": "…", "team_name": "…", "event": 8,
  "overall_points": 512, "bank": 1.5, "squad_value": 100.8,
  "picks": [{ "element": 351, "slot": 1, "is_captain": false,
              "is_vice": false, "multiplier": 1 }] }
```
`slot` 1–11 are the starting XI (1 = GK), 12–15 the bench in priority order.

**Availability.** The public API only exposes a gameweek's picks **after that
gameweek's deadline**, so right at the start of a season (before GW1's deadline)
no squad is available yet. `fetch_entry.py` walks back from the current gameweek
to the most recent one whose picks are public, and reports clearly when none are
yet. Until a real squad loads, the app shows a setup prompt rather than the
built-in sample squad (which only makes sense on a fully-sample dataset).

**Optional live input.** `config.json` may set `entry_proxy` to a *transparent
proxy* that forwards to the FPL API (a Cloudflare Worker, or a Supabase Edge
Function). When set, the My Team view's team-id box fetches any manager live in
the browser through that proxy — the clean multi-user path. Without a proxy the
box explains that a different team must be baked in via the Action. The proxy
only needs to forward `/entry/{id}/…` and add permissive CORS headers; the client
reshapes the response with the same logic as `fetch_entry.py`.

## Refresh cadence

`update-data.yml` runs on a cron (a few times a day) and on manual dispatch.
Player prices change ~once daily and form/injuries update around fixtures, so a
few refreshes a day is plenty. Every run commits only the changed JSON.
