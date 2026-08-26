import pytest

from Tree.Utils.http import ApiError, as_vertex_id, as_vertex_ids


@pytest.mark.parametrize('value, expected', [(4272, 4272), ('4272', 4272), (' 12 ', 12)])
def test_valid_ids_are_coerced(value, expected):
    assert as_vertex_id(value) == expected


@pytest.mark.parametrize('value', [
    '__import__("os").system("id")',     # the payload eval() would have executed
    None, True, 'all', [1], {},
])
def test_hostile_and_malformed_ids_are_rejected(value):
    with pytest.raises(ApiError):
        as_vertex_id(value)


def test_id_lists_are_capped():
    assert as_vertex_ids(['1', 2], max_items=5) == [1, 2]
    with pytest.raises(ApiError):
        as_vertex_ids(list(range(60)), max_items=50)
    with pytest.raises(ApiError):
        as_vertex_ids('not a list', max_items=50)
