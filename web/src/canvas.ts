/**
 * The scalable canvas: pan, zoom, and mount only what the window shows.
 *
 * This is the runtime half of the layout work. `computeLayout` (in layout.ts) positions all N
 * people once; this controller owns the viewport over that layout and, on every pan or zoom,
 * asks `cull` for the small set inside the window and mounts *only that*. Ten thousand people
 * exist as layout coordinates but only the ~150 in view are ever DOM nodes.
 *
 * Two rules keep it at 60 fps:
 *
 *   1. Pointer/wheel handlers never touch the DOM directly — they update the pan/zoom numbers
 *      and request an animation frame. The actual re-cull and re-mount happen once per frame
 *      in `frame()`, so a burst of pointer events collapses into one render.
 *   2. The transform (translate + scale) is applied to a wrapper element, so panning within
 *      the currently-mounted margin is a pure compositor transform with no re-mount at all;
 *      a re-mount only happens when the window moves far enough to expose un-mounted nodes.
 *
 * The controller is deliberately ignorant of what a person looks like: the caller passes a
 * `renderNode` that turns a `LayoutNode` into card HTML, so the same machinery serves any
 * node styling without this file knowing about relationships, labels, or the DOM shape.
 */
import { type Connector, type Layout, type LayoutNode, cull } from './layout';

const DESCENT = '#8FAE66';
const UNION = '#B08A63';

const MIN_SCALE = 0.15;
const MAX_SCALE = 2.5;
const MOUNT_MARGIN = 400; // layout px of off-screen nodes kept mounted around the window

export interface CanvasController {
  /** Tear down listeners and observers. Call before discarding the canvas element. */
  destroy(): void;
  /** Re-read the container size and re-cull (e.g. after a layout swap). */
  invalidate(): void;
  /** The current pan/zoom, so it can be restored when the canvas is recreated. */
  viewState(): CanvasViewState;
}

/** Saveable pan/zoom, so a shell re-render can recreate the canvas without losing position. */
export interface CanvasViewState {
  scale: number;
  panX: number;
  panY: number;
}

/**
 * Mount a culling canvas into `container` for the given `layout`.
 *
 * `renderNode` returns the inner HTML for one node (positioned absolutely by the caller-set
 * `left`/`top`); the controller wraps it. `container` is expected to be the scroll/clip box.
 * `saved` restores a prior pan/zoom (from `viewState()`) instead of recentring.
 */
