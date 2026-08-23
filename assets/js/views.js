// Rendering for each view. Pure-ish: given the data bundle, return a DOM node.
// No framework — small template helpers + a sortable table builder.

import { POS_ORDER, POS_LABEL, STATUS, fetchEntryViaProxy, applyEntry } from './data.js';
import * as A from './analysis.js';

// ---- tiny helpers -----------------------------------------------------------

const h = (tag, attrs = {}, children = []) => {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === 'class') e.className = v;
    else if (k === 'html') e.innerHTML = v;
    else if (k.startsWith('on') && typeof v === 'function') e.addEventListener(k.slice(2), v);
    else if (v !== null && v !== undefined) e.setAttribute(k, v);
  }
  for (const c of [].concat(children)) {
    if (c == null) continue;
    e.appendChild(typeof c === 'string' ? document.createTextNode(c) : c);
  }
  return e;
};

const money = (p) => `£${p.toFixed(1)}m`;
const pct = (x) => `${x.toFixed(1)}%`;

const fdrBadge = (fdr, label) =>
  h('span', { class: `fdr fdr-${A.fdrTier(fdr)}`, title: `FDR ${fdr}` }, label ?? String(fdr));

const posBadge = (pos) => h('span', { class: `pos pos-${pos}` }, pos);

function statusDot(p) {
  const s = STATUS[p.status] || STATUS.u;
  if (!s.flag) return h('span', { class: 'dot dot-ok', title: 'Available' });
  return h('span', { class: 'dot dot-flag', title: `${s.label}${p.news ? ': ' + p.news : ''}` });
}

// A compact strip of the next N fixtures for a player's team.
function fixtureStrip(bundle, teamId, n = 5) {
  const fx = A.teamFixtures(bundle, teamId, bundle.meta.next_gw, n);
  return h('span', { class: 'strip' },
    fx.map((f) => fdrBadge(f.fdr, `${f.opp_short}${f.home ? '' : ''}`)));
}

function playerCell(p) {
  return h('span', { class: 'pcell' }, [
    statusDot(p),
    p.owned ? h('span', { class: 'owned', title: 'In your squad' }, '★') : null,
    h('span', { class: 'pname' }, p.web),
    h('span', { class: 'pteam' }, `${p.team_short} ${p.pos}`),
  ]);
}

// Sortable table. cols: [{key,label,get,fmt,align,sortable,default}]
function table(cols, rows, { initialSort } = {}) {
  const state = { key: initialSort?.key ?? null, dir: initialSort?.dir ?? -1 };
  const thead = h('thead');
  const tbody = h('tbody');
  const tbl = h('table', { class: 'grid' }, [thead, tbody]);

  const render = () => {
    let data = rows.slice();
    if (state.key) {
      const col = cols.find((c) => c.key === state.key);
      data.sort((a, b) => {
        const va = col.sortVal ? col.sortVal(a) : col.get(a);
        const vb = col.sortVal ? col.sortVal(b) : col.get(b);
        // state.dir: 1 = ascending, -1 = descending (matches the header label).
        if (va < vb) return -state.dir;
        if (va > vb) return state.dir;
        return 0;
      });
    }
    tbody.replaceChildren(...data.map((row) =>
      h('tr', {}, cols.map((c) => {
        const raw = c.get(row);
        const content = c.fmt ? c.fmt(raw, row) : (raw ?? '');
        return h('td', { class: `al-${c.align || 'left'}` },
          typeof content === 'string' || typeof content === 'number'
            ? String(content) : content);
      }))));
  };

  thead.appendChild(h('tr', {}, cols.map((c) => {
    const th = h('th', { class: `al-${c.align || 'left'}${c.sortable === false ? '' : ' srt'}` },
      c.label);
    if (c.sortable !== false) {
      th.addEventListener('click', () => {
        if (state.key === c.key) state.dir = -state.dir;
        else { state.key = c.key; state.dir = c.desc === false ? 1 : -1; }
        thead.querySelectorAll('th').forEach((x) => x.removeAttribute('data-sort'));
        th.setAttribute('data-sort', state.dir === -1 ? 'desc' : 'asc');
        render();
      });
    }
    return th;
  })));
  render();
  return tbl;
}

function card(title, body, extra) {
  return h('section', { class: 'card' }, [
    h('div', { class: 'card-head' }, [h('h2', {}, title), extra].filter(Boolean)),
    body,
  ]);
}

function note(text) { return h('p', { class: 'muted small' }, text); }

// One-line description of which projection is powering the numbers.
function projectionBlurb(bundle) {
  const m = bundle.projections?.meta;
  return m
    ? `Projections use the ${m.model} expected-points model, fitted on ${m.history_gws} ` +
      'gameweeks of history (opponent-adjusted; see docs/MODEL.md).'
    : 'Projections use a transparent client-side heuristic (see docs/FEATURES.md).';
}

// ---- Dashboard --------------------------------------------------------------

