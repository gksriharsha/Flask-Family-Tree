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
export type LinkRole = 'biological' | 'adoptive';

/**
 * The seven ways a date actually gets recorded. Every one of them is an interval underneath:
 * `about 1955` reaches a couple of years either side, `before 1962` is open at the far end,
 * and `unknown` is no interval at all. Two dates can only be ordered when their intervals do
 * not overlap, which is why the tree so often has to ask who was elder rather than work it out.
 */
export type DateMode = 'exact' | 'year' | 'about' | 'before' | 'after' | 'between' | 'unknown';

export interface DateValue {
  mode: DateMode;
  year: number | null;
  month: number | null;
  day: number | null;
  year2: number | null;
  /** How the record reads, composed on the server so both languages agree. */
  reads: string;
  gedcom: string;
}

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
  birth: DateValue;
  death: DateValue;
  living: boolean | null;
  relationships: Relationship[];
  seniorityQuestion: SeniorityQuestion | null;
}

/** What the add/edit form sends. Anything absent is left as it was. */
export interface PersonInput {
  given?: string;
  surname?: string;
  sex?: Sex;
  living?: boolean | null;
  birth?: Partial<DateValue> & { mode: DateMode };
  death?: Partial<DateValue> & { mode: DateMode };
  attachTo?: { personId: number; relation: 'parent' | 'child' | 'spouse'; role?: LinkRole };
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
  /** Present on a windowed read (?around=); null on a full read. */
  Window: { around: number; generations: number } | null;
  Counts: {
    people: number;
    unions: number;
    openBirthOrderQuestions: number;
    /** True when the payload is a subset of the tree (a full read past MAX_GRAPH_PEOPLE). */
    truncated: boolean;
    /** How many people the whole tree holds, regardless of how many this payload carries. */
    totalPeople: number;
  };
}

/** A person as the list surfaces receive them: person_json without computed relationships. */
export type ListPerson = Omit<PersonNode, 'relationships' | 'seniorityQuestion'>;

/** One page of the cursor-paginated /people list. `NextCursor` is null on the last page. */
export interface PeoplePage {
  People: ListPerson[];
  NextCursor: string | null;
  Total: number;
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
  // FormData sets its own Content-Type, boundary and all; overriding it breaks the upload.
  if (init.body && !(init.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json');
  }

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

export interface ImportSummary {
  people: number;
  parentLinks: number;
  unions: number;
  birthOrder: number;
  /** How many people the import removed first, when it replaced rather than added. */
  replaced: number;
  source?: string;
}

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

  /** Upload a .ged/.gedcom/.gdz. `replace` clears the existing people first. */
  importTree: (file: File, replace: boolean) => {
    const form = new FormData();
    form.append('file', file);
    form.append('mode', replace ? 'replace' : 'add');
    // No Content-Type here on purpose: the browser has to set the multipart boundary itself.
    return request<{ Result: ImportSummary }>('/api/v1/trees/import',
                                              { method: 'POST', body: form });
  },

  /** Cheap token check, so a bad token gives a clear answer rather than a failed load. */
  session: () => request<{ Message: string }>('/api/v1/session'),

  graph: (root: number | null, side: Side) => {
    const params = new URLSearchParams({ side });
    if (root !== null) params.set('root', String(root));
    return request<GraphResponse>(`/api/v1/graph?${params}`);
  },

  /**
   * A window of the tree around one person, labelled from `root` (default: `around`).
   *
   * Returns only the people within `generations` parent/child hops of `around`, plus their
   * spouses and the links among the included people. This is what the tree view loads instead
   * of the whole tree, so a 10k-person tree opens on the ~dozens of people in view rather than
   * labelling all N up front. Panning/expanding toward the window edge fetches a wider or
   * re-anchored window and merges it into the Map-indexed state.
   */
  graphAround: (around: number, generations: number, side: Side, root?: number) => {
    const params = new URLSearchParams({ side, around: String(around),
                                         generations: String(generations) });
    if (root !== undefined) params.set('root', String(root));
    return request<GraphResponse>(`/api/v1/graph?${params}`);
  },

  /**
   * One keyset page of people for the list surfaces (the "view all" list, pickers).
   *
   * Cursor pagination: pass the previous page's `NextCursor` to continue, `null`/omit to start.
   * `q` restricts to a name prefix. `limit` is capped server-side by MAX_PAGE_SIZE.
   */
  people: (cursor: string | null, limit: number, q?: string) => {
    const params = new URLSearchParams({ limit: String(limit) });
    if (cursor) params.set('cursor', cursor);
    if (q) params.set('q', q);
    return request<PeoplePage>(`/api/v1/people?${params}`);
  },

  search: (q: string) =>
    request<{ Data: { ID: number; Firstname: string; Lastname?: string }[] }>(
      `/api/v1/search?q=${encodeURIComponent(q)}`,
    ),

  /**
   * Every genuine relationship between two people, fetched on demand.
   *
   * The `/graph` payload carries `relationships` for every person today, so the client rarely
   * needs this. But a later item makes `/graph` windowed, and a person outside the window will
   * arrive without their relationships computed; the client then fetches them here for the one
   * person in focus rather than forcing the server to label all N up front. Keeps working
   * either way: when the payload already carried them, this is never called.
   */
  relationshipTo: (subject: number, other: number, side: Side) =>
    request<{
      Relationships: Relationship[];
      SeniorityQuestion: SeniorityQuestion | null;
    }>(`/api/v1/people/${subject}/relationship-to/${other}?side=${side}`),

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

  /** Add a person, optionally attaching them to somebody already in the tree. */
  addPerson: (input: PersonInput) =>
    request<{ Person: { id: number } }>('/api/v1/people', {
      method: 'POST',
      body: JSON.stringify(input),
    }),

  /** Change some of a person's details. Absent fields are left alone. */
  editPerson: (id: number, input: PersonInput) =>
    request<{ Person: { id: number } }>(`/api/v1/people/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(input),
    }),

  removePerson: (id: number) =>
    request<{ Message: string }>(`/api/v1/people/${id}`, { method: 'DELETE' }),

  linkParent: (childId: number, parentId: number, role: LinkRole = 'biological') =>
    request<{ Message: string }>('/api/v1/links', {
      method: 'POST',
      body: JSON.stringify({ type: 'parent', childId, parentId, role }),
    }),

  unlinkParent: (childId: number, parentId: number) =>
    request<{ Message: string }>('/api/v1/links', {
      method: 'DELETE',
      body: JSON.stringify({ type: 'parent', childId, parentId }),
    }),

  linkUnion: (aId: number, bId: number) =>
    request<{ Message: string }>('/api/v1/links', {
      method: 'POST',
      body: JSON.stringify({ type: 'union', aId, bId }),
    }),

  unlinkUnion: (aId: number, bId: number) =>
    request<{ Message: string }>('/api/v1/links', {
      method: 'DELETE',
      body: JSON.stringify({ type: 'union', aId, bId }),
    }),
};
