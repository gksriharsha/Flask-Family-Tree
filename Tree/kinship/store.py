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

from Tree.kinship.dates import DateValue
from Tree.kinship.model import (
    ADOPTIVE,
    BIOLOGICAL,
    FEMALE,
    MALE,
    NON_BIRTH_ROLES,
    UNKNOWN,
    FamilyGraph,
    ParentLink,
    Person,
    Union,
)
from Tree.kinship.vocabulary import PATERNAL, Variant, Vocabulary

log = logging.getLogger(__name__)

# Parent -> child. The sex-neutral 'Parent_Of' sits alongside the gendered pair so that a
# parent whose sex is not recorded can still be linked; without it the interface would have to
# insist on a sex before accepting a relationship, which turns "not known" into a guess.
BIRTH_PARENT_LABELS = ('Father_Of', 'Mother_Of', 'Parent_Of')
ADOPTIVE_PARENT_LABELS = ('Father_Of*', 'Mother_Of*', 'Parent_Of*')
UNION_LABELS = ('Husband_Of', 'Wife_Of', 'Partner_Of')

#: Written alongside the parent edge, pointing the other way. Nothing reads these -- the
#: parent edges are the source of truth -- but the 2021 routes and any existing data have
#: them, so writes keep both directions consistent rather than leaving a half-linked graph.
PARENT_LABEL = {(MALE, False): 'Father_Of', (FEMALE, False): 'Mother_Of',
                (MALE, True): 'Father_Of*', (FEMALE, True): 'Mother_Of*'}
CHILD_LABEL = {(MALE, False): 'Son_Of', (FEMALE, False): 'Daughter_Of',
               (MALE, True): 'Son_Of*', (FEMALE, True): 'Daughter_Of*'}

#: Historical alias. Kept because other modules import it under the old name.
FATHER_LABELS = BIRTH_PARENT_LABELS

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


def _living(value: object) -> bool | None:
    """Tri-state, like everything else here: yes, no, or genuinely not recorded."""
    text = str(value or '').strip().lower()
    if text in ('yes', 'true', 'living', 'y'):
        return True
    if text in ('no', 'false', 'deceased', 'dead', 'n'):
        return False
    return None


def _gender_property(sex: str) -> str | None:
    return {MALE: 'Male', FEMALE: 'Female'}.get(sex)


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
            birth=DateValue.parse(row.get('Date_of_birth')),
            death=DateValue.parse(row.get('Date_of_death')),
            birth_year=_year(row.get('Date_of_birth')),
            death_year=_year(row.get('Date_of_death')),
            living=_living(_first(row.get('Alive'))),
        ))

    def edges(labels):
        return (g.E().hasLabel(*labels)
                .project('src', 'dst', 'label')
                .by(__.outV().id_()).by(__.inV().id_()).by(__.label())
                .toList())

    for role, labels in ((BIOLOGICAL, BIRTH_PARENT_LABELS), (ADOPTIVE, ADOPTIVE_PARENT_LABELS)):
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


# ── writing people ──────────────────────────────────────────────────────────────
def _apply_person_properties(traversal, *, given=None, surname=None, sex=None,
                             birth=None, death=None, living=None, creating=False):
    """Set whichever fields were supplied. Absent means "leave alone", not "clear"."""
    if given is not None:
        traversal = traversal.property('Firstname', given)
    if surname is not None:
        traversal = traversal.property('Lastname', surname)
    if sex is not None:
        gender = _gender_property(sex)
        if gender:
            traversal = traversal.property('Gender', gender)
    if birth is not None and birth.is_known:
        traversal = traversal.property('Date_of_birth', birth.gedcom())
    if death is not None and death.is_known:
        traversal = traversal.property('Date_of_death', death.gedcom())
    if living is not None:
        traversal = traversal.property('Alive', 'Yes' if living else 'No')
    return traversal


def create_person(g, given: str, surname: str = '', sex: str = UNKNOWN,
                  birth: DateValue | None = None, death: DateValue | None = None,
                  living: bool | None = None) -> int:
    """Add a person. Only a name is required; everything else may be absent.

    A record with an honest gap is worth more than one with an invented date, so nothing here
    substitutes a default for a fact nobody knows. In particular no birth date is written when
    none was given -- the placeholder dates in the original data are exactly what made every
    sibling's seniority unanswerable.
    """
    given = (given or '').strip()
    if not given:
        raise ValueError('A person needs a given name.')
    traversal = _apply_person_properties(
        g.addV('Person'), given=given, surname=(surname or '').strip(),
        sex=sex, birth=birth, death=death, living=living, creating=True)
    vertex_id = traversal.next().id
    log.info('Created person %s (%s)', vertex_id, given)
    return vertex_id


