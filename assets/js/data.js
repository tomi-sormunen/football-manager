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

export async function loadData() {
  const [meta, teams, players, fixtures] = await Promise.all([
    getJSON('data/meta.json'),
    getJSON('data/teams.json'),
    getJSON('data/players.json'),
    getJSON('data/fixtures.json'),
  ]);

  const teamById = new Map(teams.map((t) => [t.id, t]));

  // Attach convenience fields used across views.
  for (const p of players) {
    p.team_obj = teamById.get(p.team);
    p.value_pts = p.price ? +(p.pts / p.price).toFixed(2) : 0;      // pts / £m
    p.value_form = p.price ? +(p.form / p.price).toFixed(2) : 0;    // form / £m
    p.flagged = (STATUS[p.status] || STATUS.u).flag;
  }

  return { meta, teams, teamById, players, fixtures };
}
