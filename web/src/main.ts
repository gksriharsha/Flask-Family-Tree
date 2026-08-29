import './styles.css';
import type { ExportFormat } from './api';
import { ApiError, api, loadToken, setToken } from './api';
import { focusId, lineageSpine, person, state } from './state';
import type { DateDraft, PersonDraft } from './views/personform';
import { blankDraft, draftFrom, reads, renderPersonForm, sorts } from './views/personform';
import { renderRail } from './views/rail';
import { renderTree } from './views/tree';

const root = document.getElementById('app')!;
const escape = (text: string): string =>
  text.replace(/[&<>"']/g, (c) =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]!);

/* ── data ──────────────────────────────────────────────────────────────────── */
async function reload(): Promise<void> {
  state.loading = true;
  state.error = null;
  render();
  try {
    await api.session();
    state.tree = (await api.tree()).Tree;
    state.treeChecked = true;
    if (state.tree === null) {
      state.loading = false;
      render();
      return;
    }
    const graph = await api.graph(state.root, state.side);
    state.graph = graph;
    state.root = graph.Root;
    if (state.selected === null || !person(state.selected)) {
      state.selected = graph.Root;
    }
    if (state.focus !== null && !person(state.focus)) {
      state.focus = null;   // they were removed; fall back to the top of the line
    }
  } catch (error) {
    state.error = error instanceof ApiError ? error.message : String(error);
    if (error instanceof ApiError && error.status === 401) state.token = '';
  } finally {
    state.loading = false;
    render();
  }
}

/* ── shell ─────────────────────────────────────────────────────────────────── */
/**
 * The line of descent currently on the canvas, oldest first.
 *
 * Built from the person in focus rather than from the reader, so descending into an uncle's
 * branch still shows where you are instead of stranding you off your own line. Each step is
 * a button: this is how you walk back up.
 */
function spineSection(): string {
  const id = focusId();
  if (id === null) return '';
  const steps = lineageSpine(id);
  if (steps.length === 0) return '';

  return `
    <div class="rail-sec">
      <p class="lbl">This line</p>
      <div class="spine">
        ${steps
          .map((stepId, i) => {
            const p = person(stepId);
            if (!p) return '';
            const kin = p.relationships[0];
            const here = stepId === id;
            const you = stepId === state.root;
            return `<button class="spine-step${here ? ' is-here' : ''}${you ? ' is-you' : ''}"
                            data-focus="${stepId}">
                      <span class="sp-i">${i + 1}</span>
                      <span class="sp-n">${escape(p.given || p.name)}</span>
                      <span class="sp-k">${escape(kin?.te ?? '')}</span>
                    </button>`;
          })
          .join('')}
      </div>
      <div class="hint">Showing the children of
        <strong>${escape(person(id)?.given ?? '')}</strong>. Tap a step to move the subject.</div>
    </div>`;
}

function leftRail(): string {
  const rootPerson = state.root === null ? undefined : person(state.root);
  const counts = state.graph?.Counts;
  return `
    <div class="rail-in">
      <div class="rail-sec">
        <p class="lbl">Kinship measured from</p>
        <div class="rootcard">
          <div class="nm">${escape(rootPerson?.name ?? '—')}</div>
          <div class="sub">${counts ? `${counts.people} people · ${counts.unions} unions` : ''}</div>
        </div>
      </div>

      <div class="rail-sec">
        <button class="btn wide" data-addperson>Add a person</button>
      </div>

      ${state.view === 'lineage' ? spineSection() : ''}

      <div class="rail-sec">
        <p class="lbl">Family vocabulary</p>
        <div class="seg vseg">
          <button data-side="paternal" aria-pressed="${state.side === 'paternal'}">Father&rsquo;s side</button>
          <button data-side="maternal" aria-pressed="${state.side === 'maternal'}">Mother&rsquo;s side</button>
        </div>
        <div class="hint">${
          state.side === 'maternal'
            ? 'Your mother&rsquo;s people say కక్కయ్య where your father&rsquo;s say చిన్నాన్న. Same relation, different word.'
            : 'Switch to hear the tree in your mother&rsquo;s side&rsquo;s words.'
        }</div>
      </div>

      ${counts && counts.openBirthOrderQuestions > 0
        ? `<div class="rail-sec">
             <p class="lbl">Birth order</p>
             <div class="sampled">${counts.openBirthOrderQuestions} ${
               counts.openBirthOrderQuestions === 1 ? 'person needs' : 'people need'
             } a birth order before Telugu can name them. Select one and answer the question in
             the right rail.</div>
           </div>`
        : ''}

      <div class="rail-sec">
        <p class="lbl">Files</p>
        <div class="sampled">
          <strong>${escape(state.tree?.name ?? '')}</strong><br />
          ${escape(state.tree?.location ?? '')}
        </div>
        <div class="hint">Kept up to date after every change.</div>
        <div class="exports">
          <button class="btn ghost" data-export="gedzip">GEDZIP <small>with media</small></button>
          <button class="btn ghost" data-export="gedcom551">GEDCOM 5.5.1 <small>older tools</small></button>
          <button class="btn ghost" data-export="gedcom7">GEDCOM 7 <small>copy</small></button>
        </div>
        ${state.notice ? `<div class="notice">${escape(state.notice)}</div>` : ''}
      </div>

      <div class="rail-sec">
        <p class="lbl">Key</p>
        <div class="key"><i></i> Descent</div>
        <div class="key"><i class="adopt"></i> Adoptive descent</div>
        <div class="key"><i class="union"></i> Union</div>
        <div class="key"><span class="unres">అ / అ</span> Telugu label needs a fact</div>
      </div>
    </div>`;
}

function topBar(): string {
  const results = state.searchResults.length > 0
    ? `<div class="results">${state.searchResults
        .map(
          (r) => `<button data-goto="${r.ID}">${escape(r.Firstname)} ${escape(
            r.Lastname ?? '',
          )}</button>`,
        )
        .join('')}</div>`
    : '';
  return `
    <header class="top">
      <div class="brand">
        <svg width="21" height="21" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <path d="M12 21V11" stroke="#3F6D14" stroke-width="1.7" stroke-linecap="round"/>
          <path d="M12 11C12 6.5 8.5 3.5 4.5 3.5c0 4.5 3 7.5 7.5 7.5Z" stroke="#3F6D14" stroke-width="1.7" stroke-linejoin="round"/>
          <path d="M12 14c0-3.6 2.8-6 6-6 0 3.6-2.4 6-6 6Z" stroke="#7FA352" stroke-width="1.7" stroke-linejoin="round"/>
        </svg>
        <span>Family Tree</span>
      </div>
      <div class="searchbox">
        <input id="search" value="${escape(state.search)}"
               placeholder="Search names in either script — Varma, వర్మ" aria-label="Search people" />
        ${results}
      </div>
      <div class="seg">
        <button data-view="lineage" aria-pressed="${state.view === 'lineage'}">Lineage</button>
        <button data-view="all" aria-pressed="${state.view === 'all'}">View all</button>
      </div>
      <div class="seg">
        <button data-lang="en" aria-pressed="${state.lang === 'en'}">English</button>
        <button class="te" data-lang="te" aria-pressed="${state.lang === 'te'}">తెలుగు</button>
        <button data-lang="both" aria-pressed="${state.lang === 'both'}">Both</button>
      </div>
      <span class="spacer"></span>
      <span class="counts">${
        state.graph ? `${state.graph.Counts.people} people · ${state.graph.Counts.unions} unions` : ''
      }</span>
    </header>`;
}

function firstRun(): string {
  return `
    <div class="state">
      <div>
        <h2>Where should this tree live?</h2>
        <p>Everything the tree holds is kept as files in one folder &mdash; a GEDCOM 7 file
           that other genealogy software can open, its media, and the words your family uses.
           Back the tree up by copying that folder; rebuild it from there if the database is
           ever lost.</p>
        <input id="tree-name" placeholder="What to call it — Varma family" aria-label="Tree name" />
        <input id="tree-path" placeholder="Folder — /data/tree" aria-label="Folder" />
        <div><button class="btn" data-createtree>Create the tree</button></div>
        ${state.error ? `<p class="err">${escape(state.error)}</p>` : ''}
        <p style="margin-top:18px;font-size:13px;color:var(--muted)">
          Already have a GEDCOM file? Create the tree first, then use Import.
        </p>
      </div>
    </div>`;
}

function render(): void {
  if (!state.token) {
    root.innerHTML = `
      <div class="state">
        <div>
          <h2>Family Tree</h2>
          <p>This tree is private. Paste the access token to open it.</p>
          <input id="token" type="password" placeholder="Access token" aria-label="Access token" />
          <div><button class="btn" data-signin>Open</button></div>
          ${state.error ? `<p class="err">${escape(state.error)}</p>` : ''}
        </div>
      </div>`;
    return;
  }

  if (state.treeChecked && state.tree === null) {
    root.innerHTML = firstRun();
    return;
  }

  if (state.loading && !state.graph) {
    root.innerHTML = '<div class="state"><p>Loading the tree…</p></div>';
    return;
  }
  if (state.error && !state.graph) {
    root.innerHTML = `<div class="state"><div>
      <h2>Could not load the tree</h2><p class="err">${escape(state.error)}</p>
      <button class="btn" data-retry>Try again</button></div></div>`;
    return;
  }

  // The whole shell is rebuilt on every render, which resets the canvas scroll. Carry it
  // across, or selecting anyone throws the reader back to the top-left of the tree.
  const keptScroll = (() => {
    const canvas = root.querySelector('.canvas');
    return canvas ? { x: canvas.scrollLeft, y: canvas.scrollTop } : null;
  })();

  root.innerHTML = `
    <div class="shell">
      ${topBar()}
      <div class="body">
        <aside class="rail rail-l">${leftRail()}</aside>
        <main>${renderTree()}</main>
        <aside class="rail rail-r">${renderRail()}</aside>
      </div>
    </div>
    ${state.editor ? renderPersonForm(state.editor) : ''}`;

  if (keptScroll) {
    const canvas = root.querySelector('.canvas');
    if (canvas) {
      canvas.scrollLeft = keptScroll.x;
      canvas.scrollTop = keptScroll.y;
    }
  }

  drawWires();

  // Typing is not allowed to trigger a re-render, so the caret is only ever restored here --
  // after a toggle rebuilt the sheet -- rather than on every keystroke.
  if (state.editor) {
    const first = root.querySelector<HTMLInputElement>('.sheet [data-df="given"]');
    if (first && document.activeElement === document.body) first.focus();
  }
}

/* ── the add/edit sheet ────────────────────────────────────────────────────── */
/**
 * Copy what has been typed back into the draft before any re-render.
 *
 * The whole interface re-renders from state, so without this a toggle -- switching the date
 * mode, say -- would discard every field the reader had already filled in.
 */
function syncDraft(): void {
  const draft = state.editor;
  if (!draft) return;
  root.querySelectorAll<HTMLInputElement | HTMLSelectElement>('.sheet [data-df]').forEach((el) => {
    const key = el.dataset.df!;
    const value = el.value;
    if (key === 'attachId') {
      draft.attachId = value === '' ? null : Number(value);
      return;
    }
    if (key.includes('.')) {
      const [which, field] = key.split('.') as ['birth' | 'death', keyof DateDraft];
      (draft[which][field] as string) = value;
      return;
    }
    (draft as unknown as Record<string, string>)[key] = value;
  });
}

/**
 * Update the read-back in place as the year is typed.
 *
 * Deliberately not a re-render: rebuilding the sheet on every keystroke would move the caret
 * and lose the field. Only the two preview lines are touched, so the form stays exactly where
 * the reader left it while still showing what the record is about to say.
 */
function refreshPreview(): void {
  const draft = state.editor;
  if (!draft) return;
  for (const which of ['birth', 'death'] as const) {
    const box = root.querySelector(`.sheet [data-preview="${which}"]`);
    if (!box) continue;
    const value = box.querySelector('.rd-v');
    const note = box.querySelector('.rd-n');
    if (value) value.textContent = reads(draft[which]);
    if (note) note.textContent = sorts(draft[which], which);
    // An absent date is not rendered as though it were a value.
    box.classList.toggle('is-blank', draft[which].mode === 'unknown');
  }
}

function openEditor(draft: PersonDraft): void {
  state.editor = draft;
  state.error = null;
  render();
}

/** A draft field as the API wants it: absent stays absent rather than becoming zero. */
function dateInput(d: DateDraft) {
  const number = (value: string) => (value.trim() === '' ? null : Number(value));
  return {
    mode: d.mode,
    year: number(d.year),
    month: number(d.month),
    day: number(d.day),
    year2: number(d.year2),
  };
}

async function saveDraft(andAnother: boolean): Promise<void> {
  syncDraft();
  const draft = state.editor;
  if (!draft) return;
  if (!draft.given.trim()) {
    state.error = 'A person needs a given name.';
    render();
    return;
  }

  const payload = {
    given: draft.given.trim(),
    surname: draft.surname.trim(),
    sex: draft.sex,
    living: draft.living === 'unknown' ? null : draft.living === 'yes',
    birth: dateInput(draft.birth),
    // A death date on somebody recorded as living would contradict itself, so it is only
    // ever sent when the form is actually showing the field.
    death: draft.living === 'no' ? dateInput(draft.death) : { mode: 'unknown' as const },
  };

  await guard(async () => {
    if (draft.id !== null) {
      await api.editPerson(draft.id, payload);
      state.editor = null;
    } else {
      const attachTo = draft.attachId === null
        ? undefined
        : { personId: draft.attachId, relation: draft.attachRelation, role: draft.attachRole };
      const created = await api.addPerson({ ...payload, attachTo });
      state.editor = andAnother
        ? blankDraft(draft.attachId)
        : null;
      if (!andAnother) state.selected = created.Person.id;
    }
    state.error = null;
    await reload();
  });
}

/* ── events ────────────────────────────────────────────────────────────────── */
async function guard(work: () => Promise<void>): Promise<void> {
  try {
    await work();
  } catch (error) {
    state.error = error instanceof ApiError ? error.message : String(error);
    render();
  }
}

function closest(target: EventTarget | null, attr: string): HTMLElement | null {
  return (target as HTMLElement | null)?.closest?.(`[${attr}]`) ?? null;
}

root.addEventListener('click', (event) => {
  const t = event.target;

  /* ── the add/edit sheet ──────────────────────────────────────────────────── */
  const addPerson = closest(t, 'data-addperson');
  if (addPerson) {
    const near = addPerson.dataset.addperson;
    openEditor(blankDraft(near ? Number(near) : null));
    return;
  }

  const editPerson = closest(t, 'data-editperson');
  if (editPerson) {
    const target = person(Number(editPerson.dataset.editperson));
    if (target) openEditor(draftFrom(target));
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
    syncDraft();
    const [which, mode] = dateMode.dataset.dm!.split(':') as ['birth' | 'death', DateDraft['mode']];
    state.editor[which].mode = mode;
    render();
    return;
  }

  const sexButton = closest(t, 'data-sx');
  if (sexButton && state.editor) {
    syncDraft();
    state.editor.sex = sexButton.dataset.sx as typeof state.editor.sex;
    render();
    return;
  }

  const livingButton = closest(t, 'data-lv');
  if (livingButton && state.editor) {
    syncDraft();
    state.editor.living = livingButton.dataset.lv as typeof state.editor.living;
    render();
    return;
  }

  const attachRelation = closest(t, 'data-ar');
  if (attachRelation && state.editor) {
    syncDraft();
    state.editor.attachRelation = attachRelation.dataset.ar as 'parent' | 'child' | 'spouse';
    render();
    return;
  }

  const attachRole = closest(t, 'data-arole');
  if (attachRole && state.editor) {
    syncDraft();
    state.editor.attachRole = attachRole.dataset.arole as 'biological' | 'adoptive';
    render();
    return;
  }

  const save = closest(t, 'data-saveperson');
  if (save) {
    void saveDraft(save.dataset.saveperson === 'again');
    return;
  }

  if (closest(t, 'data-confirmdelete') && state.editor) {
    syncDraft();
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
  if (doDelete && state.editor?.id !== null && state.editor !== null) {
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
    state.selected = Number(personButton.dataset.person);
    state.addingWord = false;
    render();
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
    state.focus = null;   // a new reference point means a new line
    void reload();
    return;
  }

  const view = closest(t, 'data-view');
  if (view) {
    state.view = view.dataset.view as typeof state.view;
    render();
    return;
  }

  const focusStep = closest(t, 'data-focus');
  if (focusStep) {
    state.focus = Number(focusStep.dataset.focus);
    state.selected = state.focus;
    render();
    return;
  }

  const showLine = closest(t, 'data-showline');
  if (showLine) {
    // Put this person's own line on the canvas, whichever mode we were in.
    state.view = 'lineage';
    state.focus = Number(showLine.dataset.showline);
    render();
    return;
  }

  if (closest(t, 'data-recentre')) {
    const canvas = root.querySelector('.canvas');
    if (canvas) {
      canvas.scrollTo({ left: (canvas.scrollWidth - canvas.clientWidth) / 2, top: 0 });
    }
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
    state.selected = Number(goto.dataset.goto);
    state.search = '';
    state.searchResults = [];
    render();
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

let searchTimer: number | undefined;
root.addEventListener('input', (event) => {
  const input = event.target as HTMLInputElement;

  if (state.editor && input.dataset.df) {
    syncDraft();
    // Choosing somebody to attach to reveals the relation and role choices, so that one field
    // needs a real re-render. Every other field only moves the read-back, which is patched in
    // place so the caret stays where it is.
    if (input.dataset.df === 'attachId') render();
    else refreshPreview();
    return;
  }

  if (input.id !== 'search') return;
  state.search = input.value;
  window.clearTimeout(searchTimer);
  searchTimer = window.setTimeout(() => {
    const query = state.search.trim();
    if (query.length < 2) {
      state.searchResults = [];
      render();
      return;
    }
    void guard(async () => {
      state.searchResults = (await api.search(query)).Data.slice(0, 8);
      render();
      (document.getElementById('search') as HTMLInputElement | null)?.focus();
    });
  }, 220);
});

document.addEventListener('keydown', (event) => {
  if (event.key === 'Escape' && state.editor) {
    state.editor = null;
    state.error = null;
    render();
  }
});

/* ── connectors ────────────────────────────────────────────────────────────── */
/**
 * Draw the descent and marriage lines by measuring where the cards actually are.
 *
 * They used to be CSS pseudo-elements positioned at percentages -- a horizontal bar at
 * `left:16%; right:16%` with ticks dropping from each child. Those percentages have nothing
 * to do with where the children sit, so the bar overshot the outer children by tens of
 * pixels, and unevenly, because a child block is wider when a spouse pill is attached to it.
 * Measuring is the only way the line meets the card it claims to join.
 *
 * Descent is one curve per child rather than a bar with ticks: no bar means no bar to
 * misalign, and a curve carries a 1.25px stroke where a right angle would look broken.
 * Marriage is a double rule -- the mark genealogy has used for it for centuries -- in a warm
 * neutral, so a union differs from a descent in colour as well as in form.
 */
const DESCENT = '#8FAE66';
const UNION = '#B08A63';

function drawWires(): void {
  const canvases = root.querySelectorAll<HTMLElement>('.canvas-in');
  for (const canvas of canvases) {
    const svg = canvas.querySelector('svg.wires');
    if (!svg || !state.graph) continue;

    const base = canvas.getBoundingClientRect();
    // A person shows as a card or, when they married in, as a pill. Either is an endpoint.
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

    // Gather by the couple (or lone parent) the children issue from, so one trunk and one
    // sibling bar can serve all of them -- which is what a genealogy chart looks like.
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

      // The sibling bar sits midway down and spans exactly the children it joins -- measured,
      // so it can never overshoot them the way a percentage did.
      const bar = origin.y + (Math.min(...kids.map((k) => k.y)) - origin.y) / 2;
      const left = Math.min(origin.x, ...kids.map((k) => k.x));
      const right = Math.max(origin.x, ...kids.map((k) => k.x));

      const stroke = `stroke="${DESCENT}" stroke-width="1.1" stroke-linecap="square"`;
      parts.push(`<path d="M${origin.x} ${origin.y}V${bar}" fill="none" ${stroke} />`);
      if (right - left > 0.5) {
        parts.push(`<path d="M${left} ${bar}H${right}" fill="none" ${stroke} />`);
      }
      for (const kid of kids) {
        // The shared trunk is shared; the role belongs to the individual link, so only the
        // child's own drop is dashed.
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
      if (gap < 6 || gap > 80) continue;   // not drawn side by side on this canvas
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

window.addEventListener('resize', () => drawWires());

/* ── drag to move the tree ─────────────────────────────────────────────────── */
/**
 * Panning moves the canvas's own scroll rather than a CSS transform, so the wheel, the
 * scrollbars and keyboard scrolling all still work and nothing can be dragged out of reach.
 * A drag only counts past a few pixels, so a click on a card is still a click.
 */
const DRAG_SLOP = 4;
let suppressClick = false;
let pan: { canvas: HTMLElement; x: number; y: number; sl: number; st: number;
           moved: boolean } | null = null;

root.addEventListener('pointerdown', (event) => {
  if (event.button !== 0) return;
  const canvas = (event.target as HTMLElement | null)?.closest?.('[data-pan]');
  if (!(canvas instanceof HTMLElement)) return;
  pan = { canvas, x: event.clientX, y: event.clientY,
          sl: canvas.scrollLeft, st: canvas.scrollTop, moved: false };
});

window.addEventListener('pointermove', (event) => {
  if (!pan) return;
  const dx = event.clientX - pan.x;
  const dy = event.clientY - pan.y;
  if (!pan.moved && Math.abs(dx) < DRAG_SLOP && Math.abs(dy) < DRAG_SLOP) return;
  if (!pan.moved) {
    pan.moved = true;
    pan.canvas.classList.add('is-panning');
  }
  pan.canvas.scrollLeft = pan.sl - dx;
  pan.canvas.scrollTop = pan.st - dy;
});

window.addEventListener('pointerup', () => {
  if (!pan) return;
  pan.canvas.classList.remove('is-panning');
  // A drag that ended over a card must not also select that card.
  if (pan.moved) suppressClick = true;
  pan = null;
});

root.addEventListener('click', (event) => {
  if (!suppressClick) return;
  suppressClick = false;
  event.stopPropagation();
  event.preventDefault();
}, true);

/* ── boot ──────────────────────────────────────────────────────────────────── */
state.token = loadToken();
if (state.token) setToken(state.token);
render();
if (state.token) void reload();
