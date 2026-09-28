"""Birth and death places for a person.

The old Gremlin build carried ``Place_of_birth`` / ``Place_of_death`` on the person vertex and
a ``/get/location`` blueprint that geocoded them; the SQLite cutover dropped both. A place is
core genealogy data — every GEDCOM ``BIRT``/``DEAT`` event can carry a ``PLAC`` — so the two
columns are added back here (schema v2) as plain text, without the coordinate scraping that
made the old endpoint a liability.

Kept in its own module rather than appended to :mod:`Tree.storage.people` so that file stays
well under the project's 500-line limit and the places surface can be read and tested on its
own. The functions take a :class:`sqlite3.Connection`, exactly like the rest of the store.
"""

from __future__ import annotations

import sqlite3


def _clean(value: object) -> str | None:
    """A trimmed place string, or ``None`` when it is empty — NULL, never a placeholder."""
    text = str(value or '').strip()
    return text or None


def get_places(conn: sqlite3.Connection, person_id: int) -> dict:
    """The birth and death places for one person as ``{'birthPlace', 'deathPlace'}``.

    Missing values come back as empty strings, so the interface can bind them to text inputs
    without a null check; the stored value itself is NULL when unrecorded.
    """
    row = conn.execute(
        'SELECT birth_place, death_place FROM person WHERE id = ?', (person_id,)
    ).fetchone()
    if row is None:
        raise ValueError(f'No person with id {person_id}.')
    return {
        'birthPlace': str(row['birth_place'] or ''),
        'deathPlace': str(row['death_place'] or ''),
    }


def all_places(conn: sqlite3.Connection) -> dict[int, dict]:
    """Every person who has a birth or death place, keyed by id.

    Used by the read that decorates the whole-tree payload with places in one query rather
    than N. People with neither place recorded are omitted, so the map is small.
    """
    places: dict[int, dict] = {}
    for row in conn.execute(
        'SELECT id, birth_place, death_place FROM person '
        'WHERE birth_place IS NOT NULL OR death_place IS NOT NULL'
    ):
        places[int(row['id'])] = {
            'birthPlace': str(row['birth_place'] or ''),
            'deathPlace': str(row['death_place'] or ''),
        }
    return places


def set_places(conn: sqlite3.Connection, person_id: int,
               birth_place: object = ..., death_place: object = ...) -> None:
    """Set a person's birth and/or death place. An omitted argument is left as it was.

    ``...`` (the sentinel) means "leave this column alone"; an explicit value — including an
    empty string — is written, with the empty string clearing the place to NULL. This mirrors
    :func:`Tree.storage.people.update_person`'s "absent means leave alone, explicit means set"
    contract, so a partial edit never blanks a place the caller did not mention.
    """
    if conn.execute('SELECT 1 FROM person WHERE id = ?', (person_id,)).fetchone() is None:
        raise ValueError(f'No person with id {person_id}.')

    assignments: list[str] = []
    values: list[object] = []
    if birth_place is not ...:
        assignments.append('birth_place = ?')
        values.append(_clean(birth_place))
    if death_place is not ...:
        assignments.append('death_place = ?')
        values.append(_clean(death_place))
    if not assignments:
        return
    values.append(person_id)
    with conn:
        conn.execute(
            f'UPDATE person SET {", ".join(assignments)} WHERE id = ?', values)
