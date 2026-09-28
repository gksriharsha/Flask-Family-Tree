from Tree import seed


def test_fixture_matches_the_original_graph():
    assert len(seed.PEOPLE) == 29
    assert len(seed.EDGES) == 95            # 96 in the original; one Son_Of was written twice


def test_every_edge_endpoint_exists():
    keys = set(seed.PEOPLE)
    for source, _label, target in seed.EDGES:
        assert source in keys and target in keys


def test_dates_use_the_canonical_property_name():
    for props in seed.PEOPLE.values():
        assert 'Date_of_birth' in props
        assert 'Date_of_Birth' not in props


def test_adoptive_edges_are_preserved():
    assert {label for _s, label, _t in seed.EDGES if label.endswith('*')} == {
        'Son_Of*', 'Father_Of*', 'Mother_Of*', 'Brother_Of*', 'Sister_Of*',
    }


def test_seed_writes_the_demo_family_into_a_database(tmp_path):
    """Seeding into a fresh SQLite file lands all 29 people, and the within-family adoption
    survives as a child (person 7) carrying both biological and adoptive parents."""
    from Tree.storage import count_people, load_family_graph, open_database

    conn = open_database(str(tmp_path / 'family.sqlite'))
    ids = seed.seed(conn)
    assert len(ids) == 29
    assert count_people(conn) == 29

    family = load_family_graph(conn)
    assert len(family.people) == 29
    # addV7 (Harinath) has biological parents 5,6 and adoptive parents 8,9.
    harinath = ids['addV7']
    roles = {link.role for link in family.parent_links(harinath)}
    assert roles == {'biological', 'adoptive'}
    assert len(family.parent_links(harinath)) == 4