function deadlineCountdown(meta) {
  const el = h('strong', {}, '—');
  const target = meta.next_deadline_utc ? new Date(meta.next_deadline_utc) : null;
  const tick = () => {
    if (!target) { el.textContent = 'TBC'; return; }
    const ms = target - new Date();
    if (ms <= 0) { el.textContent = 'Deadline passed'; return; }
    const d = Math.floor(ms / 86400000);
    const hh = Math.floor((ms % 86400000) / 3600000);
    const mm = Math.floor((ms % 3600000) / 60000);
    el.textContent = `${d}d ${hh}h ${mm}m`;
  };
  tick();
  setInterval(tick, 30000);
  return el;
}

export function dashboard(bundle) {
  const { meta } = bundle;
  const wrap = h('div', { class: 'view' });

  const stat = (label, value) => h('div', { class: 'stat' }, [
    h('span', { class: 'stat-label' }, label), h('div', { class: 'stat-val' }, value)]);

  const model = bundle.projections?.meta;
  wrap.appendChild(h('div', { class: 'stats' }, [
    stat('Gameweek', h('strong', {}, `GW${meta.current_gw}`)),
    stat(`GW${meta.next_gw} deadline`, deadlineCountdown(meta)),
    stat('Data', h('span', { class: `tag tag-${meta.source === 'fpl-api' ? 'live' : 'sample'}` },
      meta.source === 'fpl-api' ? 'Live (FPL API)' : 'Sample data')),
    stat('Projections', model
      ? h('span', { class: 'tag tag-live', title: `${model.history_gws} GWs of history` },
          `Model ${model.model}`)
      : h('span', { class: 'tag tag-sample' }, 'Heuristic')),
  ]));

  if (meta.source !== 'fpl-api') {
    wrap.appendChild(h('div', { class: 'banner' },
      'Showing built-in sample data. Enable the “Update FPL data” GitHub Action ' +
      'to populate live prices, form and fixtures.'));
  }

  // Model validation, if a backtest report is present.
  const bt = bundle.backtest;
  if (bt && bt.model && bt.model.mae != null) {
    const seasons = bt.seasons ? Object.keys(bt.seasons).join(', ') : '';
    wrap.appendChild(h('div', { class: 'banner ok' }, [
      h('strong', {}, `Model validated: `),
      `MAE ${bt.model.mae} vs ${bt.baseline_last.mae} (last GW) / ` +
      `${bt.baseline_ppg.mae} (season avg) baseline`,
      seasons ? h('span', { class: 'muted small' }, ` — backtested on ${seasons}, `
        + `${bt.model.n.toLocaleString()} player-GW samples` ) : null,
    ]));
  }

  // Top captains
  const caps = A.captainRanking(bundle, 5);
  const capBody = table([
    { key: 'r', label: '#', get: (_r, i) => '', sortable: false,
      fmt: (_v, row) => String(caps.indexOf(row) + 1) },
    { key: 'name', label: 'Player', get: (r) => r.p.web, sortable: false,
      fmt: (_v, r) => playerCell(r.p) },
    { key: 'fx', label: 'Next', get: (r) => r.proj.fixtures[0]?.fdr ?? 3, sortable: false,
      fmt: (_v, r) => { const f = r.proj.fixtures[0];
        return f ? fdrBadge(f.fdr, `${f.opp_short} (${f.home ? 'H' : 'A'})`) : '—'; } },
    { key: 'proj', label: 'Proj', align: 'right', get: (r) => r.proj.perGame, sortable: false,
      fmt: (v) => h('strong', {}, v.toFixed(1)) },
  ], caps);

  // Best value
  const vals = A.valuePicks(bundle, { limit: 6 });
  const valBody = table([
    { key: 'name', label: 'Player', get: (p) => p.web, sortable: false, fmt: (_v, p) => playerCell(p) },
    { key: 'price', label: 'Price', align: 'right', get: (p) => p.price, sortable: false, fmt: money },
    { key: 'pts', label: 'Pts', align: 'right', get: (p) => p.pts, sortable: false },
    { key: 'val', label: 'Pts/£m', align: 'right', get: (p) => p.value_pts, sortable: false,
      fmt: (v) => h('strong', {}, v.toFixed(1)) },
  ], vals);

  // Price movers
  const { risers, fallers } = A.priceMovers(bundle, 5);
  const moverList = (arr, up) => arr.length ? h('ul', { class: 'movers' },
    arr.map((p) => h('li', {}, [
      h('span', { class: `arrow ${up ? 'up' : 'down'}` }, up ? '▲' : '▼'),
      h('span', { class: 'pname' }, p.web),
      h('span', { class: 'muted small' }, `${p.team_short} · ${money(p.price)}`)])))
    : note('None this gameweek.');

  // Watch list
  const watch = A.watchList(bundle, { limit: 6 });
  const watchBody = watch.length ? h('ul', { class: 'watch' },
    watch.map(({ p }) => h('li', {}, [
      statusDot(p),
      h('span', { class: 'pname' }, p.web),
      h('span', { class: 'muted small' },
        p.flagged ? (STATUS[p.status]?.label + (p.news ? ` — ${p.news}` : ''))
          : p.cost_change_event < 0 ? 'Price falling'
          : p.form < p.ppg - 1.5 ? 'Form dip' : 'Losing owners')])))
    : note('No widely-held players flagged. 👍');

  wrap.appendChild(h('div', { class: 'cols' }, [
    card('Top captain picks', capBody, h('a', { class: 'more', href: '#/captains' }, 'All →')),
    card('Best value', valBody, h('a', { class: 'more', href: '#/players' }, 'Explore →')),
  ]));
  wrap.appendChild(h('div', { class: 'cols' }, [
    card('Price risers', moverList(risers, true)),
    card('Price fallers', moverList(fallers, false)),
    card('Sell / watch list', watchBody),
  ]));
  return wrap;
}

