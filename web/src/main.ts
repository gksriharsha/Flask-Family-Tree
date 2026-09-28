import './styles.css';
import { ApiError, api, loadToken, setToken } from './api';
import { escapeHtml as escape } from './dom';
import {
  childrenOf,
  focusId,
  graphIndex,
  lineageSpine,
  mergeGraph,
  person,
  setGraph,
  state,
} from './state';
import { computeLayout, type Layout } from './layout';
import { mountCanvas, type CanvasController, type CanvasViewState } from './canvas';
import { installEvents } from './events';
import { applyPan, installLineagePan } from './linpan';
import { drawWires } from './views/wires';
import { renderPersonForm } from './views/personform';
import { renderRail } from './views/rail';
import { renderCanvasNode, renderTree } from './views/tree';

const root = document.getElementById('app')!;

/**
 * How many parent/child hops the tree view loads around the current root on a fresh load, and
 * how far each expansion widens the window. Kept to the server's default; the server clamps to
 * its own maximum, so asking for more here is harmless.
 */
const DEFAULT_GENERATIONS = 3;

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

    // The tree view loads a WINDOW around the root, not the whole tree — that is what keeps a
    // 10k-person tree opening on the few dozen people in view. When we do not yet have a root
    // (first load, or the previous root was deleted), discover the lowest-id person from the
    // paginated list and anchor the window there.
    let anchor = state.root;
    if (anchor === null) {
      const firstPage = await api.people(null, 1);
      if (firstPage.People.length === 0) {
        setGraph(null); // empty tree
        state.root = null;
        state.loading = false;
        render();
        return;
      }
      anchor = firstPage.People[0]!.id;
    }

    const graph = await api.graphAround(anchor, DEFAULT_GENERATIONS, state.side);
    setGraph(graph); // rebuilds the Map-based indexes once per load; a fresh root replaces
    state.root = graph.Root;
    state.windowGenerations = graph.Window?.generations ?? DEFAULT_GENERATIONS;
    // A fresh root means a fresh window: let the frontier auto-widen fire again.
    atWindowCap = false;
    lastEdgeFocus = null;
    if (state.selected === null || !person(state.selected)) {
      state.selected = graph.Root;
    }
    if (state.focus !== null && !person(state.focus)) {
      state.focus = null;
    }
    // A new graph invalidates the memoised layout and any live canvas.
    layoutCache = null;
    disposeCanvas();
    canvasViewState = null;
  } catch (error) {
    state.error = error instanceof ApiError ? error.message : String(error);
    if (error instanceof ApiError && error.status === 401) state.token = '';
  } finally {
    state.loading = false;
    render();
  }
}

/**
 * Widen the window around the current root by one step and merge the result in.
 *
 * Called when the reader reaches the edge of what is loaded — descending into a person with no
 * loaded children, or panning the canvas past the mounted set — so the tree keeps filling in
 * without ever loading all N people at once. Widening (rather than re-anchoring on a foreign
 * id) always keeps the root inside its own window, so the server never has to reject the read,
 * and the loaded region grows outward from the reader's own line. Idempotent while a fetch is
 * in flight (guarded by `state.expanding`) and a no-op once the window reaches the server's
 * maximum depth (a widen that comes back the same generations means we are already at the cap).
 */
async function expandWindow(): Promise<void> {
  if (state.root === null || state.expanding) return;
  const next = state.windowGenerations + DEFAULT_GENERATIONS;
  state.expanding = true;
  try {
    const graph = await api.graphAround(state.root, next, state.side);
    const before = state.windowGenerations;
    mergeGraph(graph);
    state.windowGenerations = graph.Window?.generations ?? next;
    layoutCache = null; // the merged graph changes the layout; let it recompute
    // If the server clamped us to the same depth we already had, we are at the cap: stop
    // asking. `atWindowCap` short-circuits the render-time trigger below.
    atWindowCap = state.windowGenerations <= before;
  } catch {
    /* a failed widen leaves the reader on what is already loaded rather than erroring out */
  } finally {
    state.expanding = false;
    render();
  }
}

/** True once widening stops revealing new depth — the loaded window covers the whole tree. */
let atWindowCap = false;
/** The focus id the last auto-widen was triggered for, so a single edge does not loop. */
let lastEdgeFocus: number | null = null;

/**
 * When the reader has moved to the edge of the loaded window, widen it in the background.
 *
 * The edge is a focused/selected person who exists in the loaded graph but sits at its
 * frontier — a person with no loaded children who is not known to be a genuine leaf. Widening
 * around the root reveals their real neighbours if there are any; if there are none the widen
 * is cheap and idempotent, and `atWindowCap`/`lastEdgeFocus` stop it from firing again for the
 * same spot. Read-only side effects only: it never blocks a render.
 */
