/**
 * All the shell's DOM event handlers, moved out of main.ts.
 *
 * One delegated click listener, one input listener (search debounce + form read-back), and a
 * keydown for Escape. Everything they need from the shell — the root element, the render and
 * reload functions, the error guard, and the editor helpers — arrives through `EventHooks`
 * rather than being closed over, which is what let this leave main.ts without dragging the
 * whole module with it.
 */
import type { ExportFormat } from './api';
import { api } from './api';
import { ensureRelationships } from './relationships';
import { person, state } from './state';
import { blankDraft, draftFrom } from './views/personform';
import { openEditor, refreshPreview, saveDraft, syncDraft } from './views/editor';
import { resetPan } from './linpan';

export interface EventHooks {
  root: HTMLElement;
  render: () => void;
  reload: () => Promise<void>;
  guard: (work: () => Promise<void>) => Promise<void>;
  setToken: (value: string) => void;
}

function closest(target: EventTarget | null, attr: string): HTMLElement | null {
  return (target as HTMLElement | null)?.closest?.(`[${attr}]`) ?? null;
}

/** Select a person and, when their relationships were not in the payload, fetch them. */
function selectPerson(id: number, render: () => void): void {
  state.selected = id;
  state.addingWord = false;
  ensureRelationships(id, render);
  render();
}

