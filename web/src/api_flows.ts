/**
 * Client for the endpoints the SQLite cutover left unfinished: places and photographs.
 *
 * Kept separate from `api.ts` (which is the people/links/graph surface) so the new flows can
 * grow their own client without touching the established one. The token is read from the same
 * localStorage key `api.ts` writes, so both clients authenticate identically without sharing
 * module state.
 */

const TOKEN_KEY = 'familytree.token';

function token(): string {
  try {
    return localStorage.getItem(TOKEN_KEY) ?? '';
  } catch {
    return '';
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const t = token();
  if (t) headers.set('X-API-Token', t);
  // FormData sets its own multipart Content-Type; a JSON body needs it set explicitly.
  if (init.body && !(init.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json');
  }
  const response = await fetch(path, { ...init, headers });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error((payload as { Message?: string }).Message ?? response.statusText);
  }
  return payload as T;
}

export interface Places {
  birthPlace: string;
  deathPlace: string;
}

export interface Photo {
  id: number;
  filename: string;
  caption: string;
  personId: number | null;
  createdAt: string;
  /** Same-origin URL the browser can put straight in an <img src>. */
  url: string;
}

export const flowsApi = {
  /** Where a person was born and died. */
  places: (personId: number) =>
    request<Places & { Person: number }>(`/api/v1/people/${personId}/places`),

  /** Set a person's birth and/or death place. Absent keys are left as they were. */
  setPlaces: (personId: number, places: Partial<Places>) =>
    request<Places & { Person: number }>(`/api/v1/people/${personId}/places`, {
      method: 'PATCH',
      body: JSON.stringify(places),
    }),

  /** Every photo, or only one person's when `personId` is given. */
  photos: (personId?: number) => {
    const q = personId === undefined ? '' : `?person=${personId}`;
    return request<{ Photos: Photo[] }>(`/api/v1/photos${q}`);
  },

  /** Upload a photo, optionally captioned and attached to a person. */
  uploadPhoto: (file: File, caption = '', personId?: number) => {
    const form = new FormData();
    form.append('image', file);
    if (caption) form.append('caption', caption);
    if (personId !== undefined) form.append('personId', String(personId));
    return request<{ Photo: Photo }>('/api/v1/photos', { method: 'POST', body: form });
  },

  /** Attach a photo to a person, or detach it with `null`. */
  attachPhoto: (photoId: number, personId: number | null) =>
    request<{ Photo: Photo }>(`/api/v1/photos/${photoId}/attach`, {
      method: 'POST',
      body: JSON.stringify({ personId }),
    }),

  /** Remove a photo and its stored file. */
  deletePhoto: (photoId: number) =>
    request<{ Message: string }>(`/api/v1/photos/${photoId}`, { method: 'DELETE' }),
};
