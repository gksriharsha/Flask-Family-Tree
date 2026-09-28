"""The words a family records, and the pins onto individual people.

Mirrors the vocabulary half of :mod:`Tree.kinship.store`. A ``kinship_term`` row is a word the
family added; a ``pinned_term`` row says "always use this word for this person". The reader
builds a :class:`~Tree.kinship.vocabulary.Vocabulary` for one side of the family from those two
tables, exactly as the graph store builds it from ``KinshipTerm`` vertices and ``PINNED_TERM``
edges.
"""

from __future__ import annotations

import sqlite3

from Tree.kinship.vocabulary import PATERNAL, Variant, Vocabulary
from Tree.storage.people import _person_exists


def load_vocabulary(conn: sqlite3.Connection, side: str = PATERNAL,
                    limit: int = 2000) -> Vocabulary:
    """The words this family has recorded for one side, plus any pins onto people."""
    vocab = Vocabulary(side=side)

    for row in conn.execute(
        'SELECT base_term, term, roman, usage FROM kinship_term WHERE side = ? '
        'ORDER BY id LIMIT ?',
        (side, limit),
    ):
        base = str(row['base_term'] or '')
        if not base:
            continue
        vocab.added.setdefault(base, []).append(Variant(
            term=str(row['term'] or ''),
            roman=str(row['roman'] or ''),
            usage=str(row['usage'] or 'added by your family'),
            added_by_family=True,
        ))

    for row in conn.execute(
        'SELECT p.person_id AS person_id, p.base_term AS base_term, '
        '       t.term AS term, t.roman AS roman '
        'FROM pinned_term p JOIN kinship_term t ON t.id = p.term_id'
    ):
        vocab.pins[(row['person_id'], row['base_term'])] = Variant(
            term=str(row['term'] or ''), roman=str(row['roman'] or ''))
    return vocab


def add_word(conn: sqlite3.Connection, base_term: str, term: str, roman: str = '',
             usage: str = '', side: str = PATERNAL) -> int:
    """Record a word the family uses. Returns the term's row id, existing or new.

    Idempotent on the ``(base_term, term, side)`` triple, like the graph store: adding the same
    word twice returns the same id rather than duplicating it.
    """
    existing = conn.execute(
        'SELECT id FROM kinship_term WHERE base_term = ? AND term = ? AND side = ?',
        (base_term, term, side),
    ).fetchone()
    if existing is not None:
        return int(existing['id'])
    with conn:
        cursor = conn.execute(
            'INSERT INTO kinship_term (base_term, term, roman, usage, side) '
            'VALUES (?, ?, ?, ?, ?)',
            (base_term, term, roman, usage or 'added by your family', side))
    return int(cursor.lastrowid)


def pin_term(conn: sqlite3.Connection, person_id: int, base_term: str,
             term_id: int) -> None:
    """Always use this word for this person.

    Replaces any prior pin for the same person and base term, so a person carries at most one
    pinned word per base term.
    """
    if not _person_exists(conn, person_id):
        raise ValueError(f'No person with id {person_id}.')
    if conn.execute('SELECT 1 FROM kinship_term WHERE id = ?', (term_id,)).fetchone() is None:
        raise ValueError(f'No kinship term with id {term_id}.')
    with conn:
        conn.execute(
            'INSERT INTO pinned_term (person_id, base_term, term_id) VALUES (?, ?, ?) '
            'ON CONFLICT(person_id, base_term) DO UPDATE SET term_id = excluded.term_id',
            (person_id, base_term, term_id))


def unpin_term(conn: sqlite3.Connection, person_id: int, base_term: str) -> None:
    """Remove the pin for this person and base term, if any."""
    with conn:
        conn.execute(
            'DELETE FROM pinned_term WHERE person_id = ? AND base_term = ?',
            (person_id, base_term))
