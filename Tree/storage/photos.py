"""Photographs, and which person each is of.

The old Gremlin photo feature was the face-recognition pipeline in :mod:`Tree.faces`, which
depends on ``dlib`` — a source-only build. That left the app with *no* photo capability at all
on any install without the toolchain, including CI: you could not upload a picture, list one,
or attach one to a person. This module is the plain, always-available half — store a file,
caption it, attach it to a person, list the lot — with face recognition remaining the optional
enhancement layered on top.

A photo row records the stored file's name (the file itself lives under
``UPLOAD_IMAGE_PATH``), an optional caption, and the id of the person it is of. Deleting a
person leaves their photos in place but unattached (``ON DELETE SET NULL``), because a
photograph of a gathering is still worth keeping after one of the people in it is removed.
"""

from __future__ import annotations

import sqlite3


def _row(row: sqlite3.Row) -> dict:
    return {
        'id': int(row['id']),
        'filename': str(row['filename']),
        'caption': str(row['caption'] or ''),
        'personId': row['person_id'],
        'createdAt': str(row['created_at']),
    }


def add_photo(conn: sqlite3.Connection, filename: str, caption: str = '',
              person_id: int | None = None) -> int:
    """Record a stored photo, optionally attached to a person. Returns the new photo id."""
    name = (filename or '').strip()
    if not name:
        raise ValueError('A photo needs a stored filename.')
    if person_id is not None and conn.execute(
            'SELECT 1 FROM person WHERE id = ?', (person_id,)).fetchone() is None:
        raise ValueError(f'No person with id {person_id}.')
    with conn:
        cursor = conn.execute(
            'INSERT INTO photo (filename, caption, person_id) VALUES (?, ?, ?)',
            (name, (caption or '').strip(), person_id))
    return int(cursor.lastrowid)


def get_photo(conn: sqlite3.Connection, photo_id: int) -> dict | None:
    """One photo by id, or ``None`` when there is no such photo."""
    row = conn.execute(
        'SELECT id, filename, caption, person_id, created_at FROM photo WHERE id = ?',
        (photo_id,),
    ).fetchone()
    return _row(row) if row is not None else None


def list_photos(conn: sqlite3.Connection, person_id: int | None = None,
                limit: int = 500) -> list[dict]:
    """Every photo, newest first — or only those attached to one person when ``person_id`` is
    given."""
    if person_id is None:
        rows = conn.execute(
            'SELECT id, filename, caption, person_id, created_at FROM photo '
            'ORDER BY id DESC LIMIT ?', (limit,),
        ).fetchall()
    else:
        rows = conn.execute(
            'SELECT id, filename, caption, person_id, created_at FROM photo '
            'WHERE person_id = ? ORDER BY id DESC LIMIT ?', (person_id, limit),
        ).fetchall()
    return [_row(row) for row in rows]


def attach_photo(conn: sqlite3.Connection, photo_id: int, person_id: int | None) -> None:
    """Attach a photo to a person, or detach it when ``person_id`` is ``None``."""
    if conn.execute('SELECT 1 FROM photo WHERE id = ?', (photo_id,)).fetchone() is None:
        raise ValueError(f'No photo with id {photo_id}.')
    if person_id is not None and conn.execute(
            'SELECT 1 FROM person WHERE id = ?', (person_id,)).fetchone() is None:
        raise ValueError(f'No person with id {person_id}.')
    with conn:
        conn.execute('UPDATE photo SET person_id = ? WHERE id = ?', (person_id, photo_id))


def delete_photo(conn: sqlite3.Connection, photo_id: int) -> str:
    """Remove a photo row and return its stored filename, so the caller can unlink the file."""
    row = conn.execute('SELECT filename FROM photo WHERE id = ?', (photo_id,)).fetchone()
    if row is None:
        raise ValueError(f'No photo with id {photo_id}.')
    with conn:
        conn.execute('DELETE FROM photo WHERE id = ?', (photo_id,))
    return str(row['filename'])
