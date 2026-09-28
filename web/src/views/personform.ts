/**
 * Add and edit a person.
 *
 * The form accepts what people actually know. Every field except the given name may be left
 * empty, "not recorded" is a real answer for sex and for living, and a date can be stated at
 * any of seven precisions rather than being forced into a false `yyyy-mm-dd`.
 *
 * On the look: sections are separated by a rule and a heading rather than boxed, because a
 * card inside a card inside a sheet is three shades of the same paper and reads as a tax
 * form. Inputs are underlined rather than boxed, which is the vocabulary the rest of the app
 * already uses. And an unrecorded value is styled QUIETLY -- an olive fill on "not recorded"
 * says a choice was made when the truth is the opposite.
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
  birthPlace: string;
  deathPlace: string;
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
    birthPlace: '',
    deathPlace: '',
    attachId,
    attachRelation: 'child',
    attachRole: 'biological',
    confirmingDelete: false,
  };
}

export function draftFrom(
  p: PersonNode,
  places: { birthPlace?: string; deathPlace?: string } = {},
): PersonDraft {
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
    birthPlace: places.birthPlace ?? '',
    deathPlace: places.deathPlace ?? '',
    attachId: null,
    attachRelation: 'child',
    attachRole: 'biological',
    confirmingDelete: false,
  };
}

/** `blank` marks the choices that mean "the record does not say", which stay quiet. */
const MODES: { id: DateMode; label: string; blank?: boolean }[] = [
  { id: 'exact', label: 'Exact date' },
  { id: 'year', label: 'Year' },
  { id: 'about', label: 'About' },
  { id: 'before', label: 'Before' },
  { id: 'after', label: 'After' },
  { id: 'between', label: 'Between' },
  { id: 'unknown', label: 'Not recorded', blank: true },
];

const SEXES: { id: Sex; label: string; blank?: boolean }[] = [
  { id: 'male', label: 'Male' },
  { id: 'female', label: 'Female' },
  { id: 'intersex', label: 'Intersex' },
  { id: 'unknown', label: 'Not recorded', blank: true },
];

const LIVING: { id: 'yes' | 'no' | 'unknown'; label: string; blank?: boolean }[] = [
  { id: 'yes', label: 'Living' },
  { id: 'no', label: 'Died' },
  { id: 'unknown', label: 'Not recorded', blank: true },
];

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

function monthName(value: string): string {
  return MONTHS[Number(value) - 1] ?? value;
}

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
    default: return 'not recorded';
  }
}

/** How it will sort, in one line. The long explanations were the worst of the clutter. */
export function sorts(d: DateDraft, which: 'birth' | 'death' = 'birth'): string {
  const y = Number(d.year);
  switch (d.mode) {
    case 'exact':
      return 'A single day — sorts and ages exactly.';
    case 'year':
      return 'The whole year. No month or day is implied.';
    case 'about':
      return Number.isFinite(y) && d.year
        ? `Treated as ${y - 2}–${y + 2}. Anyone inside that window can’t be ranked against them.`
        : 'A window a couple of years wide.';
    case 'before':
      return 'An upper bound only. Still sorts before anything known to be later.';
    case 'after':
      return 'A lower bound only. Pairs with a bound from the other side to narrow a range.';
    case 'between':
      return 'Two bounds from two documents.';
    default:
      return which === 'death'
        ? 'No death date stored — which is not the same as saying they are living.'
        : 'They still hold their place through their parents and children.';
  }
}

function chips(attr: string, items: { id: string; label: string; blank?: boolean }[],
               current: string, prefix = ''): string {
  return `<div class="chips">${items
    .map((item) => {
      const on = item.id === current;
      const cls = ['chip'];
      // A chosen "not recorded" stays quiet: an olive fill there would claim a decision
      // was made when the point is that the record does not say.
      if (on) cls.push(item.blank ? 'is-blank' : 'is-on');
      return `<button type="button" class="${cls.join(' ')}" data-${attr}="${prefix}${item.id}"
                      aria-pressed="${on}">${item.label}</button>`;
    })
    .join('')}</div>`;
}

