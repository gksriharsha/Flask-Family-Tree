"""A SQLite storage backend that mirrors :mod:`Tree.kinship.store`.

The kinship engine and the API routes speak to a *store* through a fixed set of functions:
:func:`load_family_graph`, the person writers, the link writers, the seniority writer, and
the vocabulary readers/writers. :mod:`Tree.kinship.store` implements that surface against
JanusGraph; this package implements the identical surface against a local SQLite file, so the
graph store can be swapped out later with no change to the engine or the routes.

Every public function here takes a :class:`sqlite3.Connection` in place of the Gremlin ``g``
traversal source, and carries the same semantics — a name-only ``create_person``, no
placeholder dates, an explicit date/sex clear on ``update_person``, a cascading
``delete_person``, a cycle-refusing ``link_parent``, an idempotent one-row-per-pair
``link_union``, and a birth-order answer that replaces any prior one for the pair.
"""

from __future__ import annotations

from Tree.storage.people import (
    count_people,
    create_person,
    delete_person,
    get_person,
    link_parent,
    link_union,
    load_family_graph,
    page_people,
    person_exists,
    record_birth_order,
    search_people,
    unlink_parent,
    unlink_union,
    update_person,
)
from Tree.storage.reads import (
    load_windowed_graph,
    window_ids,
)
from Tree.storage.schema import (
    SCHEMA_VERSION,
    open_database,
)
from Tree.storage.settings import (
    load_tree_settings,
    save_tree_settings,
)
from Tree.storage.vocabulary import (
    add_word,
    load_vocabulary,
    pin_term,
    unpin_term,
)

__all__ = [
    'SCHEMA_VERSION',
    'add_word',
    'count_people',
    'create_person',
    'delete_person',
    'get_person',
    'link_parent',
    'link_union',
    'load_family_graph',
    'load_tree_settings',
    'load_vocabulary',
    'load_windowed_graph',
    'open_database',
    'page_people',
    'person_exists',
    'pin_term',
    'record_birth_order',
    'save_tree_settings',
    'search_people',
    'unlink_parent',
    'unlink_union',
    'unpin_term',
    'update_person',
    'window_ids',
]
