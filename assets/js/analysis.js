// Client-side analysis engine.
//
// Everything here is a pure function of the loaded data bundle. The projection
// is a deliberately TRANSPARENT heuristic (see docs/FEATURES.md) — every number
// shown in the UI can be traced back to these inputs. It is meant to be
// improved over time without changing the rest of the app.

const clamp = (x, lo, hi) => Math.max(lo, Math.min(hi, x));

// Goal points by position (FPL scoring).
const GOAL_PTS = { GKP: 10, DEF: 6, MID: 5, FWD: 4 };
// Clean-sheet points by position.
const CS_PTS = { GKP: 4, DEF: 4, MID: 1, FWD: 0 };
// DEFCON threshold (combined defensive actions per match) by position.
const DEFCON_THRESHOLD = { GKP: 99, DEF: 10, MID: 12, FWD: 12 };

// FDR 1..5 → tailwind-ish tier used for colouring.
export function fdrTier(fdr) {
  return clamp(Math.round(fdr), 1, 5);
}

// ---- Fixtures ---------------------------------------------------------------

// Upcoming fixtures for a team from a given GW, soonest first.
export function teamFixtures(bundle, teamId, fromGw, n = 5) {
  const { fixtures, teamById } = bundle;
  const out = [];
  for (const fx of fixtures) {
    if (fx.gw < fromGw) continue;
    if (fx.team_h === teamId) {
      out.push({ gw: fx.gw, home: true, opp: fx.team_a,
        opp_short: teamById.get(fx.team_a)?.short || '?', fdr: fx.fdr_h,
        kickoff: fx.kickoff });
    } else if (fx.team_a === teamId) {
      out.push({ gw: fx.gw, home: false, opp: fx.team_h,
        opp_short: teamById.get(fx.team_h)?.short || '?', fdr: fx.fdr_a,
        kickoff: fx.kickoff });
    }
  }
  out.sort((a, b) => a.gw - b.gw);
  return out.slice(0, n);
}

export function avgFdr(fixtures) {
  if (!fixtures.length) return 3;
  return fixtures.reduce((s, f) => s + f.fdr, 0) / fixtures.length;
}

// ---- Player projection ------------------------------------------------------

// How reliable are this player's minutes / how available are they.
function minutesFactor(p, currentGw) {
  const statusFactor = { a: 1, d: 0.72, i: 0.08, s: 0.05, u: 0.05, n: 0.05 };
  const sf = statusFactor[p.status] ?? 0.4;
  const played = Math.max(1, currentGw); // GWs so far (approx)
  const reliability = clamp(p.minutes / (played * 90), 0.25, 1);
  return sf * (0.45 + 0.55 * reliability);
}

// Projected points for a single upcoming fixture with difficulty `fdr`.
// Returns a breakdown so the UI can explain every point.
export function projectForFixture(p, fdr) {
  const per90 = p.minutes ? 90 / p.minutes : 0;
  const xg90 = p.xg * per90;
  const xa90 = p.xa * per90;

  // Easier fixture (low FDR) → boost; harder → dampen. FDR 3 is neutral.
  const ease = 1 + (3 - fdr) * 0.12;               // 2→1.24 ... 4→0.76

  const appearance = 2;                             // assume 60+ mins when playing
  const attack = (xg90 * (GOAL_PTS[p.pos] || 4) + xa90 * 3) * ease;

  // Clean-sheet expectation falls as the fixture gets harder.
  const csProb = clamp(0.42 - (fdr - 3) * 0.11, 0.04, 0.72);
  const defence = csProb * (CS_PTS[p.pos] || 0) + (p.pos === 'GKP' ? 1.1 : 0);

  // DEFCON: share of matches likely to hit the threshold × 2 pts.
  const thr = DEFCON_THRESHOLD[p.pos] || 99;
  const defcon = 2 * clamp(p.defcon_per90 / thr, 0, 1);

  return { appearance, attack, defence, defcon, ease, csProb };
}

// Whether model projections (data/projections.json) were loaded.
export function hasModel(bundle) {
  return !!(bundle.projections && bundle.projections.players);
}

