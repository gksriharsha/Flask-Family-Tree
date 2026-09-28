/**
 * Descent and marriage connectors for the LINEAGE canvas, drawn by measuring where the cards
 * actually are.
 *
 * This is the bounded canvas — one generation on screen — so measuring the real DOM rects is
 * cheap and gives pixel-perfect joins that a percentage-based bar never could. (The scalable
 * view-all canvas does NOT use this; it draws from precomputed layout coordinates in
 * canvas.ts, because measuring ten thousand rects per frame is exactly what this file must not
 * be asked to do.)
 *
 * They used to be CSS pseudo-elements positioned at percentages, which overshot the outer
 * children by tens of pixels. Measuring is the only way the line meets the card it claims to
 * join. Descent is one curve per child rather than a bar with ticks; marriage is a double rule
 * in a warm neutral, so a union differs from a descent in colour as well as form.
 */
import { state } from '../state';

const DESCENT = '#8FAE66';
const UNION = '#B08A63';

export function drawWires(root: HTMLElement): void {
  const canvases = root.querySelectorAll<HTMLElement>('.canvas-in');
  for (const canvas of canvases) {
    const svg = canvas.querySelector('svg.wires');
    if (!svg || !state.graph) continue;

    const base = canvas.getBoundingClientRect();
    const nodes = new Map<number, DOMRect>();
    for (const el of canvas.querySelectorAll<HTMLElement>('[data-person]')) {
      const id = Number(el.dataset.person);
      if (!nodes.has(id)) nodes.set(id, el.getBoundingClientRect());
    }

    const parts: string[] = [];

    const pairKey = (a: number, b: number) => (a < b ? `${a}:${b}` : `${b}:${a}`);
    const married = new Set(state.graph.Unions.map((u) => pairKey(u.a, u.b)));

    const byChild = new Map<number, { parent: number; role: string }[]>();
    for (const link of state.graph.ParentLinks) {
      if (!nodes.has(link.parent) || !nodes.has(link.child)) continue;
      const list = byChild.get(link.child) ?? [];
      list.push({ parent: link.parent, role: link.role });
      byChild.set(link.child, list);
    }

    interface Origin { x: number; y: number; kids: { x: number; y: number; dashed: boolean }[] }
    const origins = new Map<string, Origin>();
    const at = (key: string, x: number, y: number) => {
      const found = origins.get(key) ?? { x, y, kids: [] };
      found.y = Math.max(found.y, y);
      origins.set(key, found);
      return found;
    };

    for (const [childId, links] of byChild) {
      const to = nodes.get(childId)!;
      const cx = to.left + to.width / 2 - base.left;
      const cy = to.top - base.top;
      const spent = new Set<number>();

      for (let i = 0; i < links.length; i++) {
        for (let j = i + 1; j < links.length; j++) {
          const a = links[i]!;
          const b = links[j]!;
          if (spent.has(a.parent) || spent.has(b.parent)) continue;
          if (!married.has(pairKey(a.parent, b.parent))) continue;
          const ra = nodes.get(a.parent)!;
          const rb = nodes.get(b.parent)!;
          const [l, r] = ra.left <= rb.left ? [ra, rb] : [rb, ra];
          at(pairKey(a.parent, b.parent), (l.right + r.left) / 2 - base.left,
             Math.max(l.bottom, r.bottom) - base.top)
            .kids.push({ x: cx, y: cy,
                         dashed: a.role !== 'biological' || b.role !== 'biological' });
          spent.add(a.parent);
          spent.add(b.parent);
        }
      }
      for (const link of links) {
        if (spent.has(link.parent)) continue;
        const from = nodes.get(link.parent)!;
        at(`p${link.parent}`, from.left + from.width / 2 - base.left, from.bottom - base.top)
          .kids.push({ x: cx, y: cy, dashed: link.role !== 'biological' });
      }
    }

    for (const origin of origins.values()) {
      const kids = origin.kids.filter((k) => k.y > origin.y + 6);
      if (kids.length === 0) continue;

      const bar = origin.y + (Math.min(...kids.map((k) => k.y)) - origin.y) / 2;
      const left = Math.min(origin.x, ...kids.map((k) => k.x));
      const right = Math.max(origin.x, ...kids.map((k) => k.x));

      const stroke = `stroke="${DESCENT}" stroke-width="1.1" stroke-linecap="square"`;
      parts.push(`<path d="M${origin.x} ${origin.y}V${bar}" fill="none" ${stroke} />`);
      if (right - left > 0.5) {
        parts.push(`<path d="M${left} ${bar}H${right}" fill="none" ${stroke} />`);
      }
      for (const kid of kids) {
        const dash = kid.dashed ? ' stroke-dasharray="4 3"' : '';
        parts.push(`<path d="M${kid.x} ${bar}V${kid.y}" fill="none" ${stroke}${dash} />`);
      }
      parts.push(`<circle cx="${origin.x}" cy="${origin.y}" r="2" fill="${DESCENT}" />`);
    }

    for (const union of state.graph.Unions) {
      const a = nodes.get(union.a);
      const b = nodes.get(union.b);
      if (!a || !b) continue;
      const [left, right] = a.left <= b.left ? [a, b] : [b, a];
      const gap = right.left - left.right;
      if (gap < 6 || gap > 80) continue;
      const x1 = left.right - base.left;
      const x2 = right.left - base.left;
      const y = (Math.max(left.top, right.top) + Math.min(left.bottom, right.bottom)) / 2
              - base.top;
      parts.push(`<path d="M${x1} ${y - 2.5}H${x2}M${x1} ${y + 2.5}H${x2}"`
               + ` stroke="${UNION}" stroke-width="1.1" stroke-linecap="round" />`);
    }

    svg.setAttribute('width', String(canvas.scrollWidth));
    svg.setAttribute('height', String(canvas.scrollHeight));
    svg.setAttribute('viewBox', `0 0 ${canvas.scrollWidth} ${canvas.scrollHeight}`);
    svg.innerHTML = parts.join('');
  }
}
