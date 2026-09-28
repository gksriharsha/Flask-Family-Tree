/**
 * The canvas, in two modes.
 *
 * **Lineage** is the default. One line of descent at a time: the person in focus sits alone
 * at the top, and the generation actually being read is the row of their children underneath.
 * A spouse is a small pill rather than a card, because a line of descent runs through blood
 * and the person who married in is context for it rather than a peer of it. Descending is a
 * deliberate click, so the canvas never fills with generations nobody asked for.
 *
 * **View all** puts every branch up at once. It is for orientation -- finding a branch,
 * spotting a gap -- not for reading a line, so it is opt-in.
 *
 * Both modes pan by dragging (wired in main.ts).
 */
import type { PersonNode } from '../api';
import {
  childrenOf,
  focusId,
  isAdoptedInto,
  label,
  onOwnLine,
  person,
  spouseOf,
  state,
  years,
} from '../state';
import { escapeHtml as escape } from '../dom';

function card(p: PersonNode, compact: boolean): string {
  const classes = ['card'];
  if (compact) classes.push('is-compact');
  if (p.id === state.selected) classes.push('is-sel');
  if (p.id === state.root) classes.push('is-focus');
  if (isAdoptedInto(p.id)) classes.push('is-adopt');
  if (state.view === 'all' && onOwnLine(p.id)) classes.push('is-ownline');

  const first = p.relationships[0];
  const chipOpen = state.lang !== 'en' && first?.unresolved ? ' is-open' : '';
  const multiple = p.relationships.length > 1 && p.id !== state.root;

  return `
    <button class="${classes.join(' ')}" data-person="${p.id}">
      ${p.id === state.root ? '<span class="rootpin">You</span>' : ''}
      ${isAdoptedInto(p.id) ? '<span class="chip-adopt">Adopted</span>' : ''}
      <span class="card-top">
        <span class="sym ${p.sex === 'female' ? 'female' : ''}"></span>
        <span>
          <span class="nm">${escape(p.name)}</span>
        </span>
      </span>
      <span class="yrs">${escape(years(p))}</span>
      <span class="kin${chipOpen}">${escape(label(p))}</span>
      ${multiple
        ? `<span class="links">${p.relationships.length} ways related to you</span>`
        : ''}
    </button>`;
}

/**
 * A spouse, drawn small.
 *
 * Deliberately not a card: in a lineage the line runs through one of the two, and giving
 * both equal weight is what makes a descent chart read as an undifferentiated mesh.
 */
function spousePill(id: number | undefined): string {
  if (id === undefined) return '';
  const p = person(id);
  if (!p) return '';
  const kin = p.relationships[0];
  return `
    <span class="knot"></span>
    <button class="spouse${p.id === state.selected ? ' is-sel' : ''}" data-person="${p.id}"
            title="${escape(p.name)}">
      <span class="sym ${p.sex === 'female' ? 'female' : ''}"></span>
      <span class="sp-txt">
        <span class="sp-nm">${escape(p.given || p.name)}</span>
        <span class="sp-kin">${escape(state.lang === 'en' ? (kin?.en ?? '') : (kin?.te ?? ''))}</span>
      </span>
    </button>`;
}

/* ── lineage ───────────────────────────────────────────────────────────────── */
function lineageChild(id: number): string {
  const p = person(id);
  if (!p) return '';
  const kids = childrenOf(id);
  const descend = kids.length > 0
    ? `<button class="descend" data-focus="${id}">
         ${kids.length} ${kids.length === 1 ? 'child' : 'children'}
         <svg width="11" height="11" viewBox="0 0 24 24" fill="none" aria-hidden="true">
           <path d="M6 9l6 6 6-6" stroke="currentColor" stroke-width="2.4"
                 stroke-linecap="round" stroke-linejoin="round"/>
         </svg>
       </button>`
    : '<span class="nokids">no children recorded</span>';

  return `
    <div class="lin-kid">
      <div class="couple">${card(p, false)}${spousePill(spouseOf(id))}</div>
      ${descend}
    </div>`;
}

/**
 * The tree exists but holds no one yet — a first-run state inside the shell, distinct from the
 * "where should this tree live?" screen. It names the next action in the ledger voice.
 */
function emptyTree(): string {
  return `
    <div class="state">
      <div>
        <h2>The tree is empty</h2>
        <p>No one has been recorded yet. Add the first person — yourself, or the oldest
           ancestor you know — and the rest of the family hangs from there.</p>
        <button class="btn is-primary" data-addperson>Add the first person</button>
      </div>
    </div>`;
}

function renderLineage(): string {
  const id = focusId();
  if (id === null) return emptyTree();
  const p = person(id);
  if (!p) return '<div class="state"><p>That person is no longer in the tree.</p></div>';

  const kids = childrenOf(id);

  const body = kids.length > 0
    ? `<div class="lin-row">
         ${kids.map((kid) => lineageChild(kid)).join('')}
       </div>`
    : `<div class="lin-leaf">
         No children recorded for ${escape(p.given || p.name)}. Step back up the line on the
         left, or add a relative.
       </div>`;

  return `
    <div class="canvas" data-pan role="application"
         aria-label="Family tree — drag to move, use the rails to navigate">
      <div class="canvas-in is-lineage">
        <svg class="wires" aria-hidden="true"></svg>
        <div class="lin-focus">
          <div class="couple">${card(p, false)}${spousePill(spouseOf(id))}</div>
        </div>
        ${body}
      </div>
      ${canvasChrome()}
    </div>`;
}

/* ── view all ──────────────────────────────────────────────────────────────── */
/** The pan hint + recentre button, used by the bounded lineage canvas. */
function canvasChrome(): string {
  return `
    <div class="panhint">
      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <path d="M5 9l-3 3 3 3M9 5l3-3 3 3M15 19l-3 3-3-3M19 9l3 3-3 3M2 12h20M12 2v20"
              stroke="currentColor" stroke-width="1.6" stroke-linecap="round"
              stroke-linejoin="round"/>
      </svg>
      Drag to move the tree
    </div>
    <button class="recentre" data-recentre>Recentre</button>`;
}

/**
 * View-all is now the SCALABLE canvas: it hosts every generation of the whole tree and mounts
 * only the people inside the viewport (see canvas.ts + layout.ts). The old frame — one
 * grandparent row plus the root's branches — did not scale past a few dozen people, so at ten
 * thousand it is replaced by the culling canvas. `renderAll` returns only the host element;
 * main.ts mounts the controller into it after the shell is in the DOM.
 */
function renderAll(): string {
  if (state.root === null) return emptyTree();
  if (!state.graph || state.graph.People.length === 0) {
    return emptyTree();
  }
  // The controller fills this host imperatively; the shell never re-renders its interior.
  return `<div class="gcanvas-host" data-tree-all></div>`;
}

/** One person as a canvas node — the same card, without the lineage-specific chrome. */
export function renderCanvasNode(id: number): string {
  const p = person(id);
  if (!p) return '';
  return card(p, true);
}

export function renderTree(): string {
  return state.view === 'lineage' ? renderLineage() : renderAll();
}
