import json

from Tree.faces import encoding_store


def test_legacy_format_is_converted_without_eval(tmp_path):
    path = tmp_path / 'faces.json'
    path.write_text(json.dumps({'(0.1, 0.2)': 4272}))
    encodings, ids = encoding_store.load(str(path))
    assert encodings == [[0.1, 0.2]] and ids == [4272]


def test_a_face_can_be_relabelled(tmp_path):
    """The old merge let the on-disk value overwrite the new one, so this was impossible."""
    path = tmp_path / 'faces.json'
    encoding_store.save(str(path), [0.1, 0.2], 4272)
    encoding_store.save(str(path), [0.1, 0.2], 9999)
    _encodings, ids = encoding_store.load(str(path))
    assert ids == [9999]


def test_stored_format_is_a_json_array(tmp_path):
    path = tmp_path / 'faces.json'
    encoding_store.save(str(path), [0.5], 1)
    assert isinstance(json.loads(path.read_text()), list)
