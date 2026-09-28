"""The SQLite schema, and the connection that carries it.

One database is one family tree. The schema is applied idempotently and versioned, so opening
an existing file is a no-op and opening a new one builds everything. ``PRAGMA foreign_keys``
makes the ``ON DELETE CASCADE`` clauses real — SQLite ignores foreign keys unless it is asked
not to — and WAL is the journal mode a read-mostly local app wants.

The shape mirrors what :mod:`Tree.kinship.store` reads out of the graph:

* a person carries name, sex, two dates (stored as GEDCOM date strings, exactly as the graph
  stores them, so :func:`Tree.kinship.dates.DateValue.parse` reads them unchanged) and a
  tri-state ``living``;
* ``parent_link`` runs child -> parent with a role, standing in for the gendered edges;
* ``union_link`` holds one row per unordered pair (``a_id < b_id``), the marriage/partnership;
* ``birth_order`` records a remembered seniority as ``elder_id`` for a pair, never a date;
* ``kinship_term`` and ``pinned_term`` are the vocabulary the family records;
* ``tree_settings`` is the key/value equivalent of the graph's ``TreeSettings`` vertex.
"""

from __future__ import annotations

import logging
import sqlite3

log = logging.getLogger(__name__)

#: Bump when the schema changes and add a migration step in :func:`_migrate`.
SCHEMA_VERSION = 3

#: v1 builds everything. Every statement is idempotent (``IF NOT EXISTS``) so re-applying it
#: to an already-current database changes nothing.
_SCHEMA_V1 = """
CREATE TABLE IF NOT EXISTS person (
    id      INTEGER PRIMARY KEY,
    given   TEXT NOT NULL,
    surname TEXT NOT NULL DEFAULT '',
    sex     TEXT,
    birth   TEXT,          -- GEDCOM date string, or NULL when not recorded
    death   TEXT,
    living  INTEGER        -- 1 / 0 / NULL, tri-state like the rest of the model
);

CREATE TABLE IF NOT EXISTS parent_link (
    child_id  INTEGER NOT NULL,
    parent_id INTEGER NOT NULL,
    role      TEXT NOT NULL DEFAULT 'biological',
    PRIMARY KEY (child_id, parent_id),
    FOREIGN KEY (child_id)  REFERENCES person(id) ON DELETE CASCADE,
    FOREIGN KEY (parent_id) REFERENCES person(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS union_link (
    a_id  INTEGER NOT NULL,
    b_id  INTEGER NOT NULL,
    kind  TEXT NOT NULL DEFAULT 'marriage',
    ended INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (a_id, b_id),
    CHECK (a_id < b_id),
    FOREIGN KEY (a_id) REFERENCES person(id) ON DELETE CASCADE,
    FOREIGN KEY (b_id) REFERENCES person(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS birth_order (
    lower_id  INTEGER NOT NULL,
    higher_id INTEGER NOT NULL,
    elder_id  INTEGER NOT NULL,
    PRIMARY KEY (lower_id, higher_id),
    CHECK (lower_id < higher_id),
    FOREIGN KEY (lower_id)  REFERENCES person(id) ON DELETE CASCADE,
    FOREIGN KEY (higher_id) REFERENCES person(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS kinship_term (
    id        INTEGER PRIMARY KEY,
    base_term TEXT NOT NULL,
    term      TEXT NOT NULL,
    roman     TEXT NOT NULL DEFAULT '',
    usage     TEXT NOT NULL DEFAULT '',
    side      TEXT NOT NULL DEFAULT 'paternal',
    UNIQUE (base_term, term, side)
);

CREATE TABLE IF NOT EXISTS pinned_term (
    person_id INTEGER NOT NULL,
    base_term TEXT NOT NULL,
    term_id   INTEGER NOT NULL,
    PRIMARY KEY (person_id, base_term),
    FOREIGN KEY (person_id) REFERENCES person(id) ON DELETE CASCADE,
    FOREIGN KEY (term_id)   REFERENCES kinship_term(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS tree_settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE INDEX IF NOT EXISTS ix_parent_link_parent ON parent_link(parent_id);
CREATE INDEX IF NOT EXISTS ix_union_link_b        ON union_link(b_id);
CREATE INDEX IF NOT EXISTS ix_person_surname      ON person(surname COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS ix_person_given        ON person(given COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS ix_kinship_term_lookup ON kinship_term(side, base_term);
"""

#: v2 adds the places a person was born and died, and a table of photographs attached to
#: people. Both are additive: ``ALTER TABLE ... ADD COLUMN`` leaves every existing row intact
#: (the new columns are NULL), and the ``photo`` table is new. Appended after v1 and applied
#: only when the database is below version 2, so an existing tree gains the columns in place
#: without a rebuild and a fresh tree gets them from v1's run followed immediately by v2's.
_SCHEMA_V2 = """
ALTER TABLE person ADD COLUMN birth_place TEXT;
ALTER TABLE person ADD COLUMN death_place TEXT;

CREATE TABLE IF NOT EXISTS photo (
    id         INTEGER PRIMARY KEY,
    filename   TEXT NOT NULL,          -- the stored file's name, under UPLOAD_IMAGE_PATH
    caption    TEXT NOT NULL DEFAULT '',
    person_id  INTEGER,                -- the person this photo is of, or NULL if unattached
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (person_id) REFERENCES person(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS ix_photo_person ON photo(person_id);
"""

#: v3 adds a composite index that backs cursor pagination on /api/v1/people. The keyset scan
#: orders by (given, surname, id) and seeks past a cursor with a tuple comparison; a composite
#: index on exactly those columns, in the default BINARY collation the ORDER BY uses, lets
#: SQLite serve the ordered page straight from the index with no temp-B-tree sort. Idempotent,
#: so re-applying is a no-op.
_SCHEMA_V3 = """
CREATE INDEX IF NOT EXISTS ix_person_page ON person(given, surname, id);
"""


def open_database(path: str) -> sqlite3.Connection:
    """Open (or create) a family-tree database, with the schema applied.

    ``path`` may be a filesystem path or ``':memory:'``. Foreign keys are turned on for the
    connection (they are per-connection in SQLite, not per-database), WAL is set once and
    persists in the file header, and the schema is brought up to :data:`SCHEMA_VERSION`.
    """
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    conn.execute('PRAGMA journal_mode = WAL')
    _migrate(conn)
    return conn


def _current_version(conn: sqlite3.Connection) -> int:
    conn.execute(
        'CREATE TABLE IF NOT EXISTS schema_version ('
        'version INTEGER NOT NULL, applied_at TEXT NOT NULL DEFAULT (datetime(\'now\')))'
    )
    row = conn.execute('SELECT MAX(version) AS v FROM schema_version').fetchone()
    return int(row['v']) if row and row['v'] is not None else 0


def _migrate(conn: sqlite3.Connection) -> None:
    """Bring the database up to :data:`SCHEMA_VERSION`, applying only missing steps."""
    version = _current_version(conn)
    if version >= SCHEMA_VERSION:
        return
    with conn:
        if version < 1:
            conn.executescript(_SCHEMA_V1)
            conn.execute('INSERT INTO schema_version(version) VALUES (1)')
        if version < 2:
            conn.executescript(_SCHEMA_V2)
            conn.execute('INSERT INTO schema_version(version) VALUES (2)')
        if version < 3:
            conn.executescript(_SCHEMA_V3)
            conn.execute('INSERT INTO schema_version(version) VALUES (3)')
        # Future migrations: `if version < 4: ...; conn.execute('INSERT ... VALUES (4)')`.
    log.info('Applied schema up to version %d', SCHEMA_VERSION)
