"""People, the links between them, and the whole-tree read.

Mirrors the person and relationship half of :mod:`Tree.kinship.store`. The Gremlin store maps
gendered edge labels onto role-bearing links at the boundary; here the role is stored
directly, so there is nothing to translate — a ``parent_link`` row already carries the role
the engine reads.

:func:`load_family_graph` is the hot path. It issues exactly four bulk SELECTs — people,
parent links, unions, birth order — and builds the whole :class:`~Tree.kinship.model.FamilyGraph`
in memory, with no per-row query, so ten thousand people load in well under a second.
"""

from __future__ import annotations

import logging
import sqlite3

from Tree.kinship.dates import DateValue
from Tree.kinship.model import (
    BIOLOGICAL,
    FEMALE,
    MALE,
    UNKNOWN,
    FamilyGraph,
    ParentLink,
    Person,
    Union,
)

log = logging.getLogger(__name__)


def _sex(value: object) -> str:
    """Normalise a stored sex string to the model's canonical values."""
    text = str(value or '').strip().lower()
    if text in ('male', 'm'):
        return MALE
    if text in ('female', 'f'):
        return FEMALE
    return UNKNOWN


def _year(value: object) -> int | None:
    """First four digits of a stored GEDCOM date string, or None.

    Kept identical to the graph store's helper: a plain-year view for the code that only wants
    a number to show, taken from the leading four digits when they are present.
    """
    if value is None:
        return None
    text = str(value).strip()
    if len(text) >= 4 and text[:4].isdigit():
        return int(text[:4])
    return None


def _stored_sex(sex: str) -> str | None:
    """The value written to the ``sex`` column. UNKNOWN stores as NULL, not a placeholder."""
    return {MALE: 'Male', FEMALE: 'Female'}.get(sex)


def _living_int(living: bool | None) -> int | None:
    if living is None:
        return None
    return 1 if living else 0


def _living_bool(value: object) -> bool | None:
    if value is None:
        return None
    return bool(value)


def _person_from_row(row: sqlite3.Row) -> Person:
    """Build a :class:`Person` from a ``person`` row selecting the standard seven columns.

    One place to turn a row into a Person, shared by every read (whole-tree load, windowed
    load, single-person get, search, paginated page) so the mapping cannot drift between them.
    """
    return Person(
        id=row['id'],
        given=str(row['given'] or ''),
        surname=str(row['surname'] or ''),
        sex=_sex(row['sex']),
        birth=DateValue.parse(row['birth']),
        death=DateValue.parse(row['death']),
        birth_year=_year(row['birth']),
        death_year=_year(row['death']),
        living=_living_bool(row['living']),
    )


def _load_relationships_into(conn: sqlite3.Connection, graph: FamilyGraph) -> None:
    """Add every parent link, union and birth-order answer whose endpoints are already loaded.

    Shared by :func:`load_family_graph` and :func:`Tree.storage.reads.load_windowed_graph`: both
    load a set of people first, then filter the link tables to that set in memory so no link
    references a person that was not loaded. Factored out so the two readers cannot drift.
    """
    people = graph.people
    for row in conn.execute('SELECT child_id, parent_id, role FROM parent_link'):
        if row['child_id'] in people and row['parent_id'] in people:
            graph.add_parent_link(ParentLink(
                child_id=row['child_id'], parent_id=row['parent_id'],
                role=row['role'] or BIOLOGICAL))

    for row in conn.execute('SELECT a_id, b_id, kind, ended FROM union_link'):
        if row['a_id'] in people and row['b_id'] in people:
            graph.add_union(Union(
                a_id=row['a_id'], b_id=row['b_id'],
                kind=row['kind'] or 'marriage', ended=bool(row['ended'])))

    for row in conn.execute('SELECT lower_id, higher_id, elder_id FROM birth_order'):
        elder = row['elder_id']
        younger = row['higher_id'] if elder == row['lower_id'] else row['lower_id']
        if elder in people and younger in people:
            graph.record_birth_order(elder_id=elder, younger_id=younger)


# ── reading the whole tree ──────────────────────────────────────────────────────
def load_family_graph(conn: sqlite3.Connection, limit: int = 5000) -> FamilyGraph:
    """Load the whole tree in four bulk queries.

    Loading everything at family scale keeps the query count constant regardless of how many
    people are shown, exactly as the graph store does. ``limit`` bounds the people read; the
    link tables are then filtered to the loaded set in memory so a truncated read never
    references a person it did not load.
    """
    graph = FamilyGraph()

    for row in conn.execute(
        'SELECT id, given, surname, sex, birth, death, living FROM person '
        'ORDER BY id LIMIT ?',
        (limit,),
    ):
        graph.add_person(_person_from_row(row))

    _load_relationships_into(conn, graph)

    log.info('Loaded %d people, %d parent links, %d unions, %d birth-order answers.',
             len(graph.people), sum(len(v) for v in graph.parents.values()),
             len(graph.unions), len(graph.birth_order))
    return graph