function maybeExpandForFocus(): void {
  if (atWindowCap || state.expanding || state.root === null) return;
  const id = state.focus ?? state.selected;
  if (id === null || id === lastEdgeFocus) return;
  const p = person(id);
  if (!p) return;
  // A frontier person: loaded, but with no loaded children — widening may reveal descendants
  // the current window stopped short of. (A true leaf simply yields no new people.)
  if (childrenOf(id).length === 0) {
    lastEdgeFocus = id;
    void expandWindow();
  }
}

/* ── the scalable view-all canvas ──────────────────────────────────────────── */
/**
 * The whole-tree layout is computed once per graph load and reused across every shell
 * re-render; only the culled window is ever mounted. The canvas controller is recreated when
 * the shell re-renders (a full innerHTML swap discards its host), but its pan/zoom is carried
 * across in `canvasViewState`, so selecting a person does not throw the reader back to centre.
 */
let layoutCache: Layout | null = null;
let canvas: CanvasController | null = null;
let canvasViewState: CanvasViewState | null = null;

function ensureLayout(): Layout {
  if (!layoutCache && state.graph) {
    layoutCache = computeLayout(state.graph, graphIndex());
  }
  return layoutCache!;
}

function disposeCanvas(): void {
  if (canvas) {
    canvasViewState = canvas.viewState();
    canvas.destroy();
    canvas = null;
  }
}

/** After the shell is in the DOM, wire the culling canvas into the view-all host. */
function mountTreeCanvas(): void {
  disposeCanvas();
  if (state.view !== 'all' || !state.graph) return;
  const host = root.querySelector<HTMLElement>('[data-tree-all]');
  if (!host) return;
  canvas = mountCanvas(host, ensureLayout(), (node) => renderCanvasNode(node.id), canvasViewState);
}

/* ── shell ─────────────────────────────────────────────────────────────────── */
/**
 * The line of descent currently on the canvas, oldest first. Built from the person in focus
 * so descending into an uncle's branch still shows where you are.
 */
function spineSection(): string {
  const id = focusId();
  if (id === null) return '';
  const steps = lineageSpine(id);
  if (steps.length === 0) return '';

  return `
    <div class="rail-sec">
      <p class="lbl">This line</p>
      <div class="spine">
        ${steps
          .map((stepId, i) => {
            const p = person(stepId);
            if (!p) return '';
            const kin = p.relationships[0];
            const here = stepId === id;
            const you = stepId === state.root;
            return `<button class="spine-step${here ? ' is-here' : ''}${you ? ' is-you' : ''}"
                            data-focus="${stepId}">
                      <span class="sp-i">${i + 1}</span>
                      <span class="sp-n">${escape(p.given || p.name)}</span>
                      <span class="sp-k">${escape(kin?.te ?? '')}</span>
                    </button>`;
          })
          .join('')}
      </div>
      <div class="hint">Showing the children of
        <strong>${escape(person(id)?.given ?? '')}</strong>. Tap a step to move the subject.</div>
    </div>`;
}

function leftRail(): string {
  const rootPerson = state.root === null ? undefined : person(state.root);
  const counts = state.graph?.Counts;
  return `
    <div class="rail-in">
      <div class="rail-sec">
        <p class="lbl">Kinship measured from</p>
        <div class="rootcard">
          <div class="nm">${escape(rootPerson?.name ?? '—')}</div>
          <div class="sub">${state.graph ? loadedSummary() : ''}</div>
        </div>
      </div>

      <div class="rail-sec">
        <button class="btn is-primary is-block" data-addperson>Add a person</button>
      </div>

      ${state.view === 'lineage' ? spineSection() : ''}

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
          <button class="btn is-ghost" data-export="gedzip">GEDZIP <small>with media</small></button>
          <button class="btn is-ghost" data-export="gedcom551">GEDCOM 5.5.1 <small>older tools</small></button>
          <button class="btn is-ghost" data-export="gedcom7">GEDCOM 7 <small>copy</small></button>
        </div>

        <div class="importer">
          <p class="lbl" style="margin-top:16px">Import</p>
          <input type="file" id="ged-file" accept=".ged,.gedcom,.gdz"
                 aria-label="GEDCOM file to import" />
          <div class="seg vseg" style="margin-top:8px">
            <button data-importmode="add" aria-pressed="${!state.importReplace}">Add to tree</button>
            <button data-importmode="replace" aria-pressed="${state.importReplace}">Replace tree</button>
          </div>
          <div class="hint">${state.importReplace
            ? 'Every person now in the tree is removed first. Your recorded words and pins are kept.'
            : 'Everyone in the file is added alongside the people already here.'}</div>
          <button class="btn" style="width:100%; margin-top:9px" data-doimport>Import file</button>
        </div>
        ${state.notice ? `<div class="notice">${escape(state.notice)}</div>` : ''}
      </div>

      <div class="rail-sec">
        <p class="lbl">Key</p>
        <div class="key"><i></i> Descent</div>
        <div class="key"><i class="is-adopt"></i> Adoptive descent</div>
        <div class="key"><i class="union"></i> Union</div>
        <div class="key"><span class="unres">అ / అ</span> Telugu label needs a fact</div>
      </div>
    </div>`;
}