// Projection over the next `horizon` fixtures (1 = captaincy / next GW).
// Prefers the fitted model (projections.json); falls back to the client
// heuristic below when projections aren't available.
export function projectPlayer(bundle, p, horizon = 1) {
  if (p.model && p.model.by_gw && p.model.by_gw.length) {
    const fixtures = teamFixtures(bundle, p.team, bundle.meta.next_gw, horizon);
    const slice = p.model.by_gw.slice(0, horizon);
    const total = slice.reduce((s, g) => s + g.exp, 0);
    const perGame = slice.length ? total / slice.length : 0;
    // The model exposes a breakdown for the next fixture (next_parts).
    const parts = p.model.next_parts
      ? { appearance: p.model.next_parts.appearance, attack: p.model.next_parts.attack,
          defence: p.model.next_parts.defence, defcon: p.model.next_parts.defcon }
      : null;
    return {
      total: +total.toFixed(2), perGame: +perGame.toFixed(2),
      fixtures, parts, detail: p.model.next_detail || null, source: 'model',
    };
  }
  return heuristicProjection(bundle, p, horizon);
}

function heuristicProjection(bundle, p, horizon = 1) {
  const { meta } = bundle;
  const fixtures = teamFixtures(bundle, p.team, meta.next_gw, horizon);
  const mf = minutesFactor(p, meta.current_gw);

  if (!fixtures.length) {
    return { total: 0, perGame: 0, mf, fixtures, parts: null };
  }

  let sum = { appearance: 0, attack: 0, defence: 0, defcon: 0 };
  for (const fx of fixtures) {
    const b = projectForFixture(p, fx.fdr);
    sum.appearance += b.appearance;
    sum.attack += b.attack;
    sum.defence += b.defence;
    sum.defcon += b.defcon;
  }
  const n = fixtures.length;
  // Per-game raw, gated by minutes reliability/availability.
  const rawPerGame = (sum.appearance + sum.attack + sum.defence + sum.defcon) / n;
  // Momentum: reward players outperforming their season average right now.
  const formAdj = clamp((p.form - p.ppg) * 0.25, -1, 1.5);
  const perGame = mf * rawPerGame + formAdj;

  return {
    total: +(perGame * n).toFixed(2),
    perGame: +perGame.toFixed(2),
    mf: +mf.toFixed(2),
    formAdj: +formAdj.toFixed(2),
    fixtures,
    parts: {
      appearance: +(mf * sum.appearance / n).toFixed(2),
      attack: +(mf * sum.attack / n).toFixed(2),
      defence: +(mf * sum.defence / n).toFixed(2),
      defcon: +(mf * sum.defcon / n).toFixed(2),
    },
  };
}

// ---- Rankings ---------------------------------------------------------------

// Captaincy: projected points for the very next fixture, ranked.
export function captainRanking(bundle, limit = 12) {
  return bundle.players
    .filter((p) => !p.flagged && p.minutes > 0)
    .map((p) => ({ p, proj: projectPlayer(bundle, p, 1) }))
    .sort((a, b) => b.proj.perGame - a.proj.perGame)
    .slice(0, limit);
}

// Best value: points-per-million, available players only.
export function valuePicks(bundle, { pos = null, limit = 10 } = {}) {
  return bundle.players
    .filter((p) => !p.flagged && p.minutes > 0 && (!pos || p.pos === pos))
    .slice()
    .sort((a, b) => b.value_pts - a.value_pts)
    .slice(0, limit);
}

// Transfer targets by position: rank by projected points over next N fixtures,
// available only, optionally under a max price.
export function transferTargets(bundle, { pos, maxPrice = Infinity, horizon = 5,
  limit = 8 } = {}) {
  return bundle.players
    .filter((p) => p.pos === pos && !p.flagged && p.price <= maxPrice && p.minutes > 0)
    .map((p) => ({ p, proj: projectPlayer(bundle, p, horizon) }))
    .sort((a, b) => b.proj.total - a.proj.total)
    .slice(0, limit);
}

// Differentials: strong projection at low ownership.
export function differentials(bundle, { maxOwn = 10, horizon = 3, limit = 10 } = {}) {
  return bundle.players
    .filter((p) => !p.flagged && p.sel <= maxOwn && p.minutes > 0)
    .map((p) => ({ p, proj: projectPlayer(bundle, p, horizon) }))
    .filter((x) => x.proj.perGame > 2)
    .sort((a, b) => b.proj.perGame - a.proj.perGame)
    .slice(0, limit);
}

// Players to consider selling: flagged, or price falling, or poor value.
export function watchList(bundle, { limit = 8 } = {}) {
  const scored = bundle.players
    .filter((p) => p.sel > 3) // only widely-held players are worth warning about
    .map((p) => {
      let risk = 0;
      if (p.flagged) risk += 5;
      if (p.cost_change_event < 0) risk += 1.5;          // price falling
      if (p.form < p.ppg - 1.5) risk += 1.5;             // form dip
      if (p.transfers_out_event > p.transfers_in_event) risk += 1;
      return { p, risk };
    })
    .filter((x) => x.risk > 0)
    .sort((a, b) => b.risk - a.risk)
    .slice(0, limit);
  return scored;
}

