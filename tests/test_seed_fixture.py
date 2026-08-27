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