// ---- Players explorer -------------------------------------------------------

export function players(bundle) {
  const wrap = h('div', { class: 'view' });
  const controls = h('div', { class: 'controls' });
  const state = { pos: '', q: '', maxPrice: 20 };
  const host = h('div', { class: 'table-wrap' });

  const projCache = new Map();
  const proj5 = (p) => {
    if (!projCache.has(p.id)) projCache.set(p.id, A.projectPlayer(bundle, p, 5).total);
    return projCache.get(p.id);
  };

  const draw = () => {
    let rows = bundle.players.filter((p) =>
      (!state.pos || p.pos === state.pos) &&
      p.price <= state.maxPrice &&
      (!state.q || p.web.toLowerCase().includes(state.q) ||
        p.name.toLowerCase().includes(state.q) ||
        p.team_short.toLowerCase().includes(state.q)));

    host.replaceChildren(table([
      { key: 'name', label: 'Player', get: (p) => p.web, sortVal: (p) => p.web.toLowerCase(),
        fmt: (_v, p) => playerCell(p), desc: false },
      { key: 'pos', label: 'Pos', get: (p) => p.pos, fmt: (v) => posBadge(v), desc: false },
      { key: 'price', label: 'Price', align: 'right', get: (p) => p.price, fmt: money },
      { key: 'form', label: 'Form', align: 'right', get: (p) => p.form },
      { key: 'pts', label: 'Pts', align: 'right', get: (p) => p.pts },
      { key: 'ppg', label: 'PPG', align: 'right', get: (p) => p.ppg },
      { key: 'value_pts', label: 'Pts/£m', align: 'right', get: (p) => p.value_pts,
        fmt: (v) => h('strong', {}, v.toFixed(1)) },
      { key: 'xgi', label: 'xGI', align: 'right', get: (p) => p.xgi, fmt: (v) => v.toFixed(1) },
      { key: 'defcon_per90', label: 'DC/90', align: 'right', get: (p) => p.defcon_per90,
        fmt: (v) => v.toFixed(1) },
      { key: 'sel', label: 'Own%', align: 'right', get: (p) => p.sel, fmt: pct },
      { key: 'fx', label: 'Fixtures', get: (p) => 0, sortable: false,
        fmt: (_v, p) => fixtureStrip(bundle, p.team, 5) },
      { key: 'proj', label: 'Proj5', align: 'right', get: (p) => proj5(p),
        fmt: (v) => h('strong', {}, v.toFixed(1)) },
    ], rows, { initialSort: { key: 'proj', dir: -1 } }));
  };

  const posSel = h('select', { onchange: (e) => { state.pos = e.target.value; draw(); } },
    [h('option', { value: '' }, 'All positions'),
      ...POS_ORDER.map((p) => h('option', { value: p }, POS_LABEL[p]))]);
  const search = h('input', { type: 'search', placeholder: 'Search player or team…',
    oninput: (e) => { state.q = e.target.value.toLowerCase().trim(); draw(); } });
  const priceOut = h('span', { class: 'muted small' }, `≤ ${money(20)}`);
  const price = h('input', { type: 'range', min: '4', max: '20', step: '0.5', value: '20',
    oninput: (e) => { state.maxPrice = +e.target.value; priceOut.textContent = `≤ ${money(state.maxPrice)}`; draw(); } });

  controls.append(posSel, search, h('label', { class: 'rangelbl' }, [price, priceOut]));
  wrap.append(
    card('Player explorer',
      h('div', {}, [controls, host, note(
        'Click a column to sort. Proj5 = projected points over the next 5 GWs. ' +
        projectionBlurb(bundle) + ' DC/90 = defensive contributions per 90 for the ' +
        'new 2025/26 scoring.')])));
  draw();
  return wrap;
}

// ---- Fixtures (FDR ticker) --------------------------------------------------

