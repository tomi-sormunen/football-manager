// App bootstrap: load data once, wire a hash router, render the active view.

import { loadData } from './data.js';
import { VIEWS } from './views.js';

const ROUTES = [
  { id: 'dashboard', label: 'Dashboard' },
  { id: 'myteam', label: 'My Team' },
  { id: 'planner', label: 'Planner' },
  { id: 'players', label: 'Players' },
  { id: 'fixtures', label: 'Fixtures' },
  { id: 'captains', label: 'Captains' },
  { id: 'transfers', label: 'Transfers' },
  { id: 'differentials', label: 'Differentials' },
];

const app = document.getElementById('app');
const navEl = document.getElementById('nav');
let bundle = null;

function currentRoute() {
  const id = (location.hash.replace(/^#\/?/, '') || 'dashboard').split('?')[0];
  return ROUTES.find((r) => r.id === id) ? id : 'dashboard';
}

function renderNav(active) {
  navEl.replaceChildren(...ROUTES.map((r) => {
    const a = document.createElement('a');
    a.href = `#/${r.id}`;
    a.textContent = r.label;
    a.className = r.id === active ? 'active' : '';
    return a;
  }));
}

function render() {
  const id = currentRoute();
  renderNav(id);
  if (!bundle) return;
  try {
    const node = VIEWS[id](bundle);
    app.replaceChildren(node);
  } catch (err) {
    app.replaceChildren(errorBox('Something went wrong rendering this view.', err));
    console.error(err);
  }
  window.scrollTo(0, 0);
}

function errorBox(msg, err) {
  const div = document.createElement('div');
  div.className = 'banner error';
  div.innerHTML = `<strong>${msg}</strong>`;
  if (err) {
    const pre = document.createElement('pre');
    pre.className = 'small';
    pre.textContent = String(err.stack || err.message || err);
    div.appendChild(pre);
  }
  return div;
}

async function main() {
  renderNav(currentRoute());
  app.innerHTML = '<div class="loading">Loading FPL data…</div>';
  try {
    bundle = await loadData();
    const fresh = bundle.meta.generated_utc
      ? new Date(bundle.meta.generated_utc).toLocaleString() : 'unknown';
    document.getElementById('freshness').textContent = `Data updated: ${fresh}`;
  } catch (err) {
    app.replaceChildren(errorBox(
      'Could not load the dataset. If this is a fresh deploy, run the ' +
      '“Update FPL data” GitHub Action (or `python scripts/make_sample_data.py`) ' +
      'to generate data/.', err));
    return;
  }
  render();
}

window.addEventListener('hashchange', render);
main();
