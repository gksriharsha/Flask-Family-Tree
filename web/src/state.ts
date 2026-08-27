import type { GraphResponse, PersonNode, Side, TreeInfo } from './api';

export type Lang = 'en' | 'te' | 'both';

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
  /** Branches the reader has opened. The root's own line is always open. */
  open: Set<number>;
  addingWord: boolean;
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
  open: new Set(),
  addingWord: false,
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
