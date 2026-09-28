"""Storage-layer tests for the photo table, the places columns, and the schema v2 migration.

These sit beside the photo feature (:mod:`Tree.faces`, whose recognition half is the optional
dlib-backed layer) and cover the always-available half plus the schema step that adds them, so
a fresh database and an upgraded v1 one both end up with the same shape.
"""

import pytest

from Tree.storage import open_database
from Tree.storage.photos import (
    add_photo,
    attach_photo,
    delete_photo,
    get_photo,
    list_photos,
)
from Tree.storage.places import all_places, get_places, set_places


@pytest.fixture()
def conn(tmp_path):
    connection = open_database(str(tmp_path / 'tree.db'))
    connection.execute("INSERT INTO person (id, given) VALUES (1, 'Ada')")
    connection.execute("INSERT INTO person (id, given) VALUES (2, 'Bob')")
    connection.commit()
    return connection


def test_schema_is_at_version_two_with_the_new_shape(conn):
    version = conn.execute('SELECT MAX(version) AS v FROM schema_version').fetchone()['v']
    assert version == 2
    columns = {row['name'] for row in conn.execute('PRAGMA table_info(person)')}
    assert {'birth_place', 'death_place'} <= columns
    tables = {row['name'] for row in
              conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert 'photo' in tables


def test_migration_from_v1_adds_the_columns_in_place(tmp_path):
    """An existing v1 database gains the places columns and photo table without a rebuild."""
    import sqlite3

    from Tree.storage.schema import _SCHEMA_V1

    path = str(tmp_path / 'legacy.db')
    raw = sqlite3.connect(path)
    raw.executescript(_SCHEMA_V1)
    raw.execute('CREATE TABLE schema_version (version INTEGER NOT NULL, '
                "applied_at TEXT NOT NULL DEFAULT (datetime('now')))")
    raw.execute('INSERT INTO schema_version(version) VALUES (1)')
    raw.execute("INSERT INTO person (given) VALUES ('Existing')")
    raw.commit()
    raw.close()

    upgraded = open_database(path)
    version = upgraded.execute('SELECT MAX(version) AS v FROM schema_version').fetchone()['v']
    assert version == 2
    # the pre-existing person is untouched, and now has NULL places
    row = upgraded.execute('SELECT given, birth_place FROM person').fetchone()
    assert row['given'] == 'Existing'
    assert row['birth_place'] is None


# ── places ───────────────────────────────────────────────────────────────────────
def test_places_default_to_empty_and_round_trip(conn):
    assert get_places(conn, 1) == {'birthPlace': '', 'deathPlace': ''}
    set_places(conn, 1, birth_place='Hyderabad', death_place='Chennai')
    assert get_places(conn, 1) == {'birthPlace': 'Hyderabad', 'deathPlace': 'Chennai'}


def test_set_places_leaves_an_omitted_column_alone(conn):
    set_places(conn, 1, birth_place='Hyderabad', death_place='Chennai')
    set_places(conn, 1, death_place='Bangalore')      # birth omitted
    assert get_places(conn, 1) == {'birthPlace': 'Hyderabad', 'deathPlace': 'Bangalore'}


def test_an_empty_string_clears_a_place_to_null(conn):
    set_places(conn, 1, birth_place='Hyderabad')
    set_places(conn, 1, birth_place='')
    assert get_places(conn, 1)['birthPlace'] == ''
    assert conn.execute('SELECT birth_place FROM person WHERE id = 1').fetchone()[0] is None


def test_all_places_only_lists_people_with_a_place(conn):
    set_places(conn, 2, birth_place='Guntur')
    everyone = all_places(conn)
    assert set(everyone) == {2}
    assert everyone[2]['birthPlace'] == 'Guntur'


def test_places_on_a_missing_person_raise(conn):
    with pytest.raises(ValueError, match='No person'):
        get_places(conn, 999)
    with pytest.raises(ValueError, match='No person'):
        set_places(conn, 999, birth_place='X')


# ── photos ───────────────────────────────────────────────────────────────────────
def test_add_list_and_get_a_photo(conn):
    pid = add_photo(conn, 'a.jpg', caption='Portrait', person_id=1)
    photo = get_photo(conn, pid)
    assert photo['filename'] == 'a.jpg'
    assert photo['caption'] == 'Portrait'
    assert photo['personId'] == 1
    assert [p['id'] for p in list_photos(conn)] == [pid]
    assert [p['id'] for p in list_photos(conn, person_id=1)] == [pid]
    assert list_photos(conn, person_id=2) == []


def test_a_photo_needs_a_filename(conn):
    with pytest.raises(ValueError, match='filename'):
        add_photo(conn, '   ')


def test_attaching_to_a_missing_person_is_refused(conn):
    pid = add_photo(conn, 'a.jpg')
    with pytest.raises(ValueError, match='No person'):
        attach_photo(conn, pid, 999)


def test_deleting_a_person_detaches_their_photos(conn):
    pid = add_photo(conn, 'a.jpg', person_id=1)
    conn.execute('DELETE FROM person WHERE id = 1')
    conn.commit()
    assert get_photo(conn, pid)['personId'] is None


def test_delete_photo_returns_its_filename(conn):
    pid = add_photo(conn, 'gone.jpg')
    assert delete_photo(conn, pid) == 'gone.jpg'
    assert get_photo(conn, pid) is None
    with pytest.raises(ValueError, match='No photo'):
        delete_photo(conn, pid)