export function fixtures(bundle) {
  const wrap = h('div', { class: 'view' });
  const N = 6;
  const startGw = bundle.meta.next_gw;
  const gws = Array.from({ length: N }, (_, i) => startGw + i);

  const rows = bundle.teams.map((t) => {
    const fx = A.teamFixtures(bundle, t.id, startGw, N);
    const byGw = new Map(fx.map((f) => [f.gw, f]));
    return { team: t, fx, byGw, avg: A.avgFdr(fx) };
  });

  const cols = [
    { key: 'team', label: 'Team', get: (r) => r.team.short, sortVal: (r) => r.team.short,
      desc: false, fmt: (_v, r) => h('span', { class: 'pname' }, r.team.name) },
    { key: 'avg', label: 'Avg FDR', align: 'right', get: (r) => r.avg,
      fmt: (v) => h('strong', {}, v.toFixed(2)), desc: false },
    ...gws.map((gw) => ({
      key: `gw${gw}`, label: `GW${gw}`, align: 'center', sortable: false,
      get: (r) => r.byGw.get(gw)?.fdr ?? 9,
      fmt: (_v, r) => { const f = r.byGw.get(gw);
        return f ? fdrBadge(f.fdr, `${f.opp_short} (${f.home ? 'H' : 'A'})`)
          : h('span', { class: 'muted' }, '—'); },
    })),
  ];

  wrap.append(card('Fixture difficulty ticker',
    h('div', { class: 'table-wrap' }, table(cols, rows, { initialSort: { key: 'avg', dir: 1 } })),
    h('div', { class: 'legend' }, [
      h('span', { class: 'muted small' }, 'Easier'),
      ...[1, 2, 3, 4, 5].map((n) => fdrBadge(n, String(n))),
      h('span', { class: 'muted small' }, 'Harder')])));
  wrap.append(note('Sorted by easiest average fixtures first — good for planning ' +
    'transfers, rotation and chips. Click GW columns are fixed; sort by Team or Avg FDR.'));
  return wrap;
}

// ---- Captains ---------------------------------------------------------------

export function captains(bundle) {
  const wrap = h('div', { class: 'view' });
  const ranked = A.captainRanking(bundle, 12);

  const bar = (label, val, max) => h('div', { class: 'bar-row' }, [
    h('span', { class: 'bar-lbl' }, label),
    h('span', { class: 'bar-track' }, h('span', { class: `bar bar-${label.toLowerCase()}`,
      style: `width:${Math.max(2, Math.min(100, (val / max) * 100))}%` })),
    h('span', { class: 'bar-val' }, val.toFixed(1))]);

  const list = h('ol', { class: 'caplist' }, ranked.map(({ p, proj }) => {
    const parts = proj.parts || { appearance: 0, attack: 0, defence: 0, defcon: 0 };
    const max = Math.max(2, parts.appearance, parts.attack, parts.defence, parts.defcon);
    const f = proj.fixtures[0];
    return h('li', { class: 'caprow' }, [
      h('div', { class: 'capmain' }, [
        h('div', { class: 'capwho' }, [statusDot(p),
          h('span', { class: 'pname big' }, p.web),
          posBadge(p.pos),
          h('span', { class: 'muted small' }, `${p.team_short} · ${money(p.price)}`)]),
        h('div', { class: 'capfx' }, f
          ? [h('span', { class: 'muted small' }, 'Next: '),
            fdrBadge(f.fdr, `${f.opp_short} (${f.home ? 'H' : 'A'})`)] : '—'),
        h('div', { class: 'capproj' }, [
          h('span', { class: 'muted small' }, 'Projected'),
          h('span', { class: 'bignum' }, proj.perGame.toFixed(1))]),
      ]),
      h('div', { class: 'capbars' }, [
        bar('Mins', parts.appearance, max),
        bar('Attack', parts.attack, max),
        bar('CS', parts.defence, max),
        bar('DEFCON', parts.defcon, max)]),
    ]);
  }));

  wrap.append(card('Captaincy rankings', list));
  wrap.append(note(projectionBlurb(bundle) + ' Bars break the next-fixture projection ' +
    'into appearance, attacking return, clean-sheet value and DEFCON. Consider a ' +
    'differential captain if chasing rank.'));
  return wrap;
}

// ---- Transfers --------------------------------------------------------------

