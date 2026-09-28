/**
 * The add/edit person sheet: everything that reads the form back into the draft and saves it.
 *
 * Split out of main.ts, which had grown past a thousand lines. Behaviour is unchanged — this
 * is a pure move — except that the shared escape helper and the render/reload callbacks are
 * now passed in rather than closed over, so the sheet no longer needs to live in the shell.
 */
import { api } from '../api';
import type { DateValue } from '../api';
import { state } from '../state';
import type { DateDraft, PersonDraft } from './personform';
import { blankDraft, reads, sorts } from './personform';

export interface EditorHooks {
  root: HTMLElement;
  render: () => void;
  reload: () => Promise<void>;
  guard: (work: () => Promise<void>) => Promise<void>;
}

/**
 * Copy what has been typed back into the draft before any re-render.
 *
 * The whole interface re-renders from state, so without this a toggle -- switching the date
 * mode, say -- would discard every field the reader had already filled in.
 */
export function syncDraft(root: HTMLElement): void {
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
export function refreshPreview(root: HTMLElement): void {
  const draft = state.editor;
  if (!draft) return;
  for (const which of ['birth', 'death'] as const) {
    const box = root.querySelector(`.sheet [data-preview="${which}"]`);
    if (!box) continue;
    const value = box.querySelector('.rd-v');
    const note = box.querySelector('.rd-n');
    if (value) value.textContent = reads(draft[which]);
    if (note) note.textContent = sorts(draft[which], which);
    box.classList.toggle('is-blank', draft[which].mode === 'unknown');
  }
}

export function openEditor(draft: PersonDraft, render: () => void): void {
  state.editor = draft;
  state.error = null;
  render();
}

/** A draft field as the API wants it: absent stays absent rather than becoming zero. */
function dateInput(d: DateDraft): Partial<DateValue> & { mode: DateDraft['mode'] } {
  const number = (value: string) => (value.trim() === '' ? null : Number(value));
  return {
    mode: d.mode,
    year: number(d.year),
    month: number(d.month),
    day: number(d.day),
    year2: number(d.year2),
  };
}

export async function saveDraft(andAnother: boolean, hooks: EditorHooks): Promise<void> {
  syncDraft(hooks.root);
  const draft = state.editor;
  if (!draft) return;
  if (!draft.given.trim()) {
    state.error = 'A person needs a given name.';
    hooks.render();
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

  await hooks.guard(async () => {
    if (draft.id !== null) {
      await api.editPerson(draft.id, payload);
      state.editor = null;
    } else {
      const attachTo = draft.attachId === null
        ? undefined
        : { personId: draft.attachId, relation: draft.attachRelation, role: draft.attachRole };
      const created = await api.addPerson({ ...payload, attachTo });
      state.editor = andAnother ? blankDraft(draft.attachId) : null;
      if (!andAnother) state.selected = created.Person.id;
    }
    state.error = null;
    await hooks.reload();
  });
}
