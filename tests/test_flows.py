"""End-to-end walk of the seven user flows against a real temp SQLite database.

Unlike ``test_write_api.py``, which stubs the store to test validation, this drives each flow
all the way to the database through the Flask test client — creating a tree, adding and
editing people, linking them, importing and exporting a GEDCOM, storing photos, recording
places, and editing vocabulary — and asserts the observable result of each step. It is the
regression guard that the app is usable end to end, not merely that its handlers exist.
"""

import io

import pytest

from Tree import create_app
from Tree.config import Configuration

AUTH = {'X-API-Token': 'test-token'}

# A tiny but valid PNG, so an upload exercises the real image pipeline.
_PNG = bytes.fromhex(
    '89504e470d0a1a0a0000000d49484452000000010000000108020000009077'
    '53de0000000c49444154789c6360000002000100' + '05a2d1e2' + '0000000049454e44ae426082'
)


@pytest.fixture()
def app(tmp_path):
    class _C(Configuration):
        API_TOKEN = 'test-token'
        DATABASE_PATH = tmp_path / 'family.sqlite'
        DATA_DIR = tmp_path / 'data'
        UPLOAD_IMAGE_PATH = tmp_path / 'data' / 'uploads'
        FACES_DIR = tmp_path / 'data' / 'faces'
        FACES_JSON_PATH = tmp_path / 'data' / 'faces' / 'faces.json'
        CORS_ALLOWED_ORIGINS = ['http://localhost:4200']

    application = create_app(_C)
    application.config['TESTING'] = True
    application._tree_dir = tmp_path / 'tree'   # handed to flow 1's create-tree step
    return application


@pytest.fixture()
def client(app):
    return app.test_client()


def _add_person(client, given, **extra):
    body = {'given': given, **extra}
    response = client.post('/api/v1/people', json=body, headers=AUTH)
    assert response.status_code == 201, response.get_json()
    return response.get_json()['Person']['id']


# ── flow 1: first run, no database, create a tree ────────────────────────────────
def test_flow_1_first_run_create_a_tree(app, client):
    assert client.get('/api/v1/trees', headers=AUTH).get_json()['Tree'] is None
    assert client.get('/api/v1/graph', headers=AUTH).get_json()['People'] == []

    created = client.post('/api/v1/trees',
                          json={'name': 'Mine', 'location': str(app._tree_dir)},
                          headers=AUTH)
    assert created.status_code == 200
    found = client.get('/api/v1/trees', headers=AUTH).get_json()['Tree']
    assert found['name'] == 'Mine'
    assert found['exists'] is True


# ── flow 2: add, edit, delete a person ───────────────────────────────────────────
def test_flow_2_add_edit_delete_person(app, client):
    client.post('/api/v1/trees', json={'name': 'T', 'location': str(app._tree_dir)},
                headers=AUTH)
    pid = _add_person(client, 'Ada', surname='Varma', sex='female')

    edited = client.patch(f'/api/v1/people/{pid}', json={'surname': 'Reddy'}, headers=AUTH)
    assert edited.status_code == 200
    people = client.get('/api/v1/graph', headers=AUTH).get_json()['People']
    assert next(p for p in people if p['id'] == pid)['surname'] == 'Reddy'

    removed = client.delete(f'/api/v1/people/{pid}', headers=AUTH)
    assert removed.status_code == 200
    assert client.get('/api/v1/graph', headers=AUTH).get_json()['People'] == []


# ── flow 3: link parent/child and spouse, birth order, pinned term ──────────────
def test_flow_3_links_birth_order_and_pins(app, client):
    client.post('/api/v1/trees', json={'name': 'T', 'location': str(app._tree_dir)},
                headers=AUTH)
    dad = _add_person(client, 'Chandra', sex='male')
    mum = _add_person(client, 'Deepa', sex='female')
    kid1 = _add_person(client, 'Aditya',
                       attachTo={'personId': dad, 'relation': 'child'})
    kid2 = _add_person(client, 'Bharath',
                       attachTo={'personId': dad, 'relation': 'child'})

    assert client.post('/api/v1/links',
                       json={'type': 'union', 'aId': dad, 'bId': mum},
                       headers=AUTH).status_code == 201
    assert client.post('/api/v1/links',
                       json={'type': 'parent', 'childId': kid1, 'parentId': mum},
                       headers=AUTH).status_code == 201
    assert client.post('/api/v1/birth-order',
                       json={'elder_id': kid1, 'younger_id': kid2},
                       headers=AUTH).status_code == 200

    pinned = client.post(f'/api/v1/people/{kid1}/pinned-term',
                         json={'base_term': 'father', 'term': 'నాన్న', 'side': 'paternal'},
                         headers=AUTH)
    assert pinned.status_code == 200
    vocab = client.get('/api/v1/vocabulary', headers=AUTH).get_json()
    assert any(pin['person'] == kid1 for pin in vocab['Pins'])

    graph = client.get('/api/v1/graph', headers=AUTH).get_json()
    assert graph['Counts']['people'] == 4
    assert graph['Counts']['unions'] == 1