export function transfers(bundle) {
  const wrap = h('div', { class: 'view' });
  const state = { pos: 'MID', maxPrice: 20 };
  const host = h('div', {});

  const draw = () => {
    const targets = A.transferTargets(bundle,
      { pos: state.pos, maxPrice: state.maxPrice, horizon: 5, limit: 10 });
    const rows = table([
      { key: 'name', label: 'Player', get: (r) => r.p.web, sortable: false,
        fmt: (_v, r) => playerCell(r.p) },
      { key: 'price', label: 'Price', align: 'right', get: (r) => r.p.price, sortable: false, fmt: money },
      { key: 'form', label: 'Form', align: 'right', get: (r) => r.p.form, sortable: false },
      { key: 'own', label: 'Own%', align: 'right', get: (r) => r.p.sel, sortable: false, fmt: pct },
      { key: 'fx', label: 'Next 5', get: () => 0, sortable: false,
        fmt: (_v, r) => fixtureStrip(bundle, r.p.team, 5) },
      { key: 'proj', label: 'Proj5', align: 'right', get: (r) => r.proj.total, sortable: false,
        fmt: (v) => h('strong', {}, v.toFixed(1)) },
    ], targets);
    host.replaceChildren(rows);
  };

  const tabs = h('div', { class: 'tabs' }, POS_ORDER.map((p) =>
    h('button', { class: `tab${p === state.pos ? ' on' : ''}`,
      onclick: (e) => { state.pos = p; tabs.querySelectorAll('.tab').forEach((b) => b.classList.remove('on'));
        e.target.classList.add('on'); draw(); } }, POS_LABEL[p])));

  const priceOut = h('span', { class: 'muted small' }, `≤ ${money(20)}`);
  const price = h('input', { type: 'range', min: '4', max: '20', step: '0.5', value: '20',
    oninput: (e) => { state.maxPrice = +e.target.value; priceOut.textContent = `≤ ${money(state.maxPrice)}`; draw(); } });

  // Sell side
  const watch = A.watchList(bundle, { limit: 8 });
  const sell = watch.length ? table([
    { key: 'name', label: 'Player', get: (r) => r.p.web, sortable: false, fmt: (_v, r) => playerCell(r.p) },
    { key: 'own', label: 'Own%', align: 'right', get: (r) => r.p.sel, sortable: false, fmt: pct },
    { key: 'why', label: 'Reason', get: (r) => r.p, sortable: false,
      fmt: (_v, r) => { const p = r.p;
        return p.flagged ? `${STATUS[p.status]?.label}${p.news ? ' — ' + p.news : ''}`
          : p.cost_change_event < 0 ? 'Price falling'
          : p.form < p.ppg - 1.5 ? 'Form dip' : 'Losing owners'; } },
  ], watch) : note('No widely-held players flagged for selling.');

  wrap.append(
    card('Transfer targets',
      h('div', {}, [tabs, h('div', { class: 'controls' },
        [h('label', { class: 'rangelbl' }, [h('span', { class: 'muted small' }, 'Max price '), price, priceOut])]),
        host, note('Ranked by projected points over the next 5 GWs. ' +
          projectionBlurb(bundle) + ' Remember: each extra transfer beyond your free ' +
          'one costs −4 pts — only take a hit if the target is projected to out-score ' +
          'the alternative by more than 4 over the coming weeks.')])),
    card('Consider selling', sell));
  draw();
  return wrap;
}

// ---- Differentials ----------------------------------------------------------

export function differentials(bundle) {
  const wrap = h('div', { class: 'view' });
  const rows = A.differentials(bundle, { maxOwn: 10, horizon: 3, limit: 15 });
  const body = table([
    { key: 'name', label: 'Player', get: (r) => r.p.web, sortable: false, fmt: (_v, r) => playerCell(r.p) },
    { key: 'pos', label: 'Pos', get: (r) => r.p.pos, sortable: false, fmt: (v) => posBadge(v) },
    { key: 'price', label: 'Price', align: 'right', get: (r) => r.p.price, sortable: false, fmt: money },
    { key: 'own', label: 'Own%', align: 'right', get: (r) => r.p.sel, sortable: false, fmt: pct },
    { key: 'form', label: 'Form', align: 'right', get: (r) => r.p.form, sortable: false },
    { key: 'fx', label: 'Next 3', get: () => 0, sortable: false,
      fmt: (_v, r) => fixtureStrip(bundle, r.p.team, 3) },
    { key: 'proj', label: 'Proj/GW', align: 'right', get: (r) => r.proj.perGame, sortable: false,
      fmt: (v) => h('strong', {}, v.toFixed(1)) },
  ], rows);
  wrap.append(card('Differentials (< 10% owned)', body));
  wrap.append(note('Low-ownership players with a strong projection — useful for ' +
    'climbing mini-leagues. Higher risk than template picks.'));
  return wrap;
}

// ---- My Team (personalised) -------------------------------------------------