# ── reading a window of the tree lives in Tree.storage.reads ─────────────────────
# window_ids / load_windowed_graph / page_people are in Tree/storage/reads.py so this module
# stays under the project's 500-line limit. They reuse _person_from_row and
# _load_relationships_into from here.


# ── writing people ──────────────────────────────────────────────────────────────
def _person_exists(conn: sqlite3.Connection, person_id: int) -> bool:
    return conn.execute(
        'SELECT 1 FROM person WHERE id = ?', (person_id,)).fetchone() is not None


def person_exists(conn: sqlite3.Connection, person_id: int) -> bool:
    """Whether a person with this id is in the tree.

    The public spelling of :func:`_person_exists`, for the routes' existence checks — the
    storage-backed replacement for the graph's ``g.V(id).hasNext()``.
    """
    return _person_exists(conn, person_id)


def get_person(conn: sqlite3.Connection, person_id: int) -> Person | None:
    """Read one person by id, or ``None`` when there is no such person.

    The single-row read the graph store did with ``g.V(id).elementMap()``; used by the face
    endpoints, which look a person up by the id a recognised encoding resolves to.
    """
    row = conn.execute(
        'SELECT id, given, surname, sex, birth, death, living FROM person WHERE id = ?',
        (person_id,),
    ).fetchone()
    if row is None:
        return None
    return _person_from_row(row)


def create_person(conn: sqlite3.Connection, given: str, surname: str = '',
                  sex: str = UNKNOWN, birth: DateValue | None = None,
                  death: DateValue | None = None, living: bool | None = None) -> int:
    """Add a person. Only a given name is required; everything else may be absent.

    No date is written unless it is genuinely known — a record with an honest gap is worth
    more than one with an invented placeholder, and placeholder birth dates are exactly what
    made every sibling's seniority unanswerable in the original data.
    """
    given = (given or '').strip()
    if not given:
        raise ValueError('A person needs a given name.')
    birth_text = birth.gedcom() if (birth is not None and birth.is_known) else None
    death_text = death.gedcom() if (death is not None and death.is_known) else None
    with conn:
        cursor = conn.execute(
            'INSERT INTO person (given, surname, sex, birth, death, living) '
            'VALUES (?, ?, ?, ?, ?, ?)',
            (given, (surname or '').strip(), _stored_sex(sex),
             birth_text, death_text, _living_int(living)),
        )
    person_id = int(cursor.lastrowid)
    log.info('Created person %s (%s)', person_id, given)
    return person_id


def update_person(conn: sqlite3.Connection, person_id: int, **fields) -> None:
    """Change some of a person's details, leaving the rest as they were.

    Absent means "leave alone". Clearing is explicit: an unknown :class:`DateValue` removes
    that date, and ``sex=UNKNOWN`` removes the recorded sex, rather than leaving a stale value
    to keep driving answers the family has since corrected.
    """
    if not _person_exists(conn, person_id):
        raise ValueError(f'No person with id {person_id}.')

    assignments: list[str] = []
    values: list[object] = []

    if 'given' in fields and fields['given'] is not None:
        assignments.append('given = ?')
        values.append(str(fields['given']).strip())
    if 'surname' in fields and fields['surname'] is not None:
        assignments.append('surname = ?')
        values.append(str(fields['surname']).strip())
    if 'sex' in fields and fields['sex'] is not None:
        # UNKNOWN clears the recorded sex (stored NULL); a known sex is written.
        assignments.append('sex = ?')
        values.append(_stored_sex(fields['sex']))
    for key, column in (('birth', 'birth'), ('death', 'death')):
        if key in fields and fields[key] is not None:
            value: DateValue = fields[key]
            assignments.append(f'{column} = ?')
            values.append(value.gedcom() if value.is_known else None)
    if 'living' in fields and fields['living'] is not None:
        assignments.append('living = ?')
        values.append(_living_int(fields['living']))

    if not assignments:
        return
    values.append(person_id)
    with conn:
        conn.execute(
            f'UPDATE person SET {", ".join(assignments)} WHERE id = ?', values)
    log.info('Updated person %s', person_id)


