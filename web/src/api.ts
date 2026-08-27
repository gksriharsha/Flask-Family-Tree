/**
 * Typed client for the family-tree API.
 *
 * Every relationship label, in both languages, is computed on the server — including which
 * word this branch of the family uses and any pin onto an individual. The browser renders
 * what it is given and never works out kinship itself, so the rules live in one place with
 * one test suite behind them.
 */

export type Sex = 'male' | 'female' | 'intersex' | 'unknown';
export type Side = 'paternal' | 'maternal';

export interface Alternative {
  term: string;
  roman: string;
  usage: string;
  added_by_family: boolean;
  base: string;
}

export interface Relationship {
  en: string;
  te: string;
  roman: string;
  gloss: string;
  unresolved: boolean;
  pinned: boolean;
  bases: string[];
  alternatives: Alternative[];
  adoptive: boolean;
  /** Set only when a person is related more than one way. */
  via: string | null;
  why: string;
  kind: string;
}

export interface SeniorityQuestion {
  a: number;
  b: number;
  aName: string;
  bName: string;
}

export interface PersonNode {
  id: number;
  given: string;
  surname: string;
  name: string;
  sex: Sex;
  birthYear: number | null;
  deathYear: number | null;
  relationships: Relationship[];
  seniorityQuestion: SeniorityQuestion | null;
}

export interface ParentLink {
  child: number;
  parent: number;
  role: 'biological' | 'adoptive' | 'step' | 'foster' | 'guardian';
}

export interface GraphResponse {
  Message: string;
  Root: number | null;
  Side: Side;
  People: PersonNode[];
  ParentLinks: ParentLink[];
  Unions: { a: number; b: number }[];
  Counts: { people: number; unions: number; openBirthOrderQuestions: number };
}

export class ApiError extends Error {
  constructor(readonly status: number, message: string) {
    super(message);
  }
}

/** Set once at boot. The token is the whole access model for now — see the day-one notes. */
let token = '';
export function setToken(value: string): void {
  token = value;
  try {
    localStorage.setItem('familytree.token', value);
  } catch {
    /* private windows and blocked storage are fine; the token just will not persist */
  }
}
export function loadToken(): string {
  try {
    return localStorage.getItem('familytree.token') ?? '';
  } catch {
    return '';
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (token) headers.set('X-API-Token', token);
  if (init.body) headers.set('Content-Type', 'application/json');

  const response = await fetch(path, { ...init, headers });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new ApiError(response.status, payload.Message ?? response.statusText);
  }
  return payload as T;
}

export interface TreeInfo {
  name: string;
  location: string;
  gedcom: string;
  exists?: boolean;
}

export type ExportFormat = 'gedcom7' | 'gedcom551' | 'gedzip';

export const api = {
  /** Where this tree keeps its files, or null if none has been created yet. */
  tree: () => request<{ Tree: TreeInfo | null }>('/api/v1/trees'),

  /** Create a tree and choose the folder its files live in. */
  createTree: (name: string, location: string) =>
    request<{ Tree: TreeInfo }>('/api/v1/trees', {
      method: 'POST',
      body: JSON.stringify({ name, location }),
    }),

  exportTree: (format: ExportFormat) =>
    request<{ Path: string; Format: string; Bytes: number }>('/api/v1/trees/export', {
      method: 'POST',
      body: JSON.stringify({ format }),
    }),

  importTree: (path: string) =>
    request<{ Result: { people: number; parentLinks: number; unions: number } }>(
      '/api/v1/trees/import',
      { method: 'POST', body: JSON.stringify({ path }) },
    ),

  /** Cheap token check, so a bad token gives a clear answer rather than a failed load. */
  session: () => request<{ Message: string }>('/api/v1/session'),

  graph: (root: number | null, side: Side) => {
    const params = new URLSearchParams({ side });
    if (root !== null) params.set('root', String(root));
    return request<GraphResponse>(`/api/v1/graph?${params}`);
  },

  search: (q: string) =>
    request<{ Data: { ID: number; Firstname: string; Lastname?: string }[] }>(
      `/api/v1/search?q=${encodeURIComponent(q)}`,
    ),

  /** Record which of two people was born first — the fact Telugu needs and dates rarely hold. */
  recordBirthOrder: (elderId: number, youngerId: number) =>
    request<{ Message: string }>('/api/v1/birth-order', {
      method: 'POST',
      body: JSON.stringify({ elder_id: elderId, younger_id: youngerId }),
    }),

  addWord: (baseTerm: string, term: string, roman: string, usage: string, side: Side) =>
    request<{ Message: string }>('/api/v1/vocabulary', {
      method: 'POST',
      body: JSON.stringify({ base_term: baseTerm, term, roman, usage, side }),
    }),

  pinTerm: (personId: number, baseTerm: string, term: string, roman: string, side: Side) =>
    request<{ Message: string }>(`/api/v1/people/${personId}/pinned-term`, {
      method: 'POST',
      body: JSON.stringify({ base_term: baseTerm, term, roman, side }),
    }),

  unpinTerm: (personId: number, baseTerm: string) =>
    request<{ Message: string }>(`/api/v1/people/${personId}/pinned-term`, {
      method: 'DELETE',
      body: JSON.stringify({ base_term: baseTerm }),
    }),
};