export function myTeam(bundle) {
  const wrap = h('div', { class: 'view' });

  const render = () => {
    const sq = A.squad(bundle);
    const parts = [teamIdCard(bundle, render)];
    if (!sq) {
      parts.push(card('My Team', h('div', {}, [
        note('No squad loaded yet. Set your FPL team ID in config.json (or the ' +
          'FPL_TEAM_ID repository variable) and run the “Update FPL data” Action — ' +
          'it fetches your team server-side and commits data/entry.json. The FPL ' +
          'API can’t be called directly from the browser (CORS), so a live team-ID ' +
          'box here needs a proxy (see docs/ARCHITECTURE.md).')])));
      wrap.replaceChildren(...parts);
      return;
    }

    const e = sq.entry;
    const sp = A.squadProjection(bundle, sq);
    const stat = (label, val) => h('div', { class: 'stat' }, [
      h('span', { class: 'stat-label' }, label), h('div', { class: 'stat-val' }, val)]);
    parts.push(h('div', { class: 'stats' }, [
      stat('Manager', h('strong', {}, e.manager || '—')),
      stat('Overall', h('strong', {}, e.overall_points != null
        ? `${e.overall_points.toLocaleString()} pts` : '—')),
      stat('In the bank', h('strong', {}, `£${(e.bank ?? 0).toFixed(1)}m`)),
      stat(`GW${bundle.meta.next_gw} projected`, h('strong', {}, sp.total.toFixed(1))),
    ]));
    if (e.source === 'sample') {
      parts.push(h('div', { class: 'banner' },
        'Sample squad — set your team ID and run the Action to load your real team.'));
    }

    parts.push(card(`Your team — GW${e.event}`, pitch(bundle, sq),
      h('span', { class: 'muted small' }, `Captain contributes +${sp.captain.toFixed(1)}`)));

    // Captain advice
    const ca = A.captainAdvice(bundle, sq);
    if (ca.best) {
      const same = sq.captain && ca.best.p.id === sq.captain.id;
      const curProj = sq.captain
        ? A.projectPlayer(bundle, sq.captain, 1).perGame.toFixed(1) : '—';
      parts.push(card('Captaincy', h('div', { class: 'advice' }, [
        same
          ? h('p', {}, [okTick(), ' Your captain ', b(sq.captain.web),
            ` is also the model’s top pick for GW${bundle.meta.next_gw} `,
            `(${ca.best.proj.toFixed(1)} pts).`])
          : h('p', {}, [warnTick(), ' Consider captaining ', b(ca.best.p.web),
            ` (${ca.best.proj.toFixed(1)}) over `, b(sq.captain ? sq.captain.web : '—'),
            ` (${curProj}) for GW${bundle.meta.next_gw}.`]),
      ])));
    }

    // Flags
    const flags = A.squadFlags(sq);
    if (flags.length) {
      parts.push(card('⚠︎ Squad alerts', h('ul', { class: 'watch' },
        flags.map((p) => h('li', {}, [statusDot(p), h('span', { class: 'pname' }, p.web),
          h('span', { class: 'muted small' },
            `${STATUS[p.status]?.label}${p.news ? ' — ' + p.news : ''}`)])))));
    }

    // Transfer suggestions
    const sugg = A.transferSuggestions(bundle, sq, { limit: 5 });
    const sBody = sugg.length ? table([
      { key: 'out', label: 'Out', get: (r) => r.out.web, sortable: false,
        fmt: (_v, r) => playerCell(r.out) },
      { key: 'in', label: 'In', get: (r) => r.in.web, sortable: false,
        fmt: (_v, r) => playerCell(r.in) },
      { key: 'op', label: 'Out proj5', align: 'right', get: (r) => r.outProj, sortable: false,
        fmt: (v) => v.toFixed(1) },
      { key: 'ip', label: 'In proj5', align: 'right', get: (r) => r.inProj, sortable: false,
        fmt: (v) => v.toFixed(1) },
      { key: 'gain', label: 'Gain', align: 'right', get: (r) => r.gain, sortable: false,
        fmt: (v) => h('strong', {}, `+${v.toFixed(1)}`) },
      { key: 'hit', label: 'After −4 hit', align: 'right', get: (r) => r.netAfterHit,
        sortable: false, fmt: (v) => h('span', { class: v > 0 ? 'pos-ok' : 'muted' },
          `${v > 0 ? '+' : ''}${v.toFixed(1)}`) },
    ], sugg) : note('No affordable upgrade improves your squad’s 5-GW projection right now.');
    parts.push(card('Suggested transfers', h('div', {}, [sBody, note(
      'Ranked by projected points gained over the next 5 GWs, within your bank ' +
      '(£' + (e.bank ?? 0).toFixed(1) + 'm) and the 3-per-club limit. “After −4 hit” ' +
      'is the net if this isn’t a free transfer — only worthwhile when positive. ' +
      'Sell prices are approximated by current price (the public API hides exact ' +
      'sell value).')])));

    wrap.replaceChildren(...parts);
  };

  render();
  return wrap;
}

function b(text) { return h('strong', {}, text); }
function okTick() { return h('span', { class: 'pos-ok' }, '✓'); }
function warnTick() { return h('span', { class: 'arrow down' }, '➜'); }

function pitch(bundle, sq) {
  const chip = (p) => {
    const proj = A.projectPlayer(bundle, p, 1).perGame;
    const isC = sq.captain && sq.captain.id === p.id;
    const isV = sq.vice && sq.vice.id === p.id;
    return h('div', { class: 'chip' + (p.flagged ? ' chip-flag' : '') }, [
      h('div', { class: 'chip-badges' }, [
        isC ? h('span', { class: 'cap' }, 'C') : (isV ? h('span', { class: 'vice' }, 'V') : null),
        p.flagged ? h('span', { class: 'dot dot-flag' }) : null]),
      h('div', { class: 'chip-name' }, p.web),
      h('div', { class: 'chip-sub' }, `${p.team_short} · ${proj.toFixed(1)}`),
    ]);
  };
  const rows = POS_ORDER.map((pos) => {
    const line = sq.xi.filter((p) => p.pos === pos);
    return line.length ? h('div', { class: 'pitch-row' }, line.map(chip)) : null;
  }).filter(Boolean);
  return h('div', {}, [
    h('div', { class: 'pitch' }, rows),
    h('div', { class: 'bench' }, [h('span', { class: 'bench-lbl' }, 'Bench'),
      ...sq.bench.map(chip)]),
  ]);
}