function field(key: string, label: string, value: string, kind: 'text' | 'num',
               extra = ''): string {
  return `
    <label class="f ${extra}">
      <span class="f-l">${label}</span>
      <input class="f-i" data-df="${key}" value="${escape(value)}" autocomplete="off"
             ${kind === 'num' ? 'type="number" inputmode="numeric"' : ''} />
    </label>`;
}

function dateSection(which: 'birth' | 'death', d: DateDraft, legend: string): string {
  let inputs = '';
  if (d.mode === 'exact') {
    inputs = field(`${which}.year`, 'Year', d.year, 'num', 'is-yr')
           + field(`${which}.month`, 'Month', d.month, 'num', 'is-sm')
           + field(`${which}.day`, 'Day', d.day, 'num', 'is-sm');
  } else if (d.mode === 'between') {
    inputs = field(`${which}.year`, 'Earliest', d.year, 'num', 'is-yr')
           + '<span class="joiner">and</span>'
           + field(`${which}.year2`, 'Latest', d.year2, 'num', 'is-yr');
  } else if (d.mode !== 'unknown') {
    inputs = field(`${which}.year`, 'Year', d.year, 'num', 'is-yr');
  }

  return `
    <section class="fgroup">
      <h3 class="fg-h">${legend}</h3>
      ${chips('dm', MODES, d.mode, `${which}:`)}
      ${inputs ? `<div class="frow">${inputs}</div>` : ''}
      <div class="reads${d.mode === 'unknown' ? ' is-blank' : ''}" data-preview="${which}">
        <span class="rd-v">${escape(reads(d))}</span>
        <span class="rd-n">${escape(sorts(d, which))}</span>
      </div>
    </section>`;
}

function placeField(key: 'birthPlace' | 'deathPlace', label: string, value: string): string {
  // A single free-text place. Read back through the same `data-df` path as the name fields
  // (syncDraft writes it straight onto the draft), then sent to /people/<id>/places on save.
  return `
    <section class="fgroup">
      <label class="f is-grow">
        <span class="f-l">${label} <span class="fg-opt">optional</span></span>
        <input class="f-i" data-df="${key}" value="${escape(value)}" autocomplete="off"
               placeholder="e.g. Hyderabad, India" />
      </label>
    </section>`;
}

function attachSection(draft: PersonDraft): string {
  if (draft.id !== null) return '';
  const others = (state.graph?.People ?? []).slice().sort((a, b) => a.name.localeCompare(b.name));

  return `
    <section class="fgroup">
      <h3 class="fg-h">Attach to <span class="fg-opt">optional</span></h3>
      <label class="f is-grow">
        <span class="f-l">Someone already in the tree</span>
        <select class="f-i" data-df="attachId">
          <option value="">Not yet — leave them unattached</option>
          ${others
            .map((p) => `<option value="${p.id}" ${draft.attachId === p.id ? 'selected' : ''}>${
              escape(p.name)}</option>`)
            .join('')}
        </select>
      </label>
      ${draft.attachId === null
        ? ''
        : `<div class="frow is-tight">
             ${chips('ar', [
               { id: 'parent', label: 'Is their parent' },
               { id: 'child', label: 'Is their child' },
               { id: 'spouse', label: 'Is their spouse' },
             ], draft.attachRelation)}
             ${draft.attachRelation === 'spouse'
               ? ''
               : chips('arole', [
                   { id: 'biological', label: 'By birth' },
                   { id: 'adoptive', label: 'By adoption' },
                 ], draft.attachRole)}
           </div>`}
    </section>`;
}

