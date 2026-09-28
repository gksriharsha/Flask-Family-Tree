import type { PersonNode, Relationship } from '../api';
import { person, state } from '../state';
import { renderPhotoPanel } from './photos';

const escape = (text: string): string =>
  text.replace(/[&<>"']/g, (c) =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]!);

/**
 * Dates at the precision they were actually recorded.
 *
 * `years()` renders a bare `b. 1955`, which reads as a fact even when the record only said
 * "about". Showing the real wording is the whole reason the seven precisions exist.
 */
function dates(p: PersonNode): string {
  const born = p.birth.mode === 'unknown' ? null : p.birth.reads;
  const died = p.death.mode === 'unknown' ? null : p.death.reads;
  if (born === null && died === null) return 'no dates recorded';
  if (died === null) return `b. ${born}`;
  if (born === null) return `d. ${died}`;
  return `${born} – ${died}`;
}

/**
 * The action stack.
 *
 * The previous version put three equal buttons in one row of a 332px rail, so each got about
 * 93px: two labels wrapped out of a 32px button and none of the three read as the thing to do
 * next. One filled primary, two genuine peers on an equal grid, and the action that rewrites
 * every label in the tree given its own row with a subtitle -- borrowing the wide
 * icon-and-subtitle shape the export buttons already use rather than inventing one.
 */
function actions(p: PersonNode): string {
  const isRoot = p.id === state.root;
  return `
    <p class="lbl" style="margin-top:20px">Actions</p>
    <div class="acts">
      <button class="btn is-primary" data-addperson="${p.id}">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <path d="M12 5v14M5 12h14" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/>
        </svg>
        Add a relative
      </button>

      <div class="acts-pair">
        <button class="btn is-quiet" data-editperson="${p.id}">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path d="M4 20h4L19 9a2.1 2.1 0 0 0-3-3L5 17v3z" stroke="currentColor" stroke-width="1.8"
                  stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
          Edit details
        </button>
        <button class="btn is-quiet is-olive" data-showline="${p.id}">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path d="M12 3v6M12 15v6M5 9h14l-3 6H8L5 9z" stroke="currentColor" stroke-width="1.8"
                  stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
          Show line
        </button>
      </div>

      <button class="btn is-wide${isRoot ? ' is-off' : ''}"
              ${isRoot ? 'disabled' : `data-reroot="${p.id}"`}>
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <circle cx="12" cy="12" r="7.5" stroke="currentColor" stroke-width="1.7"/>
          <path d="M12 2.5v3M12 18.5v3M2.5 12h3M18.5 12h3" stroke="currentColor" stroke-width="1.7"
                stroke-linecap="round"/>
        </svg>
        <span>
          <span class="w-nm">${isRoot
            ? 'Kinship is already measured from here'
            : 'Measure kinship from here'}</span>
          <span class="w-sub">${isRoot
            ? 'Select someone else to move the reference point.'
            : 'Every label in the tree is rewritten relative to this person.'}</span>
        </span>
      </button>
    </div>`;
}

function relationshipBox(p: PersonNode, link: Relationship, index: number): string {
  const alternatives = link.alternatives.length > 0
    ? `<div class="alsorow">
         <span class="al-l">Also called &mdash; tap one to always use it for ${escape(p.given)}</span>
         ${link.alternatives
           .map(
             (alt, i) => `<button data-pin="${index}:${i}" class="${alt.added_by_family ? 'is-added' : ''}">
                 <span class="al-te">${escape(alt.term)}</span>
                 <span class="al-u">${escape(alt.usage)}</span>
               </button>`,
           )
           .join('')}
         <button class="al-add" data-addword="${index}">+ add a word</button>
       </div>`
    : '';

  const pinned = link.pinned
    ? `<div class="pinrow">
         <span>Always used for ${escape(p.given)}</span>
         <button data-unpin="${index}">Undo</button>
       </div>`
    : '';

  return `
    <div class="kinbox">
      ${link.via ? `<div class="kinvia">${escape(link.via)}</div>` : ''}
      <div class="kinrow">
        <span class="tag">EN</span>
        <span><span class="val">${escape(link.en)}</span></span>
      </div>
      <div class="kinrow is-hl">
        <span class="tag">తెలుగు</span>
        <span>
          <span class="val te">${escape(link.te)}</span>
          <span class="gloss">${escape(
            [link.roman, link.gloss].filter(Boolean).join(' — '),
          )}</span>
        </span>
      </div>
      ${pinned}
      ${alternatives}
      <div class="whyrow">${escape(link.why)}</div>
    </div>`;
}

export function renderRail(): string {
  if (state.selected === null) {
    return `<div class="rail-in"><p class="lbl">Selected</p>
      <p class="hint">Choose anyone on the tree to see how they are related to you.</p></div>`;
  }
  const p = person(state.selected);
  if (!p) return '<div class="rail-in"><p class="hint">That person is no longer in the tree.</p></div>';

  const heading = p.relationships.length > 1
    ? `Related to you in ${p.relationships.length} ways`
    : 'Relationship to you';

  const question = p.seniorityQuestion;
  const ask = question
    ? `<div class="ask">
         <h4>Which of the two is older?</h4>
         <p>Telugu picks a different word depending on which was born first, and the record
            does not say.</p>
         <div class="opts">
           <button data-elder="${question.a}" data-younger="${question.b}">${escape(question.aName)}</button>
           <button data-elder="${question.b}" data-younger="${question.a}">${escape(question.bName)}</button>
         </div>
         <p class="note">English needs no answer here &mdash; it says &ldquo;brother&rdquo; either
            way. This is the asymmetry the record has to carry.</p>
       </div>`
    : '';

  const addForm = state.addingWord
    ? `<div class="addform">
         <h4>Add a word your family uses</h4>
         <input class="te" id="word-te" placeholder="Word in Telugu" aria-label="Word in Telugu" />
         <input id="word-use" placeholder="Who says it — optional" aria-label="Who says it" />
         <div class="row">
           <button class="btn" data-saveword>Add</button>
           <button class="btn is-muted" data-cancelword>Cancel</button>
         </div>
       </div>`
    : '';

  const multi = p.relationships.length > 1
    ? `<div class="multinote">Both links are real and both are kept. Several people here are
         connected by more than one route &mdash; through a marriage inside the family, or
         through an adoption &mdash; and each route has its own name in Telugu.</div>`
    : '';

  return `
    <div class="rail-in">
      <p class="lbl">Selected</p>
      <div class="selname">${escape(p.name)}</div>
      <div class="selmeta">${escape(dates(p))} · ${escape(p.sex)}</div>

      <p class="lbl" style="margin-top:16px">${escape(heading)}</p>
      ${p.relationships.map((link, i) => relationshipBox(p, link, i)).join('')}
      ${ask}
      ${addForm}
      ${multi}

      ${actions(p)}

      ${renderPhotoPanel(p.id)}
    </div>`;
}
