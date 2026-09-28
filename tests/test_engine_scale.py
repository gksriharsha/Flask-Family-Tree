"""Performance and memory floor for a ten-thousand-person tree.

These are the assertions this round exists to satisfy: the kinship engine must stay fast and
lean at the scale a real tree reaches. They are deliberately loose relative to the numbers the
code actually posts (see the PR description) -- the budgets here are a *ceiling that catches a
regression*, not a benchmark. A change that made ``relationships_from_root`` O(N^2) again, or
that reintroduced the O(N) ``children_of`` scan, would blow past these by orders of magnitude
and fail loudly; ordinary machine-to-machine variance, including a slow CI runner, sits far
inside them.

The whole file builds the 10k tree a small, fixed number of times and runs in well under ten
seconds, so nothing here is marked ``slow``.
"""

import random
import time
import tracemalloc

import pytest

from tests.fixtures.synthetic_tree import build_synthetic_family
from Tree.kinship.engine import relationships, relationships_from_root

N_PEOPLE = 10_000
SEED = 0


@pytest.fixture(scope='module')
def big_family():
    """One 10k tree shared across the timing tests (memory is measured on a fresh build)."""
    return build_synthetic_family(N_PEOPLE, seed=SEED)


def test_relationships_from_root_over_all_people_under_2s(big_family):
    root = min(big_family.people)
    start = time.perf_counter()
    result = relationships_from_root(big_family, root)
    elapsed = time.perf_counter() - start
    assert len(result) == N_PEOPLE
    assert elapsed < 2.0, f'relationships_from_root took {elapsed:.3f}s'


def test_two_hundred_random_pairs_under_half_a_second(big_family):
    ids = list(big_family.people)
    rng = random.Random(1)
    pairs = [(rng.choice(ids), rng.choice(ids)) for _ in range(200)]
    start = time.perf_counter()
    for a, b in pairs:
        relationships(big_family, a, b)
    elapsed = time.perf_counter() - start
    assert elapsed < 0.5, f'200 random pairs took {elapsed:.4f}s'


def test_children_of_for_all_people_under_200ms(big_family):
    start = time.perf_counter()
    for pid in big_family.people:
        big_family.children_of(pid)
    elapsed = time.perf_counter() - start
    assert elapsed < 0.2, f'children_of over all people took {elapsed:.4f}s'


def test_graph_peak_memory_under_150mb():
    """A fresh build, measured end to end, must stay well under 150 MB of Python heap."""
    tracemalloc.start()
    try:
        graph = build_synthetic_family(N_PEOPLE, seed=SEED)
        assert len(graph.people) == N_PEOPLE
        _current, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    peak_mb = peak / 1_000_000
    assert peak_mb < 150.0, f'peak FamilyGraph memory was {peak_mb:.1f} MB'


def test_deep_tree_resolves_at_cap_12_without_recursion_error():
    """The iterative ancestor walk must handle a high cap on a deep tree without blowing the
    Python recursion limit -- the reason the recursive walk was converted."""
    graph = build_synthetic_family(N_PEOPLE, seed=SEED)
    root = min(graph.people)
    # cap 12 exceeds the DEFAULT_DEPTH_CAP of 8; the batch must complete without raising.
    result = relationships_from_root(graph, root, cap=12)
    assert len(result) == N_PEOPLE
    # And a per-pair query at cap 12 for a deep descendant must also resolve.
    ids = list(graph.people)
    rng = random.Random(2)
    for _ in range(50):
        a, b = rng.choice(ids), rng.choice(ids)
        assert relationships(graph, a, b, cap=12)      # non-empty list, no exception
