"""Work out how two people are related, as structure.

Three layers, kept strictly apart:

    1. this module      — find the routes between two people
    2. Kinship structs  — degree, removal, side, parallel-vs-cross, seniority
    3. Tree.kinship.render — turn a struct into words, per language and per family

The separation is what makes the rest possible. Telugu is not a translation of English: it
splits paternal from maternal, elder from younger, and treats parallel cousins as siblings.
No table keyed on English labels can reach those distinctions, because by the time you have
an English label the information they need has already been discarded.
"""

from __future__ import annotations

from dataclasses import dataclass

from Tree.kinship.model import MALE, FamilyGraph, Kinship

#: How far up to look for a common ancestor. Also the cycle guard's ceiling.
DEFAULT_DEPTH_CAP = 8


@dataclass(frozen=True)
class _Route:
    """One way of reaching an ancestor: the path taken, and whether it left the birth line."""

    ancestor_id: int
    path: tuple[int, ...]
    adoptive: bool

    @property
    def generations(self) -> int:
        return len(self.path) - 1


#: Attribute name for the per-instance ancestor-routes memo. Underscored and set with
#: ``object.__setattr__``-free assignment (FamilyGraph is a plain, non-frozen dataclass) so it
#: never collides with a real field and is never part of equality or the repr.
_ROUTES_CACHE_ATTR = '_ancestor_routes_cache'


def _routes_cache(graph: FamilyGraph) -> dict[tuple[int, int], list[_Route]]:
    """The graph instance's ancestor-routes cache, created on first use.

    Scoped to the instance because a FamilyGraph is built once per request and thrown away;
    that is exactly the lifetime the memo should have. ``rebuild_indexes`` clears it so an
    in-place mutation cannot leave a stale route behind.
    """
    cache = getattr(graph, _ROUTES_CACHE_ATTR, None)
    if cache is None:
        cache = {}
        setattr(graph, _ROUTES_CACHE_ATTR, cache)
    return cache


def ancestor_routes(graph: FamilyGraph, person_id: int,
                    cap: int = DEFAULT_DEPTH_CAP) -> list[_Route]:
    """Every ancestor reachable from ``person_id``, keyed per *kind* of route.

    Keyed on the ancestor AND on whether the route passed through a non-birth link, so a
    person reachable both by birth and by adoption keeps both routes. Keying on the ancestor
    alone lets the shorter route delete the other one, which silently loses a real
    relationship -- the kind of thing that makes an app look like it is contradicting itself.

    The walk is iterative rather than recursive: a deep tree at a high ``cap`` would otherwise
    risk Python's recursion limit, and a batch over a ten-thousand-person tree walks this path
    ten thousand times. Results are memoised per ``(person_id, cap)`` on the graph instance --
    a graph is rebuilt per request, so the cache lives and dies with one request, and any
    in-place mutation between queries is the caller's cue to call
    :meth:`FamilyGraph.rebuild_indexes`, which also clears it.
    """
    cache = _routes_cache(graph)
    cached = cache.get((person_id, cap))
    if cached is not None:
        return cached

    best: dict[tuple[int, bool], _Route] = {}
    # Explicit stack of frames to expand, replacing the recursive `walk`. Each frame is the
    # same triple the recursive call carried: the current node, the path that reached it, and
    # whether that path has already left the birth line.
    stack: list[tuple[int, tuple[int, ...], bool]] = [(person_id, (person_id,), False)]
    while stack:
        current, path, adoptive = stack.pop()
        if len(path) - 1 > cap:
            continue
        key = (current, adoptive)
        seen = best.get(key)
        if seen is None or len(seen.path) > len(path):
            best[key] = _Route(current, path, adoptive)
        for link in reversed(graph.parent_links(current)):
            if link.parent_id in path:      # cycle guard
                continue
            stack.append((link.parent_id, (*path, link.parent_id),
                          adoptive or not link.is_birth))

    routes = list(best.values())
    cache[(person_id, cap)] = routes
    return routes


