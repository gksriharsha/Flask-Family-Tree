"""The folder a tree lives in.

A tree is created with a location, and everything it holds is kept there as files. The graph
database is the working index; the folder is the durable copy. That is deliberate — it means
the tree can be backed up by copying a directory, opened by other genealogy software, and
rebuilt if the database is ever lost.

    <location>/
        family.ged          GEDCOM 7 · refreshed after every change
        vocabulary.json     the family's own kinship words and pins — not a GEDCOM concept
        media/              photographs and documents
        exports/            on request: family-5.5.1.ged, family.gdz
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from gremlin_python.process.graph_traversal import __

from Tree.gedcom.mapping import parse, to_document
from Tree.gedcom.model import VERSION_7, VERSION_551, MediaObject
from Tree.gedcom.writer import write_gedcom, write_gedzip
from Tree.kinship.model import FEMALE, MALE, FamilyGraph
from Tree.kinship.store import ELDER_THAN, load_family_graph, load_vocabulary
from Tree.kinship.vocabulary import MATERNAL, PATERNAL

log = logging.getLogger(__name__)

SETTINGS_LABEL = 'TreeSettings'
GEDCOM_NAME = 'family.ged'
VOCABULARY_NAME = 'vocabulary.json'
MEDIA_DIR = 'media'
EXPORTS_DIR = 'exports'


@dataclass(frozen=True)
class TreeSettings:
    name: str
    location: Path

    @property
    def gedcom(self) -> Path:
        return self.location / GEDCOM_NAME

    @property
    def vocabulary(self) -> Path:
        return self.location / VOCABULARY_NAME

    @property
    def media(self) -> Path:
        return self.location / MEDIA_DIR

    @property
    def exports(self) -> Path:
        return self.location / EXPORTS_DIR


class TreeNotCreated(RuntimeError):
    """No tree has been created yet, so there is nowhere to keep its files."""


def _first(value):
    if isinstance(value, (list, tuple, set)):
        return next(iter(value), None)
    return value


def load_settings(g) -> TreeSettings | None:
    rows = g.V().hasLabel(SETTINGS_LABEL).limit(1).elementMap().toList()
    if not rows:
        return None
    row = rows[0]
    location = str(_first(row.get('Gedcom_path')) or '').strip()
    if not location:
        return None
    return TreeSettings(name=str(_first(row.get('Name')) or 'Family Tree'),
                        location=Path(location))


def require_settings(g) -> TreeSettings:
    settings = load_settings(g)
    if settings is None:
        raise TreeNotCreated(
            'No tree has been created yet. Create one and choose where its files should live.')
    return settings


def create_tree(g, name: str, location: str | Path) -> TreeSettings:
    """Create the tree and prepare its folder.

    The folder is made if it does not exist, and refused if it exists with a tree already in
    it — overwriting somebody's records because a path was mistyped is not a recoverable
    mistake.
    """
    path = Path(location).expanduser()
    if path.exists() and not path.is_dir():
        raise ValueError(f'{path} exists and is not a directory.')
    if (path / GEDCOM_NAME).exists() and load_settings(g) is None:
        raise ValueError(
            f'{path / GEDCOM_NAME} already exists. Import it instead of creating a new tree '
            f'over the top of it.')

    path.mkdir(parents=True, exist_ok=True)
    (path / MEDIA_DIR).mkdir(exist_ok=True)
    (path / EXPORTS_DIR).mkdir(exist_ok=True)

    existing = g.V().hasLabel(SETTINGS_LABEL)
    if existing.hasNext():
        vertex_id = existing.next().id
        (g.V(vertex_id).property('Name', name)
         .property('Gedcom_path', str(path)).iterate())
    else:
        (g.addV(SETTINGS_LABEL).property('Name', name)
         .property('Gedcom_path', str(path))
         .property('Created', datetime.now(timezone.utc).isoformat())
         .iterate())

    settings = TreeSettings(name=name, location=path)
    export(g, settings)
    log.info('Tree %r created at %s', name, path)
    return settings


# ── writing the folder ──────────────────────────────────────────────────────────
def _media_objects(settings: TreeSettings) -> list[MediaObject]:
    if not settings.media.is_dir():
        return []
    suffixes = {'.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png',
                '.gif': 'image/gif', '.tif': 'image/tiff', '.tiff': 'image/tiff',
                '.pdf': 'application/pdf', '.webp': 'image/webp'}
    found = []
    for index, item in enumerate(sorted(settings.media.iterdir()), start=1):
        if item.is_file() and item.suffix.lower() in suffixes:
            found.append(MediaObject(xref=f'@O{index}@',
                                     path=f'{MEDIA_DIR}/{item.name}',
                                     media_type=suffixes[item.suffix.lower()],
                                     title=item.stem.replace('-', ' ').replace('_', ' ')))
    return found


def export(g, settings: TreeSettings | None = None) -> Path:
    """Refresh the tree's own GEDCOM file and its vocabulary sidecar.

    Called after every change, so the folder is never out of date. It is deliberately a
    whole-file rewrite: a family tree is small, and a file that is always complete is worth
    far more than an incremental one that can drift.
    """
    settings = settings or require_settings(g)
    family = load_family_graph(g)
    document = to_document(family, tree_name=settings.name)
    document.media = _media_objects(settings)

    write_gedcom(document, settings.gedcom, VERSION_7)

    # The words a family uses are not a GEDCOM concept, so they sit beside the file rather
    # than being smuggled into it as tags no other program would understand.
    payload = {}
    for side in (PATERNAL, MATERNAL):
        vocab = load_vocabulary(g, side=side)
        payload[side] = {
            'added': {base: [{'term': v.term, 'roman': v.roman, 'usage': v.usage}
                             for v in variants]
                      for base, variants in vocab.added.items()},
            'pins': [{'person': pid, 'baseTerm': base, 'term': v.term, 'roman': v.roman}
                     for (pid, base), v in vocab.pins.items()],
        }
    settings.vocabulary.write_text(
        json.dumps({'tree': settings.name, 'vocabulary': payload}, ensure_ascii=False,
                   indent=2) + '\n',
        encoding='utf-8')
    return settings.gedcom


def export_as(g, version: str, settings: TreeSettings | None = None) -> Path:
    """Write a copy in another format, for handing to another program."""
    settings = settings or require_settings(g)
    family = load_family_graph(g)
    document = to_document(family, tree_name=settings.name)
    document.media = _media_objects(settings)
    settings.exports.mkdir(parents=True, exist_ok=True)

    if version == 'gedzip':
        return write_gedzip(document, settings.exports / 'family.gdz',
                            media_root=settings.location)
    if version == VERSION_551:
        return write_gedcom(document, settings.exports / 'family-5.5.1.ged', VERSION_551)
    if version == VERSION_7:
        return write_gedcom(document, settings.exports / 'family-7.0.ged', VERSION_7)
    raise ValueError(f'Unknown export format: {version}')


# ── reading a file back in ──────────────────────────────────────────────────────
PARENT_LABEL = {(MALE, False): 'Father_Of', (FEMALE, False): 'Mother_Of',
                (MALE, True): 'Father_Of*', (FEMALE, True): 'Mother_Of*'}
CHILD_LABEL = {(MALE, False): 'Son_Of', (FEMALE, False): 'Daughter_Of',
               (MALE, True): 'Son_Of*', (FEMALE, True): 'Daughter_Of*'}


def write_family_graph(g, family: FamilyGraph) -> dict[int, int]:
    """Write a parsed tree into the graph. Returns file-id -> vertex-id."""
    created: dict[int, int] = {}
    for person in family.people.values():
        traversal = g.addV('Person').property('Firstname', person.given)
        if person.surname:
            traversal = traversal.property('Lastname', person.surname)
        gender = {MALE: 'Male', FEMALE: 'Female'}.get(person.sex)
        if gender:
            traversal = traversal.property('Gender', gender)
        if person.birth_year is not None:
            traversal = traversal.property('Date_of_birth', f'{person.birth_year}-01-01')
        if person.death_year is not None:
            traversal = traversal.property('Date_of_death', f'{person.death_year}-01-01')
        created[person.id] = traversal.next().id

    for child_id, links in family.parents.items():
        for link in links:
            if child_id not in created or link.parent_id not in created:
                continue
            parent = family.people[link.parent_id]
            adoptive = not link.is_birth
            child = family.people[child_id]
            parent_label = PARENT_LABEL.get((parent.sex, adoptive))
            child_label = CHILD_LABEL.get((child.sex, adoptive))
            if parent_label:
                (g.V(created[link.parent_id]).addE(parent_label)
                 .to(__.V(created[child_id])).iterate())
            if child_label:
                (g.V(created[child_id]).addE(child_label)
                 .to(__.V(created[link.parent_id])).iterate())

    for union in family.unions:
        if union.a_id not in created or union.b_id not in created:
            continue
        for one, other in ((union.a_id, union.b_id), (union.b_id, union.a_id)):
            label = 'Husband_Of' if family.people[one].sex == MALE else 'Wife_Of'
            (g.V(created[one]).addE(label).to(__.V(created[other])).iterate())

    for (low, high), elder in family.birth_order.items():
        younger = high if low == elder else low
        if elder in created and younger in created:
            (g.V(created[elder]).addE(ELDER_THAN)
             .to(__.V(created[younger])).iterate())

    return created


def import_file(g, path: str | Path) -> dict:
    """Read a GEDCOM (or GEDZIP) file into the graph. Adds to whatever is already there."""
    source = Path(path).expanduser()
    if not source.is_file():
        raise ValueError(f'No file at {source}')

    if source.suffix.lower() in ('.gdz', '.zip'):
        import zipfile
        with zipfile.ZipFile(source) as archive:
            names = [n for n in archive.namelist() if n.lower().endswith('.ged')]
            if not names:
                raise ValueError('The archive holds no .ged file.')
            preferred = 'gedcom.ged' if 'gedcom.ged' in names else names[0]
            text = archive.read(preferred).decode('utf-8-sig')
    else:
        text = source.read_text(encoding='utf-8-sig')

    family, _ = parse(text)
    created = write_family_graph(g, family)
    log.info('Imported %d people from %s', len(created), source)
    return {
        'people': len(created),
        'parentLinks': sum(len(v) for v in family.parents.values()),
        'unions': len(family.unions),
        'birthOrder': len(family.birth_order),
        'source': str(source),
    }

