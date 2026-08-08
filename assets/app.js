/* Shared logic for the job board and the applications page.
 *
 * Application state lives in localStorage under one key. It never leaves the
 * browser — there is no server here, and nothing is sent anywhere. Use the
 * Export button on the applications page to keep a copy.
 */

const STORE_KEY = 'jobtracker.v1';
const STATUSES = ['To apply', 'Applied', 'Online assessment', 'Interview',
                  'Offer', 'Rejected', 'No response', 'Not interested'];
const VARIANTS = ['AI_LLM_Backend', 'Platform_Backend', 'Data_ML'];

/* ---------------------------------------------------------------- storage */

function loadState() {
  try {
    const raw = localStorage.getItem(STORE_KEY);
    return raw ? JSON.parse(raw) : {};
  } catch (e) {
    console.warn('Could not read saved state:', e);
    return {};
  }
}

function saveState(state) {
  try {
    localStorage.setItem(STORE_KEY, JSON.stringify(state));
    return true;
  } catch (e) {
    console.warn('Could not save state:', e);
    return false;
  }
}

function getEntry(id) {
  return loadState()[id] || null;
}

function setEntry(id, patch) {
  const state = loadState();
  state[id] = Object.assign(
    { status: 'Applied', appliedAt: new Date().toISOString().slice(0, 10),
      variant: '', notes: '' },
    state[id] || {}, patch);
  saveState(state);
  return state[id];
}

function clearEntry(id) {
  const state = loadState();
  delete state[id];
  saveState(state);
}

/* ------------------------------------------------------------------- data */

async function loadJobs() {
  // Cache-bust so a fresh commit from the nightly Action shows up immediately.
  const res = await fetch(`data/jobs.json?t=${Date.now()}`, { cache: 'no-store' });
  if (!res.ok) throw new Error(`jobs.json returned ${res.status}`);
  return res.json();
}

// Whole calendar days between a YYYY-MM-DD string and today, in the viewer's
// own timezone. Comparing timestamps directly drifts by a day either side of
// midnight, which made "posted today" read as "yesterday".
function daysSince(iso) {
  if (!iso) return null;
  const then = new Date(iso + 'T00:00:00');
  if (isNaN(then)) return null;
  const now = new Date();
  const a = Date.UTC(then.getFullYear(), then.getMonth(), then.getDate());
  const b = Date.UTC(now.getFullYear(), now.getMonth(), now.getDate());
  return Math.round((b - a) / 86400000);
}

function fmtWhen(iso) {
  const d = daysSince(iso);
  if (d === null) return '';
  if (d <= 0) return 'today';
  if (d === 1) return 'yesterday';
  if (d < 14) return `${d} days ago`;
  if (d < 60) return `${Math.round(d / 7)} weeks ago`;
  return `${Math.round(d / 30)} months ago`;
}

