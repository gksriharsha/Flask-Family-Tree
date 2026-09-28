"""Tests for the SQLite storage backend.

Two things are proven here. First, that every function mirrors the semantics of
:mod:`Tree.kinship.store` — name-only creates, no placeholder dates, explicit date/sex
clearing, cascading deletes, cycle refusal, idempotent unions, birth-order replacement,
settings round trips, search and count. Second — the golden test — that a family built through
the SQLite *write* functions, loaded back with :func:`load_family_graph`, drives the kinship
engine to the *same* answers as the hand-built in-memory graph in ``test_kinship.py``.
"""

from __future__ import annotations

import time
from dataclasses import replace

import pytest

from tests import family_fixture
from Tree.kinship import (
    ADOPTIVE,
    FEMALE,
    MALE,
    UNKNOWN,
    closest,
    relationships,
    render_english,
    render_telugu,
)
from Tree.kinship.dates import DateValue
from Tree.storage import (
    add_word,
    count_people,
    create_person,
    delete_person,
    link_parent,
    link_union,
    load_family_graph,
    load_tree_settings,
    load_vocabulary,
    open_database,
    pin_term,
    record_birth_order,
    save_tree_settings,
    search_people,
    unlink_parent,
    unlink_union,
    unpin_term,
    update_person,
)


@pytest.fixture()
def conn(tmp_path):
    database = open_database(str(tmp_path / 'tree.db'))
    yield database
    database.close()


# ── schema ──────────────────────────────────────────────────────────────────────
def test_open_database_is_idempotent(tmp_path):
    path = str(tmp_path / 'tree.db')
    first = open_database(path)
    create_person(first, 'Anand')
    first.close()
    # Re-opening applies no migration and loses nothing.
    second = open_database(path)
    assert count_people(second) == 1
    assert second.execute('PRAGMA foreign_keys').fetchone()[0] == 1
    assert second.execute('PRAGMA journal_mode').fetchone()[0].lower() == 'wal'
    second.close()


# ── creating people ──────────────────────────────────────────────────────────────
def test_create_requires_a_given_name(conn):
    with pytest.raises(ValueError):
        create_person(conn, '   ')


def test_create_writes_no_placeholder_date(conn):
    pid = create_person(conn, 'Anand', 'Rao', sex=MALE)
    row = conn.execute('SELECT birth, death, sex FROM person WHERE id = ?', (pid,)).fetchone()
    assert row['birth'] is None
    assert row['death'] is None
    assert row['sex'] == 'Male'


def test_create_stores_known_date_as_gedcom(conn):
    pid = create_person(conn, 'Anand', birth=DateValue('about', year=1955))
    row = conn.execute('SELECT birth FROM person WHERE id = ?', (pid,)).fetchone()
    assert row['birth'] == 'ABT 1955'
    graph = load_family_graph(conn)
    assert graph.people[pid].birth.mode == 'about'
    assert graph.people[pid].birth_year == 1955


def test_unknown_sex_stores_null(conn):
    pid = create_person(conn, 'Anand', sex=UNKNOWN)
    row = conn.execute('SELECT sex FROM person WHERE id = ?', (pid,)).fetchone()
    assert row['sex'] is None
    assert load_family_graph(conn).people[pid].sex == UNKNOWN


# ── updating people ──────────────────────────────────────────────────────────────
def test_update_leaves_absent_fields_alone(conn):
    pid = create_person(conn, 'Anand', 'Rao', sex=MALE, birth=DateValue('year', year=1950))
    update_person(conn, pid, surname='Varma')
    row = conn.execute('SELECT surname, birth, sex FROM person WHERE id = ?', (pid,)).fetchone()
    assert row['surname'] == 'Varma'
    assert row['birth'] == '1950'          # untouched
    assert row['sex'] == 'Male'            # untouched


def test_update_clears_a_date_when_passed_unknown(conn):
    pid = create_person(conn, 'Anand', birth=DateValue('year', year=1950))
    update_person(conn, pid, birth=DateValue())     # UNKNOWN
    row = conn.execute('SELECT birth FROM person WHERE id = ?', (pid,)).fetchone()
    assert row['birth'] is None


def test_update_clears_sex_when_passed_unknown(conn):
    pid = create_person(conn, 'Anand', sex=MALE)
    update_person(conn, pid, sex=UNKNOWN)
    row = conn.execute('SELECT sex FROM person WHERE id = ?', (pid,)).fetchone()
    assert row['sex'] is None


def test_update_unknown_person_raises(conn):
    with pytest.raises(ValueError):
        update_person(conn, 999, surname='X')


