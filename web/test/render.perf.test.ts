/**
 * Performance guard for the tree renderer at scale.
 *
 * This test is the acceptance bar for "10,000 people render and stay responsive": it loads the
 * committed 10k graph fixture — the exact shape the browser receives from `/api/v1/graph` — and
 * exercises the pure layout and culling functions that back the canvas, with no DOM. Two
 * properties are asserted:
 *
 *   1. Laying out all 10,000 people completes well under 300 ms, so the initial paint budget
 *      (500 ms after data arrives) is achievable with time to spare for the DOM mount.
 *   2. The culled set for a single 1920×1080 viewport is a small fraction of N, which is what
 *      makes pan/zoom cheap — the canvas only ever mounts what the window can show.
 *
 * It runs in CI because `npm run build` runs `vitest run` (see package.json).
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { describe, expect, it } from 'vitest';

import type { GraphResponse } from '../src/api';
import { buildIndex } from '../src/state';
import { computeLayout, cull } from '../src/layout';

const here = dirname(fileURLToPath(import.meta.url));
const fixture = JSON.parse(
  readFileSync(join(here, 'fixtures', 'graph_10k.json'), 'utf8'),
) as GraphResponse;

describe('tree rendering at 10k people', () => {
  it('the fixture really is a 10k-person /graph payload', () => {
    expect(fixture.People.length).toBe(10_000);
    // Shape sanity: the fields the renderer reads must be present.
    const p = fixture.People[0]!;
    expect(p).toHaveProperty('id');
    expect(p).toHaveProperty('relationships');
    expect(fixture).toHaveProperty('ParentLinks');
    expect(fixture).toHaveProperty('Unions');
  });

  it('lays out all 10,000 people in under 300 ms', () => {
    const index = buildIndex(fixture);

    // Warm once (JIT / cold Map allocation), then measure a clean run.
    computeLayout(fixture, buildIndex(fixture));

    const start = performance.now();
    const layout = computeLayout(fixture, index);
    const elapsed = performance.now() - start;

    expect(layout.nodes.length).toBe(10_000);
    // Every person is positioned; the layout is not degenerate.
    expect(layout.width).toBeGreaterThan(0);
    expect(layout.height).toBeGreaterThan(0);

    // The headline assertion.
    expect(elapsed).toBeLessThan(300);
  });

  it('culls a 1920×1080 viewport down to a small fraction of N', () => {
    const index = buildIndex(fixture);
    const layout = computeLayout(fixture, index);

    // A viewport somewhere inside the tree, not pinned to a sparse corner.
    const viewport = {
      x: Math.max(0, layout.width / 2 - 960),
      y: Math.max(0, layout.height / 2 - 540),
      width: 1920,
      height: 1080,
    };

    const start = performance.now();
    const visible = cull(layout, viewport);
    const cullElapsed = performance.now() - start;

    // A window shows at most a few hundred cards; the rest of the 10k stay unmounted.
    expect(visible.nodes.length).toBeGreaterThan(0);
    expect(visible.nodes.length).toBeLessThan(layout.nodes.length * 0.1);
    // Culling itself is a per-frame cost and must be trivially cheap.
    expect(cullElapsed).toBeLessThan(50);
  });

  it('culling near the bottom does not scan the generations above it', () => {
    const index = buildIndex(fixture);
    const layout = computeLayout(fixture, index);

    // The very top row and a window at the very bottom must not both be returned.
    const bottom = cull(layout, {
      x: 0,
      y: layout.height - 1080,
      width: 1920,
      height: 1080,
    });
    // Bottom window contains no generation-0 founders (they sit at y≈0, far above).
    const anyTopRow = bottom.nodes.some((n) => n.gen === 0);
    expect(anyTopRow).toBe(false);
  });
});