# ── flow 4: GEDCOM export / import round-trip ───────────────────────────────────
def test_flow_4_gedcom_round_trip(app, client):
    client.post('/api/v1/trees', json={'name': 'T', 'location': str(app._tree_dir)},
                headers=AUTH)
    dad = _add_person(client, 'Chandra', sex='male', birth={'mode': 'year', 'year': 1958})
    _add_person(client, 'Aditya', attachTo={'personId': dad, 'relation': 'child'})

    export = client.post('/api/v1/trees/export', json={'format': 'gedcom7'}, headers=AUTH)
    assert export.status_code == 200
    assert export.get_json()['Bytes'] > 0

    # The tree's own family.ged is refreshed on every write; read it and import it back.
    from Tree.gedcom.store import export as refresh
    with app.app_context():
        from Tree.db import get_db
        text = refresh(get_db()).read_text()

    reimport = client.post('/api/v1/trees/import',
                           data={'file': (io.BytesIO(text.encode()), 'family.ged'),
                                 'mode': 'replace'},
                           content_type='multipart/form-data', headers=AUTH)
    assert reimport.status_code == 200
    result = reimport.get_json()['Result']
    assert result['people'] == 2
    assert result['parentLinks'] == 1
    assert client.get('/api/v1/graph', headers=AUTH).get_json()['Counts']['people'] == 2


# ── flow 5: photos ─────────────────────────────────────────────────────────────
def test_flow_5_photos_upload_list_attach_serve(app, client):
    client.post('/api/v1/trees', json={'name': 'T', 'location': str(app._tree_dir)},
                headers=AUTH)
    pid = _add_person(client, 'Ada')

    assert client.get('/api/v1/photos', headers=AUTH).get_json()['Photos'] == []

    upload = client.post('/api/v1/photos',
                         data={'image': (io.BytesIO(_PNG), 'me.png'),
                               'caption': 'A portrait', 'personId': str(pid)},
                         content_type='multipart/form-data', headers=AUTH)
    assert upload.status_code == 201
    photo = upload.get_json()['Photo']
    assert photo['caption'] == 'A portrait'
    assert photo['personId'] == pid

    listed = client.get('/api/v1/photos', headers=AUTH).get_json()['Photos']
    assert len(listed) == 1
    by_person = client.get(f'/api/v1/photos?person={pid}', headers=AUTH).get_json()['Photos']
    assert len(by_person) == 1

    served = client.get(photo['url'], headers=AUTH)
    assert served.status_code == 200
    assert served.data == _PNG

    detached = client.post(f'/api/v1/photos/{photo["id"]}/attach',
                           json={'personId': None}, headers=AUTH)
    assert detached.get_json()['Photo']['personId'] is None


def test_flow_5_photo_endpoints_registered_without_dlib(app):
    """The photo blueprint must be reachable whether or not face recognition is installed:
    it carries no heavy dependency, unlike Tree.faces."""
    rules = {str(r) for r in app.url_map.iter_rules()}
    assert '/api/v1/photos' in rules
    assert '/api/v1/photos/<int:photo_id>/file' in rules


def test_flow_5_deleting_a_person_keeps_their_photo_unattached(app, client):
    client.post('/api/v1/trees', json={'name': 'T', 'location': str(app._tree_dir)},
                headers=AUTH)
    pid = _add_person(client, 'Ada')
    client.post('/api/v1/photos',
                data={'image': (io.BytesIO(_PNG), 'x.png'), 'personId': str(pid)},
                content_type='multipart/form-data', headers=AUTH)
    client.delete(f'/api/v1/people/{pid}', headers=AUTH)
    photos = client.get('/api/v1/photos', headers=AUTH).get_json()['Photos']
    assert len(photos) == 1
    assert photos[0]['personId'] is None


