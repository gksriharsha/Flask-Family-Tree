"""Read a FamilyGraph out of JanusGraph, and persist what the family tells us.

Two directions:

*Reading* maps the existing gendered edge labels (``Father_Of``, ``Mother_Of`` and their
``*``-suffixed adoptive variants, ``Husband_Of``/``Wife_Of``) onto role-bearing links the
engine understands. The gendered labels stay in the graph — this is a translation at the
boundary, not a migration.

*Writing* stores the two things the graph cannot derive: a birth order somebody remembers,
and the words a family actually uses.
"""

from __future__ import annotations

import logging

from gremlin_python.process.graph_traversal import __
from gremlin_python.process.traversal import T

from Tree.kinship.model import (
    ADOPTIVE,
    BIOLOGICAL,
    FEMALE,
    MALE,
    UNKNOWN,
    FamilyGraph,
    ParentLink,
    Person,
    Union,
)
from Tree.kinship.vocabulary import PATERNAL, Variant, Vocabulary

log = logging.getLogger(__name__)

FATHER_LABELS = ('Father_Of', 'Mother_Of')
ADOPTIVE_PARENT_LABELS = ('Father_Of*', 'Mother_Of*')
UNION_LABELS = ('Husband_Of', 'Wife_Of')

ELDER_THAN = 'ELDER_THAN'
PINNED_TERM = 'PINNED_TERM'
TERM_LABEL = 'KinshipTerm'


def _sex(gender: object) -> str:
    text = str(gender or '').strip().lower()
    if text in ('male', 'm'):
        return MALE
    if text in ('female', 'f'):
        return FEMALE
    return UNKNOWN


def _year(value: object) -> int | None:
    """First four digits of a date string, or None.

    A graph that records the same placeholder date for everybody yields the same year for
    everybody, and the engine then reports the birth order as unknown — which is correct,
    and is exactly what the interface should be showing.
    """
    if value is None:
        return None
    if isinstance(value, (list, tuple, set)):
        for item in value:
            found = _year(item)
            if found is not None:
                return found
        return None
    text = str(value).strip()
    if len(text) >= 4 and text[:4].isdigit():
        return int(text[:4])
    return None


def _first(value: object) -> object:
    """Graph properties with set cardinality come back as lists."""
    if isinstance(value, (list, tuple, set)):
        return next(iter(value), None)
    return value


def load_family_graph(g, limit: int = 5000) -> FamilyGraph:
    """Load the whole tree.

    Loading everything is the right call at family scale — a few thousand vertices — and it
    keeps the traversal count at four regardless of how many people are shown. A subtree
    loader is the optimisation to reach for when a tree outgrows that, not before.
    """
    graph = FamilyGraph()

    for row in g.V().hasLabel('Person').limit(limit).elementMap().toList():
        graph.add_person(Person(
            id=row[T.id],
            given=str(_first(row.get('Firstname')) or ''),
            surname=str(_first(row.get('Lastname')) or ''),
            sex=_sex(_first(row.get('Gender'))),
            birth_year=_year(row.get('Date_of_birth')),
            death_year=_year(row.get('Date_of_death')),
        ))

    def edges(labels):
        return (g.E().hasLabel(*labels)
                .project('src', 'dst', 'label')
                .by(__.outV().id_()).by(__.inV().id_()).by(__.label())
                .toList())

    for role, labels in ((BIOLOGICAL, FATHER_LABELS), (ADOPTIVE, ADOPTIVE_PARENT_LABELS)):
        for edge in edges(labels):
            # the edge runs parent -> child
            if edge['src'] in graph.people and edge['dst'] in graph.people:
                graph.add_parent_link(ParentLink(child_id=edge['dst'],
                                                 parent_id=edge['src'], role=role))

    seen_unions: set[tuple[int, int]] = set()
    for edge in edges(UNION_LABELS):
        pair = (min(edge['src'], edge['dst']), max(edge['src'], edge['dst']))
        if pair in seen_unions:
            continue
        if edge['src'] in graph.people and edge['dst'] in graph.people:
            seen_unions.add(pair)
            graph.add_union(Union(a_id=edge['src'], b_id=edge['dst']))

    for edge in edges((ELDER_THAN,)):
        if edge['src'] in graph.people and edge['dst'] in graph.people:
            graph.record_birth_order(elder_id=edge['src'], younger_id=edge['dst'])

    log.info('Loaded %d people, %d parent links, %d unions, %d birth-order answers.',
             len(graph.people), sum(len(v) for v in graph.parents.values()),
             len(graph.unions), len(graph.birth_order))
    return graph


# ── writing ─────────────────────────────────────────────────────────────────────
def record_birth_order(g, elder_id: int, younger_id: int) -> None:
    """Remember that one person was born before another.

    Stored as an edge rather than a fabricated date, because that is the fact somebody
    actually knows. Guessing a date to encode it would be inventing a record.
    """
    if elder_id == younger_id:
        raise ValueError('A person cannot be elder than themselves.')
    for a, b in ((elder_id, younger_id), (younger_id, elder_id)):
        g.V(a).outE(ELDER_THAN).where(__.inV().hasId(b)).drop().iterate()
    g.V(elder_id).addE(ELDER_THAN).to(__.V(younger_id)).iterate()


def load_vocabulary(g, side: str = PATERNAL, limit: int = 2000) -> Vocabulary:
    """The words this family has recorded, plus any pins onto individual people."""
    vocab = Vocabulary(side=side)

    for row in g.V().hasLabel(TERM_LABEL).limit(limit).elementMap().toList():
        base = str(_first(row.get('Base_term')) or '')
        if not base:
            continue
        if str(_first(row.get('Vocabulary_side')) or PATERNAL) != side:
            continue
        vocab.added.setdefault(base, []).append(Variant(
            term=str(_first(row.get('Term')) or ''),
            roman=str(_first(row.get('Roman')) or ''),
            usage=str(_first(row.get('Usage')) or 'added by your family'),
            added_by_family=True,
        ))

    pins = (g.E().hasLabel(PINNED_TERM)
            .project('person', 'base', 'term', 'roman')
            .by(__.outV().id_())
            .by(__.values('Base_term'))
            .by(__.inV().values('Term'))
            .by(__.inV().values('Roman'))
            .toList())
    for pin in pins:
        vocab.pins[(pin['person'], pin['base'])] = Variant(term=pin['term'],
                                                           roman=pin['roman'])
    return vocab


def add_word(g, base_term: str, term: str, roman: str = '', usage: str = '',
             side: str = PATERNAL) -> int:
    """Record a word the family uses. Returns the new term's vertex id."""
    existing = (g.V().hasLabel(TERM_LABEL)
                .has('Base_term', base_term).has('Term', term)
                .has('Vocabulary_side', side))
    if existing.hasNext():
        return existing.next().id
    vertex = (g.addV(TERM_LABEL)
              .property('Base_term', base_term)
              .property('Term', term)
              .property('Roman', roman)
              .property('Usage', usage or 'added by your family')
              .property('Vocabulary_side', side)
              .next())
    return vertex.id


def pin_term(g, person_id: int, base_term: str, term_vertex_id: int) -> None:
    """Always use this word for this person."""
    (g.V(person_id).outE(PINNED_TERM).has('Base_term', base_term).drop().iterate())
    (g.V(person_id).addE(PINNED_TERM).to(__.V(term_vertex_id))
     .property('Base_term', base_term).iterate())


def unpin_term(g, person_id: int, base_term: str) -> None:
    g.V(person_id).outE(PINNED_TERM).has('Base_term', base_term).drop().iterate()
