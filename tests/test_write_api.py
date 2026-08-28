"""The write endpoints, and what they refuse.

Rejection cases fail during validation and never reach the store. Acceptance cases mock the
store outright: asserting merely that a request is "not a 400" is what let an earlier version
of this file write nine junk people into a live family tree, because the request sailed past
validation and straight into a JanusGraph that happened to be running on localhost. A test
that means "this payload is accepted" must say so against a stub, never against whatever
database is within reach.
"""

import pytest

from Tree import create_app
from Tree.api import routes
from Tree.config import Configuration

AUTH = {'X-API-Token': 'test-token'}


class _Config(Configuration):
    API_TOKEN = 'test-token'
    INJECT_GROOVY_AT_STARTUP = False
    CORS_ALLOWED_ORIGINS = ['http://localhost:4200']


@pytest.fixture()
def client():
    app = create_app(_Config)
    app.config['TESTING'] = True
    return app.test_client()


@pytest.fixture()
def stub_store(monkeypatch):
    """Replace the store so an accepted payload has somewhere harmless to land.

    Returns the list of calls, so a test can check what the endpoint actually passed down
    rather than only that it did not complain.
    """
    calls = []

    def fake_create(_g, **fields):
        calls.append(fields)
        return 4242

    # Patch the module object directly: the string form resolves `Tree.api` to the
    # Blueprint that package re-exports, not to the module.
    monkeypatch.setattr(routes, 'create_person', fake_create)
    monkeypatch.setattr(routes, '_refresh_files', lambda: None)
    monkeypatch.setattr(routes, 'link_parent',
                        lambda *a, **k: calls.append(('link_parent', a, k)))
    monkeypatch.setattr(routes, 'link_union',
                        lambda *a, **k: calls.append(('link_union', a, k)))
    return calls


def test_the_write_endpoints_exist_and_are_authenticated(client):
    """They did not exist at all before: the tree could be read and never added to."""
    assert client.post('/api/v1/people', json={'given': 'A'}).status_code == 401
    assert client.patch('/api/v1/people/1', json={'given': 'A'}).status_code == 401
    assert client.delete('/api/v1/people/1').status_code == 401
    assert client.post('/api/v1/links', json={'type': 'union'}).status_code == 401
    assert client.delete('/api/v1/links', json={'type': 'union'}).status_code == 401


def test_a_person_needs_a_given_name(client):
    assert client.post('/api/v1/people', json={}, headers=AUTH).status_code == 400
    response = client.post('/api/v1/people', json={'given': '   '}, headers=AUTH)
    assert response.status_code == 400
    assert 'given name' in response.get_json()['Message']


def test_sex_must_be_one_of_the_four_recorded_values(client):
    response = client.post('/api/v1/people',
                           json={'given': 'A', 'sex': 'yes'}, headers=AUTH)
    assert response.status_code == 400
    assert 'sex must be' in response.get_json()['Message']


def test_unknown_is_an_accepted_sex_not_an_error(client, stub_store):
    """The form offers it as a real answer, so the API has to treat it as one."""
    response = client.post('/api/v1/people',
                           json={'given': 'Ada', 'sex': 'unknown'}, headers=AUTH)
    assert response.status_code == 201
    assert stub_store[0]['sex'] == 'unknown'


def test_a_date_mode_that_does_not_exist_is_refused(client):
    response = client.post('/api/v1/people',
                           json={'given': 'A', 'birth': {'mode': 'roughly', 'year': 1955}},
                           headers=AUTH)
    assert response.status_code == 400
    assert 'birth' in response.get_json()['Message']


def test_a_range_that_runs_backwards_is_refused(client):
    response = client.post(
        '/api/v1/people',
        json={'given': 'A', 'birth': {'mode': 'between', 'year': 1960, 'year2': 1950}},
        headers=AUTH)
    assert response.status_code == 400


def test_a_date_missing_the_year_its_mode_requires_is_refused(client):
    response = client.post('/api/v1/people',
                           json={'given': 'A', 'birth': {'mode': 'about'}}, headers=AUTH)
    assert response.status_code == 400


def test_dying_before_being_born_is_refused(client):
    response = client.post('/api/v1/people',
                           json={'given': 'A',
                                 'birth': {'mode': 'year', 'year': 1960},
                                 'death': {'mode': 'year', 'year': 1950}},
                           headers=AUTH)
    assert response.status_code == 400
    assert 'before the birth date' in response.get_json()['Message']


