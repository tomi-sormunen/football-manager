"""Shared data contract for the football-manager data pipeline.

Both the live fetcher (``fetch_fpl_data.py``) and the sample generator
(``make_sample_data.py``) build the same slim dataset and write it through
``write_dataset`` here, which validates the required keys. That way the JSON the
static site consumes is guaranteed to have the same shape whether it came from
the live FPL API or from the committed sample data.

The full schema is documented in ``docs/ARCHITECTURE.md``.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

# Required keys per record. Extra keys are allowed (forward-compatible); missing
# keys are a hard error so we notice contract breaks at generation time.
TEAM_KEYS = {
    "id", "name", "short", "strength",
    "att_home", "att_away", "def_home", "def_away",
}
PLAYER_KEYS = {
    "id", "name", "web", "team", "team_short", "pos", "price", "status", "news",
    "form", "pts", "ppg", "sel", "minutes", "goals", "assists", "cs",
    "xg", "xa", "xgi", "defcon", "defcon_per90", "ict", "bonus", "ep_next",
    "cost_change_event", "transfers_in_event", "transfers_out_event",
}
FIXTURE_KEYS = {
    "gw", "team_h", "team_a", "kickoff", "fdr_h", "fdr_a", "finished",
}

POSITIONS = {"GKP", "DEF", "MID", "FWD"}


def _require(records, required, label):
    for i, rec in enumerate(records):
        missing = required - rec.keys()
        if missing:
            raise ValueError(
                f"{label}[{i}] (id={rec.get('id', '?')}) missing keys: "
                f"{sorted(missing)}"
            )
    return records


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_dataset(outdir: str, *, meta: dict, teams: list, players: list,
                  fixtures: list) -> None:
    """Validate and write the four JSON files the frontend loads."""
    _require(teams, TEAM_KEYS, "team")
    _require(players, PLAYER_KEYS, "player")
    _require(fixtures, FIXTURE_KEYS, "fixture")
    for p in players:
        if p["pos"] not in POSITIONS:
            raise ValueError(f"player id={p['id']} bad pos {p['pos']!r}")

    meta = {"generated_utc": utc_now_iso(), **meta}

    os.makedirs(outdir, exist_ok=True)
    files = {
        "meta.json": meta,
        "teams.json": teams,
        "players.json": players,
        "fixtures.json": fixtures,
    }
    for name, payload in files.items():
        path = os.path.join(outdir, name)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, separators=(",", ":"))
            fh.write("\n")
    print(
        f"Wrote {len(teams)} teams, {len(players)} players, "
        f"{len(fixtures)} fixtures to {outdir}/ (source={meta.get('source')})"
    )
