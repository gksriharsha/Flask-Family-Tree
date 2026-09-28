/**
 * Whole-tree layout and viewport culling — pure, DOM-free, and testable.
 *
 * The old canvas rendered a bounded slice (one lineage generation, or one view-all frame), so
 * it never had to think about scale. Making the tree show ten thousand people at once needs a
 * real layout: every person gets a position, but only the handful inside the viewport is ever
 * mounted. Both halves live here as pure functions over the graph indexes, with no reference
 * to the DOM, `window`, or module state — which is what lets `render.perf.test.ts` load the
 * 10k fixture and measure them headlessly.
 *
 * Layout is generation-bucketed: a person's row is their depth below the oldest ancestor on
 * their line, and within a row people are packed left to right, each married couple kept
 * adjacent. That is O(N) in time and memory and keeps the descent-chart reading of the design
 * (generations stacked top to bottom, unions side by side, children under their parents).
 *
 * Culling is the cheap part done every frame: given a viewport rectangle in layout
 * coordinates (already adjusted for pan/zoom by the caller) plus a margin, return only the
 * nodes and connectors that intersect it. Nodes are bucketed by row so a vertical range check
 * skips whole generations without touching their members.
 */
import type { GraphResponse } from './api';
import type { GraphIndex } from './state';

/** A laid-out person. Coordinates are in layout space (before pan/zoom). */
export interface LayoutNode {
  id: number;
  x: number;
  y: number;
  w: number;
  h: number;
  gen: number;
  /** The row index within its generation bucket, for fast culling. */
  row: number;
}

/** A connector between two laid-out points. `kind` picks descent vs union styling. */
export interface Connector {
  kind: 'descent' | 'union';
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  /** Descent connectors passing through a non-birth link are drawn dashed. */
  dashed: boolean;
}

export interface Layout {
  nodes: LayoutNode[];
  connectors: Connector[];
  /** Fast index for culling: node ids grouped by generation row, with each row's y-band. */
  rows: { gen: number; top: number; bottom: number; nodeIndexes: number[] }[];
  width: number;
  height: number;
}

