"""A deterministic, dependency-free generator for large synthetic family trees.

Why this exists
---------------
The kinship engine has one golden fixture -- the hand-built family in
``tests/test_kinship.py`` -- and that family is exactly right for proving *correctness*: it
carries a within-family adoption, uncles with and without recorded birth years, and both
parallel and cross cousins. It is far too small to prove anything about *speed*. A page that
is instant over two dozen people can still take seconds over ten thousand, and the whole point
of this round is to make ten thousand fast.

So this module builds a plausible tree of any size on demand. It is:

* **Deterministic.** Given the same ``n_people`` and ``seed`` it produces byte-for-byte the
  same graph, so a perf assertion is reproducible and a failure is investigable. All randomness
  comes from a single seeded :class:`random.Random`; nothing reads the clock or the global RNG.
* **Dependency-free.** Only the standard library and :mod:`Tree.kinship.model`. Later rounds
  reuse it for API and UI perf tests, and a fixture that drags in test-only packages would
  make those harder, not easier.
* **Plausible.** Couples have one to five children; the tree runs eight to twelve generations
  deep; a small fraction of parent links are adoptive; some sibling birth orders are recorded
  and most are not; and a slice of people have no birth date at all -- because a real tree is
  mostly missing dates, and the engine's seniority logic is exercised precisely by that gap.

Shape of the tree
-----------------
The tree is grown generation by generation from a pool of founder couples. Each generation,
every couple in the *current* frontier produces a small brood; roughly half of those children
are themselves paired off with a freshly minted spouse (an in-married person with no ancestors
in the tree, exactly as a real tree acquires people), and those pairs become the frontier for
the next generation. Growth stops as soon as the requested head-count is reached, so the last
generation is usually partial -- which is realistic, and which keeps ``n_people`` exact.

Person ids are assigned in creation order starting at 1, so they are dense and stable.
"""

from __future__ import annotations

import random

from Tree.kinship.model import (
    ADOPTIVE,
    BIOLOGICAL,
    FEMALE,
    MALE,
    FamilyGraph,
    ParentLink,
    Person,
    Union,
)

#: The first founder couple is born around here; each generation adds ~28 years.
_FOUNDER_BIRTH_YEAR = 1700
_YEARS_PER_GENERATION = 28

#: Fraction of people whose birth date is left unrecorded (a real tree is mostly gaps).
_UNKNOWN_DATE_RATE = 0.25
#: Fraction of birth links replaced by an adoptive link to a same-generation couple.
_ADOPTIVE_RATE = 0.03
#: Fraction of sibling pairs whose birth order is explicitly recorded.
_RECORDED_ORDER_RATE = 0.30

_GIVEN_NAMES = (
    'Aditya', 'Bharath', 'Chandra', 'Deepa', 'Eshwar', 'Girija', 'Harinath', 'Indira',
    'Jyothi', 'Kalyani', 'Lokesh', 'Madhava', 'Nirmala', 'Padmini', 'Raghava', 'Sita',
    'Tara', 'Umesh', 'Vasanth', 'Yeshwanth', 'Bhavani', 'Chandana', 'Dinesh', 'Gowri',
)
_SURNAMES = ('Varma', 'Naidu', 'Reddy', 'Rao', 'Sastry', 'Chowdary', 'Murthy', 'Prasad')