function esc(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

/* --------------------------------------------------------------- job board */

function initBoard() {
  const listEl = document.getElementById('list');
  const statsEl = document.getElementById('stats');
  const stampEl = document.getElementById('stamp');
  const emptyEl = document.getElementById('empty');
  let data = null;

  async function refresh(userClicked) {
    listEl.setAttribute('aria-busy', 'true');
    if (userClicked) {
      const btn = document.getElementById('refresh');
      btn.disabled = true;
      btn.textContent = 'Checking…';
    }
    try {
      data = await loadJobs();
      render();
    } catch (e) {
      listEl.innerHTML =
        `<div class="card err"><b>Could not load the job list.</b><br>${esc(e.message)}
         <br><span class="mute">If you opened this file directly from disk, your browser is
         blocking the fetch. Serve it instead: <code>python3 -m http.server</code> in the repo
         folder, then open http://localhost:8000</span></div>`;
    } finally {
      listEl.removeAttribute('aria-busy');
      const btn = document.getElementById('refresh');
      btn.disabled = false;
      btn.textContent = 'Refresh';
    }
  }

  function activeFilters() {
    return {
      q: (document.getElementById('q').value || '').toLowerCase().trim(),
      newOnly: document.getElementById('f-new').checked,
      hideDone: document.getElementById('f-hide').checked,
      source: document.getElementById('f-source').value,
    };
  }

  function render() {
    if (!data) return;
    const state = loadState();
    const f = activeFilters();

    const shown = data.jobs.filter(j => {
      if (f.newOnly && !j.is_new) return false;
      if (f.source && j.source !== f.source) return false;
      if (f.hideDone && state[j.id]) return false;
      if (f.q) {
        const hay = `${j.company} ${j.title} ${j.location} ${j.note || ''}`.toLowerCase();
        if (!hay.includes(f.q)) return false;
      }
      return true;
    });

    const applied = data.jobs.filter(j => state[j.id]).length;
    stampEl.textContent =
      `List built ${data.generated_date}${data.generated_date === new Date().toISOString().slice(0, 10) ? ' (today)' : ''}`;
    statsEl.innerHTML =
      `<b>${data.jobs.length}</b> roles tracked · <b>${data.counts.new_today || 0}</b> new in the
       last run · <b>${applied}</b> marked applied · showing <b>${shown.length}</b>`;

    // Populate the source filter once.
    const sel = document.getElementById('f-source');
    if (sel.options.length <= 1) {
      [...new Set(data.jobs.map(j => j.source))].sort().forEach(s => {
        const o = document.createElement('option');
        o.value = s; o.textContent = s;
        sel.appendChild(o);
      });
    }

    emptyEl.hidden = shown.length > 0;
    listEl.innerHTML = shown.map(j => card(j, state[j.id])).join('');

    listEl.querySelectorAll('[data-apply]').forEach(btn => {
      btn.addEventListener('click', () => {
        const id = btn.dataset.apply;
        if (state[id]) { clearEntry(id); } else { setEntry(id, { status: 'Applied' }); }
        render();
      });
    });
  }

  function card(j, entry) {
    const done = !!entry;
    const bits = [j.experience, j.location, j.comp, j.posted ? fmtWhen(j.posted) : '']
      .filter(Boolean).map(b => `<span>${esc(b)}</span>`).join('');
    return `
      <article class="card${done ? ' done' : ''}">
        <div class="chead">
          <div>
            <span class="co">${esc(j.company || 'Company on posting')}</span>
            ${j.is_new ? '<span class="tag new">new</span>' : ''}
            ${done ? `<span class="tag ok">${esc(entry.status)}</span>` : ''}
          </div>
          <span class="src">${esc(j.source)}</span>
        </div>
        <div class="role">${esc(j.title)}</div>
        <div class="meta">${bits}</div>
        ${j.note ? `<p class="why">${esc(j.note)}</p>` : ''}
        <div class="actions">
          <a class="btn" href="${esc(j.url)}" target="_blank" rel="noopener">Open &amp; apply →</a>
          <button class="btn ghost" data-apply="${esc(j.id)}">
            ${done ? 'Undo — not applied' : 'Mark as applied'}
          </button>
          ${done ? `<a class="btn link" href="applied.html">Edit in tracker</a>` : ''}
        </div>
      </article>`;
  }

  document.getElementById('refresh').addEventListener('click', () => refresh(true));
  ['q', 'f-new', 'f-hide', 'f-source'].forEach(id =>
    document.getElementById(id).addEventListener('input', render));

  refresh(false);
}

/* ------------------------------------------------------- applications page */

function initApplied() {
  const bodyEl = document.getElementById('rows');
  const statsEl = document.getElementById('stats');
  const emptyEl = document.getElementById('empty');
  let jobsById = {};

  async function boot() {
    try {
      const data = await loadJobs();
      data.jobs.forEach(j => { jobsById[j.id] = j; });
    } catch (e) {
      console.warn('jobs.json unavailable, showing saved entries only', e);
    }
    render();
  }

  function render() {
    const state = loadState();
    const ids = Object.keys(state).sort((a, b) =>
      (state[b].appliedAt || '').localeCompare(state[a].appliedAt || ''));

    emptyEl.hidden = ids.length > 0;
    const counts = {};
    ids.forEach(id => { counts[state[id].status] = (counts[state[id].status] || 0) + 1; });
    statsEl.innerHTML = ids.length
      ? `<b>${ids.length}</b> applications · ` +
        Object.entries(counts).map(([k, v]) => `${esc(k)}: <b>${v}</b>`).join(' · ')
      : 'Nothing logged yet.';

    bodyEl.innerHTML = ids.map(id => {
      const e = state[id];
      const j = jobsById[id] || {};
      const age = daysSince(e.appliedAt);
      return `
        <tr>
          <td class="nowrap">${esc(e.appliedAt || '')}
            ${age !== null ? `<span class="mute">(${age}d)</span>` : ''}</td>
          <td><b>${esc(j.company || e.company || '—')}</b><br>
            <span class="mute">${esc(j.title || e.title || '')}</span></td>
          <td>
            <select data-status="${esc(id)}">
              ${STATUSES.map(s =>
                `<option${s === e.status ? ' selected' : ''}>${esc(s)}</option>`).join('')}
            </select>
          </td>
          <td>
            <select data-variant="${esc(id)}">
              <option value="">— variant —</option>
              ${VARIANTS.map(v =>
                `<option${v === e.variant ? ' selected' : ''}>${esc(v)}</option>`).join('')}
            </select>
          </td>
          <td><input data-notes="${esc(id)}" value="${esc(e.notes || '')}"
                     placeholder="referral, recruiter name, next step…"></td>
          <td class="nowrap">
            ${j.url ? `<a href="${esc(j.url)}" target="_blank" rel="noopener">posting</a> · ` : ''}
            <button class="linkbtn" data-del="${esc(id)}">remove</button>
          </td>
        </tr>`;
    }).join('');

    bodyEl.querySelectorAll('[data-status]').forEach(el =>
      el.addEventListener('change', () => {
        setEntry(el.dataset.status, { status: el.value }); render();
      }));
    bodyEl.querySelectorAll('[data-variant]').forEach(el =>
      el.addEventListener('change', () => setEntry(el.dataset.variant, { variant: el.value })));
    bodyEl.querySelectorAll('[data-notes]').forEach(el =>
      el.addEventListener('change', () => setEntry(el.dataset.notes, { notes: el.value })));
    bodyEl.querySelectorAll('[data-del]').forEach(el =>
      el.addEventListener('click', () => {
        if (confirm('Remove this application from the tracker?')) {
          clearEntry(el.dataset.del); render();
        }
      }));
  }

  function download(name, text, type) {
    const url = URL.createObjectURL(new Blob([text], { type }));
    const a = document.createElement('a');
    a.href = url; a.download = name; a.click();
    URL.revokeObjectURL(url);
  }

  document.getElementById('export-csv').addEventListener('click', () => {
    const state = loadState();
    const rows = [['Date', 'Company', 'Role', 'Status', 'Resume variant', 'Notes', 'URL']];
    Object.keys(state).forEach(id => {
      const e = state[id], j = jobsById[id] || {};
      rows.push([e.appliedAt || '', j.company || '', j.title || '', e.status || '',
                 e.variant || '', e.notes || '', j.url || '']);
    });
    const csv = rows.map(r =>
      r.map(c => `"${String(c).replace(/"/g, '""')}"`).join(',')).join('\n');
    download(`applications-${new Date().toISOString().slice(0, 10)}.csv`, csv, 'text/csv');
  });

  document.getElementById('export-json').addEventListener('click', () =>
    download(`applications-${new Date().toISOString().slice(0, 10)}.json`,
             JSON.stringify(loadState(), null, 2), 'application/json'));

  document.getElementById('import-json').addEventListener('change', ev => {
    const file = ev.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      try {
        const incoming = JSON.parse(reader.result);
        saveState(Object.assign(loadState(), incoming));
        render();
      } catch (e) {
        alert('That file could not be read as saved application data.');
      }
    };
    reader.readAsText(file);
  });

  boot();
}