export interface Viewport {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface CullResult {
  nodes: LayoutNode[];
  connectors: Connector[];
}

/* ── tunables — the visual grid the design's card sizes imply ──────────────── */
export const NODE_W = 168;
export const NODE_H = 64;
export const H_GAP = 28; // horizontal gap between people in a row
export const V_GAP = 96; // vertical gap between generation rows
export const COUPLE_GAP = 12; // gap between two spouses drawn side by side

/**
 * Assign every person a generation number.
 *
 * A person's generation is one below the deepest parent that has a generation; people with no
 * parents in the graph (founders, in-married spouses whose own line is absent) start at 0.
 * Computed with a Kahn-style longest-path pass so a person always sits below both parents even
 * when the two parents are themselves different depths, and cycles (a malformed graph) cannot
 * loop forever.
 */
export function assignGenerations(index: GraphIndex): Map<number, number> {
  const gen = new Map<number, number>();
  const { people, parentsByChild } = index;

  // Memoised longest path to a root, with cycle guarding via an in-progress set.
  const inProgress = new Set<number>();
  const depthOf = (id: number): number => {
    const cached = gen.get(id);
    if (cached !== undefined) return cached;
    if (inProgress.has(id)) return 0; // cycle: treat as a root to break the loop
    inProgress.add(id);
    const parents = parentsByChild.get(id);
    let d = 0;
    if (parents && parents.length > 0) {
      let max = -1;
      for (const { parent } of parents) {
        if (people.has(parent)) max = Math.max(max, depthOf(parent));
      }
      d = max + 1;
    }
    inProgress.delete(id);
    gen.set(id, d);
    return d;
  };

  for (const id of people.keys()) depthOf(id);
  return gen;
}

/**
 * Lay the whole graph out into a generation-bucketed grid.
 *
 * O(N): one pass to bucket people by generation, one pass per row to place them (couples kept
 * together), and one pass over parent links and unions to emit connectors between the points
 * just placed. Nothing here measures the DOM — positions come from the fixed grid constants.
 */
export function computeLayout(graph: GraphResponse, index: GraphIndex): Layout {
  const gen = assignGenerations(index);
  const { childrenByParent, spousesByPerson } = index;

  // Bucket ids by generation, each bucket in a stable order (by id) so layout is deterministic.
  const buckets = new Map<number, number[]>();
  let maxGen = 0;
  for (const [id, g] of gen) {
    (buckets.get(g) ?? buckets.set(g, []).get(g)!).push(id);
    if (g > maxGen) maxGen = g;
  }

  const pos = new Map<number, { x: number; y: number }>();
  const nodes: LayoutNode[] = [];
  const rows: Layout['rows'] = [];

  // First pass: place each generation left-aligned from x=0 and record its width. Couples are
  // kept adjacent. We defer committing coordinates until we know every row's width, so rows
  // can be centred on a common line in the second pass (a descent chart is a centred pyramid,
  // not a left ragged edge — and a centred layout makes a central viewport actually land on
  // content rather than past the end of the shorter rows).
  interface Placed { id: number; localX: number }
  const rowPlacements: { g: number; y: number; width: number; placed: Placed[] }[] = [];
  let maxRowWidth = 0;

  for (let g = 0; g <= maxGen; g++) {
    const ids = (buckets.get(g) ?? []).slice().sort((a, b) => a - b);
    const y = g * (NODE_H + V_GAP);
    let x = 0;
    const seen = new Set<number>();
    const placed: Placed[] = [];

    for (const id of ids) {
      if (seen.has(id)) continue;
      const spouse = spousesByPerson.get(id)?.find(
        (s) => !seen.has(s) && gen.get(s) === g,
      );
      placed.push({ id, localX: x });
      seen.add(id);
      x += NODE_W;
      if (spouse !== undefined) {
        x += COUPLE_GAP;
        placed.push({ id: spouse, localX: x });
        seen.add(spouse);
        x += NODE_W;
      }
      x += H_GAP;
    }

    const rowWidth = placed.length > 0 ? x - H_GAP : 0;
    if (rowWidth > maxRowWidth) maxRowWidth = rowWidth;
    rowPlacements.push({ g, y, width: rowWidth, placed });
  }

  // Second pass: commit centred coordinates.
  const width = maxRowWidth;
  for (const rp of rowPlacements) {
    const offset = (maxRowWidth - rp.width) / 2;
    const rowNodeIndexes: number[] = [];
    for (const { id, localX } of rp.placed) {
      const gx = offset + localX;
      pos.set(id, { x: gx, y: rp.y });
      const idx = nodes.length;
      nodes.push({ id, x: gx, y: rp.y, w: NODE_W, h: NODE_H, gen: rp.g, row: rp.g });
      rowNodeIndexes.push(idx);
    }
    if (rowNodeIndexes.length > 0) {
      rows.push({ gen: rp.g, top: rp.y, bottom: rp.y + NODE_H, nodeIndexes: rowNodeIndexes });
    }
  }

  const height = maxGen * (NODE_H + V_GAP) + NODE_H;

  // Connectors. A descent connector runs from the midpoint of a parent's bottom edge to the
  // midpoint of a child's top edge; a union connector runs between the facing edges of two
  // spouses on the same row. Only points that were actually placed produce a connector.
  const connectors: Connector[] = [];
  const centreBottom = (p: { x: number; y: number }) => ({ x: p.x + NODE_W / 2, y: p.y + NODE_H });
  const centreTop = (p: { x: number; y: number }) => ({ x: p.x + NODE_W / 2, y: p.y });

  for (const [parent, kids] of childrenByParent) {
    const pp = pos.get(parent);
    if (!pp) continue;
    const from = centreBottom(pp);
    const parentLinks = index.parentsByChild;
    for (const child of kids) {
      const cp = pos.get(child);
      if (!cp) continue;
      const to = centreTop(cp);
      const role = parentLinks.get(child)?.find((l) => l.parent === parent)?.role;
      connectors.push({
        kind: 'descent',
        x1: from.x, y1: from.y, x2: to.x, y2: to.y,
        dashed: role !== undefined && role !== 'biological',
      });
    }
  }

  for (const u of graph.Unions) {
    const a = pos.get(u.a);
    const b = pos.get(u.b);
    if (!a || !b) continue;
    // Only draw a union rule when the two are on the same row and side by side.
    if (a.y !== b.y) continue;
    const [l, r] = a.x <= b.x ? [a, b] : [b, a];
    connectors.push({
      kind: 'union',
      x1: l.x + NODE_W, y1: l.y + NODE_H / 2,
      x2: r.x, y2: r.y + NODE_H / 2,
      dashed: false,
    });
  }

  return { nodes, connectors, rows, width, height };
}

/**
 * The nodes and connectors that intersect the viewport (plus a margin).
 *
 * Rows are skipped wholesale by a y-band test, so a viewport near the bottom of a 10k tree
 * never iterates the generations above it. Connectors are filtered by a rectangle-overlap
 * test on their bounding box. Called every animation frame, so it allocates only the arrays
 * it returns and does no per-node work outside the visible band.
 */
export function cull(layout: Layout, viewport: Viewport, margin = 300): CullResult {
  const minX = viewport.x - margin;
  const minY = viewport.y - margin;
  const maxX = viewport.x + viewport.width + margin;
  const maxY = viewport.y + viewport.height + margin;

  const nodes: LayoutNode[] = [];
  for (const row of layout.rows) {
    if (row.bottom < minY || row.top > maxY) continue; // whole generation off-screen
    for (const idx of row.nodeIndexes) {
      const n = layout.nodes[idx]!;
      if (n.x + n.w < minX || n.x > maxX) continue;
      nodes.push(n);
    }
  }

  // A connector is mounted when EITHER endpoint falls inside the window. A descent line whose
  // parent and child both sit far outside the window can, geometrically, still cross a corner
  // of it, but at any usable zoom that is a sliver not worth an SVG node — and endpoint-based
  // culling is what keeps the mounted connector count proportional to the mounted node count
  // rather than to how wide the pyramid is. (A bounding-box test kept thousands of long
  // diagonals whose lines never actually enter the window.)
  const inWindow = (x: number, y: number) => x >= minX && x <= maxX && y >= minY && y <= maxY;
  const connectors: Connector[] = [];
  for (const c of layout.connectors) {
    if (inWindow(c.x1, c.y1) || inWindow(c.x2, c.y2)) connectors.push(c);
  }

  return { nodes, connectors };
}
