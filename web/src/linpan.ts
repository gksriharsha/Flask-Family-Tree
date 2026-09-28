/**
 * Panning for the LINEAGE canvas — moving one bounded generation by translating its contents.
 *
 * Scrolling only works when the tree is bigger than the window; the lineage view shows one
 * generation, which fits, so a transform is used instead — it always has somewhere to go. The
 * offset is clamped so a corner of the tree always stays on screen.
 *
 * The scalable view-all canvas has its own pan/zoom in canvas.ts; this file is only for the
 * bounded lineage canvas, which is why it stays a simple translate with no culling.
 */
const DRAG_SLOP = 4;
const KEEP_VISIBLE = 150;

let suppressClick = false;
let panOffset = { x: 0, y: 0 };
let drag: { x: number; y: number; ox: number; oy: number; moved: boolean } | null = null;

export function applyPan(root: HTMLElement): void {
  const canvas = root.querySelector<HTMLElement>('.canvas');
  const inner = canvas?.querySelector<HTMLElement>('.canvas-in');
  if (!canvas || !inner) return;
  if (canvas.clientWidth === 0 || canvas.clientHeight === 0) return;

  const limit = (offset: number, content: number, view: number) => {
    const keep = Math.min(KEEP_VISIBLE, view / 2, content / 2);
    const lo = keep - content;
    const hi = view - keep;
    if (lo > hi) return (view - content) / 2;
    return Math.max(lo, Math.min(hi, offset));
  };
  panOffset.x = limit(panOffset.x, inner.offsetWidth, canvas.clientWidth);
  panOffset.y = limit(panOffset.y, inner.offsetHeight, canvas.clientHeight);
  inner.style.transform = `translate(${panOffset.x}px, ${panOffset.y}px)`;
}

/** Going somewhere new -- another view, another generation -- starts from centre again. */
export function resetPan(): void {
  panOffset = { x: 0, y: 0 };
}

/** Wire the lineage pan handlers to the shell root. Called once at boot. */
export function installLineagePan(root: HTMLElement): void {
  root.addEventListener('pointerdown', (event) => {
    if (event.button !== 0) return;
    if (!(event.target as HTMLElement | null)?.closest?.('[data-pan]')) return;
    // Only the lineage canvas uses this pan; the scalable canvas handles its own pointers.
    if (!(event.target as HTMLElement | null)?.closest?.('.canvas')) return;
    drag = { x: event.clientX, y: event.clientY, ox: panOffset.x, oy: panOffset.y, moved: false };
  });

  window.addEventListener('pointermove', (event) => {
    if (!drag) return;
    const dx = event.clientX - drag.x;
    const dy = event.clientY - drag.y;
    if (!drag.moved && Math.abs(dx) < DRAG_SLOP && Math.abs(dy) < DRAG_SLOP) return;
    if (!drag.moved) {
      drag.moved = true;
      root.querySelector('.canvas')?.classList.add('is-panning');
    }
    panOffset = { x: drag.ox + dx, y: drag.oy + dy };
    applyPan(root);
  });

  window.addEventListener('pointerup', () => {
    if (!drag) return;
    root.querySelector('.canvas')?.classList.remove('is-panning');
    if (drag.moved) {
      suppressClick = true;
      setTimeout(() => { suppressClick = false; }, 0);
    }
    drag = null;
  });

  root.addEventListener('wheel', (event) => {
    const target = event.target as HTMLElement | null;
    if (!target?.closest?.('[data-pan]')) return;
    if (!target?.closest?.('.canvas')) return;
    event.preventDefault();
    panOffset = { x: panOffset.x - event.deltaX, y: panOffset.y - event.deltaY };
    applyPan(root);
  }, { passive: false });

  window.addEventListener('resize', () => applyPan(root));

  root.addEventListener('click', (event) => {
    if (!suppressClick) return;
    suppressClick = false;
    event.stopPropagation();
    event.preventDefault();
  }, true);
}
