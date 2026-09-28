/**
 * The photo panel — the one UI for the photograph endpoints PR #7 shipped without a face.
 *
 * Deliberately minimal and read-from-state: it renders whatever `state.photos` holds for the
 * selected person (loaded in events.ts when the selection changes), offers a file input that
 * uploads-and-attaches to that person, and a delete that asks once before removing. It uses
 * ONLY the existing `flowsApi` photo functions — no new client, no backend change, no
 * face-recognition UI. Everything is styled from the tokens with the block / is- convention,
 * so tools/check_design_css.py covers it like every other surface.
 */
import { state } from '../state';

const escape = (text: string): string =>
  text.replace(/[&<>"']/g, (c) =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]!);

/**
 * The panel for the currently-selected person. Shows a loading line while a fresh person's
 * photos are still in flight (photosFor lagging selected), the thumbnails once they arrive,
 * or a ledger-voice empty state when the person has none.
 */
export function renderPhotoPanel(personId: number): string {
  const ready = state.photosFor === personId;
  const photos = ready ? state.photos : [];
  const busy = state.photoBusy;

  let body: string;
  if (!ready) {
    body = '<p class="photos-note">Loading photographs…</p>';
  } else if (photos.length === 0) {
    body = '<p class="photos-note is-empty">No photos yet. Add one below — a face puts a name in context.</p>';
  } else {
    body = `<div class="photos-grid">${photos
      .map((photo) => {
        const confirming = state.confirmingPhotoDelete === photo.id;
        const alt = photo.caption ? escape(photo.caption) : 'Photograph';
        return `
          <figure class="photo${confirming ? ' is-confirming' : ''}">
            <img class="photo-img" src="${escape(photo.url)}" alt="${alt}" loading="lazy" />
            ${photo.caption ? `<figcaption class="photo-cap">${escape(photo.caption)}</figcaption>` : ''}
            ${confirming
              ? `<div class="photo-confirm">
                   <span>Remove this photograph?</span>
                   <button type="button" class="btn is-danger" data-photodelete="${photo.id}"
                           ${busy ? 'disabled' : ''}>Remove</button>
                   <button type="button" class="btn is-flat" data-photodeletecancel>Keep</button>
                 </div>`
              : `<button type="button" class="photo-x" data-photodeleteask="${photo.id}"
                         aria-label="Remove photograph" ${busy ? 'disabled' : ''}>
                   <svg width="13" height="13" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                     <path d="M6 6l12 12M18 6L6 18" stroke="currentColor" stroke-width="2"
                           stroke-linecap="round"/>
                   </svg>
                 </button>`}
          </figure>`;
      })
      .join('')}</div>`;
  }

  return `
    <div class="rail-sec photos">
      <p class="lbl">Photographs</p>
      ${body}
      <label class="photos-add${busy ? ' is-busy' : ''}">
        <input type="file" id="photo-file" accept="image/*" data-photoupload="${personId}"
               aria-label="Add a photograph of this person" ${busy ? 'disabled' : ''} />
        <span>${busy ? 'Working…' : 'Add a photograph'}</span>
      </label>
    </div>`;
}