# ── deleting people cascades ─────────────────────────────────────────────────────
def test_delete_cascades_every_link(conn):
    a = create_person(conn, 'Parent', sex=MALE)
    b = create_person(conn, 'Child', sex=MALE)
    c = create_person(conn, 'Spouse', sex=FEMALE)
    d = create_person(conn, 'Sibling', sex=MALE)
    link_parent(conn, child_id=b, parent_id=a)
    link_union(conn, a, c)
    link_parent(conn, child_id=d, parent_id=a)
    record_birth_order(conn, elder_id=b, younger_id=d)
    term_id = add_word(conn, 'నాన్న', 'నాన్నగారు', 'Nannagaru')
    pin_term(conn, a, 'నాన్న', term_id)

    delete_person(conn, a)

    assert conn.execute('SELECT COUNT(*) FROM parent_link').fetchone()[0] == 0
    assert conn.execute('SELECT COUNT(*) FROM union_link').fetchone()[0] == 0
    assert conn.execute('SELECT COUNT(*) FROM pinned_term').fetchone()[0] == 0
    # birth_order between b and d does not involve a, so it survives
    assert conn.execute('SELECT COUNT(*) FROM birth_order').fetchone()[0] == 1


def test_delete_unknown_person_raises(conn):
    with pytest.raises(ValueError):
        delete_person(conn, 999)


# ── parent links ─────────────────────────────────────────────────────────────────
def test_link_parent_refuses_self(conn):
    a = create_person(conn, 'Anand')
    with pytest.raises(ValueError):
        link_parent(conn, child_id=a, parent_id=a)


def test_link_parent_refuses_ancestry_cycle(conn):
    a = create_person(conn, 'A')
    b = create_person(conn, 'B')
    c = create_person(conn, 'C')
    link_parent(conn, child_id=b, parent_id=a)   # a -> b
    link_parent(conn, child_id=c, parent_id=b)   # b -> c
    # Making a the child of c would make a its own great-... ancestor.
    with pytest.raises(ValueError):
        link_parent(conn, child_id=a, parent_id=c)


def test_link_parent_stores_role(conn):
    a = create_person(conn, 'Parent', sex=MALE)
    b = create_person(conn, 'Child', sex=MALE)
    link_parent(conn, child_id=b, parent_id=a, role=ADOPTIVE)
    graph = load_family_graph(conn)
    link = graph.parent_links(b)[0]
    assert link.role == ADOPTIVE
    assert link.is_birth is False


def test_link_parent_is_idempotent_on_role(conn):
    a = create_person(conn, 'Parent')
    b = create_person(conn, 'Child')
    link_parent(conn, child_id=b, parent_id=a)
    link_parent(conn, child_id=b, parent_id=a, role=ADOPTIVE)   # updates role
    rows = conn.execute('SELECT role FROM parent_link WHERE child_id=? AND parent_id=?',
                        (b, a)).fetchall()
    assert len(rows) == 1
    assert rows[0]['role'] == ADOPTIVE


def test_unlink_parent_works_in_either_direction(conn):
    a = create_person(conn, 'Parent')
    b = create_person(conn, 'Child')
    link_parent(conn, child_id=b, parent_id=a)
    unlink_parent(conn, child_id=a, parent_id=b)   # swapped args
    assert conn.execute('SELECT COUNT(*) FROM parent_link').fetchone()[0] == 0


# ── unions ───────────────────────────────────────────────────────────────────────
def test_link_union_is_idempotent_and_one_row_per_pair(conn):
    a = create_person(conn, 'A')
    b = create_person(conn, 'B')
    link_union(conn, a, b)
    link_union(conn, b, a)     # same pair, other order
    link_union(conn, a, b)
    rows = conn.execute('SELECT a_id, b_id FROM union_link').fetchall()
    assert len(rows) == 1
    assert rows[0]['a_id'] < rows[0]['b_id']


def test_link_union_refuses_self(conn):
    a = create_person(conn, 'A')
    with pytest.raises(ValueError):
        link_union(conn, a, a)


def test_unlink_union_works_in_either_order(conn):
    a = create_person(conn, 'A')
    b = create_person(conn, 'B')
    link_union(conn, a, b)
    unlink_union(conn, b, a)
    assert conn.execute('SELECT COUNT(*) FROM union_link').fetchone()[0] == 0


# ── birth order ──────────────────────────────────────────────────────────────────
def test_record_birth_order_replaces_prior_answer(conn):
    a = create_person(conn, 'A')
    b = create_person(conn, 'B')
    record_birth_order(conn, elder_id=a, younger_id=b)
    record_birth_order(conn, elder_id=b, younger_id=a)   # the family changed its mind
    rows = conn.execute('SELECT elder_id FROM birth_order').fetchall()
    assert len(rows) == 1
    assert rows[0]['elder_id'] == b