/**
 * The header count. When the whole tree is loaded it reads "N people · U unions" as before;
 * while a window is loaded and more of the tree exists off-screen it reads "N of M people
 * loaded", so the reader knows the view is a window and that panning fetches more. The loaded
 * count is the ACCUMULATED people in the merged graph (which grows as windows fold in), not
 * the last payload's own count; the total comes from Counts.totalPeople.
 */
function loadedSummary(): string {
  const g = state.graph;
  if (!g) return '';
  const loaded = g.People.length;
  const total = g.Counts.totalPeople;
  if (loaded < total) return `${loaded} of ${total} people loaded`;
  return `${loaded} people · ${g.Unions.length} unions`;
}

function topBar(): string {
  const shown = state.searchResults.slice(0, SEARCH_SHOWN);
  const more = state.searchResults.length > SEARCH_SHOWN;
  const query = state.search.trim();
  let results = '';
  if (state.searchResults.length > 0) {
    results = `<div class="results">${shown
      .map(
        (r) => `<button data-goto="${r.ID}">${escape(r.Firstname)} ${escape(
          r.Lastname ?? '',
        )}</button>`,
      )
      .join('')}${more ? `<div class="more">Showing ${SEARCH_SHOWN} — refine to narrow.</div>` : ''}</div>`;
  } else if (query.length >= 2) {
    // A typed query that found nobody says so, rather than showing an empty dropdown.
    results = `<div class="results"><div class="empty">No one in the tree matches
      &ldquo;${escape(query)}&rdquo;. Try the other script, or a shorter part of the name.</div></div>`;
  }
  return `
    <header class="top">
      <div class="brand">
        <svg class="brand-mark" width="21" height="21" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <path class="bm-1" d="M12 21V11" stroke-width="1.7" stroke-linecap="round"/>
          <path class="bm-1" d="M12 11C12 6.5 8.5 3.5 4.5 3.5c0 4.5 3 7.5 7.5 7.5Z" stroke-width="1.7" stroke-linejoin="round"/>
          <path class="bm-2" d="M12 14c0-3.6 2.8-6 6-6 0 3.6-2.4 6-6 6Z" stroke-width="1.7" stroke-linejoin="round"/>
        </svg>
        <span>Family Tree</span>
      </div>
      <div class="searchbox">
        <input id="search" value="${escape(state.search)}"
               placeholder="Search names in either script — Varma, వర్మ" aria-label="Search people" />
        ${results}
      </div>
      <div class="seg">
        <button data-view="lineage" aria-pressed="${state.view === 'lineage'}">Lineage</button>
        <button data-view="all" aria-pressed="${state.view === 'all'}">View all</button>
      </div>
      <div class="seg">
        <button data-lang="en" aria-pressed="${state.lang === 'en'}">English</button>
        <button class="te" data-lang="te" aria-pressed="${state.lang === 'te'}">తెలుగు</button>
        <button data-lang="both" aria-pressed="${state.lang === 'both'}">Both</button>
      </div>
      <span class="spacer"></span>
      <span class="counts">${loadedSummary()}</span>
    </header>`;
}

/** Results shown in the typeahead before the "refine to narrow" affordance. */
const SEARCH_SHOWN = 8;

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
          Already have a GEDCOM file? Create the tree first, then import it from the left rail.
        </p>
      </div>
    </div>`;
}

function render(): void {
  if (!state.token) {
    disposeCanvas();
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
    disposeCanvas();
    root.innerHTML = firstRun();
    return;
  }

  if (state.loading && !state.graph) {
    disposeCanvas();
    root.innerHTML = '<div class="state"><p>Loading the tree…</p></div>';
    return;
  }
  if (state.error && !state.graph) {
    disposeCanvas();
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
    </div>
    ${state.editor ? renderPersonForm(state.editor) : ''}`;

  if (state.view === 'lineage') {
    // The bounded lineage canvas: transform pan + measured connectors.
    applyPan(root);
    drawWires(root);
  } else {
    // The scalable view-all canvas: culling controller mounted into its host.
    mountTreeCanvas();
  }

  if (state.editor) {
    const first = root.querySelector<HTMLInputElement>('.sheet [data-df="given"]');
    if (first && document.activeElement === document.body) first.focus();
  }

  // If the reader has reached the edge of the loaded window, widen it in the background. This
  // runs AFTER the DOM is in place so the current view paints immediately from what is loaded;
  // the widen, when it lands, re-renders with the newly-arrived people merged in.
  maybeExpandForFocus();
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

// Lineage-only: connectors are measured from the live DOM, so re-measure on resize.
window.addEventListener('resize', () => {
  if (state.view === 'lineage') drawWires(root);
});

installEvents({ root, render, reload, guard, setToken });
installLineagePan(root);

/* ── boot ──────────────────────────────────────────────────────────────────── */
state.token = loadToken();
if (state.token) setToken(state.token);
render();
if (state.token) void reload();

// Re-export nothing; this module is the entry point.
