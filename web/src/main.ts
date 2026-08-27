import './styles.css';
import type { ExportFormat } from './api';
import { ApiError, api, loadToken, setToken } from './api';
import { person, state } from './state';
import { renderRail } from './views/rail';
import { renderTree } from './views/tree';

const root = document.getElementById('app')!;
const escape = (text: string): string =>
  text.replace(/[&<>"']/g, (c) =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]!);

/* ── data ──────────────────────────────────────────────────────────────────── */
async function reload(): Promise<void> {
  state.loading = true;
  state.error = null;
  render();
  try {
    await api.session();
    state.tree = (await api.tree()).Tree;
    state.treeChecked = true;
    if (state.tree === null) {
      state.loading = false;
      render();
      return;
    }
    const graph = await api.graph(state.root, state.side);
    state.graph = graph;
    state.root = graph.Root;
    if (state.selected === null || !person(state.selected)) {
      state.selected = graph.Root;
    }
  } catch (error) {
    state.error = error instanceof ApiError ? error.message : String(error);
    if (error instanceof ApiError && error.status === 401) state.token = '';
  } finally {
    state.loading = false;
    render();
  }
}

/* ── shell ─────────────────────────────────────────────────────────────────── */
function leftRail(): string {
  const rootPerson = state.root === null ? undefined : person(state.root);
  const counts = state.graph?.Counts;
  return `
    <div class="rail-in">
      <div class="rail-sec">
        <p class="lbl">Kinship measured from</p>
        <div class="rootcard">
          <div class="nm">${escape(rootPerson?.name ?? '—')}</div>
          <div class="sub">${counts ? `${counts.people} people · ${counts.unions} unions` : ''}</div>
        </div>
      </div>

      <div class="rail-sec">
        <p class="lbl">Family vocabulary</p>
        <div class="seg vseg">
          <button data-side="paternal" aria-pressed="${state.side === 'paternal'}">Father&rsquo;s side</button>
          <button data-side="maternal" aria-pressed="${state.side === 'maternal'}">Mother&rsquo;s side</button>
        </div>
        <div class="hint">${
          state.side === 'maternal'
            ? 'Your mother&rsquo;s people say కక్కయ్య where your father&rsquo;s say చిన్నాన్న. Same relation, different word.'
            : 'Switch to hear the tree in your mother&rsquo;s side&rsquo;s words.'
        }</div>
      </div>

      ${counts && counts.openBirthOrderQuestions > 0
        ? `<div class="rail-sec">
             <p class="lbl">Birth order</p>
             <div class="sampled">${counts.openBirthOrderQuestions} ${
               counts.openBirthOrderQuestions === 1 ? 'person needs' : 'people need'
             } a birth order before Telugu can name them. Select one and answer the question in
             the right rail.</div>
           </div>`
        : ''}

      <div class="rail-sec">
        <p class="lbl">Files</p>
        <div class="sampled">
          <strong>${escape(state.tree?.name ?? '')}</strong><br />
          ${escape(state.tree?.location ?? '')}
        </div>
        <div class="hint">Kept up to date after every change.</div>
        <div class="exports">
          <button class="btn ghost" data-export="gedzip">GEDZIP <small>with media</small></button>
          <button class="btn ghost" data-export="gedcom551">GEDCOM 5.5.1 <small>older tools</small></button>
          <button class="btn ghost" data-export="gedcom7">GEDCOM 7 <small>copy</small></button>
        </div>
        ${state.notice ? `<div class="notice">${escape(state.notice)}</div>` : ''}
      </div>

      <div class="rail-sec">
        <p class="lbl">Key</p>
        <div class="key"><i></i> Descent</div>
        <div class="key"><i class="adopt"></i> Adoptive descent</div>
        <div class="key"><i class="union"></i> Union</div>
        <div class="key"><span class="unres">అ / అ</span> Telugu label needs a fact</div>
      </div>
    </div>`;
}

function topBar(): string {
  const results = state.searchResults.length > 0
    ? `<div class="results">${state.searchResults
        .map(
          (r) => `<button data-goto="${r.ID}">${escape(r.Firstname)} ${escape(
            r.Lastname ?? '',
          )}</button>`,
        )
        .join('')}</div>`
    : '';
  return `
    <header class="top">
      <div class="brand">
        <svg width="21" height="21" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <path d="M12 21V11" stroke="#3F6D14" stroke-width="1.7" stroke-linecap="round"/>
          <path d="M12 11C12 6.5 8.5 3.5 4.5 3.5c0 4.5 3 7.5 7.5 7.5Z" stroke="#3F6D14" stroke-width="1.7" stroke-linejoin="round"/>
          <path d="M12 14c0-3.6 2.8-6 6-6 0 3.6-2.4 6-6 6Z" stroke="#7FA352" stroke-width="1.7" stroke-linejoin="round"/>
        </svg>
        <span>Family Tree</span>
      </div>
      <div class="searchbox">
        <input id="search" value="${escape(state.search)}"
               placeholder="Search names in either script — Varma, వర్మ" aria-label="Search people" />
        ${results}
      </div>
      <div class="seg">
        <button data-lang="en" aria-pressed="${state.lang === 'en'}">English</button>
        <button class="te" data-lang="te" aria-pressed="${state.lang === 'te'}">తెలుగు</button>
        <button data-lang="both" aria-pressed="${state.lang === 'both'}">Both</button>
      </div>
      <span class="spacer"></span>
      <span class="counts">${
        state.graph ? `${state.graph.Counts.people} people · ${state.graph.Counts.unions} unions` : ''
      }</span>
    </header>`;
}

function firstRun(): string {
  return `
    <div class="state">
      <div>
        <h2>Where should this tree live?</h2>
        <p>Everything the tree holds is kept as files in one folder &mdash; a GEDCOM 7 file
           that other genealogy software can open, its media, and the words your family uses.
           Back the tree up by copying that folder; rebuild it from there if the database is
           ever lost.</p>
        <input id="tree-name" placeholder="What to call it — Varma family" aria-label="Tree name" />
        <input id="tree-path" placeholder="Folder — /data/tree" aria-label="Folder" />
        <div><button class="btn" data-createtree>Create the tree</button></div>
        ${state.error ? `<p class="err">${escape(state.error)}</p>` : ''}
        <p style="margin-top:18px;font-size:13px;color:var(--muted)">
          Already have a GEDCOM file? Create the tree first, then use Import.
        </p>
      </div>
    </div>`;
}

function render(): void {
  if (!state.token) {
    root.innerHTML = `
      <div class="state">
        <div>
          <h2>Family Tree</h2>
          <p>This tree is private. Paste the access token to open it.</p>
          <input id="token" type="password" placeholder="Access token" aria-label="Access token" />
          <div><button class="btn" data-signin>Open</button></div>
          ${state.error ? `<p class="err">${escape(state.error)}</p>` : ''}
        </div>
      </div>`;
    return;
  }

  if (state.treeChecked && state.tree === null) {
    root.innerHTML = firstRun();
    return;
  }

  if (state.loading && !state.graph) {
    root.innerHTML = '<div class="state"><p>Loading the tree…</p></div>';
    return;
  }
  if (state.error && !state.graph) {
    root.innerHTML = `<div class="state"><div>
      <h2>Could not load the tree</h2><p class="err">${escape(state.error)}</p>
      <button class="btn" data-retry>Try again</button></div></div>`;
    return;
  }

  root.innerHTML = `
    <div class="shell">
      ${topBar()}
      <div class="body">
        <aside class="rail rail-l">${leftRail()}</aside>
        <main>${renderTree()}</main>
        <aside class="rail rail-r">${renderRail()}</aside>
      </div>
    </div>`;
}

/* ── events ────────────────────────────────────────────────────────────────── */
async function guard(work: () => Promise<void>): Promise<void> {
  try {
    await work();
  } catch (error) {
    state.error = error instanceof ApiError ? error.message : String(error);
    render();
  }
}

function closest(target: EventTarget | null, attr: string): HTMLElement | null {
  return (target as HTMLElement | null)?.closest?.(`[${attr}]`) ?? null;
}

root.addEventListener('click', (event) => {
  const t = event.target;

  const signIn = closest(t, 'data-signin');
  if (signIn) {
    const input = document.getElementById('token') as HTMLInputElement | null;
    if (input?.value) {
      state.token = input.value.trim();
      setToken(state.token);
      void reload();
    }
    return;
  }
  if (closest(t, 'data-retry')) { void reload(); return; }

  if (closest(t, 'data-createtree')) {
    const name = (document.getElementById('tree-name') as HTMLInputElement | null)?.value.trim();
    const location = (document.getElementById('tree-path') as HTMLInputElement | null)?.value.trim();
    if (!name || !location) {
      state.error = 'A tree needs a name and a folder.';
      render();
      return;
    }
    void guard(async () => {
      state.tree = (await api.createTree(name, location)).Tree;
      await reload();
    });
    return;
  }

  const exporter = closest(t, 'data-export');
  if (exporter) {
    const format = exporter.dataset.export as ExportFormat;
    void guard(async () => {
      const written = await api.exportTree(format);
      state.notice = `Wrote ${written.Path} (${Math.round(written.Bytes / 102.4) / 10} kB)`;
      render();
    });
    return;
  }

  const personButton = closest(t, 'data-person');
  if (personButton) {
    state.selected = Number(personButton.dataset.person);
    state.addingWord = false;
    render();
    return;
  }

  const opener = closest(t, 'data-open');
  if (opener) {
    state.open.add(Number(opener.dataset.open));
    render();
    return;
  }

  const reroot = closest(t, 'data-reroot');
  if (reroot) {
    state.root = Number(reroot.dataset.reroot);
    state.open.clear();
    void reload();
    return;
  }

  const side = closest(t, 'data-side');
  if (side) {
    state.side = side.dataset.side as typeof state.side;
    void reload();
    return;
  }

  const lang = closest(t, 'data-lang');
  if (lang) {
    state.lang = lang.dataset.lang as typeof state.lang;
    render();
    return;
  }

  const goto = closest(t, 'data-goto');
  if (goto) {
    state.selected = Number(goto.dataset.goto);
    state.search = '';
    state.searchResults = [];
    render();
    return;
  }

  const elder = closest(t, 'data-elder');
  if (elder) {
    const elderId = Number(elder.dataset.elder);
    const youngerId = Number(elder.dataset.younger);
    void guard(async () => {
      await api.recordBirthOrder(elderId, youngerId);
      await reload();
    });
    return;
  }

  const pin = closest(t, 'data-pin');
  if (pin && state.selected !== null) {
    const [linkIndex, altIndex] = pin.dataset.pin!.split(':').map(Number);
    const target = person(state.selected);
    const alt = target?.relationships[linkIndex!]?.alternatives[altIndex!];
    if (alt) {
      const personId = state.selected;
      void guard(async () => {
        await api.pinTerm(personId, alt.base, alt.term, alt.roman, state.side);
        await reload();
      });
    }
    return;
  }

  const unpin = closest(t, 'data-unpin');
  if (unpin && state.selected !== null) {
    const target = person(state.selected);
    const bases = target?.relationships[Number(unpin.dataset.unpin)]?.bases ?? [];
    const personId = state.selected;
    void guard(async () => {
      for (const base of bases) await api.unpinTerm(personId, base);
      await reload();
    });
    return;
  }

  if (closest(t, 'data-addword')) { state.addingWord = true; render(); return; }
  if (closest(t, 'data-cancelword')) { state.addingWord = false; render(); return; }

  if (closest(t, 'data-saveword') && state.selected !== null) {
    const word = (document.getElementById('word-te') as HTMLInputElement | null)?.value.trim();
    const usage = (document.getElementById('word-use') as HTMLInputElement | null)?.value.trim();
    const base = person(state.selected)?.relationships[0]?.bases[0];
    if (word && base) {
      void guard(async () => {
        await api.addWord(base, word, '', usage ?? '', state.side);
        state.addingWord = false;
        await reload();
      });
    }
    return;
  }
});

let searchTimer: number | undefined;
root.addEventListener('input', (event) => {
  const input = event.target as HTMLInputElement;
  if (input.id !== 'search') return;
  state.search = input.value;
  window.clearTimeout(searchTimer);
  searchTimer = window.setTimeout(() => {
    const query = state.search.trim();
    if (query.length < 2) {
      state.searchResults = [];
      render();
      return;
    }
    void guard(async () => {
      state.searchResults = (await api.search(query)).Data.slice(0, 8);
      render();
      (document.getElementById('search') as HTMLInputElement | null)?.focus();
    });
  }, 220);
});

/* ── boot ──────────────────────────────────────────────────────────────────── */
state.token = loadToken();
if (state.token) setToken(state.token);
render();
if (state.token) void reload();