def _build(graph: FamilyGraph, subject: int, other: int,
           up: _Route, down: _Route) -> Kinship:
    """Turn one pair of routes into a Kinship struct."""
    a, b = up.generations, down.generations
    person = graph.people[other]
    sex = person.sex
    adoptive = up.adoptive or down.adoptive
    side = 'na'
    if a > 0:
        side = 'paternal' if graph.people[up.path[1]].sex == MALE else 'maternal'

    if a == 0:
        return Kinship(kind='descendant', depth=b, sex=sex, side=side, adoptive=adoptive,
                       elder=graph.seniority(subject, other))
    if b == 0:
        return Kinship(kind='ancestor', depth=a, sex=sex, side=side, adoptive=adoptive)

    if a == 1 and b == 1:
        # A full sibling is reachable through both parents. That is two routes to ONE
        # relationship, not two relationships — and "side" is not a meaningful idea for a
        # sibling anyway, so it is cleared and the two routes collapse.
        return Kinship(kind='sibling', sex=sex, side='na', adoptive=adoptive,
                       elder=graph.seniority(subject, other),
                       seniority_pair=(subject, other))

    if b == 1 and a >= 2:
        link = up.path[1]
        return Kinship(kind='parent_sibling', sex=sex, side=side,
                       link_sex=graph.people[link].sex, generations_up=a - 2,
                       elder=graph.seniority(link, other), seniority_pair=(link, other),
                       adoptive=adoptive)

    if a == 1 and b >= 2:
        link = down.path[1]
        # Same reasoning as siblings: a full sibling's child is reachable through either
        # parent, and the side of the family is not part of what they are called.
        return Kinship(kind='niblings', sex=sex, side='na', generations_down=b - 2,
                       link_sex=graph.people[link].sex,
                       # parallel vs cross is relative to the VIEWER's sex: a man's
                       # brother's child is parallel, a woman's brother's child is cross
                       parallel=graph.people[subject].sex == graph.people[link].sex,
                       elder=graph.seniority(subject, other), adoptive=adoptive)

    link_up, link_down = up.path[1], down.path[1]
    return Kinship(
        kind='cousin', degree=min(a, b) - 1, removal=abs(a - b), up=a > b,
        parallel=graph.people[link_up].sex == graph.people[link_down].sex,
        link_sex=graph.people[link_up].sex, sex=sex, side=side, adoptive=adoptive,
        elder=graph.seniority(subject, other),
        elder_than_link=graph.seniority(link_up, other),
        seniority_pair=(link_up, other) if a > b else (subject, other),
    )


def relationships(graph: FamilyGraph, subject: int, other: int,
                  cap: int = DEFAULT_DEPTH_CAP,
                  _allow_spouse_hop: bool = True) -> list[Kinship]:
    """Every genuine relationship between two people, closest first.

    Not just the nearest one. People are often connected more than one way — a marriage
    inside the family, or an adoption that moves someone between households — and each route
    is a real relationship with its own name. A route by birth and a route through an
    adoptive link are different *kinds* of relation, so the shortest of each is returned.
    """
    if subject == other:
        return [Kinship(kind='self')]
    if subject not in graph.people or other not in graph.people:
        return [Kinship(kind='none')]

    ups = ancestor_routes(graph, subject, cap)
    by_ancestor: dict[int, list[_Route]] = {}
    for route in ups:
        by_ancestor.setdefault(route.ancestor_id, []).append(route)
    return _relationships_with_ups(graph, subject, other, cap, ups, by_ancestor,
                                   _allow_spouse_hop=_allow_spouse_hop)


def closest(graph: FamilyGraph, subject: int, other: int,
            cap: int = DEFAULT_DEPTH_CAP) -> Kinship:
    """The single nearest relationship — for a compact label where only one fits."""
    return relationships(graph, subject, other, cap)[0]


