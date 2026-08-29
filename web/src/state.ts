import type { GraphResponse, PersonNode, Side, TreeInfo } from './api';
import type { PersonDraft } from './views/personform';

export type Lang = 'en' | 'te' | 'both';
export type View = 'lineage' | 'all';

export interface AppState {
  token: string;
  tree: TreeInfo | null;
  /** True once we know whether a tree exists, so the first run is not shown by mistake. */
  treeChecked: boolean;
  notice: string | null;
  graph: GraphResponse | null;
  loading: boolean;
  error: string | null;
  root: number | null;
  selected: number | null;
  side: Side;
  lang: Lang;
  /** Lineage is the default: one line of descent, explored a generation at a time. */
  view: View;
  /** Whose children the lineage view is showing. Null until the graph loads. */
  focus: number | null;
  /** Branches the reader has opened. Only used by the view-all mode. */
  open: Set<number>;
  addingWord: boolean;
  /** The add/edit sheet, or null when it is closed. */
  editor: PersonDraft | null;
  search: string;
  searchResults: { ID: number; Firstname: string; Lastname?: string }[];
}

export const state: AppState = {
  token: '',
  tree: null,
  treeChecked: false,
  notice: null,
  graph: null,
  loading: false,
  error: null,
  root: null,
  selected: null,
  side: 'paternal',
  lang: 'both',
  view: 'lineage',
  focus: null,
  open: new Set(),
  addingWord: false,
  editor: null,
  search: '',
  searchResults: [],
};

/* ── reading the graph ─────────────────────────────────────────────────────── */
export function person(id: number): PersonNode | undefined {
  return state.graph?.People.find((p) => p.id === id);
}

export function parentsOf(id: number, birthsOnly = true): number[] {
  return (state.graph?.ParentLinks ?? [])
    .filter((l) => l.child === id && (!birthsOnly || l.role === 'biological'))
    .map((l) => l.parent);
}

export function isAdoptedInto(id: number): boolean {
  return (state.graph?.ParentLinks ?? []).some((l) => l.child === id && l.role !== 'biological');
}

export function childrenOf(id: number): number[] {
  const ids = (state.graph?.ParentLinks ?? [])
    .filter((l) => l.parent === id)
    .map((l) => l.child);
  const unique = [...new Set(ids)];
  // Unknown birth years sort last in a stable order, rather than by a number that
  // does not exist.
  return unique.sort((a, b) => {
    const ya = person(a)?.birthYear ?? null;
    const yb = person(b)?.birthYear ?? null;
    if (ya === null && yb === null) return a - b;
    if (ya === null) return 1;
    if (yb === null) return -1;
    return ya - yb;
  });
}

export function spouseOf(id: number): number | undefined {
  const union = (state.graph?.Unions ?? []).find((u) => u.a === id || u.b === id);
  if (!union) return undefined;
  return union.a === id ? union.b : union.a;
}

export interface Frame {
  top: number[];
  branchIds: number[];
}

/**
 * The tree restructures around whoever kinship is measured from: the reader's own parental
 * line sits in the middle, their aunts and uncles beside it, and their grandparents above.
 */
export function frame(root: number): Frame {
  const parents = parentsOf(root);
  const anchor = parents.find((id) => person(id)?.sex === 'male') ?? parents[0] ?? root;
  const grandparents = parentsOf(anchor);
  if (grandparents.length === 0) return { top: [], branchIds: [anchor] };

  const grandfather =
    grandparents.find((id) => person(id)?.sex === 'male') ?? grandparents[0]!;
  const grandmother = grandparents.find((id) => id !== grandfather);
  const branchIds = childrenOf(grandfather);
  return {
    top: grandmother === undefined ? [grandfather] : [grandfather, grandmother],
    branchIds: branchIds.length > 0 ? branchIds : [anchor],
  };
}

/** Is this branch the reader's own parental line? Those always show their spouse. */
export function onRootLine(branchId: number): boolean {
  if (state.root === null) return false;
  return branchId === state.root || parentsOf(state.root).includes(branchId);
}

export function label(p: PersonNode): string {
  const first = p.relationships[0];
  if (!first) return '';
  if (state.lang === 'te') return first.te;
  if (state.lang === 'both') return `${first.en} · ${first.te}`;
  return first.en;
}

export function years(p: PersonNode): string {
  if (p.birthYear === null) return 'birth year not recorded';
  return p.deathYear === null ? `b. ${p.birthYear}` : `${p.birthYear}–${p.deathYear}`;
}


/* ── lineage ───────────────────────────────────────────────────────────────── */
/** Guard against a malformed graph sending an ancestor walk to the moon. */
const MAX_DEPTH = 40;

/**
 * The parent a line of descent is followed through.
 *
 * A tree can only draw one spine, so one parent has to be picked. Sex is the tiebreak
 * because that is how the families this is built for describe a line -- and it is only a
 * tiebreak: with one parent recorded, that parent is the line, whoever they are.
 */
export function anchorParent(id: number): number | undefined {
  const parents = parentsOf(id, false);
  if (parents.length === 0) return undefined;
  return parents.find((p) => person(p)?.sex === 'male') ?? parents[0];
}

/** Every ancestor up this person's line, oldest first, excluding them. */
export function ancestorsOf(id: number): number[] {
  const out: number[] = [];
  const seen = new Set<number>([id]);
  let current = anchorParent(id);
  while (current !== undefined && !seen.has(current) && out.length < MAX_DEPTH) {
    out.unshift(current);
    seen.add(current);
    current = anchorParent(current);
  }
  return out;
}

/**
 * The chain the left rail walks: the topmost ancestor down to the person in focus.
 *
 * Built from the focus rather than from the root, so descending into an uncle's branch
 * still shows where you are instead of stranding you off the reader's own line.
 */
export function lineageSpine(focusId: number): number[] {
  return [...ancestorsOf(focusId), focusId];
}

/**
 * Where the lineage view opens: the oldest recorded ancestor on the reader's own line.
 *
 * The brief is "if a grandfather is present, show their children" -- so the subject is the
 * furthest ancestor, and the generation on display is the one below them.
 */
export function defaultFocus(): number | null {
  if (state.root === null) return null;
  const line = ancestorsOf(state.root);
  return line[0] ?? state.root;
}

export function focusId(): number | null {
  return state.focus ?? defaultFocus();
}

/** Is this person on the reader's own descent line? Used to keep them findable. */
export function onOwnLine(id: number): boolean {
  if (state.root === null) return false;
  if (id === state.root) return true;
  return ancestorsOf(state.root).includes(id);
}
