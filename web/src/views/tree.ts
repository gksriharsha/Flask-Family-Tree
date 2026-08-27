import type { PersonNode } from '../api';
import {
  childrenOf,
  frame,
  isAdoptedInto,
  label,
  onRootLine,
  person,
  spouseOf,
  state,
  years,
} from '../state';

const escape = (text: string): string =>
  text.replace(/[&<>"']/g, (c) =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]!);

function card(p: PersonNode, compact: boolean): string {
  const classes = ['card'];
  if (compact) classes.push('compact');
  if (p.id === state.selected) classes.push('sel');
  if (p.id === state.root) classes.push('focus');
  if (isAdoptedInto(p.id)) classes.push('adopt');

  const first = p.relationships[0];
  const chipOpen = state.lang !== 'en' && first?.unresolved ? ' is-open' : '';
  const multiple = p.relationships.length > 1 && p.id !== state.root;

  return `
    <button class="${classes.join(' ')}" data-person="${p.id}">
      ${p.id === state.root ? '<span class="rootpin">You</span>' : ''}
      ${isAdoptedInto(p.id) ? '<span class="chip-adopt">Adopted</span>' : ''}
      <span class="card-top">
        <span class="sym ${p.sex === 'female' ? 'female' : ''}"></span>
        <span>
          <span class="nm">${escape(p.name)}</span>
        </span>
      </span>
      <span class="yrs">${escape(years(p))}</span>
      <span class="kin${chipOpen}">${escape(label(p))}</span>
      ${multiple
        ? `<span class="links">${p.relationships.length} ways related to you</span>`
        : ''}
    </button>`;
}

function couple(aId: number, bId: number | undefined, compact: boolean): string {
  const a = person(aId);
  if (!a) return '';
  const b = bId === undefined ? undefined : person(bId);
  return `<div class="couple">${card(a, compact)}${
    b ? `<span class="knot"></span>${card(b, true)}` : ''
  }</div>`;
}

function branch(branchId: number): string {
  const p = person(branchId);
  if (!p) return '';
  const kids = childrenOf(branchId);
  const isOpen = state.open.has(branchId) || onRootLine(branchId);
  const spouse = isOpen ? spouseOf(branchId) : undefined;

  const kidRow = isOpen && kids.length > 0
    ? `<div class="kidrow${kids.length > 1 ? ' multi' : ''}">
         ${kids
           .map((id) => {
             const kid = person(id);
             return kid
               ? `<div class="kid${kids.length > 1 ? ' tick' : ''}">${card(kid, true)}</div>`
               : '';
           })
           .join('')}
       </div>`
    : '';

  const toggle = !isOpen && kids.length > 0
    ? `<button class="expand" data-open="${branchId}">
         + ${kids.length} ${kids.length === 1 ? 'child' : 'children'}
       </button>`
    : '';

  return `<div class="branch">${couple(branchId, spouse, !onRootLine(branchId))}${kidRow}${toggle}</div>`;
}

export function renderTree(): string {
  if (state.root === null) return '<div class="state"><p>Nothing to show yet.</p></div>';
  const { top, branchIds } = frame(state.root);
  const hasTop = top.length > 0;

  const topRow = hasTop
    ? `<div class="genrow">${couple(top[0]!, top[1], false)}</div>`
    : '';

  const rowClasses = ['branchrow'];
  if (hasTop) rowClasses.push('hastop');
  if (branchIds.length > 1) rowClasses.push('multi');

  return `
    <div class="canvas">
      <div class="canvas-in">
        ${topRow}
        <div class="${rowClasses.join(' ')}">
          ${branchIds.map((id) => branch(id)).join('')}
        </div>
      </div>
    </div>`;
}