def update_person(g, person_id: int, **fields) -> None:
    """Change some of a person's details, leaving the rest as they were.

    Clearing a date is explicit: pass a :data:`~Tree.kinship.dates.UNKNOWN` date and the
    property is removed, rather than being quietly left behind where it would keep driving
    seniority answers that the family has since said are wrong.
    """
    if not g.V(person_id).hasNext():
        raise ValueError(f'No person with id {person_id}.')

    for key, prop in (('birth', 'Date_of_birth'), ('death', 'Date_of_death')):
        value = fields.get(key)
        if value is not None and not value.is_known:
            g.V(person_id).properties(prop).drop().iterate()
            fields[key] = None
    if fields.get('sex') == UNKNOWN:
        g.V(person_id).properties('Gender').drop().iterate()
        fields['sex'] = None

    traversal = _apply_person_properties(g.V(person_id), **fields)
    traversal.iterate()
    log.info('Updated person %s', person_id)


def delete_person(g, person_id: int) -> None:
    """Remove a person and every link that referred to them.

    Dropping the vertex drops its edges with it, which is what keeps the graph from being left
    with links pointing at somebody who is no longer there.
    """
    if not g.V(person_id).hasNext():
        raise ValueError(f'No person with id {person_id}.')
    g.V(person_id).drop().iterate()
    log.info('Deleted person %s', person_id)


# ── writing relationships ───────────────────────────────────────────────────────
def _sex_of(g, person_id: int) -> str:
    rows = g.V(person_id).elementMap().toList()
    if not rows:
        raise ValueError(f'No person with id {person_id}.')
    return _sex(_first(rows[0].get('Gender')))


def link_parent(g, child_id: int, parent_id: int, role: str = BIOLOGICAL) -> None:
    """Record that one person is a parent of another.

    Both directions are written -- parent->child and child->parent -- because the 2021 routes
    and the existing data both expect the pair. Only the parent->child edge is ever read.
    """
    if child_id == parent_id:
        raise ValueError('A person cannot be their own parent.')
    if _creates_ancestry_cycle(g, child_id, parent_id):
        raise ValueError(
            'That link would make someone their own ancestor. Check which of the two is the '
            'parent.')

    adoptive = role in NON_BIRTH_ROLES
    parent_sex, child_sex = _sex_of(g, parent_id), _sex_of(g, child_id)
    parent_label = PARENT_LABEL.get((parent_sex, adoptive),
                                    'Parent_Of*' if adoptive else 'Parent_Of')
    child_label = CHILD_LABEL.get((child_sex, adoptive),
                                  'Child_Of*' if adoptive else 'Child_Of')

    unlink_parent(g, child_id, parent_id)
    g.V(parent_id).addE(parent_label).to(__.V(child_id)).iterate()
    g.V(child_id).addE(child_label).to(__.V(parent_id)).iterate()
    log.info('Linked parent %s -> child %s as %s', parent_id, child_id, role)


def unlink_parent(g, child_id: int, parent_id: int) -> None:
    """Remove every parent link between the two, in either direction and of either role."""
    parent_labels = BIRTH_PARENT_LABELS + ADOPTIVE_PARENT_LABELS
    child_labels = (*CHILD_LABEL.values(), 'Child_Of', 'Child_Of*')
    (g.V(parent_id).outE(*parent_labels).where(__.inV().hasId(child_id)).drop().iterate())
    (g.V(child_id).outE(*child_labels).where(__.inV().hasId(parent_id)).drop().iterate())


def link_union(g, a_id: int, b_id: int) -> None:
    """Record a marriage or partnership. Written in both directions, as the data has it."""
    if a_id == b_id:
        raise ValueError('A person cannot be married to themselves.')
    unlink_union(g, a_id, b_id)
    for one, other in ((a_id, b_id), (b_id, a_id)):
        sex = _sex_of(g, one)
        label = {MALE: 'Husband_Of', FEMALE: 'Wife_Of'}.get(sex, 'Partner_Of')
        g.V(one).addE(label).to(__.V(other)).iterate()
    log.info('Linked union %s <-> %s', a_id, b_id)


def unlink_union(g, a_id: int, b_id: int) -> None:
    for one, other in ((a_id, b_id), (b_id, a_id)):
        (g.V(one).outE(*UNION_LABELS).where(__.inV().hasId(other)).drop().iterate())


def _creates_ancestry_cycle(g, child_id: int, parent_id: int, depth: int = 40) -> bool:
    """Would making ``parent_id`` a parent of ``child_id`` close a loop?

    True when the proposed parent is already a descendant of the proposed child. Without this
    check a mistyped link makes somebody their own grandparent, and every ancestor walk in the
    engine then runs until it hits its depth cap.
    """
    if child_id == parent_id:
        return True
    labels = BIRTH_PARENT_LABELS + ADOPTIVE_PARENT_LABELS
    descendants = (g.V(child_id).repeat(__.out(*labels).dedup())
                   .times(depth).emit().id_().toList())
    return parent_id in set(descendants)


# ── writing what the graph cannot derive ────────────────────────────────────────
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
