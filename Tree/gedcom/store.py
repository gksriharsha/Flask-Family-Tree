"""The folder a tree lives in.

A tree is created with a location, and everything it holds is kept there as files. The SQLite
database is the working store; the folder is the durable, portable copy. That is deliberate —
it means the tree can be backed up by copying a directory, opened by other genealogy software,
and rebuilt if the database is ever lost.

    <location>/
        family.ged          GEDCOM 7 · refreshed after every change
        vocabulary.json     the family's own kinship words and pins — not a GEDCOM concept
        media/              photographs and documents
        exports/            on request: family-5.5.1.ged, family.gdz

The tree's own name and folder are kept in the database's ``tree_settings`` table (the SQLite
equivalent of the graph's old ``TreeSettings`` vertex), read and written through
:func:`Tree.storage.load_tree_settings` / :func:`Tree.storage.save_tree_settings`.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from Tree.gedcom.mapping import parse_with_places, to_document
from Tree.gedcom.model import VERSION_7, VERSION_551, MediaObject
from Tree.gedcom.writer import write_gedcom, write_gedzip
from Tree.kinship.dates import DateValue
from Tree.kinship.model import FEMALE, MALE, FamilyGraph
from Tree.kinship.vocabulary import MATERNAL, PATERNAL
from Tree.storage import (
    load_family_graph,
    load_tree_settings,
    load_vocabulary,
    save_tree_settings,
)
from Tree.storage.places import all_places, set_places

log = logging.getLogger(__name__)

# The keys used inside tree_settings. 'Name' and 'Gedcom_path' mirror the graph vertex's
# property names, so the meaning is unchanged even though the storage is now a key/value table.
SETTINGS_NAME = 'Name'
SETTINGS_PATH = 'Gedcom_path'
SETTINGS_CREATED = 'Created'

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


def load_settings(conn: sqlite3.Connection) -> TreeSettings | None:
    settings = load_tree_settings(conn)
    if not settings:
        return None
    location = str(settings.get(SETTINGS_PATH) or '').strip()
    if not location:
        return None
    return TreeSettings(name=str(settings.get(SETTINGS_NAME) or 'Family Tree'),
                        location=Path(location))


def require_settings(conn: sqlite3.Connection) -> TreeSettings:
    settings = load_settings(conn)
    if settings is None:
        raise TreeNotCreated(
            'No tree has been created yet. Create one and choose where its files should live.')
    return settings


def create_tree(conn: sqlite3.Connection, name: str, location: str | Path) -> TreeSettings:
    """Create the tree and prepare its folder.

    The folder is made if it does not exist, and refused if it exists with a tree already in
    it — overwriting somebody's records because a path was mistyped is not a recoverable
    mistake.
    """
    path = Path(location).expanduser()
    if path.exists() and not path.is_dir():
        raise ValueError(f'{path} exists and is not a directory.')
    if (path / GEDCOM_NAME).exists() and load_settings(conn) is None:
        raise ValueError(
            f'{path / GEDCOM_NAME} already exists. Import it instead of creating a new tree '
            f'over the top of it.')

    path.mkdir(parents=True, exist_ok=True)
    (path / MEDIA_DIR).mkdir(exist_ok=True)
    (path / EXPORTS_DIR).mkdir(exist_ok=True)

    fields = {SETTINGS_NAME: name, SETTINGS_PATH: str(path)}
    existing = load_tree_settings(conn) or {}
    if SETTINGS_CREATED not in existing:
        fields[SETTINGS_CREATED] = datetime.now(timezone.utc).isoformat()
    save_tree_settings(conn, **fields)

    settings = TreeSettings(name=name, location=path)
    export(conn, settings)
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


def export(conn: sqlite3.Connection, settings: TreeSettings | None = None) -> Path:
    """Refresh the tree's own GEDCOM file and its vocabulary sidecar.

    Called after every change, so the folder is never out of date. It is deliberately a
    whole-file rewrite: a family tree is small, and a file that is always complete is worth
    far more than an incremental one that can drift.
    """
    settings = settings or require_settings(conn)
    family = load_family_graph(conn)
    document = to_document(family, tree_name=settings.name, places=all_places(conn))
    document.media = _media_objects(settings)

    write_gedcom(document, settings.gedcom, VERSION_7)

    # The words a family uses are not a GEDCOM concept, so they sit beside the file rather
    # than being smuggled into it as tags no other program would understand.
    payload = {}
    for side in (PATERNAL, MATERNAL):
        vocab = load_vocabulary(conn, side=side)
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


def export_as(conn: sqlite3.Connection, version: str,
              settings: TreeSettings | None = None) -> Path:
    """Write a copy in another format, for handing to another program."""
    settings = settings or require_settings(conn)
    family = load_family_graph(conn)
    document = to_document(family, tree_name=settings.name, places=all_places(conn))
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
def _stored_sex(sex: str) -> str | None:
    """The value written to the ``sex`` column. UNKNOWN stores as NULL, matching the store."""
    return {MALE: 'Male', FEMALE: 'Female'}.get(sex)


def _date_text(value: DateValue | None) -> str | None:
    return value.gedcom() if (value is not None and value.is_known) else None


def write_family_graph(conn: sqlite3.Connection, family: FamilyGraph) -> dict[int, int]:
    """Write a parsed tree into the SQLite store in one transaction. Returns file-id -> db-id.

    All the people are inserted with :meth:`executemany`, then all the parent links, unions and
    birth-order rows the same way, so a ten-thousand-person GEDCOM lands in a single fast
    transaction rather than one round trip per row. The parsed graph carries file-order ids
    (1, 2, …); the database assigns its own, so a file-id -> db-id map is built from the people
    insert and every link is translated through it before it is written.
    """
    ordered = sorted(family.people.values(), key=lambda p: p.id)

    # Assign dense db ids starting after the current maximum, so an add-mode import does not
    # collide with people already present, and executemany can carry the ids explicitly.
    row = conn.execute('SELECT COALESCE(MAX(id), 0) AS m FROM person').fetchone()
    base = int(row['m'])
    file_to_db: dict[int, int] = {}
    person_rows = []
    for offset, person in enumerate(ordered, start=1):
        db_id = base + offset
        file_to_db[person.id] = db_id
        person_rows.append((
            db_id, (person.given or '').strip(), (person.surname or '').strip(),
            _stored_sex(person.sex), _date_text(person.birth_date),
            _date_text(person.death_date), None,
        ))

    parent_rows = []
    for child_id, links in family.parents.items():
        if child_id not in file_to_db:
            continue
        for link in links:
            if link.parent_id in file_to_db:
                parent_rows.append(
                    (file_to_db[child_id], file_to_db[link.parent_id], link.role))

    union_rows = []
    for union in family.unions:
        if union.a_id in file_to_db and union.b_id in file_to_db:
            a, b = file_to_db[union.a_id], file_to_db[union.b_id]
            low, high = (a, b) if a < b else (b, a)
            union_rows.append((low, high))

    order_rows = []
    for (low, high), elder in family.birth_order.items():
        younger = high if low == elder else low
        if elder in file_to_db and younger in file_to_db:
            e, y = file_to_db[elder], file_to_db[younger]
            lo, hi = (e, y) if e < y else (y, e)
            order_rows.append((lo, hi, e))

    with conn:
        conn.executemany(
            'INSERT INTO person (id, given, surname, sex, birth, death, living) '
            'VALUES (?, ?, ?, ?, ?, ?, ?)', person_rows)
        if parent_rows:
            conn.executemany(
                'INSERT INTO parent_link (child_id, parent_id, role) VALUES (?, ?, ?) '
                'ON CONFLICT(child_id, parent_id) DO UPDATE SET role = excluded.role',
                parent_rows)
        if union_rows:
            conn.executemany(
                'INSERT INTO union_link (a_id, b_id) VALUES (?, ?) '
                'ON CONFLICT(a_id, b_id) DO NOTHING', union_rows)
        if order_rows:
            conn.executemany(
                'INSERT INTO birth_order (lower_id, higher_id, elder_id) VALUES (?, ?, ?) '
                'ON CONFLICT(lower_id, higher_id) DO UPDATE SET elder_id = excluded.elder_id',
                order_rows)

    return file_to_db


GEDCOM_SUFFIXES = ('.ged', '.gedcom')
ARCHIVE_SUFFIXES = ('.gdz', '.zip')


def read_gedcom_text(data: bytes, filename: str = '') -> str:
    """Get the GEDCOM text out of an uploaded file, unwrapping a GEDZIP if that is what it is.

    Decoded as utf-8-sig: 5.5.1 files written on Windows very often carry a byte-order mark,
    and a stray BOM on the first line makes the whole header unparseable.
    """
    suffix = Path(filename).suffix.lower()
    if suffix in ARCHIVE_SUFFIXES:
        import io
        import zipfile
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                names = [n for n in archive.namelist() if n.lower().endswith('.ged')]
                if not names:
                    raise ValueError('That archive holds no .ged file.')
                preferred = 'gedcom.ged' if 'gedcom.ged' in names else names[0]
                return archive.read(preferred).decode('utf-8-sig')
        except zipfile.BadZipFile as exc:
            raise ValueError('That file is not a readable archive.') from exc
    try:
        return data.decode('utf-8-sig')
    except UnicodeDecodeError as exc:
        raise ValueError('That file is not UTF-8 text, so it cannot be read as GEDCOM.') from exc


def clear_people(conn: sqlite3.Connection) -> int:
    """Remove every person, and with them every link between people.

    Deliberately leaves the tree's settings and the family's vocabulary alone: the words a
    family uses for its relationships are not part of any one imported file, and losing them
    on an import nobody warned you about would be its own small disaster. Pins go with their
    people, because a pin points at a person who no longer exists (the foreign key cascades).
    """
    count = conn.execute('SELECT COUNT(*) AS n FROM person').fetchone()['n']
    with conn:
        conn.execute('DELETE FROM person')
    return int(count)


def import_document(conn: sqlite3.Connection, text: str, replace: bool = False) -> dict:
    """Write a parsed GEDCOM into the store, in the shape the rest of the app expects.

    Everything goes in through :func:`write_family_graph`, the same path the seed uses, so an
    imported tree carries dates at their recorded precision, roles on parent links, one row per
    union, and the recorded birth orders. Nothing about an imported person is stored differently
    from one typed in by hand.
    """
    family, _, places = parse_with_places(text)
    if not family.people:
        raise ValueError('No people were found in that file. Is it really a GEDCOM?')

    removed = clear_people(conn) if replace else 0
    created = write_family_graph(conn, family)
    # Places travel beside the graph (they are not part of the engine's Person), so they are
    # written after the people exist, translated from the parser's file-order ids to the
    # database ids write_family_graph just assigned.
    for file_id, place in places.items():
        db_id = created.get(file_id)
        if db_id is not None:
            set_places(conn, db_id,
                       birth_place=place.get('birthPlace') or '',
                       death_place=place.get('deathPlace') or '')
    log.info('Imported %d people (replace=%s, removed %d)', len(created), replace, removed)
    return {
        'people': len(created),
        'parentLinks': sum(len(v) for v in family.parents.values()),
        'unions': len(family.unions),
        'birthOrder': len(family.birth_order),
        'places': len(places),
        'replaced': removed,
    }


def import_file(conn: sqlite3.Connection, path: str | Path, replace: bool = False) -> dict:
    """Read a GEDCOM or GEDZIP file from disk. Used by the command line."""
    source = Path(path).expanduser()
    if not source.is_file():
        raise ValueError(f'No file at {source}')
    summary = import_document(conn, read_gedcom_text(source.read_bytes(), source.name),
                              replace=replace)
    summary['source'] = str(source)
    return summary


# Kept importable for callers that referenced the sex-neutral constant set. The label maps that
# once lived here belonged to the Gremlin write path, which no longer exists.
__all__ = [
    'ARCHIVE_SUFFIXES', 'GEDCOM_SUFFIXES', 'TreeNotCreated', 'TreeSettings',
    'clear_people', 'create_tree', 'export', 'export_as', 'import_document', 'import_file',
    'load_settings', 'read_gedcom_text', 'require_settings', 'write_family_graph',
]