def delete_person(conn: sqlite3.Connection, person_id: int) -> None:
    """Remove a person and every link that referred to them.

    The foreign keys cascade, so dropping the row drops its parent links, unions, birth-order
    answers and pins with it — nothing is left pointing at somebody who is gone.
    """
    if not _person_exists(conn, person_id):
        raise ValueError(f'No person with id {person_id}.')
    with conn:
        conn.execute('DELETE FROM person WHERE id = ?', (person_id,))
    log.info('Deleted person %s', person_id)


# ── writing relationships ───────────────────────────────────────────────────────
def _creates_ancestry_cycle(conn: sqlite3.Connection, child_id: int, parent_id: int) -> bool:
    """Would making ``parent_id`` a parent of ``child_id`` close an ancestry loop?

    True when the proposed parent is already a descendant of the proposed child. Walked with a
    recursive CTE over ``parent_link`` (child -> parent), starting at the child and following
    its descendants downward: if the proposed parent turns up among them, the link would make
    somebody their own ancestor.
    """
    if child_id == parent_id:
        return True
    row = conn.execute(
        """
        WITH RECURSIVE descendants(id) AS (
            SELECT child_id FROM parent_link WHERE parent_id = ?
            UNION
            SELECT pl.child_id FROM parent_link pl
            JOIN descendants d ON pl.parent_id = d.id
        )
        SELECT 1 FROM descendants WHERE id = ? LIMIT 1
        """,
        (child_id, parent_id),
    ).fetchone()
    return row is not None


def link_parent(conn: sqlite3.Connection, child_id: int, parent_id: int,
                role: str = BIOLOGICAL) -> None:
    """Record that one person is a parent of another.

    Refuses self-parenting and any link that would make someone their own ancestor. The role
    is stored directly (``biological`` / ``adoptive`` / …); the engine reads it through
    :data:`NON_BIRTH_ROLES`, so no gendered-label translation is needed.
    """
    if child_id == parent_id:
        raise ValueError('A person cannot be their own parent.')
    if not _person_exists(conn, child_id):
        raise ValueError(f'No person with id {child_id}.')
    if not _person_exists(conn, parent_id):
        raise ValueError(f'No person with id {parent_id}.')
    if _creates_ancestry_cycle(conn, child_id, parent_id):
        raise ValueError(
            'That link would make someone their own ancestor. Check which of the two is the '
            'parent.')
    with conn:
        conn.execute(
            'INSERT INTO parent_link (child_id, parent_id, role) VALUES (?, ?, ?) '
            'ON CONFLICT(child_id, parent_id) DO UPDATE SET role = excluded.role',
            (child_id, parent_id, role))
    log.info('Linked parent %s -> child %s as %s', parent_id, child_id, role)


def unlink_parent(conn: sqlite3.Connection, child_id: int, parent_id: int) -> None:
    """Remove the parent link between the two, in either direction."""
    with conn:
        conn.execute(
            'DELETE FROM parent_link WHERE (child_id = ? AND parent_id = ?) '
            'OR (child_id = ? AND parent_id = ?)',
            (child_id, parent_id, parent_id, child_id))


def link_union(conn: sqlite3.Connection, a_id: int, b_id: int) -> None:
    """Record a marriage or partnership. Idempotent, one row per unordered pair.

    The row is keyed on the ordered pair (``a_id < b_id``), so linking the same two people
    again in either order changes nothing beyond touching the single existing row.
    """
    if a_id == b_id:
        raise ValueError('A person cannot be married to themselves.')
    if not _person_exists(conn, a_id):
        raise ValueError(f'No person with id {a_id}.')
    if not _person_exists(conn, b_id):
        raise ValueError(f'No person with id {b_id}.')
    low, high = (a_id, b_id) if a_id < b_id else (b_id, a_id)
    with conn:
        conn.execute(
            'INSERT INTO union_link (a_id, b_id) VALUES (?, ?) '
            'ON CONFLICT(a_id, b_id) DO NOTHING',
            (low, high))
    log.info('Linked union %s <-> %s', a_id, b_id)


def unlink_union(conn: sqlite3.Connection, a_id: int, b_id: int) -> None:
    """Remove a union between the two, whichever order it was stored in."""
    low, high = (a_id, b_id) if a_id < b_id else (b_id, a_id)
    with conn:
        conn.execute('DELETE FROM union_link WHERE a_id = ? AND b_id = ?', (low, high))


