import pytest

from Tree.Utils.RelationReducer import reduce


@pytest.mark.parametrize('chain, expected', [
    ([], []),                                        # used to return [None]
    (['Son_Of'], ['Son_Of']),                        # used to return [None]
    (['Son_Of', 'Father_Of*'], ['Son_Of', 'Father_Of']),   # '*' used to leak to the caller
    (['Father_Of', 'Brother_Of', 'Son_Of'], ['Cousin_Of']),
])
def test_reduce_edge_cases(chain, expected):
    assert reduce(chain) == expected


def test_reduce_always_returns_a_list():
    for chain in ([], ['Son_Of'], ['Father_Of', 'Son_Of']):
        assert isinstance(reduce(chain), list)


@pytest.mark.xfail(reason='The composition table cannot express cousin degree or removal. '
                          'Documented for the kinship-engine rewrite.')
def test_second_cousin_is_distinguished_from_first_cousin():
    first = reduce(['Father_Of', 'Brother_Of', 'Son_Of'])
    second = reduce(['Father_Of', 'Father_Of', 'Brother_Of', 'Son_Of', 'Son_Of'])
    assert first != second
