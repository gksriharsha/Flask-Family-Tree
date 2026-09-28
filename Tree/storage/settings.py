"""The tree's own settings — the SQLite equivalent of the graph's ``TreeSettings`` vertex.

:mod:`Tree.gedcom.store` reads a single ``TreeSettings`` vertex carrying ``Name``,
``Gedcom_path`` and ``Created``, and writes it when a tree is created. The cutover item will
port that code to this backend, so the store offers the same read/write against a key/value
``tree_settings`` table: :func:`save_tree_settings` upserts arbitrary named fields, and
:func:`load_tree_settings` returns them as a dict — or ``None`` when nothing has been saved,
which is how the graph store signals "no tree created yet".
"""

from __future__ import annotations

import sqlite3


def load_tree_settings(conn: sqlite3.Connection) -> dict | None:
    """Every saved setting as a ``{key: value}`` dict, or ``None`` when none are saved.

    ``None`` (rather than an empty dict) is the "no tree yet" signal, matching the graph
    store's ``load_settings`` returning ``None`` when the ``TreeSettings`` vertex is absent.
    """
    rows = conn.execute('SELECT key, value FROM tree_settings').fetchall()
    if not rows:
        return None
    return {row['key']: row['value'] for row in rows}


def save_tree_settings(conn: sqlite3.Connection, **fields: object) -> None:
    """Upsert named settings. Existing keys are overwritten; others are left alone.

    Values are stored as text; ``None`` is stored as SQL NULL. Passing no fields is a no-op.
    """
    if not fields:
        return
    with conn:
        for key, value in fields.items():
            stored = None if value is None else str(value)
            conn.execute(
                'INSERT INTO tree_settings (key, value) VALUES (?, ?) '
                'ON CONFLICT(key) DO UPDATE SET value = excluded.value',
                (key, stored))
