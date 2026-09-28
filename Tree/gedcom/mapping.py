"""Convert between a FamilyGraph and a GEDCOM Document.

The awkward part is that GEDCOM links a child to a *family*, while this application links a
child to each *parent* with a role of its own. Going out, parents are grouped into families;
coming back, families are unrolled into per-parent links. A within-family adoption survives
the trip because it becomes two FAMC links with different pedigrees, which is exactly what
GEDCOM is for.
"""

from __future__ import annotations

from Tree.gedcom.model import PEDIGREE, Document, Family, Individual
from Tree.kinship.dates import UNKNOWN_DATE, DateValue
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

PEDIGREE_TO_ROLE = {
    'BIRTH': BIOLOGICAL,
    'ADOPTED': ADOPTIVE,
    'FOSTER': 'foster',
    'SEALING': BIOLOGICAL,
    'OTHER': 'step',
}


def to_document(graph: FamilyGraph, tree_name: str = 'Family Tree',
                places: dict[int, dict] | None = None) -> Document:
    """Build a GEDCOM Document from the graph.

    ``places`` optionally maps a person id to ``{'birthPlace', 'deathPlace'}``. The place is
    not a field on the engine's :class:`Person` (the kinship engine has no use for it), so it
    is passed alongside the graph and written as a ``PLAC`` under the ``BIRT`` / ``DEAT``
    event. Absent or empty places write nothing, so a tree with no places recorded produces
    exactly the file it did before.
    """
    places = places or {}
    person_xref = {pid: f'@I{index + 1}@' for index, pid in enumerate(sorted(graph.people))}
    document = Document(tree_name=tree_name)

    families: list[Family] = []
    by_partners: dict[frozenset[int], Family] = {}

    def family_for(parent_ids: frozenset[int]) -> Family:
        existing = by_partners.get(parent_ids)
        if existing is not None:
            return existing
        family = Family(xref=f'@F{len(families) + 1}@')
        ordered = sorted(parent_ids)
        for pid in ordered:
            sex = graph.people[pid].sex if pid in graph.people else UNKNOWN
            if sex == MALE and family.husband is None:
                family.husband = person_xref[pid]
            elif sex == FEMALE and family.wife is None:
                family.wife = person_xref[pid]
            else:
                family.partners.append(person_xref[pid])
        families.append(family)
        by_partners[parent_ids] = family
        return family

    # unions first, so a couple with children keeps one family record rather than two
    for union in graph.unions:
        if union.a_id in graph.people and union.b_id in graph.people:
            family_for(frozenset({union.a_id, union.b_id}))

    child_links: dict[int, list[tuple[str, str]]] = {}
    for child_id, links in graph.parents.items():
        if child_id not in graph.people:
            continue
        by_role: dict[str, set[int]] = {}
        for link in links:
            if link.parent_id in graph.people:
                by_role.setdefault(link.role, set()).add(link.parent_id)
        for role, parent_ids in by_role.items():
            family = family_for(frozenset(parent_ids))
            if person_xref[child_id] not in family.children:
                family.children.append(person_xref[child_id])
            child_links.setdefault(child_id, []).append(
                (family.xref, PEDIGREE.get(role, 'OTHER'))
            )

    spouse_in: dict[int, list[str]] = {}
    for parents, family in by_partners.items():
        for pid in parents:
            spouse_in.setdefault(pid, []).append(family.xref)

    for pid in sorted(graph.people):
        person = graph.people[pid]
        younger = [
            person_xref[other]
            for (low, high), elder in sorted(graph.birth_order.items())
            for other in ((high if low == elder else low),)
            if elder == pid and other in person_xref
        ]
        document.individuals.append(Individual(
            xref=person_xref[pid],
            given=person.given,
            surname=person.surname,
            sex=person.sex,
            birth=person.birth_date,
            death=person.death_date,
            birth_place=str((places.get(pid) or {}).get('birthPlace') or ''),
            death_place=str((places.get(pid) or {}).get('deathPlace') or ''),
            child_of=child_links.get(pid, []),
            spouse_in=sorted(spouse_in.get(pid, [])),
            elder_than=younger,
        ))

    document.families = families
    return document


def _year(value: str) -> int | None:
    """Pull a four-digit year out of a GEDCOM date, ignoring modifiers like ABT or BEF."""
    for token in value.replace(',', ' ').split():
        if len(token) == 4 and token.isdigit():
            return int(token)
    return None


def _split_name(value: str) -> tuple[str, str]:
    """``Aditya Varun /Varma/`` -> given, surname."""
    if '/' in value:
        before, _, rest = value.partition('/')
        surname, _, _ = rest.partition('/')
        return before.strip(), surname.strip()
    return value.strip(), ''


SEX_FROM_GEDCOM = {'M': MALE, 'F': FEMALE, 'X': 'intersex', 'U': UNKNOWN}


def parse(text: str) -> tuple[FamilyGraph, dict[str, int]]:
    """Read a GEDCOM file into a FamilyGraph.

    Accepts 5.5.1 and 7.0. Returns the graph and the xref-to-id map, so an importer can
    report what it created. Ids are assigned in file order; the graph database assigns its
    own on write.

    Kept as a two-tuple for the callers and tests that only want the graph and ids;
    :func:`parse_with_places` is the same parse and additionally returns the birth/death
    places, which the store persists on import.
    """
    graph, ids, _places = parse_with_places(text)
    return graph, ids


