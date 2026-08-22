// Rendering for each view. Pure-ish: given the data bundle, return a DOM node.
// No framework — small template helpers + a sortable table builder.

import { POS_ORDER, POS_LABEL, STATUS } from './data.js';
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

export const VIEWS = { dashboard, players, fixtures, captains, transfers, differentials };
