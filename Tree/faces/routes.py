"""Photo endpoints.

The header values that drove this pipeline were ``eval``-ed straight out of the WSGI environ.
They are parsed as JSON now. Uploads are stored under a generated name rather than the
client-supplied one, because the original joined ``secure_filename(...)`` onto a shared
directory -- so two callers uploading ``photo.jpg`` overwrote each other, and the second caller's
task id resolved to the first caller's image.

Known remaining limitation, unchanged by this pass: the task table is a module-level dictionary,
so the two-phase upload flow only works when both requests land on the same worker process. A
shared store is the real fix and is out of scope here; the table is at least bounded now so it
cannot grow without limit.
"""

import logging
from collections import OrderedDict
from pathlib import Path

from flask import Blueprint, current_app

from Tree.faces.recognition import UNKNOWN, draw_boxes, recognize_person, relate_person_to_face
from Tree.model.Person import Person
from Tree.people.people_Service import retrieve_person_service
from Tree.relations.gremlin_Interface import get_all_relations
from Tree.Utils.http import ApiError, as_vertex_id, as_vertex_ids, json_header, ok
from Tree.Utils.ImageReducer import reduce

log = logging.getLogger(__name__)

faces = Blueprint('faces', __name__, url_prefix='/picture')

MAX_TRACKED_TASKS = 256
_tasks = OrderedDict()


def _remember(token, path):
    _tasks[token] = path
    while len(_tasks) > MAX_TRACKED_TASKS:
        _tasks.popitem(last=False)


def _lookup(token):
    path = _tasks.get(token)
    if path is None:
        raise ApiError('Unknown or expired Task-id.', status=404)
    return path


def _allowed(filename):
    if not filename or '.' not in filename:
        return False
    extension = filename.rsplit('.', 1)[1].lower()
    return extension in current_app.config['ALLOWED_IMAGE_EXTENSIONS']


def _store_upload(field='image'):
    """Save an upload under a generated name and return its path, or None if absent."""
    from flask import request
    if field not in request.files:
        return None
    upload = request.files[field]
    if not upload or not _allowed(upload.filename):
        raise ApiError('Filename or extension is invalid.', status=406)

    extension = upload.filename.rsplit('.', 1)[1].lower()
    import uuid
    destination = Path(current_app.config['UPLOAD_IMAGE_PATH']) / f'{uuid.uuid4()}.{extension}'
    upload.save(destination)
    reduce(destination, fixed_height=current_app.config['RESIZED_IMAGE_HEIGHT'])
    return destination


def _person_response(vertex_id):
    relations, person_dictionary = retrieve_person_service(vertex_id)
    return ok('Person found',
              Data=Person.createPersonObject(person_dictionary).to_dict(),
              Relations=relations)


@faces.route('/search', methods=['POST'])
def picture_search():
    path = _store_upload()

    if path is None:
        # Second phase: the caller picked one face out of a multi-face photo.
        token = json_header('Task-id', required=False)
        location = json_header('face-location', required=False)
        if token is None or location is None:
            raise ApiError('Provide an image, or both Task-id and face-location.', status=404)
        path = _lookup(str(token))
        response = recognize_person(path, face_location=location)
    else:
        response = recognize_person(str(path))

    if isinstance(response, tuple):
        encoded, locations = response
        token = str(__import__('uuid').uuid4())
        _remember(token, str(path))
        return ok('Multiple people detected', Image=encoded,
                  **{'Face-locations': locations, 'Task-id': token})

    if response == UNKNOWN:
        return ok('Selected person is not recognized', status=404)
    return _person_response(response)


@faces.route('/recognize', methods=['POST'])
def recognize():
    path = _store_upload()

    if path is not None:
        token, _filename, encoded, locations = draw_boxes(
            str(path), encoded_Image=True, numbering=True,
        )
        _remember(token, str(path))
        return ok('Multiple people detected', Image=encoded,
                  **{'Face-locations': locations, 'Task-id': token})

    token = str(json_header('Task-id'))
    path = _lookup(token)
    vertex_map = _parse_vertex_map(json_header('Vertex-id-map'))
    recorded = relate_person_to_face(image_path=path, vertex_id_map=vertex_map)
    return ok('Mapped the picture to faces', Result=recorded)


def _parse_vertex_map(payload):
    """Accept ``[{"box": [t,r,b,l], "vertex_id": n}, ...]`` or the legacy flat list of fives."""
    if isinstance(payload, list) and payload and isinstance(payload[0], dict):
        return {
            tuple(int(v) for v in entry['box']): as_vertex_id(entry['vertex_id'])
            for entry in payload
        }
    if isinstance(payload, list):
        if len(payload) % 5 != 0:
            raise ApiError('Vertex-id-map must contain groups of five values.')
        mapping = {}
        for index in range(0, len(payload), 5):
            box = tuple(int(v) for v in payload[index:index + 4])
            mapping[box] = as_vertex_id(payload[index + 4])
        return mapping
    raise ApiError('Vertex-id-map must be a JSON array.')


@faces.route('/relate', methods=['POST'])
def relate():
    path = _store_upload()

    if path is not None:
        token, _filename, encoded, locations = draw_boxes(str(path), encoded_Image=True)
        _remember(token, str(path))
        return ok('Select the faces to relate to this person', Image=encoded,
                  **{'Face-locations': locations, 'Task-id': token})

    token = str(json_header('Task-id'))
    path = _lookup(token)
    start_id = as_vertex_id(json_header('start_id'), field='start_id')
    end_ids = as_vertex_ids(
        json_header('end_ids'), current_app.config['MAX_RELATION_TARGETS'], field='end_ids',
    )
    relatives = get_all_relations(start_id=start_id, end_ids=end_ids)
    _token, _filename, encoded, _locations = draw_boxes(
        img_path=path, relatives_dictionary=relatives, encoded_Image=True,
    )
    return ok('All selections related', Image=encoded)