function teamIdCard(bundle, rerender) {
  const current = bundle.entry?.id || bundle.config?.fpl_team_id || '';
  const proxy = bundle.config?.entry_proxy;
  const input = h('input', { type: 'text', inputmode: 'numeric', value: String(current),
    placeholder: 'FPL team ID', class: 'teamid' });
  const status = h('span', { class: 'muted small' });

  const load = async () => {
    const id = input.value.trim();
    if (!/^\d+$/.test(id)) { status.textContent = 'Enter a numeric team ID.'; return; }
    try { localStorage.setItem('fpl_team_id', id); } catch { /* ignore */ }
    if (proxy) {
      status.textContent = 'Loading…';
      try {
        const entry = await fetchEntryViaProxy(proxy, id, bundle.meta.current_gw || 1);
        applyEntry(bundle, entry);
        status.textContent = `Loaded ${entry.manager || id}.`;
        rerender();
      } catch (err) { status.textContent = `Could not load team ${id}: ${err.message}`; }
    } else if (String(id) === String(bundle.entry?.id)) {
      status.textContent = 'This is the team loaded by the Action.';
    } else {
      status.textContent = 'Saved. To load a different team without a proxy, set ' +
        'FPL_TEAM_ID / config.json and re-run the Action (the browser can’t call the ' +
        'FPL API directly).';
    }
  };
  const btn = h('button', { class: 'btn', onclick: load }, 'Load');
  input.addEventListener('keydown', (ev) => { if (ev.key === 'Enter') load(); });

  return card('Team ID', h('div', { class: 'controls' }, [
    input, btn, status,
    h('a', { class: 'muted small', href: 'https://fantasy.premierleague.com/',
      target: '_blank', rel: 'noopener' }, 'Where do I find this?')]));
}

// ---- Planner (multi-transfer & chip timing) ---------------------------------

const CHIP_EMOJI = { 'Triple Captain': '👑', 'Bench Boost': '🪑',
  'Free Hit': '🎯', 'Wildcard': '🃏' };

export function planner(bundle) {
  const wrap = h('div', { class: 'view' });
  const sq = A.squad(bundle);

  if (!sq) {
    wrap.append(card('Planner', note('Load your squad first (see the My Team tab) — ' +
      'the planner works from your 15 players, their projections and the fixtures.')));
    return wrap;
  }
  if (!A.hasModel(bundle)) {
    wrap.append(card('Planner', note('The planner needs model projections ' +
      '(data/projections.json). Run the “Update FPL data” Action to generate them.')));
    return wrap;
  }

  const horizon = Math.min(6, bundle.projections.meta.horizon || 6);
  const outlook = A.gameweekOutlook(bundle, sq, horizon);

  // free-transfer control (persisted per browser)
  let ft = 1;
  try { ft = Math.max(0, Math.min(5, +(localStorage.getItem('fpl_ft') ?? 1))); }
  catch { ft = 1; }

  const planHost = h('div', {});
  const drawPlan = () => {
    const plan = A.optimiseTransfers(bundle, sq, { freeTransfers: ft, maxTransfers: 3 });
    planHost.replaceChildren(renderPlan(bundle, plan));
  };

  const ftInput = h('input', { type: 'number', min: '0', max: '5', value: String(ft),
    class: 'teamid', style: 'min-width:64px',
    oninput: (e) => { ft = Math.max(0, Math.min(5, +e.target.value || 0));
      try { localStorage.setItem('fpl_ft', String(ft)); } catch { /* ignore */ }
      drawPlan(); } });

  // 1) Gameweek outlook
  wrap.append(card('Gameweek outlook', outlookTable(bundle, outlook, sq),
    h('span', { class: 'muted small' }, `Next ${horizon} GWs`)));

  // 2) Chip recommendations
  const recs = A.chipRecommendations(bundle, outlook, sq);
  wrap.append(card('Chip timing', h('div', { class: 'chips' }, recs.map((r) =>
    h('div', { class: 'chiprec' }, [
      h('div', { class: 'chiprec-head' }, [
        h('span', { class: 'chip-emoji' }, CHIP_EMOJI[r.chip] || '•'),
        h('span', { class: 'chip-title' }, r.chip),
        r.gw ? h('span', { class: 'tag tag-live' }, `GW${r.gw}`)
          : h('span', { class: 'tag tag-sample' }, 'Hold')]),
      h('p', { class: 'muted small' }, r.detail),
    ])))));

  // 3) Transfer plan
  wrap.append(card('Transfer plan — next GW', h('div', {}, [
    h('div', { class: 'controls' }, [
      h('label', { class: 'rangelbl' },
        [h('span', { class: 'muted small' }, 'Free transfers available '), ftInput])]),
    planHost]), h('span', { class: 'muted small' }, `GW${bundle.meta.next_gw}`)));
  drawPlan();

  wrap.append(note('Projections are opponent-adjusted expected points (see MODEL.md). ' +
    'Chip picks use the strongest week in the horizon for each chip. The transfer plan ' +
    'is a combined optimiser: it jointly chooses the best set of up to 3 like-for-like ' +
    'moves that maximises 5-GW net gain within your bank and the 3-per-club limit, ' +
    'after −4 hits. Double/blank gameweeks are read from the fixtures. Sell prices are ' +
    'approximated by current price (the public API hides exact sell value).'));
  return wrap;
}

