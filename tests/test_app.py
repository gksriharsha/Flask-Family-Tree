import pathlib
import sys

import pytest

from Tree import create_app
from Tree.config import Configuration


class _Config(Configuration):
    API_TOKEN = 'test-token'
    CORS_ALLOWED_ORIGINS = ['http://localhost:4200']


@pytest.fixture()
def client(tmp_path):
    class _C(_Config):
        DATABASE_PATH = tmp_path / 'family.sqlite'
    app = create_app(_C)
    app.config['TESTING'] = True
    return app.test_client()


def test_app_boots_without_a_database(client):
    """create_app used to submit functions.groovy synchronously and call sys.exit(1) on
    failure, so the factory could not complete without a live backend. It now opens a plain
    SQLite file lazily per request, so the factory always completes and /health never touches
    the store."""
    assert client.get('/health').status_code == 200


def test_ready_reports_the_database_is_reachable(client):
    """A fresh SQLite file is created and the schema applied on first connection, so /ready
    answers 200 against a brand-new database."""
    response = client.get('/ready')
    assert response.status_code == 200
    assert response.get_json()['Message'] == 'ready'


def test_every_api_route_requires_the_token_except_health(client):
    assert client.get('/api/v1/graph').status_code == 401
    assert client.post('/api/v1/people', json={'given': 'A'}).status_code == 401
    assert client.delete('/api/v1/people/1').status_code == 401
    assert client.get('/health').status_code == 200
    assert client.get('/ready').status_code == 200


def test_token_is_accepted_via_either_header(client):
    # /api/v1/session is authenticated but touches no database, so this isolates the
    # auth decision from everything else.
    for headers in ({'X-API-Token': 'test-token'},
                    {'Authorization': 'Bearer test-token'}):
        assert client.get('/api/v1/session', headers=headers).status_code == 200
    assert client.get('/api/v1/session', headers={'X-API-Token': 'wrong'}).status_code == 401
    assert client.get('/api/v1/session').status_code == 401


def test_the_interface_shell_is_public_but_the_api_is_not(client):
    """The browser must be able to load the page that asks for a token."""
    assert client.get('/api/v1/graph').status_code == 401


def test_the_debug_and_legacy_endpoints_are_gone(client):
    """The unauthenticated whole-database wipe (/delete/nodes/all), the /spoc reseed routes,
    and the 2021 blueprints (/get/person, /query/*, /add/person) are removed entirely — they
    are no longer routable at all."""
    headers = {'X-API-Token': 'test-token'}
    for path in ('/spoc', '/spoc2', '/spoc3', '/spoc4'):
        assert client.get(path, headers=headers).status_code == 404
    assert client.delete('/delete/nodes/all', headers=headers).status_code == 404
    assert client.delete('/delete/nodes/1', headers=headers).status_code == 404
    assert client.post('/get/person', json={'ID': 1}, headers=headers).status_code == 404
    assert client.get('/query/count_people', headers=headers).status_code == 404


def test_cors_is_an_allowlist_not_a_wildcard(client):
    response = client.get('/health', headers={'Origin': 'https://evil.example'})
    assert 'Access-Control-Allow-Origin' not in response.headers
    response = client.get('/health', headers={'Origin': 'http://localhost:4200'})
    assert response.headers['Access-Control-Allow-Origin'] == 'http://localhost:4200'


def test_json_body_is_parsed_not_evaluated(client):
    headers = {'X-API-Token': 'test-token'}
    # A bare Python expression is no longer a valid body, and is certainly not executed.
    response = client.post('/api/v1/people', data='__import__("os").getpid()',
                           content_type='application/json', headers=headers)
    assert response.status_code == 400
    assert 'JSON' in response.get_json()['Message']


def test_malformed_id_is_a_400_not_a_500(client):
    """A non-integer id on a typed-int route is a 404 (no route matches); a bad id in a body
    field is a 400 from validation, never a 500 and never executed."""
    headers = {'X-API-Token': 'test-token'}
    response = client.post('/api/v1/birth-order',
                           json={'elder_id': 'all', 'younger_id': 2}, headers=headers)
    assert response.status_code == 400


def test_responses_are_served_as_json(client):
    """Every response previously set a header literally named 'ContentType', so JSON was served
    as text/html."""
    assert client.get('/health').headers['Content-Type'].startswith('application/json')


def test_no_eval_remains_in_application_code():
    """Parses the AST rather than grepping, so comments describing the old behaviour do not
    trip it. The same checker runs in CI."""
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
    from tools.check_no_eval import offenders

    root = pathlib.Path(__file__).resolve().parent.parent
    targets = [*sorted((root / 'Tree').rglob('*.py')), root / 'wsgi.py', root / 'TreeServer.py']
    assert offenders(targets) == []