def relationships_from_root(graph: FamilyGraph, root_id: int,
                            cap: int = DEFAULT_DEPTH_CAP) -> dict[int, list[Kinship]]:
    """Every person's relationship to one root, computed in a single pass.

    This is the batch form of calling ``relationships(graph, root_id, pid)`` for every ``pid``
    in the graph, and it returns exactly that: a dict from person id to the same list, in the
    same order, of the same :class:`Kinship` structs the per-pair call would produce. It is
    the shape :func:`Tree.api.routes.graph_view` wants -- that view labels every person from
    one root, and computing the root's ancestor routes once instead of once per person is what
    turns an O(N^2) page into an O(N * degree) one.

    The saving is real but narrow: the root's up-routes and the ``by_ancestor`` map are built
    once here, and each person's own down-routes still have to be walked (they are, and they
    are memoised on the graph instance, so a later per-pair call reuses them). Everything else
    -- the birth/adoptive grouping, the shortest-route selection, the signature dedup, the
    one-hop affinal spouse fallback, and the ``self`` / ``none`` special cases -- is identical
    to :func:`relationships`, deliberately, so the two can never disagree.
    """
    if root_id not in graph.people:
        # Match the per-pair contract: an unknown subject yields 'none' for every 'other'
        # that exists, and 'none' likewise for the unknown ones. relationships(root, pid)
        # returns [none] whenever either endpoint is missing.
        return {pid: [Kinship(kind='none')] for pid in graph.people}

    ups = ancestor_routes(graph, root_id, cap)
    by_ancestor: dict[int, list[_Route]] = {}
    for route in ups:
        by_ancestor.setdefault(route.ancestor_id, []).append(route)

    out: dict[int, list[Kinship]] = {}
    for other in graph.people:
        out[other] = _relationships_with_ups(graph, root_id, other, cap, ups, by_ancestor)
    return out


def _relationships_with_ups(graph: FamilyGraph, subject: int, other: int, cap: int,
                            ups: list[_Route],
                            by_ancestor: dict[int, list[_Route]],
                            _allow_spouse_hop: bool = True) -> list[Kinship]:
    """The body of :func:`relationships`, given the subject's up-routes already computed.

    Factored out so the batch path can share one computation of the root's routes across every
    ``other`` while remaining, line for line, the same algorithm the per-pair function runs.
    """
    if subject == other:
        return [Kinship(kind='self')]
    if subject not in graph.people or other not in graph.people:
        return [Kinship(kind='none')]

    downs = ancestor_routes(graph, other, cap)

    candidates: list[tuple[_Route, _Route]] = []
    for down in downs:
        for up in by_ancestor.get(down.ancestor_id, ()):
            candidates.append((up, down))

    if not candidates:
        if _allow_spouse_hop:
            # One hop only: spouse_of is symmetric, so an unguarded second hop recurses
            # between two blood-unrelated spouses forever.
            for spouse in graph.spouse_ids(other):
                via = relationships(graph, subject, spouse, cap, _allow_spouse_hop=False)[0]
                if via.kind != 'none':
                    return [Kinship(kind='affinal', via=via, sex=graph.people[other].sex,
                                    via_sex=graph.people[other].sex)]
        return [Kinship(kind='none')]

    results: list[Kinship] = []
    for group in (
        [c for c in candidates if not (c[0].adoptive or c[1].adoptive)],
        [c for c in candidates if c[0].adoptive or c[1].adoptive],
    ):
        if not group:
            continue
        shortest = min(up.generations + down.generations for up, down in group)
        seen: set[tuple] = set()
        for up, down in group:
            if up.generations + down.generations != shortest:
                continue
            built = _build(graph, subject, other, up, down)
            signature = (built.kind, built.depth, built.degree, built.removal,
                         built.generations_up, built.generations_down, built.side,
                         built.link_sex, built.parallel, built.adoptive)
            if signature in seen:
                continue
            seen.add(signature)
            results.append(built)

    return results or [Kinship(kind='none')]


def unresolved_seniority(links: list[Kinship]) -> tuple[int, int] | None:
    """The pair whose birth order would settle a term, when one is missing.

    This is what lets the interface ask for exactly the fact it needs instead of guessing.
    """
    for link in links:
        target = link.via if link.kind == 'affinal' and link.via else link
        if target.elder is None and target.seniority_pair:
            return target.seniority_pair
    return None