def parse_with_places(
    text: str,
) -> tuple[FamilyGraph, dict[str, int], dict[int, dict]]:
    """As :func:`parse`, and also return ``{file_id: {'birthPlace', 'deathPlace'}}``.

    The place is not part of the engine's :class:`Person`, so it travels beside the graph.
    Only people with a birth or death place recorded appear in the map, keyed by the same
    file-order id the graph carries, so the importer can translate it to the database id.
    """
    graph = FamilyGraph()
    ids: dict[str, int] = {}
    raw_individuals: dict[str, dict] = {}
    raw_families: dict[str, dict] = {}

    current: dict | None = None
    context: list[str] = []

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        parts = line.split(' ', 2)
        if not parts[0].isdigit():
            continue
        level = int(parts[0])
        rest = parts[1:] or ['']

        if rest[0].startswith('@') and rest[0].endswith('@') and len(rest) > 1:
            xref, tag = rest[0], rest[1]
            value = parts[2].split(' ', 1)[1] if len(parts) > 2 and ' ' in parts[2] else ''
            if tag == 'INDI':
                current = raw_individuals.setdefault(
                    xref, {'xref': xref, 'famc': [], 'fams': [], 'elder': []})
            elif tag == 'FAM':
                current = raw_families.setdefault(
                    xref, {'xref': xref, 'husb': None, 'wife': None,
                           'partners': [], 'chil': []})
            else:
                current = None
            context = [tag]
            del value
            continue

        tag = rest[0]
        value = parts[2] if len(parts) > 2 else ''
        context = [*context[:level], tag]
        if current is None:
            continue

        if 'INDI' in context[:1]:
            if level == 1 and tag == 'NAME':
                current['given'], current['surname'] = _split_name(value)
            elif level == 2 and tag == 'GIVN':
                current['given'] = value
            elif level == 2 and tag == 'SURN':
                current['surname'] = value
            elif level == 1 and tag == 'SEX':
                current['sex'] = SEX_FROM_GEDCOM.get(value.strip().upper(), UNKNOWN)
            elif level == 2 and tag == 'DATE' and len(context) >= 2:
                if context[-2] == 'BIRT':
                    current['birth'] = DateValue.parse(value)
                elif context[-2] == 'DEAT':
                    current['death'] = DateValue.parse(value)
            elif level == 2 and tag == 'PLAC' and len(context) >= 2:
                if context[-2] == 'BIRT':
                    current['birth_place'] = value.strip()
                elif context[-2] == 'DEAT':
                    current['death_place'] = value.strip()
            elif level == 1 and tag == 'FAMC':
                current['famc'].append([value.strip(), 'BIRTH'])
            elif level == 2 and tag == 'PEDI' and current['famc']:
                current['famc'][-1][1] = value.strip().upper()
            elif level == 1 and tag == 'FAMS':
                current['fams'].append(value.strip())
            elif level == 1 and tag == '_ELDER':
                current['elder'].append(value.strip())
        elif 'FAM' in context[:1]:
            if tag == 'HUSB':
                current['husb'] = value.strip()
            elif tag == 'WIFE':
                current['wife'] = value.strip()
            elif tag == 'CHIL':
                current['chil'].append(value.strip())
            elif tag == 'ASSO':
                current['partners'].append(value.strip())

    for index, (xref, record) in enumerate(raw_individuals.items(), start=1):
        ids[xref] = index
        graph.add_person(Person(
            id=index,
            given=record.get('given', ''),
            surname=record.get('surname', ''),
            sex=record.get('sex', UNKNOWN),
            birth=record.get('birth') or UNKNOWN_DATE,
            death=record.get('death') or UNKNOWN_DATE,
        ))

    for record in raw_families.values():
        parents = [p for p in (record['husb'], record['wife'], *record['partners']) if p]
        for child_xref in record['chil']:
            child = raw_individuals.get(child_xref)
            if child is None:
                continue
            pedigree = next(
                (p for f, p in child['famc'] if f == record['xref']), 'BIRTH')
            role = PEDIGREE_TO_ROLE.get(pedigree, BIOLOGICAL)
            for parent_xref in parents:
                if parent_xref in ids:
                    graph.add_parent_link(ParentLink(
                        child_id=ids[child_xref], parent_id=ids[parent_xref], role=role))
        if len(parents) >= 2 and all(p in ids for p in parents[:2]):
            graph.add_union(Union(a_id=ids[parents[0]], b_id=ids[parents[1]]))

    for xref, record in raw_individuals.items():
        for younger in record['elder']:
            if xref in ids and younger in ids:
                graph.record_birth_order(ids[xref], ids[younger])

    places: dict[int, dict] = {}
    for xref, record in raw_individuals.items():
        birth_place = str(record.get('birth_place') or '')
        death_place = str(record.get('death_place') or '')
        if birth_place or death_place:
            places[ids[xref]] = {'birthPlace': birth_place, 'deathPlace': death_place}

    return graph, ids, places
