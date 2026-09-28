"""The windowed, paginated read API (item E).

Two things are proven here. First, correctness: the windowed ``/graph``, the capped full
``/graph``, cursor-paginated ``/people`` and the now-indexed ``/search`` behave exactly as the
deliverables specify — every existing response key preserved, the new keys added, and the
edge cases (bad cursor, root outside the window, unknown anchor) answered rather than 500ing.
Second, speed: on the committed 10k synthetic tree the windowed graph, a page and a search all
land well inside their budgets. The perf assertions are a ceiling that catches an O(N)
regression, not a benchmark — the numbers the code actually posts are far below them and are
stated in the PR description — so ordinary CI-runner variance sits comfortably inside.
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


def _add(client, given, surname='', sex='male'):
    return client.post('/api/v1/people',
                       json={'given': given, 'surname': surname, 'sex': sex},
                       headers=AUTH).get_json()['Person']['id']


def _link_parent(client, child, parent):
    client.post('/api/v1/links', json={'type': 'parent', 'childId': child, 'parentId': parent},
                headers=AUTH)


def _link_union(client, a, b):
    client.post('/api/v1/links', json={'type': 'union', 'aId': a, 'bId': b}, headers=AUTH)


@pytest.fixture()
def small_tree(client):
    """Grandpa → Dad → Me → Kid, Me married to Spouse, plus an unrelated Stranger."""
    ids = {name: _add(client, name) for name in
           ('Grandpa', 'Dad', 'Me', 'Kid', 'Spouse', 'Stranger')}
    _link_parent(client, ids['Dad'], ids['Grandpa'])
    _link_parent(client, ids['Me'], ids['Dad'])
    _link_parent(client, ids['Kid'], ids['Me'])
    _link_union(client, ids['Me'], ids['Spouse'])
    return ids


# ── windowed /graph ──────────────────────────────────────────────────────────────
def test_window_returns_only_people_within_the_hop_radius(client, small_tree):
    ids = small_tree
    body = client.get(f'/api/v1/graph?around={ids["Me"]}&generations=1',
                      headers=AUTH).get_json()
    got = {p['id'] for p in body['People']}
    # One hop from Me: Dad (parent), Kid (child), Spouse (union). Not Grandpa (2 hops), not
    # the unrelated Stranger.
    assert got == {ids['Dad'], ids['Me'], ids['Kid'], ids['Spouse']}
    assert ids['Grandpa'] not in got
    assert ids['Stranger'] not in got


def test_window_widening_reaches_the_grandparent(client, small_tree):
    ids = small_tree
    body = client.get(f'/api/v1/graph?around={ids["Me"]}&generations=2',
                      headers=AUTH).get_json()
    got = {p['id'] for p in body['People']}
    assert ids['Grandpa'] in got
    assert ids['Stranger'] not in got


def test_window_preserves_existing_keys_and_adds_the_new_ones(client, small_tree):
    ids = small_tree
    body = client.get(f'/api/v1/graph?around={ids["Me"]}&generations=1',
                      headers=AUTH).get_json()
    # Every historical key is still present.
    for key in ('Root', 'Side', 'People', 'ParentLinks', 'Unions', 'Counts'):
        assert key in body
    # A person still carries relationships + seniorityQuestion.
    me = next(p for p in body['People'] if p['id'] == ids['Me'])
    assert 'relationships' in me and 'seniorityQuestion' in me
    # The added keys.
    assert body['Window'] == {'around': ids['Me'], 'generations': 1}
    assert body['Counts']['truncated'] is False
    assert body['Counts']['totalPeople'] == 6
    # Links are only among included people.
    included = {p['id'] for p in body['People']}
    for link in body['ParentLinks']:
        assert link['child'] in included and link['parent'] in included


def test_window_defaults_generations_and_root_to_around(client, small_tree):
    ids = small_tree
    body = client.get(f'/api/v1/graph?around={ids["Me"]}', headers=AUTH).get_json()
    assert body['Window']['generations'] == Configuration.GRAPH_DEFAULT_GENERATIONS
    assert body['Root'] == ids['Me']


def test_window_generations_is_clamped_to_the_max(client, small_tree):
    ids = small_tree
    body = client.get(f'/api/v1/graph?around={ids["Me"]}&generations=999',
                      headers=AUTH).get_json()
    assert body['Window']['generations'] == Configuration.GRAPH_MAX_GENERATIONS


def test_window_rejects_bad_generations(client, small_tree):
    ids = small_tree
    assert client.get(f'/api/v1/graph?around={ids["Me"]}&generations=-1',
                      headers=AUTH).status_code == 400
    assert client.get(f'/api/v1/graph?around={ids["Me"]}&generations=abc',
                      headers=AUTH).status_code == 400


def test_window_unknown_anchor_is_404(client, small_tree):
    assert client.get('/api/v1/graph?around=999999', headers=AUTH).status_code == 404


def test_window_root_outside_the_window_is_400(client, small_tree):
    ids = small_tree
    # Grandpa is 2 hops from Me, so with generations=1 he is outside the window.
    resp = client.get(
        f'/api/v1/graph?around={ids["Me"]}&generations=1&root={ids["Grandpa"]}', headers=AUTH)
    assert resp.status_code == 400


def test_window_labels_are_computed_from_root(client, small_tree):
    ids = small_tree
    body = client.get(f'/api/v1/graph?around={ids["Me"]}&generations=1',
                      headers=AUTH).get_json()
    dad = next(p for p in body['People'] if p['id'] == ids['Dad'])
    labels = [r['en'].lower() for r in dad['relationships']]
    assert any('father' in label for label in labels)


# ── full /graph, capped ────────────────────────────────────────────────────────
def test_full_graph_still_works_and_carries_new_counts(client, small_tree):
    body = client.get('/api/v1/graph', headers=AUTH).get_json()
    assert body['Window'] is None
    assert body['Counts']['people'] == 6
    assert body['Counts']['totalPeople'] == 6
    assert body['Counts']['truncated'] is False


def test_full_graph_is_capped_and_reports_truncation(client, small_tree):
    # Force the cap below the tree size; the read must return the cap's worth and flag it,
    # never 500.
    client.application.config['MAX_GRAPH_PEOPLE'] = 3
    resp = client.get('/api/v1/graph', headers=AUTH)
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['Counts']['people'] == 3
    assert body['Counts']['totalPeople'] == 6
    assert body['Counts']['truncated'] is True


def test_empty_tree_is_not_an_error(client):
    body = client.get('/api/v1/graph', headers=AUTH).get_json()
    assert body['People'] == []
    assert body['Counts']['truncated'] is False
    assert body['Counts']['totalPeople'] == 0
    assert body['Window'] is None


# ── cursor-paginated /people ──────────────────────────────────────────────────────
def test_people_pagination_walks_every_person_once(client):
    names = [f'P{i:03d}' for i in range(25)]
    for n in names:
        _add(client, n)
    seen = []
    cursor = None
    for _ in range(20):  # generous ceiling; the loop breaks on the last page
        url = '/api/v1/people?limit=10' + (f'&cursor={cursor}' if cursor else '')
        body = client.get(url, headers=AUTH).get_json()
        seen.extend(p['given'] for p in body['People'])
        assert body['Total'] == 25
        cursor = body['NextCursor']
        if cursor is None:
            break
    assert sorted(seen) == sorted(names)
    assert len(seen) == 25  # no duplicates, no skips


def test_people_limit_is_capped(client):
    for i in range(5):
        _add(client, f'P{i}')
    client.application.config['MAX_PAGE_SIZE'] = 2
    body = client.get('/api/v1/people?limit=1000', headers=AUTH).get_json()
    assert len(body['People']) == 2


def test_people_filter_by_prefix(client):
    _add(client, 'Aditya', 'Varma')
    _add(client, 'Bharath', 'Reddy')
    _add(client, 'Anand', 'Rao')
    body = client.get('/api/v1/people?q=A', headers=AUTH).get_json()
    givens = {p['given'] for p in body['People']}
    assert givens == {'Aditya', 'Anand'}


def test_people_bad_cursor_is_400(client):
    _add(client, 'A')
    assert client.get('/api/v1/people?cursor=@@notbase64@@', headers=AUTH).status_code == 400
    # Valid base64 but wrong shape is also rejected.
    import base64
    bad = base64.urlsafe_b64encode(b'{"not":"a cursor"}').decode()
    assert client.get(f'/api/v1/people?cursor={bad}', headers=AUTH).status_code == 400


def test_people_bad_limit_is_400(client):
    assert client.get('/api/v1/people?limit=abc', headers=AUTH).status_code == 400
    assert client.get('/api/v1/people?limit=0', headers=AUTH).status_code == 400


def test_people_person_json_shape(client):
    pid = _add(client, 'Ada', 'Varma', sex='female')
    body = client.get('/api/v1/people', headers=AUTH).get_json()
    ada = next(p for p in body['People'] if p['id'] == pid)
    for key in ('id', 'given', 'surname', 'name', 'sex', 'birthYear', 'birth', 'living'):
        assert key in ada


# ── /search shape and index ───────────────────────────────────────────────────────
def test_search_shape_is_unchanged(client):
    _add(client, 'Deepa', 'Reddy', sex='female')
    _add(client, 'Bharath', 'Varma')
    by_given = client.get('/api/v1/search?q=Deep', headers=AUTH).get_json()['Data']
    assert any(row['Firstname'] == 'Deepa' for row in by_given)
    row = by_given[0]
    assert set(row).issubset({'ID', 'Firstname', 'Lastname', 'Gender'})
    assert 'ID' in row and 'Firstname' in row


def test_search_matches_by_surname_prefix(client):
    _add(client, 'Bharath', 'Varma')
    by_surname = client.get('/api/v1/search?q=Varm', headers=AUTH).get_json()['Data']
    assert any(row.get('Lastname') == 'Varma' for row in by_surname)


def test_search_uses_an_index_not_a_full_scan():
    """EXPLAIN QUERY PLAN over the query search_people runs must use a name index.

    A ``LIKE '%q%'`` substring scan reads every row (SCAN) and is exactly the full scan this
    round removes; a prefix (``q%``) is a range the NOCASE name indexes serve. We assert the
    planner picks an index for both name columns.
    """
    from Tree.storage import open_database
    conn = open_database(':memory:')
    conn.executemany('INSERT INTO person (given, surname) VALUES (?, ?)',
                     [('Aditya', 'Varma'), ('Bharath', 'Reddy')])
    for column, index in (('given', 'ix_person_given'), ('surname', 'ix_person_surname')):
        plan = conn.execute(
            f"EXPLAIN QUERY PLAN SELECT id FROM person WHERE {column} LIKE 'a%' ESCAPE '\\'"
        ).fetchall()
        detail = ' '.join(row['detail'] for row in plan)
        assert 'SCAN person' not in detail, f'{column} search does a full scan: {detail}'
        assert index in detail, f'{column} search does not use {index}: {detail}'


def test_people_page_uses_the_page_index_not_a_temp_sort():
    """The paginated ORDER BY must be served by ix_person_page, with no temp-B-tree sort."""
    from Tree.storage import open_database
    conn = open_database(':memory:')
    plan = conn.execute(
        'EXPLAIN QUERY PLAN SELECT id, given, surname, sex, birth, death, living '
        'FROM person ORDER BY given, surname, id LIMIT 200'
    ).fetchall()
    detail = ' '.join(row['detail'] for row in plan)
    assert 'ix_person_page' in detail, detail
    assert 'TEMP B-TREE' not in detail.upper(), detail


# ── performance on the 10k synthetic tree ──────────────────────────────────────────
def _seed_10k(client, make_synthetic_family):
    from Tree.gedcom.store import write_family_graph
    from Tree.storage import count_people, open_database
    family = make_synthetic_family(10000, seed=1)
    db_path = client.application.config['DATABASE_PATH']
    conn = open_database(str(db_path))
    id_map = write_family_graph(conn, family)
    assert count_people(conn) == 10000
    return conn, id_map


def _best_anchor(conn):
    """The db id with the most parent/child/union incidence — a well-connected window centre."""
    row = conn.execute(
        'SELECT id FROM ('
        '  SELECT parent_id AS id FROM parent_link '
        '  UNION ALL SELECT child_id FROM parent_link'
        ') GROUP BY id ORDER BY COUNT(*) DESC LIMIT 1'
    ).fetchone()
    return int(row['id'])


def test_windowed_graph_under_300ms_on_10k(client, make_synthetic_family):
    conn, _ = _seed_10k(client, make_synthetic_family)
    anchor = _best_anchor(conn)
    # Warm (schema/connection caches), then measure.
    client.get(f'/api/v1/graph?around={anchor}&generations=3', headers=AUTH)
    started = time.perf_counter()
    resp = client.get(f'/api/v1/graph?around={anchor}&generations=3', headers=AUTH)
    elapsed = time.perf_counter() - started
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['Window'] == {'around': anchor, 'generations': 3}
    assert body['Counts']['totalPeople'] == 10000
    # The window is a small fraction of the whole tree, not the whole tree.
    assert len(body['People']) < 300, f"window held {len(body['People'])} people"
    assert elapsed < 0.3, f'/graph?around took {elapsed * 1000:.0f}ms for 10k people'


def test_people_page_under_50ms_on_10k(client, make_synthetic_family):
    _seed_10k(client, make_synthetic_family)
    client.get('/api/v1/people?limit=200', headers=AUTH)  # warm
    started = time.perf_counter()
    resp = client.get('/api/v1/people?limit=200', headers=AUTH)
    elapsed = time.perf_counter() - started
    assert resp.status_code == 200
    assert len(resp.get_json()['People']) == 200
    assert elapsed < 0.05, f'/people?limit=200 took {elapsed * 1000:.0f}ms for 10k people'


def test_search_under_50ms_on_10k(client, make_synthetic_family):
    _seed_10k(client, make_synthetic_family)
    client.get('/api/v1/search?q=A', headers=AUTH)  # warm
    started = time.perf_counter()
    resp = client.get('/api/v1/search?q=A', headers=AUTH)
    elapsed = time.perf_counter() - started
    assert resp.status_code == 200
    assert elapsed < 0.05, f'/search?q=A took {elapsed * 1000:.0f}ms for 10k people'
