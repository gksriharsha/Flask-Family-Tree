"""End-to-end coverage of the SQLite cutover.

Unlike ``test_write_api``, which stubs the store to test validation in isolation, this file
exercises the whole path through the *real* SQLite store: the app boots against a fresh
database, and every assertion is about data that actually landed in a file. These are the
tests that would have caught a store that was wired up wrong rather than merely a validator
that was too strict.
"""

import time

import pytest

from Tree import create_app
from Tree.config import Configuration

AUTH = {'X-API-Token': 'test-token'}


@pytest.fixture()
def client(tmp_path):
    class _Config(Configuration):
        API_TOKEN = 'test-token'
        CORS_ALLOWED_ORIGINS = ['http://localhost:4200']
        DATABASE_PATH = tmp_path / 'family.sqlite'

    app = create_app(_Config)
    app.config['TESTING'] = True
    return app.test_client()


def test_app_boots_on_a_fresh_db_and_ready_is_200(client):
    assert client.get('/ready').status_code == 200
    # A brand-new tree is empty, not an error.
    graph = client.get('/api/v1/graph', headers=AUTH)
    assert graph.status_code == 200
    assert graph.get_json()['People'] == []


def test_posting_a_person_shows_up_in_the_graph(client):
    created = client.post('/api/v1/people',
                          json={'given': 'Ada', 'surname': 'Varma', 'sex': 'female'},
                          headers=AUTH)
    assert created.status_code == 201
    person_id = created.get_json()['Person']['id']

    graph = client.get('/api/v1/graph', headers=AUTH).get_json()
    ids = {p['id'] for p in graph['People']}
    assert person_id in ids
    ada = next(p for p in graph['People'] if p['id'] == person_id)
    assert ada['given'] == 'Ada'
    assert ada['surname'] == 'Varma'
    assert ada['sex'] == 'female'


def test_link_and_relationship_run_end_to_end_through_the_real_store(client):
    parent = client.post('/api/v1/people', json={'given': 'Chandra', 'sex': 'male'},
                         headers=AUTH).get_json()['Person']['id']
    child = client.post('/api/v1/people', json={'given': 'Aditya', 'sex': 'male'},
                        headers=AUTH).get_json()['Person']['id']

    linked = client.post('/api/v1/links',
                         json={'type': 'parent', 'childId': child, 'parentId': parent},
                         headers=AUTH)
    assert linked.status_code == 201

    rel = client.get(f'/api/v1/people/{child}/relationship-to/{parent}', headers=AUTH)
    assert rel.status_code == 200
    labels = [r['en'] for r in rel.get_json()['Relationships']]
    # The child's father, described from the child's point of view.
    assert any('father' in label.lower() for label in labels)

    # The parent link is visible in the whole-graph read too.
    graph = client.get('/api/v1/graph', headers=AUTH).get_json()
    assert {'child': child, 'parent': parent, 'role': 'biological'} in graph['ParentLinks']


def test_search_finds_by_given_and_surname_case_insensitively(client):
    client.post('/api/v1/people', json={'given': 'Deepa', 'surname': 'Reddy'}, headers=AUTH)
    client.post('/api/v1/people', json={'given': 'Bharath', 'surname': 'Varma'}, headers=AUTH)

    by_given = client.get('/api/v1/search?q=deep', headers=AUTH).get_json()['Data']
    assert any(row['Firstname'] == 'Deepa' for row in by_given)

    by_surname = client.get('/api/v1/search?q=VARMA', headers=AUTH).get_json()['Data']
    assert any(row.get('Lastname') == 'Varma' for row in by_surname)


def _seed_and_export_roundtrip(client, tmp_path):
    """Create a tree, seed the demo family into it, export, and re-import into a fresh tree."""
    from Tree import seed as seed_module
    from Tree.gedcom.store import export_as, import_document
    from Tree.storage import count_people, open_database

    location = tmp_path / 'tree'
    client.post('/api/v1/trees',
                json={'name': 'Demo', 'location': str(location)}, headers=AUTH)

    # Seed straight into the same database the app uses.
    db_path = client.application.config['DATABASE_PATH']
    conn = open_database(str(db_path))
    seed_module.seed(conn)
    original = count_people(conn)
    assert original == 29

    exported = export_as(conn, '7.0')
    text = exported.read_text(encoding='utf-8')

    # Import that GEDCOM into a brand-new, empty database and count.
    fresh = open_database(str(tmp_path / 'fresh.sqlite'))
    summary = import_document(fresh, text, replace=False)
    return original, summary['people'], count_people(fresh)


def test_gedcom_import_export_round_trips_the_seed_family(client, tmp_path):
    original, imported, reloaded = _seed_and_export_roundtrip(client, tmp_path)
    assert imported == original
    assert reloaded == original


def test_ten_thousand_people_graph_returns_under_three_seconds(client, make_synthetic_family):
    """Write a 10k-person synthetic tree straight through the store, then time a full
    /api/v1/graph read in the test client. The whole-tree load is four bulk SELECTs, so it
    stays well inside the budget even at this size."""
    from Tree.gedcom.store import write_family_graph
    from Tree.storage import count_people, open_database

    family = make_synthetic_family(10000, seed=1)
    db_path = client.application.config['DATABASE_PATH']
    conn = open_database(str(db_path))
    write_family_graph(conn, family)
    assert count_people(conn) == 10000

    started = time.perf_counter()
    response = client.get('/api/v1/graph', headers=AUTH)
    elapsed = time.perf_counter() - started

    assert response.status_code == 200
    assert response.get_json()['Counts']['people'] == 10000
    assert elapsed < 3.0, f'/api/v1/graph took {elapsed:.2f}s for 10k people'
