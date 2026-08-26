import type { PersonNode, Relationship } from '../api';
import { person, state, years } from '../state';

const escape = (text: string): string =>
  text.replace(/[&<>"']/g, (c) =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]!);

function relationshipBox(p: PersonNode, link: Relationship, index: number): string {
  const alternatives = link.alternatives.length > 0
    ? `<div class="alsorow">
         <span class="al-l">Also called &mdash; tap one to always use it for ${escape(p.given)}</span>
         ${link.alternatives
           .map(
             (alt, i) => `<button data-pin="${index}:${i}" class="${alt.added_by_family ? 'added' : ''}">
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
      <div class="kinrow hl">
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
           <button class="btn quiet" data-cancelword>Cancel</button>
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
      <div class="selmeta">${escape(years(p))} · ${escape(p.sex)}</div>

      <p class="lbl" style="margin-top:16px">${escape(heading)}</p>
      ${p.relationships.map((link, i) => relationshipBox(p, link, i)).join('')}
      ${ask}
      ${addForm}
      ${multi}

      <div class="acts">
        <button class="btn ghost" data-reroot="${p.id}">Measure from here</button>
      </div>
    </div>`;
}
