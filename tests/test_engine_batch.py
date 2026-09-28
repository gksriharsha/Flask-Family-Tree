"""The batch API must be indistinguishable from the per-pair one.

``relationships_from_root`` exists only to be faster, never different. The moment it can
return a different list, a different order, or a different struct than calling
``relationships(graph, root, pid)`` for each ``pid``, it stops being an optimisation and
becomes a second, subtly-wrong engine. These tests pin the two together over the whole golden
fixture -- every pair, from every root -- so any divergence fails here rather than as a wrong
word in front of a relative.
"""

import pytest

from tests.test_kinship import build
from Tree.kinship import FamilyGraph, relationships, relationships_from_root
from Tree.kinship.engine import DEFAULT_DEPTH_CAP, ancestor_routes


@pytest.fixture()
def g() -> FamilyGraph:
    return build()


def test_batch_equals_per_pair_from_every_root(g):
    """The whole point of the batch API: same list, same order, same structs, every pair."""
    ids = sorted(g.people)
    for root in ids:
        batch = relationships_from_root(g, root)
        assert set(batch) == set(ids)          # one entry per person, no more, no fewer
        for pid in ids:
            assert batch[pid] == relationships(g, root, pid), (root, pid)


def test_batch_matches_per_pair_at_a_higher_cap(g):
    """The equality must hold at any cap the caller passes, not just the default."""
    for cap in (2, 4, DEFAULT_DEPTH_CAP, 12):
        batch = relationships_from_root(g, 1, cap=cap)
        for pid in g.people:
            assert batch[pid] == relationships(g, 1, pid, cap=cap), (cap, pid)


def test_batch_on_unknown_root_is_none_for_everyone(g):
    """An unknown subject relates to nobody -- exactly what the per-pair call returns."""
    missing = max(g.people) + 999
    batch = relationships_from_root(g, missing)
    assert set(batch) == set(g.people)
    for pid in g.people:
        assert batch[pid][0].kind == 'none'
        assert batch[pid] == relationships(g, missing, pid)


def test_batch_equals_per_pair_over_a_synthetic_tree(make_synthetic_family):
    """Beyond the hand-built fixture: hold the two together over a generated tree too."""
    graph = make_synthetic_family(1500, seed=11)
    root = min(graph.people)
    batch = relationships_from_root(graph, root)
    # Sampling 400 keeps the test quick while still crossing blood, affinal and none cases.
    for pid in list(graph.people)[:400]:
        assert batch[pid] == relationships(graph, root, pid), pid


# ── the indexes themselves ───────────────────────────────────────────────────────
def test_children_of_preserves_birth_year_then_id_order(g):
    """The index must not change the documented sort: birth year, then id, unknowns last."""
    # id 5 (Eshwar) is the paternal grandfather of 1/2; his children include dated and
    # undated people, so this exercises the unknown-last rule.
    for parent in sorted(g.people):
        got = g.children_of(parent)
        expected = sorted(got, key=lambda cid: (
            g.people[cid].birth_date.sort_year is None,
            g.people[cid].birth_date.sort_year or 0,
            cid,
        ))
        assert got == expected


def test_lazy_index_build_when_fields_assigned_directly():
    """Code that fills ``people``/``parents``/``unions`` without the add_* methods must still
    get correct queries -- the indexes build themselves on first use."""
    seed = build()
    bare = FamilyGraph()
    bare.people = dict(seed.people)
    bare.parents = dict(seed.parents)
    bare.unions = list(seed.unions)
    bare.birth_order = dict(seed.birth_order)
    # No add_* calls, so the indexes start empty; the queries must lazily rebuild them.
    assert bare.children == {}
    assert bare.spouse_ids(5) == seed.spouse_ids(5)
    assert bare.children_of(5) == seed.children_of(5)


def test_rebuild_indexes_is_idempotent_and_clears_the_route_cache():
    seed = build()
    # Warm the engine's per-instance route cache.
    ancestor_routes(seed, 1)
    assert hasattr(seed, '_ancestor_routes_cache')
    before_children = {p: seed.children_of(p) for p in seed.people}
    seed.rebuild_indexes()
    assert not hasattr(seed, '_ancestor_routes_cache')     # stale memo dropped
    after_children = {p: seed.children_of(p) for p in seed.people}
    assert before_children == after_children               # rebuild changed nothing


def test_empty_graph_constructs_and_queries():
    g = FamilyGraph()
    assert g.children_of(1) == []
    assert g.spouse_ids(1) == []
    assert relationships_from_root(g, 1) == {}