export function mountCanvas(
  container: HTMLElement,
  layout: Layout,
  renderNode: (node: LayoutNode) => string,
  saved?: CanvasViewState | null,
): CanvasController {
  container.classList.add('gcanvas');
  container.innerHTML = `
    <div class="gcanvas-vp" data-pan>
      <div class="gcanvas-world">
        <svg class="gcanvas-wires" aria-hidden="true"></svg>
        <div class="gcanvas-nodes"></div>
      </div>
      <div class="panhint">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <path d="M5 9l-3 3 3 3M9 5l3-3 3 3M15 19l-3 3-3-3M19 9l3 3-3 3M2 12h20M12 2v20"
                stroke="currentColor" stroke-width="1.6" stroke-linecap="round"
                stroke-linejoin="round"/>
        </svg>
        Drag to move · scroll to zoom
      </div>
      <button class="recentre" data-grecentre>Recentre</button>
    </div>`;

  const world = container.querySelector<HTMLElement>('.gcanvas-world')!;
  const svg = container.querySelector<SVGSVGElement>('.gcanvas-wires')! as unknown as SVGSVGElement;
  const nodesLayer = container.querySelector<HTMLElement>('.gcanvas-nodes')!;

  let scale = 1;
  let panX = 0;
  let panY = 0;
  // The window (in layout coords) the currently-mounted set was culled for. A re-mount only
  // happens when the live window leaves this box.
  let mounted: { minX: number; minY: number; maxX: number; maxY: number } | null = null;
  let rafPending = false;

  const viewportSize = () => ({
    w: container.clientWidth || 1,
    h: container.clientHeight || 1,
  });

  /** The layout-space rectangle currently visible, given pan/zoom. */
  const layoutWindow = () => {
    const { w, h } = viewportSize();
    return {
      x: -panX / scale,
      y: -panY / scale,
      width: w / scale,
      height: h / scale,
    };
  };

  const applyTransform = () => {
    world.style.transform = `translate(${panX}px, ${panY}px) scale(${scale})`;
  };

  const needsRemount = (win: { x: number; y: number; width: number; height: number }) => {
    if (!mounted) return true;
    return (
      win.x < mounted.minX ||
      win.y < mounted.minY ||
      win.x + win.width > mounted.maxX ||
      win.y + win.height > mounted.maxY
    );
  };

  const remount = (win: { x: number; y: number; width: number; height: number }) => {
    const visible = cull(layout, win, MOUNT_MARGIN);
    mountNodes(visible.nodes);
    mountWires(visible.connectors);
    mounted = {
      minX: win.x - MOUNT_MARGIN,
      minY: win.y - MOUNT_MARGIN,
      maxX: win.x + win.width + MOUNT_MARGIN,
      maxY: win.y + win.height + MOUNT_MARGIN,
    };
  };

  const mountNodes = (nodes: LayoutNode[]) => {
    const html: string[] = [];
    for (const n of nodes) {
      html.push(
        `<div class="gnode" style="left:${n.x}px;top:${n.y}px;width:${n.w}px;height:${n.h}px">`
        + renderNode(n)
        + `</div>`,
      );
    }
    nodesLayer.innerHTML = html.join('');
  };

  const mountWires = (connectors: Connector[]) => {
    const parts: string[] = [];
    for (const c of connectors) {
      if (c.kind === 'descent') {
        // An elbow: down from the parent, across, down to the child — the descent-chart shape.
        const midY = c.y1 + (c.y2 - c.y1) / 2;
        const dash = c.dashed ? ' stroke-dasharray="4 3"' : '';
        parts.push(
          `<path d="M${c.x1} ${c.y1}V${midY}H${c.x2}V${c.y2}" fill="none" stroke="${DESCENT}"`
          + ` stroke-width="1.1" stroke-linecap="square" stroke-linejoin="round"${dash} />`,
        );
      } else {
        parts.push(
          `<path d="M${c.x1} ${c.y1 - 2.5}H${c.x2}M${c.x1} ${c.y1 + 2.5}H${c.x2}"`
          + ` stroke="${UNION}" stroke-width="1.1" stroke-linecap="round" />`,
        );
      }
    }
    // The svg spans the whole world; viewBox equals the layout so paths use layout coords.
    svg.setAttribute('width', String(layout.width));
    svg.setAttribute('height', String(layout.height));
    svg.setAttribute('viewBox', `0 0 ${layout.width} ${layout.height}`);
    svg.innerHTML = parts.join('');
  };

  const frame = () => {
    rafPending = false;
    applyTransform();
    const win = layoutWindow();
    if (needsRemount(win)) remount(win);
  };

  const schedule = () => {
    if (rafPending) return;
    rafPending = true;
    requestAnimationFrame(frame);
  };

  /* ── centring ─────────────────────────────────────────────────────────────── */
  const recentre = () => {
    const { w } = viewportSize();
    // Fit the tree width to the viewport, capped so a huge tree is not shrunk to nothing.
    scale = Math.min(1, Math.max(MIN_SCALE, (w - 40) / Math.max(layout.width, 1)));
    panX = (w - layout.width * scale) / 2;
    panY = 24;
    mounted = null;
    schedule();
  };

  /* ── pan ──────────────────────────────────────────────────────────────────── */
  let drag: { x: number; y: number; ox: number; oy: number; moved: boolean } | null = null;

  const onPointerDown = (e: PointerEvent) => {
    if (e.button !== 0) return;
    if (!(e.target as HTMLElement | null)?.closest?.('[data-pan]')) return;
    drag = { x: e.clientX, y: e.clientY, ox: panX, oy: panY, moved: false };
  };
  const onPointerMove = (e: PointerEvent) => {
    if (!drag) return;
    const dx = e.clientX - drag.x;
    const dy = e.clientY - drag.y;
    if (!drag.moved && Math.abs(dx) < 4 && Math.abs(dy) < 4) return;
    drag.moved = true;
    container.classList.add('is-panning');
    panX = drag.ox + dx;
    panY = drag.oy + dy;
    schedule();
  };
  const onPointerUp = () => {
    if (!drag) return;
    container.classList.remove('is-panning');
    if (drag.moved) {
      suppressClick = true;
      setTimeout(() => { suppressClick = false; }, 0);
    }
    drag = null;
  };

  /* ── zoom (wheel / trackpad pinch) ──────────────────────────────────────────── */
  const onWheel = (e: WheelEvent) => {
    if (!(e.target as HTMLElement | null)?.closest?.('[data-pan]')) return;
    e.preventDefault();
    const rect = container.getBoundingClientRect();
    const px = e.clientX - rect.left;
    const py = e.clientY - rect.top;
    if (e.ctrlKey) {
      // Pinch-zoom (or ctrl+wheel): zoom toward the cursor.
      const next = Math.min(MAX_SCALE, Math.max(MIN_SCALE, scale * (1 - e.deltaY * 0.01)));
      // Keep the layout point under the cursor fixed across the scale change.
      const lx = (px - panX) / scale;
      const ly = (py - panY) / scale;
      scale = next;
      panX = px - lx * scale;
      panY = py - ly * scale;
    } else {
      panX -= e.deltaX;
      panY -= e.deltaY;
    }
    schedule();
  };

  /* ── a drag that ends over a card must not also click it ───────────────────── */
  let suppressClick = false;
  const onClickCapture = (e: MouseEvent) => {
    if (!suppressClick) return;
    suppressClick = false;
    e.stopPropagation();
    e.preventDefault();
  };

  const onRecentre = (e: MouseEvent) => {
    if ((e.target as HTMLElement | null)?.closest?.('[data-grecentre]')) recentre();
  };

  container.addEventListener('pointerdown', onPointerDown);
  window.addEventListener('pointermove', onPointerMove);
  window.addEventListener('pointerup', onPointerUp);
  container.addEventListener('wheel', onWheel, { passive: false });
  container.addEventListener('click', onClickCapture, true);
  container.addEventListener('click', onRecentre);

  const resize = new ResizeObserver(() => schedule());
  resize.observe(container);

  if (saved) {
    scale = saved.scale;
    panX = saved.panX;
    panY = saved.panY;
    mounted = null;
    schedule();
  } else {
    recentre();
  }

  return {
    destroy() {
      container.removeEventListener('pointerdown', onPointerDown);
      window.removeEventListener('pointermove', onPointerMove);
      window.removeEventListener('pointerup', onPointerUp);
      container.removeEventListener('wheel', onWheel);
      container.removeEventListener('click', onClickCapture, true);
      container.removeEventListener('click', onRecentre);
      resize.disconnect();
    },
    invalidate() {
      mounted = null;
      schedule();
    },
    viewState() {
      return { scale, panX, panY };
    },
  };
}
