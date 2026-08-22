// Loads the committed JSON dataset (refreshed by the GitHub Action) and
// normalises it into a bundle the rest of the app uses. All paths are relative
// so the site works from a GitHub Pages project subpath (e.g. /football-manager/).

export const POS_ORDER = ['GKP', 'DEF', 'MID', 'FWD'];

export const POS_LABEL = {
  GKP: 'Goalkeepers', DEF: 'Defenders', MID: 'Midfielders', FWD: 'Forwards',
};

// FPL availability status → human label + severity.
export const STATUS = {
  a: { label: 'Available', flag: false },
  d: { label: 'Doubtful', flag: true },
  i: { label: 'Injured', flag: true },
  s: { label: 'Suspended', flag: true },
  u: { label: 'Unavailable', flag: true },
  n: { label: 'Not in squad', flag: true },
};

async function getJSON(path) {
  const res = await fetch(path, { cache: 'no-cache' });
  if (!res.ok) throw new Error(`Failed to load ${path}: HTTP ${res.status}`);
  return res.json();
}

// Optional file: absent on very first deploy, so failure is non-fatal.
async function getJSONOptional(path) {
  try { return await getJSON(path); } catch { return null; }
}

// Shape an FPL entry + picks response into our entry.json schema (mirrors
// scripts/fetch_entry.py::build_entry so the proxy path and the Action agree).
export function buildEntry(id, entry, picksResp, event) {
  const eh = picksResp.entry_history || {};
  return {
    id: Number(id),
    manager: `${entry.player_first_name || ''} ${entry.player_last_name || ''}`.trim(),
    team_name: entry.name || '',
    event,
    overall_points: entry.summary_overall_points,
    overall_rank: entry.summary_overall_rank,
    gw_points: eh.points,
    bank: (eh.bank || 0) / 10,
    squad_value: (eh.value || 0) / 10,
    event_transfers: eh.event_transfers,
    event_transfers_cost: eh.event_transfers_cost,
    picks: (picksResp.picks || []).map((p) => ({
      element: p.element, slot: p.position,
      is_captain: !!p.is_captain, is_vice: !!p.is_vice_captain,
      multiplier: p.multiplier ?? 1,
    })),
    source: 'proxy',
  };
}

// Fetch a manager's squad live through a transparent proxy that forwards to the
// FPL API (e.g. a Cloudflare Worker or Supabase Edge Function). `base` is the
// proxy origin; it must expose the same /entry/{id}/ paths as the FPL API.
export async function fetchEntryViaProxy(base, id, fallbackEvent = 1) {
  const b = base.replace(/\/$/, '');
  const entry = await getJSON(`${b}/entry/${id}/`);
  const ev = entry.current_event || fallbackEvent;
  const picks = await getJSON(`${b}/entry/${id}/event/${ev}/picks/`);
  return buildEntry(id, entry, picks, ev);
}

// Re-apply an entry to the loaded bundle (updates owned/pick flags in place).
export function applyEntry(bundle, entry) {
  const pickBy = new Map(entry.picks.map((pk) => [pk.element, pk]));
  for (const p of bundle.players) {
    const pk = pickBy.get(p.id) || null;
    p.owned = !!pk;
    p.pick = pk;
  }
  bundle.entry = entry;
}

export async function loadData() {
  const [meta, teams, players, fixtures, projections, backtest, entry, config] =
    await Promise.all([
      getJSON('data/meta.json'),
      getJSON('data/teams.json'),
      getJSON('data/players.json'),
      getJSON('data/fixtures.json'),
      getJSONOptional('data/projections.json'),
      getJSONOptional('data/backfill/backtest.json'),   // model validation report
      getJSONOptional('data/entry.json'),               // the manager's squad
      getJSONOptional('config.json'),
    ]);

  const teamById = new Map(teams.map((t) => [t.id, t]));

  const playerById = new Map(players.map((p) => [p.id, p]));

  // Squad membership from the manager's entry, if loaded.
  const pickBy = entry ? new Map(entry.picks.map((pk) => [pk.element, pk])) : null;

  // Attach convenience fields used across views.
  const projById = projections?.players || null;
  for (const p of players) {
    p.team_obj = teamById.get(p.team);
    p.value_pts = p.price ? +(p.pts / p.price).toFixed(2) : 0;      // pts / £m
    p.value_form = p.price ? +(p.form / p.price).toFixed(2) : 0;    // form / £m
    p.flagged = (STATUS[p.status] || STATUS.u).flag;
    // Model projection for this player, if projections.json was present.
    p.model = projById ? (projById[p.id] || projById[String(p.id)] || null) : null;
    // Squad info.
    const pk = pickBy ? pickBy.get(p.id) : null;
    p.owned = !!pk;
    p.pick = pk || null;
  }

  return { meta, teams, teamById, players, playerById, fixtures, projections,
           backtest, entry, config };
}
