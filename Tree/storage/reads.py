"""Windowed reads of the tree.

The whole-tree read (:func:`Tree.storage.people.load_family_graph`) loads every person; this
module loads only a *window* around one anchor — the people within a bounded number of
parent/child hops, plus their spouses. That is what lets :func:`Tree.api.reads.graph_view`
answer ``/api/v1/graph?around=<id>&generations=<n>`` in constant time regardless of how large
the tree is, instead of labelling all N people against the root on every request.

Split out of :mod:`Tree.storage.people` so that module stays under the project's 500-line
limit. It reuses that module's private row-mapper and relationship-loader, so a windowed read
builds exactly the :class:`~Tree.kinship.model.FamilyGraph` a whole-tree read would build for
the same people — the engine cannot tell the two apart.
"""

from __future__ import annotations

import sqlite3

from Tree.kinship.model import FamilyGraph
from Tree.storage.people import _load_relationships_into, _person_from_row


def window_ids(conn: sqlite3.Connection, around: int, generations: int) -> set[int]:
    """The people within ``generations`` parent/child hops of ``around``, plus their spouses.

    Walked in SQL with a recursive CTE over ``parent_link`` in both directions from the anchor:
    each step adds the parents and children of everyone reached so far, up to ``generations``
    hops. Spouses of the reached set are then added (one hop across ``union_link``), because a
    window that showed a person but not the person they married reads as broken. The anchor is
    always included even when it has no links.

    Returns a set of ids. The link tables are filtered to this set in memory by
    :func:`load_windowed_graph`, exactly as :func:`Tree.storage.people.load_family_graph`
    filters to its loaded people, so the window never references a person it did not include.
    """
    depth = max(0, int(generations))
    rows = conn.execute(
        """
        WITH RECURSIVE hop(id, d) AS (
            SELECT ?, 0
            UNION
            SELECT pl.parent_id, hop.d + 1 FROM parent_link pl
                JOIN hop ON pl.child_id = hop.id WHERE hop.d < ?
            UNION
            SELECT pl.child_id, hop.d + 1 FROM parent_link pl
                JOIN hop ON pl.parent_id = hop.id WHERE hop.d < ?
        )
        SELECT id FROM hop
        """,
        (around, depth, depth),
    ).fetchall()
    ids = {row['id'] for row in rows}
    ids.add(around)

    # Spouses of everyone in the window (one hop across a union, not counted against depth).
    if ids:
        placeholders = ','.join('?' * len(ids))
        params = list(ids)
        spouses = conn.execute(
            f'SELECT a_id, b_id FROM union_link '
            f'WHERE a_id IN ({placeholders}) OR b_id IN ({placeholders})',
            params + params,
        ).fetchall()
        for row in spouses:
            if row['a_id'] in ids or row['b_id'] in ids:
                ids.add(row['a_id'])
                ids.add(row['b_id'])
    return ids


def load_windowed_graph(conn: sqlite3.Connection, around: int,
                        generations: int) -> tuple[FamilyGraph, bool]:
    """Load only the window around ``around`` into a :class:`FamilyGraph`.

    Returns ``(graph, truncated)``. ``truncated`` is always ``False`` here — a window is
    defined by hop distance, not a head-count cap, so it is never cut short — but the flag is
    returned so the route can treat windowed and full reads uniformly. Only parent links and
    unions whose BOTH endpoints are inside the window are loaded, so no link points at a person
    the window omitted; that matches :func:`Tree.storage.people.load_family_graph`'s filter.

    A window is small (bounded by generations), so the id set is spliced straight into the
    person SELECT rather than loading the whole ``person`` table and filtering.
    """
    ids = window_ids(conn, around, generations)
    graph = FamilyGraph()
    if not ids:
        return graph, False

    placeholders = ','.join('?' * len(ids))
    for row in conn.execute(
        f'SELECT id, given, surname, sex, birth, death, living FROM person '
        f'WHERE id IN ({placeholders}) ORDER BY id',
        list(ids),
    ):
        graph.add_person(_person_from_row(row))

    _load_relationships_into(conn, graph)
    return graph, False