function linksSection(draft: PersonDraft): string {
  if (draft.id === null) return '';
  const id = draft.id;
  const links = state.graph?.ParentLinks ?? [];
  const rows: string[] = [];

  const row = (text: string, role: string, attr: string) =>
    `<li><span>${text}${role === 'biological' ? '' : ` <em>${escape(role)}</em>`}</span>
       <button type="button" ${attr}>Remove</button></li>`;

  for (const link of links.filter((l) => l.child === id)) {
    const p = person(link.parent);
    if (p) rows.push(row(`Child of <strong>${escape(p.name)}</strong>`, link.role,
                         `data-unlinkparent="${id}:${link.parent}"`));
  }
  for (const link of links.filter((l) => l.parent === id)) {
    const p = person(link.child);
    if (p) rows.push(row(`Parent of <strong>${escape(p.name)}</strong>`, link.role,
                         `data-unlinkparent="${link.child}:${id}"`));
  }
  for (const union of state.graph?.Unions ?? []) {
    if (union.a !== id && union.b !== id) continue;
    const p = person(union.a === id ? union.b : union.a);
    if (p) rows.push(row(`Married to <strong>${escape(p.name)}</strong>`, 'biological',
                         `data-unlinkunion="${union.a}:${union.b}"`));
  }

  return `
    <section class="fgroup">
      <h3 class="fg-h">Relationships</h3>
      ${rows.length === 0
        ? '<p class="fg-note">None yet. An unattached person is still a valid record.</p>'
        : `<ul class="links-list">${rows.join('')}</ul>`}
    </section>`;
}

export function renderPersonForm(draft: PersonDraft): string {
  const editing = draft.id !== null;
  const title = editing ? 'Edit this person' : 'Add a person';
  const named = draft.given.trim();

  return `
    <div class="sheet" role="dialog" aria-modal="true" aria-label="${title}">
      <div class="sheet-in">
        <header class="sheet-top">
          <div>
            <h2>${title}</h2>
            <p class="sheet-sub">Only a name is required — a record with an honest gap is
               worth more than one with an invented date.</p>
          </div>
          <button type="button" class="x" data-cancelperson aria-label="Close">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <path d="M6 6l12 12M18 6L6 18" stroke="currentColor" stroke-width="2"
                    stroke-linecap="round"/>
            </svg>
          </button>
        </header>

        <div class="sheet-body">
          <section class="fgroup is-first">
            <div class="frow">
              ${field('given', 'Given name', draft.given, 'text', 'is-grow is-hero')}
              ${field('surname', 'Surname', draft.surname, 'text', 'is-grow')}
            </div>
          </section>

          <section class="fgroup">
            <h3 class="fg-h">Identity</h3>
            <div class="sub-l">Sex on the record</div>
            ${chips('sx', SEXES, draft.sex)}
            <div class="sub-l">Living</div>
            ${chips('lv', LIVING, draft.living)}
          </section>

          ${dateSection('birth', draft.birth, 'Born')}
          ${placeField('birthPlace', 'Place of birth', draft.birthPlace)}
          ${draft.living === 'no' ? dateSection('death', draft.death, 'Died') : ''}
          ${draft.living === 'no' ? placeField('deathPlace', 'Place of death', draft.deathPlace) : ''}
          ${attachSection(draft)}
          ${linksSection(draft)}

          ${state.error ? `<p class="sheet-err">${escape(state.error)}</p>` : ''}
        </div>

        <footer class="sheet-foot">
          ${editing
            ? draft.confirmingDelete
              ? `<span class="delwarn">Remove ${escape(named || 'this person')} and every link
                   to them? The tree’s file is rewritten at once, so there is no undo.</span>
                 <button type="button" class="btn is-danger" data-deleteperson>Yes, remove</button>
                 <button type="button" class="btn is-flat" data-canceldelete>Keep</button>`
              : `<button type="button" class="btn is-flat is-danger-text" data-confirmdelete>Remove</button>
                 <span class="spacer"></span>
                 <button type="button" class="btn is-flat" data-cancelperson>Cancel</button>
                 <button type="button" class="btn is-primary" data-saveperson>Save changes</button>`
            : `<span class="spacer"></span>
               <button type="button" class="btn is-flat" data-cancelperson>Cancel</button>
               <button type="button" class="btn is-flat" data-saveperson="again">Save &amp; add another</button>
               <button type="button" class="btn is-primary" data-saveperson="close">Save person</button>`}
        </footer>
      </div>
    </div>`;
}