def test_record_birth_order_refuses_self(conn):
    a = create_person(conn, 'A')
    with pytest.raises(ValueError):
        record_birth_order(conn, elder_id=a, younger_id=a)


def test_birth_order_survives_the_load(conn):
    a = create_person(conn, 'A', birth=DateValue('year', year=1950))
    b = create_person(conn, 'B', birth=DateValue('year', year=1955))
    record_birth_order(conn, elder_id=b, younger_id=a)   # contradicts the dates
    graph = load_family_graph(conn)
    # a recorded answer beats the dates
    assert graph.seniority(a, b) is True


# ── settings round trip ──────────────────────────────────────────────────────────
def test_settings_round_trip(conn):
    assert load_tree_settings(conn) is None
    save_tree_settings(conn, Name='Varma Family', Gedcom_path='/trees/varma')
    save_tree_settings(conn, Name='Varma Kutumbam')      # overwrite one field
    settings = load_tree_settings(conn)
    assert settings == {'Name': 'Varma Kutumbam', 'Gedcom_path': '/trees/varma'}


# ── search ───────────────────────────────────────────────────────────────────────
def test_search_is_case_insensitive_substring_on_both_names(conn):
    create_person(conn, 'Aditya', 'Varma')
    create_person(conn, 'Bharath', 'Reddy')
    create_person(conn, 'Chandra', 'Varma')
    assert {p.given for p in search_people(conn, 'ADIT')} == {'Aditya'}
    assert {p.given for p in search_people(conn, 'varm')} == {'Aditya', 'Chandra'}
    assert search_people(conn, '') == []


def test_search_finds_telugu_text(conn):
    create_person(conn, 'చంద్ర', 'వర్మ')
    create_person(conn, 'భరత్', 'రెడ్డి')
    found = search_people(conn, 'వర్మ')
    assert [p.given for p in found] == ['చంద్ర']


def test_count_people(conn):
    assert count_people(conn) == 0
    create_person(conn, 'A')
    create_person(conn, 'B')
    assert count_people(conn) == 2


# ── vocabulary ───────────────────────────────────────────────────────────────────
def test_add_word_is_idempotent(conn):
    first = add_word(conn, 'చిన్నాన్న', 'బాబాయి', 'Babai')
    second = add_word(conn, 'చిన్నాన్న', 'బాబాయి', 'Babai')
    assert first == second
    vocab = load_vocabulary(conn)
    assert [v.term for v in vocab.added['చిన్నాన్న']] == ['బాబాయి']
    assert vocab.added['చిన్నాన్న'][0].added_by_family is True


def test_pin_and_unpin_term(conn):
    person = create_person(conn, 'Uncle', sex=MALE)
    term_id = add_word(conn, 'చిన్నాన్న', 'బాబాయి', 'Babai')
    pin_term(conn, person, 'చిన్నాన్న', term_id)
    vocab = load_vocabulary(conn)
    assert vocab.pins[(person, 'చిన్నాన్న')].term == 'బాబాయి'
    unpin_term(conn, person, 'చిన్నాన్న')
    assert (person, 'చిన్నాన్న') not in load_vocabulary(conn).pins


def test_pin_replaces_prior_pin(conn):
    person = create_person(conn, 'Uncle', sex=MALE)
    first = add_word(conn, 'చిన్నాన్న', 'బాబాయి', 'Babai')
    second = add_word(conn, 'చిన్నాన్న', 'చిన్నయ్య', 'Chinnayya')
    pin_term(conn, person, 'చిన్నాన్న', first)
    pin_term(conn, person, 'చిన్నాన్న', second)
    rows = conn.execute('SELECT COUNT(*) FROM pinned_term WHERE person_id=?', (person,)).fetchone()
    assert rows[0] == 1
    assert load_vocabulary(conn).pins[(person, 'చిన్నాన్న')].term == 'చిన్నయ్య'


def test_vocabulary_is_scoped_by_side(conn):
    add_word(conn, 'చిన్నాన్న', 'బాబాయి', side='paternal')
    add_word(conn, 'చిన్నాన్న', 'కక్కయ్య', side='maternal')
    assert 'చిన్నాన్న' in load_vocabulary(conn, side='paternal').added
    paternal = load_vocabulary(conn, side='paternal').added['చిన్నాన్న']
    assert [v.term for v in paternal] == ['బాబాయి']