// ---- Personalised squad (from data/entry.json) -----------------------------

// Decompose the manager's entry into resolved players.
export function squad(bundle) {
  const e = bundle.entry;
  if (!e || !e.picks) return null;
  const byId = bundle.playerById;
  const resolved = e.picks
    .map((pk) => ({ pk, p: byId.get(pk.element) }))
    .filter((x) => x.p);
  resolved.sort((a, b) => a.pk.slot - b.pk.slot);
  const xi = resolved.filter((x) => x.pk.slot <= 11).map((x) => x.p);
  const bench = resolved.filter((x) => x.pk.slot >= 12).map((x) => x.p);
  const captain = resolved.find((x) => x.pk.is_captain)?.p || null;
  const vice = resolved.find((x) => x.pk.is_vice)?.p || null;
  return { entry: e, all: resolved.map((x) => x.p), xi, bench, captain, vice };
}

// Projected points for the XI next GW, counting the captain twice.
export function squadProjection(bundle, sq) {
  let total = 0;
  for (const p of sq.xi) total += projectPlayer(bundle, p, 1).perGame;
  const capExtra = sq.captain ? projectPlayer(bundle, sq.captain, 1).perGame : 0;
  return { total: +(total + capExtra).toFixed(1), captain: +capExtra.toFixed(1) };
}

// Best captain in the XI for next GW vs the current armband.
export function captainAdvice(bundle, sq) {
  const ranked = sq.xi
    .map((p) => ({ p, proj: projectPlayer(bundle, p, 1).perGame }))
    .sort((a, b) => b.proj - a.proj);
  return { best: ranked[0] || null, current: sq.captain, ranked };
}

// Suggested single transfers: for each squad player, the best affordable,
// available upgrade in the same position, ranked by 5-GW projected gain.
// Sell price is approximated by current price (public API hides exact sell
// value); the −4 hit break-even is shown so the call is explicit.
export function transferSuggestions(bundle, sq, { limit = 5 } = {}) {
  const bank = sq.entry.bank ?? 0;
  const ownedIds = new Set(sq.all.map((p) => p.id));
  // count owned players per club (for the 3-per-club rule)
  const perClub = {};
  for (const p of sq.all) perClub[p.team] = (perClub[p.team] || 0) + 1;

  const proj5 = (p) => projectPlayer(bundle, p, 5).total;

  const suggestions = [];
  for (const out of sq.all) {
    const budget = out.price + bank;
    const outProj = proj5(out);
    const candidates = bundle.players.filter((c) =>
      c.pos === out.pos && !ownedIds.has(c.id) && !c.flagged &&
      c.minutes > 0 && c.price <= budget &&
      // 3-per-club: ok if different club, or that club has room after selling `out`
      ((c.team === out.team) || ((perClub[c.team] || 0) < 3)));
    if (!candidates.length) continue;
    let best = null, bestP = -Infinity;
    for (const c of candidates) {
      const cp = proj5(c);
      if (cp > bestP) { bestP = cp; best = c; }
    }
    const gain = +(bestP - outProj).toFixed(1);
    if (best && gain > 0) {
      suggestions.push({ out, in: best, gain, outProj: +outProj.toFixed(1),
        inProj: +bestP.toFixed(1), netAfterHit: +(gain - 4).toFixed(1) });
    }
  }
  // Highest-gain first, then keep at most one suggestion per incoming player and
  // per outgoing player, so the list reads as distinct realistic moves rather
  // than the same star target proposed for several slots.
  suggestions.sort((a, b) => b.gain - a.gain);
  const usedIn = new Set(), usedOut = new Set();
  const deduped = [];
  for (const s of suggestions) {
    if (usedIn.has(s.in.id) || usedOut.has(s.out.id)) continue;
    usedIn.add(s.in.id);
    usedOut.add(s.out.id);
    deduped.push(s);
  }
  return deduped.slice(0, limit);
}

// Flagged (injured/doubtful) players in the squad.
export function squadFlags(sq) {
  return sq.all.filter((p) => p.flagged);
}

// Price movers this gameweek.
export function priceMovers(bundle, limit = 6) {
  const risers = bundle.players.filter((p) => p.cost_change_event > 0)
    .sort((a, b) => b.transfers_in_event - a.transfers_in_event).slice(0, limit);
  const fallers = bundle.players.filter((p) => p.cost_change_event < 0)
    .sort((a, b) => b.transfers_out_event - a.transfers_out_event).slice(0, limit);
  return { risers, fallers };
}