def build_synthetic_family(n_people: int, seed: int = 0) -> FamilyGraph:
    """Build a deterministic synthetic :class:`FamilyGraph` of about ``n_people`` people.

    The head-count is met exactly: growth halts the moment the graph reaches ``n_people``, so
    ``len(graph.people) == n_people`` for any ``n_people >= 2``. ``seed`` selects one of an
    unlimited number of reproducible trees; the same ``(n_people, seed)`` always yields the
    same graph, down to ids, dates, adoptions and recorded birth orders.

    :raises ValueError: if ``n_people`` is less than 2 (a tree needs at least one couple).
    """
    if n_people < 2:
        raise ValueError('a synthetic family needs at least two people')

    rng = random.Random(seed)
    graph = FamilyGraph()
    next_id = 1

    def make_person(sex: str, generation: int) -> int:
        """Mint one person and return their id, honouring the head-count ceiling caller-side."""
        nonlocal next_id
        pid = next_id
        next_id += 1
        given = rng.choice(_GIVEN_NAMES)
        surname = rng.choice(_SURNAMES)
        # Spread births across the generation's ~28-year window, then blank a quarter of them.
        base = _FOUNDER_BIRTH_YEAR + generation * _YEARS_PER_GENERATION
        birth_year: int | None = base + rng.randint(0, _YEARS_PER_GENERATION - 1)
        if rng.random() < _UNKNOWN_DATE_RATE:
            birth_year = None
        graph.add_person(Person(id=pid, given=given, surname=surname, sex=sex,
                                birth_year=birth_year))
        return pid

    def remaining() -> int:
        return n_people - len(graph.people)

    # ── founders ────────────────────────────────────────────────────────────────
    # A handful of unrelated founding couples so the tree is a small forest at the top rather
    # than a single dynasty; that produces genuinely unrelated people (kind == 'none') as well
    # as blood kin, which the engine must handle.
    n_founder_couples = max(1, min(3, remaining() // 2))
    frontier: list[tuple[int, int]] = []
    for _ in range(n_founder_couples):
        if remaining() < 2:
            break
        husband = make_person(MALE, 0)
        wife = make_person(FEMALE, 0)
        graph.add_union(Union(a_id=husband, b_id=wife))
        frontier.append((husband, wife))

    # ── generations ──────────────────────────────────────────────────────────────
    generation = 1
    max_generations = 12
    while frontier and remaining() > 0 and generation <= max_generations:
        next_frontier: list[tuple[int, int]] = []
        for father, mother in frontier:
            if remaining() <= 0:
                break
            n_children = rng.randint(1, 5)
            children: list[int] = []
            for _ in range(n_children):
                if remaining() <= 0:
                    break
                sex = MALE if rng.random() < 0.5 else FEMALE
                child = make_person(sex, generation)
                # Most children are the biological children of this couple; a small fraction
                # are adopted in from *another* couple in the same generation instead, so the
                # engine's adoptive-route handling is exercised at scale.
                if children and rng.random() < _ADOPTIVE_RATE:
                    graph.add_parent_link(ParentLink(child, father, role=ADOPTIVE))
                    graph.add_parent_link(ParentLink(child, mother, role=ADOPTIVE))
                else:
                    graph.add_parent_link(ParentLink(child, father, role=BIOLOGICAL))
                    graph.add_parent_link(ParentLink(child, mother, role=BIOLOGICAL))
                children.append(child)

            # Record some sibling birth orders explicitly; the engine prefers a recorded order
            # over the dates, and a tree with a mix of both is what production looks like.
            for i in range(len(children) - 1):
                if rng.random() < _RECORDED_ORDER_RATE:
                    graph.record_birth_order(elder_id=children[i],
                                             younger_id=children[i + 1])

            # About half the children marry in a new (ancestor-less) spouse and carry the line
            # forward. The spouse is unrelated by blood -- a real affinal link.
            for child in children:
                if remaining() <= 0:
                    break
                if rng.random() < 0.5:
                    spouse_sex = FEMALE if graph.people[child].sex == MALE else MALE
                    spouse = make_person(spouse_sex, generation)
                    graph.add_union(Union(a_id=child, b_id=spouse))
                    next_frontier.append((child, spouse))
        frontier = next_frontier
        generation += 1

    # If we ran out of couples to expand before hitting the head-count (a very small n, or an
    # unlucky seed), top up with extra founder couples so ``len(people) == n_people`` still
    # holds. These are unrelated to the main tree, which is fine for a perf fixture.
    while remaining() >= 2:
        husband = make_person(MALE, 0)
        wife = make_person(FEMALE, 0)
        graph.add_union(Union(a_id=husband, b_id=wife))
    if remaining() == 1:
        make_person(MALE if rng.random() < 0.5 else FEMALE, 0)

    return graph