def record_birth_order(conn: sqlite3.Connection, elder_id: int, younger_id: int) -> None:
    """Remember that one person was born before another, replacing any prior answer.

    Stored as ``elder_id`` for the unordered pair rather than a fabricated date — that is the
    fact somebody actually knows. Recording it again for the same pair overwrites the earlier
    answer, so the latest thing the family said wins.
    """
    if elder_id == younger_id:
        raise ValueError('A person cannot be elder than themselves.')
    if not _person_exists(conn, elder_id):
        raise ValueError(f'No person with id {elder_id}.')
    if not _person_exists(conn, younger_id):
        raise ValueError(f'No person with id {younger_id}.')
    low, high = (elder_id, younger_id) if elder_id < younger_id else (younger_id, elder_id)
    with conn:
        conn.execute(
            'INSERT INTO birth_order (lower_id, higher_id, elder_id) VALUES (?, ?, ?) '
            'ON CONFLICT(lower_id, higher_id) DO UPDATE SET elder_id = excluded.elder_id',
            (low, high, elder_id))


# ── search and count ────────────────────────────────────────────────────────────
def search_people(conn: sqlite3.Connection, query: str, limit: int = 50) -> list[Person]:
    """People whose given OR surname *begins with* ``query``, case-insensitively.

    Prefix matching, not the old ``LIKE '%q%'`` substring scan. A leading ``%`` forces SQLite
    to read every row — the ``ix_person_given`` / ``ix_person_surname`` NOCASE indexes cannot
    be used for it — which is exactly the full scan this round removes. A prefix (``q%``) is a
    range the index serves directly, so search stays fast at ten thousand people.

    It still works with Telugu as well as Latin: the NOCASE collation folds only ASCII, so a
    Latin query matches case-insensitively and a Telugu query matches on the raw characters;
    both are anchored at the start of a name. The two columns are queried separately and the
    ids unioned so BOTH indexes are available to the planner, rather than an ``OR`` across
    columns that no single index covers.
    """
    needle = (query or '').strip()
    if not needle:
        return []
    # Escape LIKE wildcards in the user's text so a '%' or '_' in a name is matched literally.
    escaped = needle.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
    prefix = f'{escaped}%'
    rows = conn.execute(
        "SELECT id, given, surname, sex, birth, death, living FROM person "
        "WHERE id IN ("
        "  SELECT id FROM person WHERE given LIKE ? ESCAPE '\\' "
        "  UNION "
        "  SELECT id FROM person WHERE surname LIKE ? ESCAPE '\\'"
        ") "
        "ORDER BY given, surname, id LIMIT ?",
        (prefix, prefix, limit),
    ).fetchall()
    return [_person_from_row(row) for row in rows]


def page_people(conn: sqlite3.Connection, limit: int,
                after: tuple[str, str, int] | None = None,
                q: str | None = None) -> tuple[list[Person], bool]:
    """One keyset page of people, ordered by ``(given, surname, id)``.

    Cursor pagination, not offset: the page starts strictly after the ``(given, surname, id)``
    tuple the previous page ended on, so inserts and deletes between pages never skip or repeat
    a row the way an OFFSET does. ``after`` is that tuple, decoded from the opaque cursor by the
    route; ``None`` starts at the beginning. An optional ``q`` restricts the page to a name
    prefix, matched the same way :func:`search_people` matches, so a filtered list paginates too.

    Returns ``(people, has_more)``. One extra row beyond ``limit`` is fetched to learn whether a
    further page exists without a second COUNT; it is dropped before returning.
    """
    clauses: list[str] = []
    params: list[object] = []
    if q:
        needle = q.strip()
        if needle:
            escaped = needle.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
            prefix = f'{escaped}%'
            clauses.append("(given LIKE ? ESCAPE '\\' OR surname LIKE ? ESCAPE '\\')")
            params.extend((prefix, prefix))
    if after is not None:
        # Keyset seek: the row tuple must sort strictly after the cursor tuple, in the same
        # (given, surname, id) order the page is sorted by. Written as the lexicographic
        # expansion rather than SQLite's row-value comparison so it reads on every version.
        clauses.append('(given > ? OR (given = ? AND surname > ?) '
                        'OR (given = ? AND surname = ? AND id > ?))')
        g, s, i = after
        params.extend((g, g, s, g, s, i))
    where = f'WHERE {" AND ".join(clauses)}' if clauses else ''
    params.append(limit + 1)
    rows = conn.execute(
        f'SELECT id, given, surname, sex, birth, death, living FROM person '
        f'{where} ORDER BY given, surname, id LIMIT ?',
        params,
    ).fetchall()
    has_more = len(rows) > limit
    return [_person_from_row(row) for row in rows[:limit]], has_more


def count_people(conn: sqlite3.Connection) -> int:
    """How many people are in the tree."""
    row = conn.execute('SELECT COUNT(*) AS n FROM person').fetchone()
    return int(row['n']) if row else 0
