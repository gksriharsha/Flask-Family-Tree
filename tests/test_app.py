import pathlib
import sys

import pytest

from Tree import create_app
from Tree.config import Configuration


class _Config(Configuration):
    API_TOKEN = 'test-token'
    INJECT_GROOVY_AT_STARTUP = False
    CORS_ALLOWED_ORIGINS = ['http://localhost:4200']


@pytest.fixture()
def client():
    app = create_app(_Config)
    app.config['TESTING'] = True
    return app.test_client()


def test_app_boots_without_a_database(client):
    """create_app used to submit functions.groovy synchronously and call sys.exit(1) on
    failure, so the factory could not complete without Gremlin Server -- and under gunicorn
    that was a respawn loop."""
    assert client.get('/health').status_code == 200


def test_every_route_requires_the_token_except_health(client):
    assert client.get('/query/count_people').status_code == 401
    assert client.post('/get/person', json={'ID': 1}).status_code == 401
    assert client.delete('/delete/nodes/1').status_code == 401
    assert client.get('/health').status_code == 200


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


def test_debug_endpoints_are_gone(client):
    headers = {'X-API-Token': 'test-token'}
    for path in ('/spoc', '/spoc2', '/spoc3', '/spoc4'):
        assert client.get(path, headers=headers).status_code == 404
    # The unauthenticated whole-database wipe is no longer routable.
    assert client.delete('/delete/nodes/all', headers=headers).status_code == 404


def test_cors_is_an_allowlist_not_a_wildcard(client):
    response = client.get('/health', headers={'Origin': 'https://evil.example'})
    assert 'Access-Control-Allow-Origin' not in response.headers
    response = client.get('/health', headers={'Origin': 'http://localhost:4200'})
    assert response.headers['Access-Control-Allow-Origin'] == 'http://localhost:4200'


def test_json_body_is_parsed_not_evaluated(client):
    headers = {'X-API-Token': 'test-token'}
    # A bare Python expression is no longer a valid body, and is certainly not executed.
    response = client.post('/get/person', data='__import__("os").getpid()',
                           content_type='application/json', headers=headers)
    assert response.status_code == 400
    assert 'JSON' in response.get_json()['Message']


def test_malformed_id_is_a_400_not_a_500(client):
    response = client.post('/get/person', json={'ID': 'all'},
                           headers={'X-API-Token': 'test-token'})
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
