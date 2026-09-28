/**
 * The windowed-load client behaviour (item E).
 *
 * The tree view no longer loads the whole tree: it loads a window around the root and, as the
 * reader reaches the window's edge, fetches a wider window and MERGES it into the Map-indexed
 * state rather than replacing it. These tests exercise the two pure pieces of that:
 *
 *   1. `mergeGraph` folds a new window into the accumulated graph — people unioned by id
 *      (incoming wins, so a re-labelled person updates), parent links by (child,parent),
 *      unions by unordered pair — and the derived indexes reflect the union of both.
 *   2. The `api.graphAround` / `api.people` helpers build the query strings the server expects.
 *
 * No DOM and no network: `mergeGraph` is pure over module state, and the api helpers are
 * checked by stubbing `fetch` and reading the URL they call.
 */
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { GraphResponse, PersonNode } from '../src/api';
import { api, setToken } from '../src/api';
import { childrenOf, mergeGraph, parentsOf, person, setGraph, spouseOf, state } from '../src/state';

function node(id: number, given = `P${id}`): PersonNode {
  return {
    id, given, surname: 'Varma', name: `${given} Varma`, sex: 'male',
    birthYear: 1950 + id, deathYear: null,
    birth: { mode: 'year', year: 1950 + id, month: null, day: null, year2: null,
             reads: String(1950 + id), gedcom: String(1950 + id) },
    death: { mode: 'unknown', year: null, month: null, day: null, year2: null,
             reads: 'not recorded', gedcom: '' },
    living: null, relationships: [], seniorityQuestion: null,
  };
}

function graph(people: PersonNode[], parentLinks: { child: number; parent: number }[] = [],
               unions: { a: number; b: number }[] = [],
               counts?: Partial<GraphResponse['Counts']>): GraphResponse {
  return {
    Message: 'ok', Root: people[0]?.id ?? null, Side: 'paternal',
    People: people,
    ParentLinks: parentLinks.map((l) => ({ ...l, role: 'biological' as const })),
    Unions: unions,
    Window: { around: people[0]?.id ?? 0, generations: 3 },
    Counts: {
      people: people.length, unions: unions.length, openBirthOrderQuestions: 0,
      truncated: false, totalPeople: people.length, ...counts,
    },
  };
}

describe('mergeGraph', () => {
  it('unions people from both windows and indexes them', () => {
    setGraph(graph([node(1), node(2)], [{ child: 2, parent: 1 }]));
    mergeGraph(graph([node(2), node(3)], [{ child: 3, parent: 2 }]));

    // All three people are present after the merge.
    expect(person(1)).toBeDefined();
    expect(person(2)).toBeDefined();
    expect(person(3)).toBeDefined();
    // Both parent links survived and the children index reflects the union.
    expect(childrenOf(1)).toContain(2);
    expect(childrenOf(2)).toContain(3);
    expect(parentsOf(3)).toContain(2);
  });

  it('does not duplicate a person, link, or union present in both windows', () => {
    setGraph(graph([node(1), node(2)], [{ child: 2, parent: 1 }], [{ a: 1, b: 2 }]));
    mergeGraph(graph([node(2), node(1)], [{ child: 2, parent: 1 }], [{ a: 2, b: 1 }]));

    expect(state.graph!.People.filter((p) => p.id === 1)).toHaveLength(1);
    expect(state.graph!.ParentLinks.filter((l) => l.child === 2 && l.parent === 1)).toHaveLength(1);
    expect(state.graph!.Unions).toHaveLength(1);
    // spouseOf still resolves once, not twice.
    expect(spouseOf(1)).toBe(2);
  });

  it('lets the incoming copy of a person win, so a re-anchored window relabels them', () => {
    const stale = node(2, 'Stale');
    const fresh = node(2, 'Fresh');
    setGraph(graph([node(1), stale]));
    mergeGraph(graph([fresh]));
    expect(person(2)!.given).toBe('Fresh');
  });

  it('takes Counts (loaded-of-total) from the incoming payload', () => {
    setGraph(graph([node(1)], [], [], { totalPeople: 10 }));
    mergeGraph(graph([node(2), node(3)], [], [], { totalPeople: 10 }));
    // Accumulated people = 3, total tree = 10.
    expect(state.graph!.People).toHaveLength(3);
    expect(state.graph!.Counts.totalPeople).toBe(10);
  });

  it('sets the graph when merging into an empty accumulator', () => {
    setGraph(null);
    mergeGraph(graph([node(1), node(2)]));
    expect(person(1)).toBeDefined();
    expect(person(2)).toBeDefined();
  });
});

describe('api windowed helpers build the right URLs', () => {
  afterEach(() => vi.restoreAllMocks());

  function stubFetch(): () => string {
    let calledUrl = '';
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      calledUrl = url;
      return {
        ok: true,
        json: async () => ({ Message: 'ok', People: [], ParentLinks: [], Unions: [],
                             Window: null, Root: null, Side: 'paternal',
                             Counts: { people: 0, unions: 0, openBirthOrderQuestions: 0,
                                       truncated: false, totalPeople: 0 },
                             NextCursor: null, Total: 0 }),
      } as unknown as Response;
    }));
    return () => calledUrl;
  }

  it('graphAround passes around, generations and side', async () => {
    setToken('t');
    const url = stubFetch();
    await api.graphAround(42, 3, 'maternal');
    expect(url()).toContain('/api/v1/graph?');
    expect(url()).toContain('around=42');
    expect(url()).toContain('generations=3');
    expect(url()).toContain('side=maternal');
  });

  it('graphAround includes root when given', async () => {
    setToken('t');
    const url = stubFetch();
    await api.graphAround(42, 2, 'paternal', 7);
    expect(url()).toContain('root=7');
  });

  it('people passes limit, cursor and q', async () => {
    setToken('t');
    const url = stubFetch();
    await api.people('CURSOR123', 50, 'Var');
    expect(url()).toContain('/api/v1/people?');
    expect(url()).toContain('limit=50');
    expect(url()).toContain('cursor=CURSOR123');
    expect(url()).toContain('q=Var');
  });

  it('people omits cursor and q when not supplied', async () => {
    setToken('t');
    const url = stubFetch();
    await api.people(null, 200);
    expect(url()).toContain('limit=200');
    expect(url()).not.toContain('cursor=');
    expect(url()).not.toContain('q=');
  });
});
