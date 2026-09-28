"""The one family both the engine tests and the SQLite-store tests are built on.

``test_kinship.py`` proved the engine against a hand-built :class:`FamilyGraph`; the SQLite
store has to reproduce that same family through its *write* functions and show the engine
returns identical structs. Rather than describe the family twice, its shape lives here as
data — a list of people, parent links, adoptive links, unions — and both the in-memory
builder and the SQLite builder consume it.

``build()`` returns exactly the graph ``test_kinship.py`` built inline, so that suite's
assertions are unchanged.
"""

from __future__ import annotations

from Tree.kinship import (
    ADOPTIVE,
    FEMALE,
    MALE,
    FamilyGraph,
    ParentLink,
    Person,
    Union,
)

#: (id, given, sex, birth year or None). The shapes that actually occur: uncles with and
#: without a recorded year, both parallel and cross cousins, a within-family adoption.
PEOPLE: tuple[tuple[int, str, str, int | None], ...] = (
    (1, 'Aditya Varun', MALE, 1990), (2, 'Bharath Kiran', MALE, 1993),
    (3, 'Chandra Mohan', MALE, 1958), (4, 'Deepa Latha', FEMALE, 1962),
    (5, 'Eshwar Datta', MALE, 1928), (6, 'Girija', FEMALE, 1932),
    (8, 'Parent1', MALE, 1901), (9, 'Parent2', FEMALE, 1905),
    (7, 'Harinath', MALE, None),          # no recorded birth year
    (10, 'Kalyani Naidu', FEMALE, 1959),
    (11, 'Lokesh', MALE, 1991), (29, 'Manoj', MALE, 1995),
    (12, 'Madhava', MALE, None),           # no recorded birth year
    (13, 'Nirmala', FEMALE, 1957),
    (14, 'Padmini', FEMALE, 1984), (15, 'Raghava', MALE, 1987),
    (20, 'Yeshwanth', MALE, 1964), (21, 'Bhavani', FEMALE, 1966),
    (22, 'Chandana Sri', FEMALE, 1992),
    (23, 'Dinesh', MALE, 1957), (24, 'Gowri', FEMALE, 1961),
    (25, 'Hema', FEMALE, 1986), (26, 'Indira', FEMALE, 1989),
)

SURNAME = 'Varma'

#: (child, parent) birth links.
BIRTH_LINKS: tuple[tuple[int, int], ...] = (
    (1, 3), (1, 4), (2, 3), (2, 4),
    (6, 8), (6, 9),
    (3, 5), (3, 6), (12, 5), (12, 6), (24, 5), (24, 6), (20, 5), (20, 6),
    (7, 5), (7, 6),
    (11, 7), (11, 10), (29, 7), (29, 10),
    (14, 12), (14, 13), (15, 12), (15, 13),
    (25, 23), (25, 24), (26, 23), (26, 24),
    (22, 20), (22, 21),
)

#: (child, parent) adoptive links — the within-family adoption: born to 5+6, adopted by
#: Girija's own parents.
ADOPTIVE_LINKS: tuple[tuple[int, int], ...] = (
    (7, 8), (7, 9),
)

#: Marriages and partnerships.
UNIONS: tuple[tuple[int, int], ...] = (
    (3, 4), (5, 6), (7, 10), (12, 13), (23, 24), (20, 21), (8, 9),
)


def build() -> FamilyGraph:
    """The hand-built in-memory graph, identical to what ``test_kinship.py`` used inline."""
    g = FamilyGraph()
    for pid, given, sex, born in PEOPLE:
        g.add_person(Person(id=pid, given=given, surname=SURNAME, sex=sex, birth_year=born))
    for child, parent in BIRTH_LINKS:
        g.add_parent_link(ParentLink(child_id=child, parent_id=parent))
    for child, parent in ADOPTIVE_LINKS:
        g.add_parent_link(ParentLink(child_id=child, parent_id=parent, role=ADOPTIVE))
    for a, b in UNIONS:
        g.add_union(Union(a_id=a, b_id=b))
    return g
