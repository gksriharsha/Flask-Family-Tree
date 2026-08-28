/**
 * Add and edit a person.
 *
 * The whole point of this form is that it accepts what people actually know. A record with an
 * honest gap is worth more than one with an invented date, so every field except the given
 * name may be left empty, "unknown" is a real answer for sex and for living, and a birth date
 * can be stated at any of seven precisions rather than being forced into a false `yyyy-mm-dd`.
 * The 1 January placeholder dates that fill so many family trees are what this is designed to
 * stop being necessary.
 */
import type { DateMode, LinkRole, PersonNode, Sex } from '../api';
import { person, state } from '../state';

const escape = (text: string): string =>
  text.replace(/[&<>"']/g, (c) =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]!);

export interface DateDraft {
  mode: DateMode;
  year: string;
  month: string;
  day: string;
  year2: string;
}

export interface PersonDraft {
  /** null when adding; the person's id when editing. */
  id: number | null;
  given: string;
  surname: string;
  sex: Sex;
  living: 'yes' | 'no' | 'unknown';
  birth: DateDraft;
  death: DateDraft;
  attachId: number | null;
  attachRelation: 'parent' | 'child' | 'spouse';
  attachRole: LinkRole;
  confirmingDelete: boolean;
}

const EMPTY_DATE: DateDraft = { mode: 'unknown', year: '', month: '', day: '', year2: '' };

export function blankDraft(attachId: number | null = null): PersonDraft {
  return {
    id: null,
    given: '',
    surname: '',
    sex: 'unknown',
    living: 'unknown',
    birth: { ...EMPTY_DATE },
    death: { ...EMPTY_DATE },
    attachId,
    attachRelation: 'child',
    attachRole: 'biological',
    confirmingDelete: false,
  };
}

export function draftFrom(p: PersonNode): PersonDraft {
  const asDraft = (d: PersonNode['birth']): DateDraft => ({
    mode: d.mode,
    year: d.year === null ? '' : String(d.year),
    month: d.month === null ? '' : String(d.month),
    day: d.day === null ? '' : String(d.day),
    year2: d.year2 === null ? '' : String(d.year2),
  });
  return {
    id: p.id,
    given: p.given,
    surname: p.surname,
    sex: p.sex,
    living: p.living === null ? 'unknown' : p.living ? 'yes' : 'no',
    birth: asDraft(p.birth),
    death: asDraft(p.death),
    attachId: null,
    attachRelation: 'child',
    attachRole: 'biological',
    confirmingDelete: false,
  };
}

const MODES: { id: DateMode; label: string }[] = [
  { id: 'exact', label: 'Exact' },
  { id: 'year', label: 'Year only' },
  { id: 'about', label: 'About' },
  { id: 'before', label: 'Before' },
  { id: 'after', label: 'After' },
  { id: 'between', label: 'Between' },
  { id: 'unknown', label: 'Unknown' },
];

const SEXES: { id: Sex; label: string }[] = [
  { id: 'male', label: 'Male' },
  { id: 'female', label: 'Female' },
  { id: 'intersex', label: 'Intersex' },
  { id: 'unknown', label: 'Unknown' },
];

/** What the record will say, mirrored from the server's own wording. */
export function reads(d: DateDraft): string {
  const y = d.year || '—';
  switch (d.mode) {
    case 'exact': {
      const parts = [d.day, d.month && monthName(d.month), d.year].filter(Boolean);
      return parts.length > 0 ? parts.join(' ') : '—';
    }
    case 'year': return y;
    case 'about': return `about ${y}`;
    case 'before': return `before ${y}`;
    case 'after': return `after ${y}`;
    case 'between': return `between ${y} and ${d.year2 || '—'}`;
    default: return 'unknown';
  }
}

function monthName(value: string): string {
  const names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  return names[Number(value) - 1] ?? value;
}

/** Why this precision is the honest one, and how it will sort. */
export function sorts(d: DateDraft): string {
  const y = Number(d.year);
  switch (d.mode) {
    case 'exact':
      return 'Stored as a single day. Sorts and calculates ages exactly.';
    case 'year':
      return `Stored as the whole of ${d.year || 'that year'}. Sorts by year; no month or day is implied.`;
    case 'about':
      return Number.isFinite(y) && d.year
        ? `Treated as ${y - 2} to ${y + 2}. Anyone inside that window cannot be ranked against this person, so the tree will ask instead of guessing.`
        : 'Treated as a window a couple of years wide.';
    case 'before':
      return 'An open interval with only an upper bound. Sorts before anything known to be later.';
    case 'after':
      return 'An open interval with only a lower bound. Pairs with a bound from the other direction to narrow a range.';
    case 'between':
      return 'Two bounds from two documents — what genealogical research actually produces.';
    default:
      return 'No interval stored. This person still holds their place through their parents and children.';
  }
}

function dateBlock(which: 'birth' | 'death', d: DateDraft, legend: string): string {
  const numeric = (name: string, label: string, value: string, width: string) => `
    <label class="fld is-${width}">
      <span>${label}</span>
      <input type="number" data-df="${which}.${name}" value="${escape(value)}"
             inputmode="numeric" autocomplete="off" />
    </label>`;

  let fields = '';
  if (d.mode === 'exact') {
    fields = numeric('year', 'Year', d.year, 'yr') +
             numeric('month', 'Month', d.month, 'sm') +
             numeric('day', 'Day', d.day, 'sm');
  } else if (d.mode === 'between') {
    fields = numeric('year', 'Earliest year', d.year, 'yr') +
             `<span class="andword">and</span>` +
             numeric('year2', 'Latest year', d.year2, 'yr');
  } else if (d.mode !== 'unknown') {
    fields = numeric('year', 'Year', d.year, 'yr');
  } else {
    fields = `<p class="nothing">Nothing to enter. The record will say the ${which} date is
              unknown, rather than implying a date nobody has.</p>`;
  }

  return `
    <fieldset class="dategroup">
      <legend>${legend}</legend>
      <div class="modes">
        ${MODES.map(
          (m) => `<button type="button" data-dm="${which}:${m.id}"
                     aria-pressed="${d.mode === m.id}">${m.label}</button>`,
        ).join('')}
      </div>
      <div class="daterow">${fields}</div>
      <div class="preview" data-preview="${which}">
        <div class="pv">The record will read <strong>${escape(reads(d))}</strong></div>
        <div class="pm">${escape(sorts(d))}</div>
      </div>
    </fieldset>`;
}

function attachBlock(draft: PersonDraft): string {
  if (draft.id !== null) return '';
  const others = (state.graph?.People ?? [])
    .slice()
    .sort((a, b) => a.name.localeCompare(b.name));
  const options = others
    .map((p) => `<option value="${p.id}" ${draft.attachId === p.id ? 'selected' : ''}>
        ${escape(p.name)}</option>`)
    .join('');

  return `
    <fieldset class="dategroup">
      <legend>Attach to</legend>
      <p class="nothing">Optional. An unattached person is a valid record &mdash; you can link
         them once you know how they fit.</p>
      <div class="daterow">
        <label class="fld is-grow">
          <span>Person already in the tree</span>
          <select data-df="attachId">
            <option value="">Not yet</option>
            ${options}
          </select>
        </label>
      </div>
      ${draft.attachId === null ? '' : `
        <div class="modes">
          ${(['parent', 'child', 'spouse'] as const)
            .map(
              (r) => `<button type="button" data-ar="${r}"
                        aria-pressed="${draft.attachRelation === r}">
                        Is their ${r === 'spouse' ? 'spouse' : r}</button>`,
            )
            .join('')}
        </div>
        ${draft.attachRelation === 'spouse' ? '' : `
          <div class="modes">
            ${(['biological', 'adoptive'] as const)
              .map(
                (r) => `<button type="button" data-arole="${r}"
                          aria-pressed="${draft.attachRole === r}">${r}</button>`,
              )
              .join('')}
          </div>`}
      `}
    </fieldset>`;
}

/** Existing links, so an edit can correct a wrong relationship rather than only add one. */
function linksBlock(draft: PersonDraft): string {
  if (draft.id === null) return '';
  const id = draft.id;
  const links = state.graph?.ParentLinks ?? [];
  const rows: string[] = [];

  for (const link of links.filter((l) => l.child === id)) {
    const p = person(link.parent);
    if (p) {
      rows.push(`<li><span>Child of <strong>${escape(p.name)}</strong>
        ${link.role === 'biological' ? '' : `<em>· ${escape(link.role)}</em>`}</span>
        <button type="button" data-unlinkparent="${id}:${link.parent}">Remove</button></li>`);
    }
  }
  for (const link of links.filter((l) => l.parent === id)) {
    const p = person(link.child);
    if (p) {
      rows.push(`<li><span>Parent of <strong>${escape(p.name)}</strong>
        ${link.role === 'biological' ? '' : `<em>· ${escape(link.role)}</em>`}</span>
        <button type="button" data-unlinkparent="${link.child}:${id}">Remove</button></li>`);
    }
  }
  for (const union of state.graph?.Unions ?? []) {
    if (union.a !== id && union.b !== id) continue;
    const p = person(union.a === id ? union.b : union.a);
    if (p) {
      rows.push(`<li><span>Married to <strong>${escape(p.name)}</strong></span>
        <button type="button" data-unlinkunion="${union.a}:${union.b}">Remove</button></li>`);
    }
  }

  return `
    <fieldset class="dategroup">
      <legend>Relationships</legend>
      ${rows.length === 0
        ? `<p class="nothing">No links yet. This person still holds a valid record.</p>`
        : `<ul class="linklist">${rows.join('')}</ul>`}
    </fieldset>`;
}

export function renderPersonForm(draft: PersonDraft): string {
  const editing = draft.id !== null;
  const title = editing ? 'Edit this person' : 'Add a person';

  return `
    <div class="sheet" role="dialog" aria-modal="true" aria-label="${title}">
      <div class="sheet-in">
        <header class="sheet-top">
          <h2>${title}</h2>
          <button type="button" class="x" data-cancelperson aria-label="Close">&times;</button>
        </header>

        <p class="lede">Only a name is required. Everything else can be partial, approximate,
           or left out &mdash; a record with an honest gap is worth more than one with an
           invented date.</p>

        <fieldset class="dategroup">
          <legend>Name</legend>
          <div class="daterow">
            <label class="fld is-grow">
              <span>Given name *</span>
              <input data-df="given" value="${escape(draft.given)}" autocomplete="off" />
            </label>
            <label class="fld is-grow">
              <span>Surname</span>
              <input data-df="surname" value="${escape(draft.surname)}" autocomplete="off"
                     placeholder="Leave blank if it isn&rsquo;t known" />
            </label>
          </div>
        </fieldset>

        <fieldset class="dategroup">
          <legend>Identity</legend>
          <div class="modes">
            ${SEXES.map(
              (s) => `<button type="button" data-sx="${s.id}"
                        aria-pressed="${draft.sex === s.id}">${s.label}</button>`,
            ).join('')}
          </div>
          <p class="nothing">Recorded as a fact about the document. It is not what decides a
             relationship&rsquo;s name, so &ldquo;unknown&rdquo; is a real answer and nothing
             downstream breaks.</p>
          <div class="modes">
            ${(['yes', 'no', 'unknown'] as const)
              .map(
                (v) => `<button type="button" data-lv="${v}"
                          aria-pressed="${draft.living === v}">Living: ${v}</button>`,
              )
              .join('')}
          </div>
        </fieldset>

        ${dateBlock('birth', draft.birth, 'Born')}
        ${draft.living === 'no' ? dateBlock('death', draft.death, 'Died') : ''}
        ${attachBlock(draft)}
        ${linksBlock(draft)}

        ${state.error ? `<p class="err">${escape(state.error)}</p>` : ''}

        <footer class="sheet-foot">
          ${editing
            ? draft.confirmingDelete
              ? `<span class="delwarn">Remove ${escape(draft.given)} and every link to them?
                   The tree&rsquo;s file is rewritten straight away, so there is no undo.</span>
                 <button type="button" class="btn danger" data-deleteperson>Yes, remove</button>
                 <button type="button" class="btn ghost" data-canceldelete>Keep</button>`
              : `<button type="button" class="btn ghost danger-text" data-confirmdelete>Remove</button>
                 <span class="spacer"></span>
                 <button type="button" class="btn ghost" data-cancelperson>Cancel</button>
                 <button type="button" class="btn" data-saveperson>Save changes</button>`
            : `<span class="spacer"></span>
               <button type="button" class="btn ghost" data-cancelperson>Cancel</button>
               <button type="button" class="btn ghost" data-saveperson="again">Save and add another</button>
               <button type="button" class="btn" data-saveperson="close">Save person</button>`}
        </footer>
      </div>
    </div>`;
}
