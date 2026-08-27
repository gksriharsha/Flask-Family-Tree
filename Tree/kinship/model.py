"""Value types for the kinship engine.

The engine never touches the graph. It takes a plain snapshot of people, parent links and
unions, and returns *structs* — never strings. Naming happens in a separate layer, which is
what lets the same relationship be rendered in English, in Telugu, and in whichever words a
particular branch of the family uses.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field, replace

MALE = 'male'
FEMALE = 'female'
INTERSEX = 'intersex'
UNKNOWN = 'unknown'

BIOLOGICAL = 'biological'
ADOPTIVE = 'adoptive'
STEP = 'step'
FOSTER = 'foster'
GUARDIAN = 'guardian'

#: Link roles that mean "this person was not born into this parent's line".
NON_BIRTH_ROLES = frozenset({ADOPTIVE, STEP, FOSTER, GUARDIAN})


@dataclass(frozen=True)
class Person:
    id: int
    given: str
    surname: str = ''
    sex: str = UNKNOWN
    #: None is the normal case, not an edge case: most records carry no usable birth date.
    birth_year: int | None = None
    death_year: int | None = None

    @property
    def full_name(self) -> str:
        return f'{self.given} {self.surname}'.strip()


@dataclass(frozen=True)
class ParentLink:
    child_id: int
    parent_id: int
    role: str = BIOLOGICAL

    @property
    def is_birth(self) -> bool:
        return self.role not in NON_BIRTH_ROLES


@dataclass(frozen=True)
class Union:
    a_id: int
    b_id: int
    kind: str = 'marriage'
    ended: bool = False


@dataclass(frozen=True)
class Kinship:
    """One relationship between two people, as structure rather than as words.

    ``elder`` is deliberately tri-state. ``None`` means the birth order is not recorded,
    which is the common case — and Telugu cannot name a sibling or a paternal uncle without
    it, while English can.
    """

    kind: str                       # self | ancestor | descendant | sibling | parent_sibling
                                    # | niblings | cousin | affinal | none
    sex: str = UNKNOWN
    depth: int = 0                  # generations, for ancestor / descendant
    degree: int = 0                 # cousin degree
    removal: int = 0                # cousin removal
    up: bool = False                # target sits nearer the common ancestor
    generations_up: int = 0         # granduncle = 1, great-granduncle = 2
    generations_down: int = 0
    parallel: bool | None = None    # linking relatives share a sex
    side: str = 'na'                # paternal | maternal | na
    link_sex: str | None = None     # sex of the relative the route passes through
    elder: bool | None = None
    elder_than_link: bool | None = None
    adoptive: bool = False          # the route passes through a non-birth link
    via: Kinship | None = None      # affinal: the blood relative this person is married to
    via_sex: str | None = None
    #: The two people whose birth order would settle a seniority-dependent term.
    seniority_pair: tuple[int, int] | None = None

    def with_seniority(self, elder: bool | None) -> Kinship:
        return replace(self, elder=elder)


@dataclass
class FamilyGraph:
    """A snapshot the engine can walk. Built once per request from the graph database."""

    people: dict[int, Person] = field(default_factory=dict)
    #: child id -> the links naming that child's parents
    parents: dict[int, list[ParentLink]] = field(default_factory=dict)
    unions: list[Union] = field(default_factory=list)
    #: (lower id, higher id) -> the id of whichever is elder, when a person has said so
    birth_order: dict[tuple[int, int], int] = field(default_factory=dict)

    # ---- construction -------------------------------------------------------
    def add_person(self, person: Person) -> None:
        self.people[person.id] = person

    def add_parent_link(self, link: ParentLink) -> None:
        self.parents.setdefault(link.child_id, []).append(link)

    def add_union(self, union: Union) -> None:
        self.unions.append(union)

    def record_birth_order(self, elder_id: int, younger_id: int) -> None:
        self.birth_order[_pair(elder_id, younger_id)] = elder_id

    # ---- queries ------------------------------------------------------------
    def parent_links(self, child_id: int) -> list[ParentLink]:
        return self.parents.get(child_id, [])

    def parent_ids(self, child_id: int, births_only: bool = True) -> list[int]:
        return [
            link.parent_id for link in self.parent_links(child_id)
            if link.is_birth or not births_only
        ]

    def children_of(self, parent_id: int) -> list[int]:
        found = [
            child_id for child_id, links in self.parents.items()
            if any(link.parent_id == parent_id for link in links)
        ]
        # Unknown birth years sort last, in a stable order, rather than by a number
        # that does not exist.
        return sorted(found, key=lambda cid: (
            self.people[cid].birth_year is None,
            self.people[cid].birth_year or 0,
            cid,
        ))

    def spouse_ids(self, person_id: int) -> list[int]:
        out = []
        for union in self.unions:
            if union.a_id == person_id:
                out.append(union.b_id)
            elif union.b_id == person_id:
                out.append(union.a_id)
        return out

    def spouse_of(self, person_id: int) -> int | None:
        found = self.spouse_ids(person_id)
        return found[0] if found else None

    def seniority(self, x: int, y: int) -> bool | None:
        """Is ``y`` elder than ``x``? ``None`` when nothing in the record can say.

        A recorded answer from a family member wins over the dates, because someone who was
        there knows better than a placeholder.
        """
        answer = self.birth_order.get(_pair(x, y))
        if answer is not None:
            return answer == y
        bx = self.people[x].birth_year if x in self.people else None
        by = self.people[y].birth_year if y in self.people else None
        if bx is None or by is None or bx == by:
            return None
        return by < bx

    def __contains__(self, person_id: object) -> bool:
        return person_id in self.people

    def __iter__(self) -> Iterable[Person]:
        return iter(self.people.values())


def _pair(a: int, b: int) -> tuple[int, int]:
    return (a, b) if a <= b else (b, a)