# ── the golden test: the SQLite store drives the engine identically ──────────────
def _build_family_in_sqlite(conn):
    """Build the shared fixture family through the store, returning fixture-id -> sqlite-id."""
    id_map: dict[int, int] = {}
    for pid, given, sex, born in family_fixture.PEOPLE:
        birth = DateValue('year', year=born) if born is not None else None
        id_map[pid] = create_person(conn, given, family_fixture.SURNAME, sex=sex, birth=birth)
    for child, parent in family_fixture.BIRTH_LINKS:
        link_parent(conn, child_id=id_map[child], parent_id=id_map[parent])
    for child, parent in family_fixture.ADOPTIVE_LINKS:
        link_parent(conn, child_id=id_map[child], parent_id=id_map[parent], role=ADOPTIVE)
    for a, b in family_fixture.UNIONS:
        link_union(conn, id_map[a], id_map[b])
    return id_map


def _remap(kinship, id_map):
    """Rewrite the fixture ids inside a Kinship struct into their sqlite ids, for comparison."""
    changes = {}
    if kinship.seniority_pair is not None:
        changes['seniority_pair'] = tuple(id_map[i] for i in kinship.seniority_pair)
    if kinship.via is not None:
        changes['via'] = _remap(kinship.via, id_map)
    return replace(kinship, **changes) if changes else kinship


def test_golden_engine_parity_across_the_whole_family(conn):
    """Every relationship, rendered in English and Telugu, matches the in-memory graph."""
    mem = family_fixture.build()
    id_map = _build_family_in_sqlite(conn)
    db = load_family_graph(conn)

    ids = sorted(mem.people)
    for a in ids:
        for b in ids:
            mem_links = relationships(mem, a, b)
            db_links = relationships(db, id_map[a], id_map[b])
            assert len(mem_links) == len(db_links), f'link count differs for ({a}, {b})'
            for m, d in zip(mem_links, db_links, strict=True):
                assert _remap(m, id_map) == d, f'struct differs for ({a}, {b})'
                assert render_english(m) == render_english(d)
                assert render_telugu(m).text == render_telugu(d).text


def test_golden_representative_pairs(conn):
    """A named spot-check of the distinctions test_kinship.py cares about."""
    mem = family_fixture.build()
    id_map = _build_family_in_sqlite(conn)
    db = load_family_graph(conn)

    def en(graph, x, y):
        return render_english(closest(graph, x, y))

    def te(graph, x, y):
        return render_telugu(closest(graph, x, y)).text

    pairs = [(1, 3), (1, 5), (1, 6), (1, 11), (1, 14), (1, 20), (1, 25), (1, 7), (1, 10)]
    for a, b in pairs:
        assert en(mem, a, b) == en(db, id_map[a], id_map[b]), f'english ({a},{b})'
        assert te(mem, a, b) == te(db, id_map[a], id_map[b]), f'telugu ({a},{b})'
    # the seniority answer flows through the store, not just the in-memory graph
    assert en(db, id_map[1], id_map[20]) == 'Father’s younger brother'


def test_golden_recorded_seniority_resolves_through_the_store(conn):
    id_map = _build_family_in_sqlite(conn)
    # Harinath (7) has no birth year, so his rank vs the father (3) is unresolved.
    record_birth_order(conn, elder_id=id_map[7], younger_id=id_map[3])
    db = load_family_graph(conn)
    assert render_telugu(closest(db, id_map[1], id_map[7])).text == 'పెద్దనాన్న'


# ── performance: 10k people load in well under a second ──────────────────────────
def test_load_ten_thousand_people_under_a_second(conn):
    n = 10_000
    people = [(f'Person{i}', 'Varma', 'Male', str(1900 + (i % 120)), None, None)
              for i in range(n)]
    with conn:
        conn.executemany(
            'INSERT INTO person (given, surname, sex, birth, death, living) '
            'VALUES (?, ?, ?, ?, ?, ?)', people)
    ids = [row[0] for row in conn.execute('SELECT id FROM person ORDER BY id').fetchall()]
    # ~10k parent links: each person i (from the second) is a child of person i-1's slot,
    # kept acyclic by always linking a lower id as parent of a higher id.
    links = [(ids[i], ids[i - 1], 'biological') for i in range(1, n)]
    with conn:
        conn.executemany(
            'INSERT INTO parent_link (child_id, parent_id, role) VALUES (?, ?, ?)', links)

    start = time.perf_counter()
    graph = load_family_graph(conn, limit=n)
    elapsed = time.perf_counter() - start

    assert len(graph.people) == n
    assert sum(len(v) for v in graph.parents.values()) == n - 1
    assert elapsed < 1.0, f'load took {elapsed:.3f}s'
