/**
 * Integration test for the view-all render path, without a DOM.
 *
 * The perf test proves layout and culling are fast; this proves they actually produce
 * something mountable. It walks the exact pipeline the canvas uses at runtime — load the graph
 * into the indexes with `setGraph`, lay it out, cull a viewport, then render each visible node
 * with `renderCanvasNode` (the same function the canvas passes each `LayoutNode`) — and checks
 * that real, escaped card markup comes out for real people. If a refactor breaks the wiring
 * between these modules, this fails even though each unit still compiles.
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { describe, expect, it } from 'vitest';

import type { GraphResponse } from '../src/api';
import { graphIndex, person, setGraph, state } from '../src/state';
import { computeLayout, cull } from '../src/layout';
import { renderCanvasNode } from '../src/views/tree';

const here = dirname(fileURLToPath(import.meta.url));
const fixture = JSON.parse(
  readFileSync(join(here, 'fixtures', 'graph_10k.json'), 'utf8'),
) as GraphResponse;

describe('view-all render pipeline', () => {
  it('renders every culled node to a card without a DOM', () => {
    setGraph(fixture);
    state.root = fixture.Root;
    state.view = 'all';

    const layout = computeLayout(fixture, graphIndex());
    const visible = cull(layout, {
      x: Math.max(0, layout.width / 2 - 960),
      y: 0,
      width: 1920,
      height: 1080,
    });

    expect(visible.nodes.length).toBeGreaterThan(0);

    for (const node of visible.nodes) {
      const html = renderCanvasNode(node.id);
      // A real person renders a card button carrying their id for click handling.
      expect(html).toContain('class="card');
      expect(html).toContain(`data-person="${node.id}"`);
      // The person the node points at really exists in the indexed graph.
      expect(person(node.id)).toBeDefined();
    }
  });

  it('escapes person names so a stray angle bracket cannot inject markup', () => {
    // Build a tiny graph with a hostile name and confirm it comes out escaped.
    const hostile: GraphResponse = {
      Message: 'x', Root: 1, Side: 'paternal',
      People: [{
        id: 1, given: '<script>', surname: '&"', name: '<script> &"', sex: 'male',
        birthYear: 1950, deathYear: null,
        birth: { mode: 'year', year: 1950, month: null, day: null, year2: null, reads: '1950', gedcom: '1950' },
        death: { mode: 'unknown', year: null, month: null, day: null, year2: null, reads: 'not recorded', gedcom: '' },
        living: null, relationships: [], seniorityQuestion: null,
      }],
      ParentLinks: [], Unions: [], Counts: { people: 1, unions: 0, openBirthOrderQuestions: 0 },
    };
    setGraph(hostile);
    state.root = 1;
    const html = renderCanvasNode(1);
    expect(html).not.toContain('<script>');
    expect(html).toContain('&lt;script&gt;');
  });
});