function outlookTable(bundle, outlook, sq) {
  const cols = [
    { key: 'gw', label: 'GW', get: (r) => r.gw, sortable: false,
      fmt: (v, r) => h('span', {}, [h('strong', {}, `GW${v}`),
        r.doubles.length ? h('span', { class: 'gw-tag dgw', title: 'Double GW players' },
          ` ×${r.doubles.length}D`) : null,
        r.blanks.length ? h('span', { class: 'gw-tag bgw', title: 'Blank GW players' },
          ` ${r.blanks.length}B`) : null]) },
    { key: 'xi', label: 'XI proj', align: 'right', get: (r) => r.xiProj, sortable: false,
      fmt: (v) => h('strong', {}, v.toFixed(1)) },
    { key: 'bench', label: 'Bench', align: 'right', get: (r) => r.benchProj, sortable: false,
      fmt: (v) => v.toFixed(1) },
    { key: 'cap', label: 'Best captain', get: (r) => r.captain, sortable: false,
      fmt: (_v, r) => r.captain
        ? h('span', {}, [h('span', { class: 'pname' }, r.captain.p.web),
          h('span', { class: 'muted small' }, ` ${r.captain.exp.toFixed(1)}`)]) : '—' },
    { key: 'note', label: '', get: (r) => r, sortable: false, fmt: (_v, r) => {
      if (r.blanks.length) return h('span', { class: 'muted small' },
        `${r.blanks.length} blank${r.blanks.length > 1 ? 's' : ''}`);
      if (r.doubles.length) return h('span', { class: 'pos-ok' },
        `${r.doubles.length} play twice`);
      return h('span', { class: 'muted small' }, '');
    } },
  ];
  return h('div', { class: 'table-wrap' }, table(cols, outlook));
}

function renderPlan(bundle, plan) {
  const rec = plan.recommend;
  const head = rec.k === 0
    ? h('p', {}, [okTick(), ' ', b('Roll your transfer'),
      ' — no combination of moves beats holding over the next 5 GWs.'])
    : h('p', {}, [h('strong', {}, `Make ${rec.k} transfer${rec.k > 1 ? 's' : ''}`),
      rec.hits ? h('span', { class: 'arrow down' }, ` (−${rec.hits * 4} hit)`) : null,
      ` — projected net +${rec.net.toFixed(1)} pts over 5 GWs`,
      rec.cost !== 0 ? h('span', { class: 'muted small' },
        `, ${rec.cost > 0 ? 'spends' : 'frees'} £${Math.abs(rec.cost).toFixed(1)}m`) : null,
      '.']);

  const rows = rec.transfers.length ? table([
    { key: 'out', label: 'Out', get: (r) => r.out.web, sortable: false,
      fmt: (_v, r) => playerCell(r.out) },
    { key: 'in', label: 'In', get: (r) => r.in.web, sortable: false,
      fmt: (_v, r) => playerCell(r.in) },
    { key: 'cost', label: 'Cost', align: 'right', get: (r) => r.cost, sortable: false,
      fmt: (v) => h('span', { class: 'muted small' },
        `${v > 0 ? '+' : ''}£${v.toFixed(1)}m`) },
    { key: 'gain', label: 'Gain (5GW)', align: 'right', get: (r) => r.gain, sortable: false,
      fmt: (v) => h('strong', {}, `+${v.toFixed(1)}`) },
  ], rec.transfers) : null;

  // compare the 0/1/2/3 options
  const compare = h('div', { class: 'plan-compare' }, plan.byK.map((o) =>
    h('span', { class: 'plan-opt' + (o.k === rec.k ? ' on' : '') },
      `${o.k} transfer${o.k === 1 ? '' : 's'}: net ${o.net >= 0 ? '+' : ''}${o.net.toFixed(1)}`
      + (o.hits ? ` (−${o.hits * 4})` : ''))));

  return h('div', {}, [head, rows, compare].filter(Boolean));
}

export const VIEWS = { dashboard, myteam: myTeam, planner, players, fixtures, captains,
  transfers, differentials };