def test_an_overlapping_birth_and_death_is_allowed(client, stub_store):
    """Born about 1955, died 1956 is odd but not impossible, and the API is not the place to
    decide it is wrong. Only a death provably before the birth is refused."""
    response = client.post('/api/v1/people',
                           json={'given': 'Ada',
                                 'birth': {'mode': 'about', 'year': 1955},
                                 'death': {'mode': 'year', 'year': 1956}},
                           headers=AUTH)
    assert response.status_code == 201
    assert stub_store[0]['birth'].mode == 'about'


def test_an_update_with_no_fields_is_refused(client):
    response = client.patch('/api/v1/people/1', json={}, headers=AUTH)
    assert response.status_code == 400
    assert 'Nothing to change' in response.get_json()['Message']


def test_link_type_must_be_parent_or_union(client):
    response = client.post('/api/v1/links',
                           json={'type': 'cousin', 'aId': 1, 'bId': 2}, headers=AUTH)
    assert response.status_code == 400
    assert "'parent' or 'union'" in response.get_json()['Message']


def test_link_ids_must_be_integers(client):
    response = client.post('/api/v1/links',
                           json={'type': 'parent', 'childId': 'one', 'parentId': 2},
                           headers=AUTH)
    assert response.status_code == 400


def test_a_link_role_must_be_one_the_engine_understands(client):
    """'step' and 'foster' exist in the model but the interface only offers the two the
    kinship renderers currently distinguish, so anything else is refused rather than silently
    stored as biological."""
    response = client.post('/api/v1/links',
                           json={'type': 'parent', 'childId': 1, 'parentId': 2,
                                 'role': 'godparent'},
                           headers=AUTH)
    assert response.status_code == 400
    assert 'role must be' in response.get_json()['Message']


def test_attach_to_must_name_a_relation_the_api_supports(client, stub_store):
    response = client.post('/api/v1/people',
                           json={'given': 'Ada',
                                 'attachTo': {'personId': 1, 'relation': 'uncle'}},
                           headers=AUTH)
    assert response.status_code == 400


def test_attaching_a_child_links_it_the_right_way_round(client, stub_store):
    """'child' means the new person is a child of the one named, so the new id has to arrive
    as the child and the named one as the parent. Getting this backwards would invert a
    generation and rename every relationship downstream of it."""
    response = client.post('/api/v1/people',
                           json={'given': 'Ada',
                                 'attachTo': {'personId': 7, 'relation': 'child'}},
                           headers=AUTH)
    assert response.status_code == 201
    link = next(c for c in stub_store if isinstance(c, tuple) and c[0] == 'link_parent')
    assert link[2]['child_id'] == 4242
    assert link[2]['parent_id'] == 7


def test_attaching_a_parent_links_it_the_other_way_round(client, stub_store):
    client.post('/api/v1/people',
                json={'given': 'Ada', 'attachTo': {'personId': 7, 'relation': 'parent'}},
                headers=AUTH)
    link = next(c for c in stub_store if isinstance(c, tuple) and c[0] == 'link_parent')
    assert link[2]['child_id'] == 7
    assert link[2]['parent_id'] == 4242


@pytest.mark.parametrize(('sent', 'stored'), [
    (True, True), (False, False), ('yes', True), ('no', False),
    ('unknown', None), (None, None),
])
def test_living_accepts_yes_no_and_unknown(client, stub_store, sent, stored):
    response = client.post('/api/v1/people',
                           json={'given': 'Ada', 'living': sent}, headers=AUTH)
    assert response.status_code == 201
    assert stub_store[0]['living'] is stored


def test_living_refuses_anything_else(client):
    response = client.post('/api/v1/people',
                           json={'given': 'Ada', 'living': 'maybe'}, headers=AUTH)
    assert response.status_code == 400


def test_a_created_person_is_reported_with_its_new_id(client, stub_store):
    response = client.post('/api/v1/people',
                           json={'given': 'Ada', 'surname': 'Varma'}, headers=AUTH)
    assert response.status_code == 201
    assert response.get_json()['Person']['id'] == 4242
    assert stub_store[0]['given'] == 'Ada'
    assert stub_store[0]['surname'] == 'Varma'


def test_a_date_reaches_the_store_at_the_precision_it_was_sent(client, stub_store):
    """The interval, not a flattened year -- otherwise "about 1955" would be stored as a
    January day nobody has a document for, which is the whole problem this replaced."""
    client.post('/api/v1/people',
                json={'given': 'Ada', 'birth': {'mode': 'between', 'year': 1950,
                                                'year2': 1960}},
                headers=AUTH)
    birth = stub_store[0]['birth']
    assert (birth.mode, birth.year, birth.year2) == ('between', 1950, 1960)
    assert birth.gedcom() == 'BET 1950 AND 1960'