# ── flow 6: places ───────────────────────────────────────────────────────────────
def test_flow_6_places_set_get_and_partial_update(app, client):
    client.post('/api/v1/trees', json={'name': 'T', 'location': str(app._tree_dir)},
                headers=AUTH)
    pid = _add_person(client, 'Ada')

    assert client.get(f'/api/v1/people/{pid}/places', headers=AUTH).get_json() == {
        'Message': 'Places loaded', 'Person': pid, 'birthPlace': '', 'deathPlace': ''}

    client.patch(f'/api/v1/people/{pid}/places',
                 json={'birthPlace': 'Hyderabad', 'deathPlace': 'Chennai'}, headers=AUTH)
    got = client.get(f'/api/v1/people/{pid}/places', headers=AUTH).get_json()
    assert got['birthPlace'] == 'Hyderabad'
    assert got['deathPlace'] == 'Chennai'

    # A partial update leaves the field it does not mention alone.
    client.patch(f'/api/v1/people/{pid}/places', json={'deathPlace': 'Bangalore'}, headers=AUTH)
    got = client.get(f'/api/v1/people/{pid}/places', headers=AUTH).get_json()
    assert got['birthPlace'] == 'Hyderabad'
    assert got['deathPlace'] == 'Bangalore'


def test_flow_6_places_survive_a_gedcom_round_trip(app, client):
    client.post('/api/v1/trees', json={'name': 'T', 'location': str(app._tree_dir)},
                headers=AUTH)
    pid = _add_person(client, 'Ada', birth={'mode': 'year', 'year': 1950})
    client.patch(f'/api/v1/people/{pid}/places',
                 json={'birthPlace': 'Hyderabad, India', 'deathPlace': 'Chennai'}, headers=AUTH)

    from Tree.gedcom.store import export as refresh
    with app.app_context():
        from Tree.db import get_db
        text = refresh(get_db()).read_text()
    assert '2 PLAC Hyderabad, India' in text
    assert '2 PLAC Chennai' in text

    client.post('/api/v1/trees/import',
                data={'file': (io.BytesIO(text.encode()), 'family.ged'), 'mode': 'replace'},
                content_type='multipart/form-data', headers=AUTH)
    newid = client.get('/api/v1/graph', headers=AUTH).get_json()['People'][0]['id']
    got = client.get(f'/api/v1/people/{newid}/places', headers=AUTH).get_json()
    assert got['birthPlace'] == 'Hyderabad, India'
    assert got['deathPlace'] == 'Chennai'


def test_flow_6_a_place_with_no_date_still_writes_its_event(app, client):
    """A place is often known when the date is not; the BIRT/DEAT event must still be emitted
    so the PLAC has somewhere to hang."""
    client.post('/api/v1/trees', json={'name': 'T', 'location': str(app._tree_dir)},
                headers=AUTH)
    pid = _add_person(client, 'Ada')   # no dates at all
    client.patch(f'/api/v1/people/{pid}/places', json={'birthPlace': 'Guntur'}, headers=AUTH)
    from Tree.gedcom.store import export as refresh
    with app.app_context():
        from Tree.db import get_db
        text = refresh(get_db()).read_text()
    assert '1 BIRT' in text
    assert '2 PLAC Guntur' in text


# ── flow 7: vocabulary editing ───────────────────────────────────────────────────
def test_flow_7_vocabulary_add_and_list(app, client):
    client.post('/api/v1/trees', json={'name': 'T', 'location': str(app._tree_dir)},
                headers=AUTH)
    added = client.post('/api/v1/vocabulary',
                        json={'base_term': 'aunt', 'term': 'అత్త', 'side': 'paternal'},
                        headers=AUTH)
    assert added.status_code == 200
    vocab = client.get('/api/v1/vocabulary', headers=AUTH).get_json()
    assert 'aunt' in vocab['Added']
    assert vocab['Added']['aunt'][0]['term'] == 'అత్త'