export function installEvents(hooks: EventHooks): void {
  const { root, render, reload, guard, setToken } = hooks;

  root.addEventListener('click', (event) => {
    const t = event.target;

    /* ── the add/edit sheet ──────────────────────────────────────────────────── */
    const addPerson = closest(t, 'data-addperson');
    if (addPerson) {
      const near = addPerson.dataset.addperson;
      openEditor(blankDraft(near ? Number(near) : null), render);
      return;
    }

    const editPerson = closest(t, 'data-editperson');
    if (editPerson) {
      const target = person(Number(editPerson.dataset.editperson));
      if (target) openEditor(draftFrom(target), render);
      return;
    }

    if (closest(t, 'data-cancelperson')) {
      state.editor = null;
      state.error = null;
      render();
      return;
    }

    const dateMode = closest(t, 'data-dm');
    if (dateMode && state.editor) {
      syncDraft(root);
      const [which, mode] = dateMode.dataset.dm!.split(':') as
        ['birth' | 'death', import('./views/personform').DateDraft['mode']];
      state.editor[which].mode = mode;
      render();
      return;
    }

    const sexButton = closest(t, 'data-sx');
    if (sexButton && state.editor) {
      syncDraft(root);
      state.editor.sex = sexButton.dataset.sx as typeof state.editor.sex;
      render();
      return;
    }

    const livingButton = closest(t, 'data-lv');
    if (livingButton && state.editor) {
      syncDraft(root);
      state.editor.living = livingButton.dataset.lv as typeof state.editor.living;
      render();
      return;
    }

    const attachRelation = closest(t, 'data-ar');
    if (attachRelation && state.editor) {
      syncDraft(root);
      state.editor.attachRelation = attachRelation.dataset.ar as 'parent' | 'child' | 'spouse';
      render();
      return;
    }

    const attachRole = closest(t, 'data-arole');
    if (attachRole && state.editor) {
      syncDraft(root);
      state.editor.attachRole = attachRole.dataset.arole as 'biological' | 'adoptive';
      render();
      return;
    }

    const save = closest(t, 'data-saveperson');
    if (save) {
      void saveDraft(save.dataset.saveperson === 'again', { root, render, reload, guard });
      return;
    }

    if (closest(t, 'data-confirmdelete') && state.editor) {
      syncDraft(root);
      state.editor.confirmingDelete = true;
      render();
      return;
    }
    if (closest(t, 'data-canceldelete') && state.editor) {
      state.editor.confirmingDelete = false;
      render();
      return;
    }
    const doDelete = closest(t, 'data-deleteperson');
    if (doDelete && state.editor?.id != null) {
      const id = state.editor.id;
      void guard(async () => {
        await api.removePerson(id);
        state.editor = null;
        if (state.selected === id) state.selected = null;
        if (state.root === id) state.root = null;
        await reload();
      });
      return;
    }

    const unlinkParent = closest(t, 'data-unlinkparent');
    if (unlinkParent) {
      const [childId, parentId] = unlinkParent.dataset.unlinkparent!.split(':').map(Number);
      void guard(async () => {
        await api.unlinkParent(childId!, parentId!);
        await reload();
      });
      return;
    }

    const unlinkUnion = closest(t, 'data-unlinkunion');
    if (unlinkUnion) {
      const [aId, bId] = unlinkUnion.dataset.unlinkunion!.split(':').map(Number);
      void guard(async () => {
        await api.unlinkUnion(aId!, bId!);
        await reload();
      });
      return;
    }

    const signIn = closest(t, 'data-signin');
    if (signIn) {
      const input = document.getElementById('token') as HTMLInputElement | null;
      if (input?.value) {
        state.token = input.value.trim();
        setToken(state.token);
        void reload();
      }
      return;
    }
    if (closest(t, 'data-retry')) { void reload(); return; }

    if (closest(t, 'data-createtree')) {
      const name = (document.getElementById('tree-name') as HTMLInputElement | null)?.value.trim();
      const location = (document.getElementById('tree-path') as HTMLInputElement | null)?.value.trim();
      if (!name || !location) {
        state.error = 'A tree needs a name and a folder.';
        render();
        return;
      }
      void guard(async () => {
        state.tree = (await api.createTree(name, location)).Tree;
        await reload();
      });
      return;
    }

    const importMode = closest(t, 'data-importmode');
    if (importMode) {
      state.importReplace = importMode.dataset.importmode === 'replace';
      render();
      return;
    }

    if (closest(t, 'data-doimport')) {
      const picker = document.getElementById('ged-file') as HTMLInputElement | null;
      const file = picker?.files?.[0];
      if (!file) {
        state.error = 'Choose a .ged, .gedcom or .gdz file first.';
        render();
        return;
      }
      const replace = state.importReplace;
      void guard(async () => {
        const summary = (await api.importTree(file, replace)).Result;
        const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;
        state.notice = `Imported ${plural(summary.people, 'person', 'people')}`
          + `, ${plural(summary.parentLinks, 'parent link', 'parent links')}`
          + ` and ${plural(summary.unions, 'union', 'unions')} from ${file.name}`
          + (summary.replaced
              ? ` — ${plural(summary.replaced, 'previous person', 'previous people')} removed`
              : '');
        state.error = null;
        state.root = null;
        state.focus = null;
        state.selected = null;
        state.open.clear();
        resetPan();
        await reload();
      });
      return;
    }

    const exporter = closest(t, 'data-export');
    if (exporter) {
      const format = exporter.dataset.export as ExportFormat;
      void guard(async () => {
        const written = await api.exportTree(format);
        state.notice = `Wrote ${written.Path} (${Math.round(written.Bytes / 102.4) / 10} kB)`;
        render();
      });
      return;
    }

    const personButton = closest(t, 'data-person');
    if (personButton) {
      selectPerson(Number(personButton.dataset.person), render);
      return;
    }

    const opener = closest(t, 'data-open');
    if (opener) {
      state.open.add(Number(opener.dataset.open));
      render();
      return;
    }

    const reroot = closest(t, 'data-reroot');
    if (reroot) {
      state.root = Number(reroot.dataset.reroot);
      state.open.clear();
      state.focus = null;
      void reload();
      return;
    }

    const view = closest(t, 'data-view');
    if (view) {
      state.view = view.dataset.view as typeof state.view;
      resetPan();
      render();
      return;
    }

    const focusStep = closest(t, 'data-focus');
    if (focusStep) {
      state.focus = Number(focusStep.dataset.focus);
      state.selected = state.focus;
      resetPan();
      render();
      return;
    }

    const showLine = closest(t, 'data-showline');
    if (showLine) {
      state.view = 'lineage';
      state.focus = Number(showLine.dataset.showline);
      resetPan();
      render();
      return;
    }

    const side = closest(t, 'data-side');
    if (side) {
      state.side = side.dataset.side as typeof state.side;
      void reload();
      return;
    }

    const lang = closest(t, 'data-lang');
    if (lang) {
      state.lang = lang.dataset.lang as typeof state.lang;
      render();
      return;
    }

    const goto = closest(t, 'data-goto');
    if (goto) {
      const id = Number(goto.dataset.goto);
      state.search = '';
      state.searchResults = [];
      selectPerson(id, render);
      return;
    }

    const elder = closest(t, 'data-elder');
    if (elder) {
      const elderId = Number(elder.dataset.elder);
      const youngerId = Number(elder.dataset.younger);
      void guard(async () => {
        await api.recordBirthOrder(elderId, youngerId);
        await reload();
      });
      return;
    }

    const pin = closest(t, 'data-pin');
    if (pin && state.selected !== null) {
      const [linkIndex, altIndex] = pin.dataset.pin!.split(':').map(Number);
      const target = person(state.selected);
      const alt = target?.relationships[linkIndex!]?.alternatives[altIndex!];
      if (alt) {
        const personId = state.selected;
        void guard(async () => {
          await api.pinTerm(personId, alt.base, alt.term, alt.roman, state.side);
          await reload();
        });
      }
      return;
    }

    const unpin = closest(t, 'data-unpin');
    if (unpin && state.selected !== null) {
      const target = person(state.selected);
      const bases = target?.relationships[Number(unpin.dataset.unpin)]?.bases ?? [];
      const personId = state.selected;
      void guard(async () => {
        for (const base of bases) await api.unpinTerm(personId, base);
        await reload();
      });
      return;
    }

    if (closest(t, 'data-addword')) { state.addingWord = true; render(); return; }
    if (closest(t, 'data-cancelword')) { state.addingWord = false; render(); return; }

    if (closest(t, 'data-saveword') && state.selected !== null) {
      const word = (document.getElementById('word-te') as HTMLInputElement | null)?.value.trim();
      const usage = (document.getElementById('word-use') as HTMLInputElement | null)?.value.trim();
      const base = person(state.selected)?.relationships[0]?.bases[0];
      if (word && base) {
        void guard(async () => {
          await api.addWord(base, word, '', usage ?? '', state.side);
          state.addingWord = false;
          await reload();
        });
      }
      return;
    }
  });

  /* ── search (debounced) + form read-back ──────────────────────────────────── */
  let searchTimer: number | undefined;
  root.addEventListener('input', (event) => {
    const input = event.target as HTMLInputElement;

    if (state.editor && input.dataset.df) {
      syncDraft(root);
      // Choosing somebody to attach to reveals the relation/role choices, so that field needs
      // a real re-render. Every other field only moves the read-back, patched in place.
      if (input.dataset.df === 'attachId') render();
      else refreshPreview(root);
      return;
    }

    if (input.id !== 'search') return;
    state.search = input.value;
    window.clearTimeout(searchTimer);
    // 150 ms debounce: a burst of keystrokes issues one search, not one per character.
    searchTimer = window.setTimeout(() => {
      const query = state.search.trim();
      if (query.length < 2) {
        state.searchResults = [];
        render();
        return;
      }
      void guard(async () => {
        state.searchResults = (await api.search(query)).Data.slice(0, SEARCH_CAP);
        render();
        (document.getElementById('search') as HTMLInputElement | null)?.focus();
      });
    }, SEARCH_DEBOUNCE_MS);
  });

  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && state.editor) {
      state.editor = null;
      state.error = null;
      render();
    }
  });
}

/** Search input debounce, per the brief. */
export const SEARCH_DEBOUNCE_MS = 150;
/** Results shown before the "more" affordance. */
export const SEARCH_CAP = 8;
