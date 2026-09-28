"""Endpoints for the flows the cutover left unfinished: places and photographs.

Kept out of :mod:`Tree.api.routes` deliberately. That module is the people/links/vocabulary
surface and is already close to the project's file-length limit; a new flow belongs in a new
module registered alongside it (see :func:`Tree.create_app`) rather than growing it.

**Places** are the birth and death locations the old ``/get/location`` blueprint carried and
the SQLite cutover dropped. They live as two text columns on ``person`` (schema v2) and are
read and written here without the coordinate scraping that made the old endpoint a liability.

**Photos** are the plain, always-available half of the photograph feature. The face-recognition
pipeline in :mod:`Tree.faces` depends on ``dlib`` (a source-only build) and is registered only
when that import succeeds — so on an install without the toolchain the app had *no* photo
capability at all. This blueprint stores a file, captions it, attaches it to a person, lists
the lot and serves it back, with no heavy dependency, so a photograph is usable end to end
whether or not face recognition is installed.
"""

import logging
import uuid
from pathlib import Path

from flask import Blueprint, current_app, request, send_from_directory

from Tree.db import get_db
from Tree.storage import person_exists
from Tree.storage.photos import (
    add_photo,
    attach_photo,
    delete_photo,
    get_photo,
    list_photos,
)
from Tree.storage.places import get_places, set_places
from Tree.Utils.http import ApiError, as_vertex_id, json_body, ok

log = logging.getLogger(__name__)

flows = Blueprint('flows', __name__, url_prefix='/api/v1')


# ── places ──────────────────────────────────────────────────────────────────────
@flows.route('/people/<int:person_id>/places', methods=['GET'])
def get_person_places(person_id: int):
    """Where a person was born and where they died, as free text."""
    conn = get_db()
    try:
        places = get_places(conn, person_id)
    except ValueError as exc:
        raise ApiError(str(exc), status=404) from exc
    return ok('Places loaded', Person=person_id, **places)


@flows.route('/people/<int:person_id>/places', methods=['PATCH'])
def patch_person_places(person_id: int):
    """Set a person's birth and/or death place.

    An absent key is left as it was; an empty string clears that place. Mirrors the person
    write's "absent means leave alone, explicit means set" contract, so a partial edit never
    blanks a place the caller did not mention.
    """
    conn = get_db()
    body = json_body()
    kwargs = {}
    if 'birthPlace' in body:
        kwargs['birth_place'] = str(body.get('birthPlace') or '')
    if 'deathPlace' in body:
        kwargs['death_place'] = str(body.get('deathPlace') or '')
    if not kwargs:
        raise ApiError('Nothing to change.')
    try:
        set_places(conn, person_id, **kwargs)
    except ValueError as exc:
        raise ApiError(str(exc), status=404) from exc
    _refresh()
    return ok('Places updated', Person=person_id, **get_places(conn, person_id))


# ── photos ────────────────────────────────────────────────────────────────────
def _allowed(filename: str) -> bool:
    if not filename or '.' not in filename:
        return False
    extension = filename.rsplit('.', 1)[1].lower()
    return extension in current_app.config['ALLOWED_IMAGE_EXTENSIONS']


def _photo_json(photo: dict) -> dict:
    """Add a servable URL to a stored photo record."""
    return {**photo, 'url': f'/api/v1/photos/{photo["id"]}/file'}


@flows.route('/photos', methods=['GET'])
def get_photos():
    """Every photo, newest first — or only one person's when ``?person=`` is given."""
    conn = get_db()
    person_param = request.args.get('person')
    person_id = as_vertex_id(person_param, field='person') if person_param else None
    photos = list_photos(conn, person_id=person_id)
    return ok('Photos loaded', Photos=[_photo_json(p) for p in photos])


@flows.route('/photos', methods=['POST'])
def post_photo():
    """Upload a photo, optionally captioned and attached to a person.

    Multipart: ``image`` is the file, ``caption`` and ``personId`` are optional form fields.
    The file is stored under a generated name (never the client-supplied one, so two uploads
    of ``photo.jpg`` cannot overwrite each other) beneath ``UPLOAD_IMAGE_PATH``.
    """
    conn = get_db()
    upload = request.files.get('image')
    if upload is None or not upload.filename:
        raise ApiError('Provide an image file in the "image" field.')
    if not _allowed(upload.filename):
        raise ApiError('Filename or extension is invalid.', status=406)

    person_id = None
    raw_person = request.form.get('personId')
    if raw_person:
        person_id = as_vertex_id(raw_person, field='personId')
        if not person_exists(conn, person_id):
            raise ApiError('No such person.', status=404)

    extension = upload.filename.rsplit('.', 1)[1].lower()
    stored_name = f'{uuid.uuid4()}.{extension}'
    directory = Path(current_app.config['UPLOAD_IMAGE_PATH'])
    directory.mkdir(parents=True, exist_ok=True)
    upload.save(directory / stored_name)

    caption = (request.form.get('caption') or '').strip()
    try:
        photo_id = add_photo(conn, stored_name, caption=caption, person_id=person_id)
    except ValueError as exc:
        raise ApiError(str(exc)) from exc
    _refresh()
    return ok('Photo added', Photo=_photo_json(get_photo(conn, photo_id)), status=201)


@flows.route('/photos/<int:photo_id>/file', methods=['GET'])
def get_photo_file(photo_id: int):
    """Serve the stored image bytes for a photo."""
    conn = get_db()
    photo = get_photo(conn, photo_id)
    if photo is None:
        raise ApiError('No such photo.', status=404)
    return send_from_directory(current_app.config['UPLOAD_IMAGE_PATH'], photo['filename'])


@flows.route('/photos/<int:photo_id>/attach', methods=['POST'])
def post_photo_attach(photo_id: int):
    """Attach a photo to a person, or detach it when ``personId`` is null."""
    conn = get_db()
    body = json_body()
    raw = body.get('personId')
    person_id = None if raw is None else as_vertex_id(raw, field='personId')
    try:
        attach_photo(conn, photo_id, person_id)
    except ValueError as exc:
        raise ApiError(str(exc), status=404) from exc
    _refresh()
    return ok('Photo attached', Photo=_photo_json(get_photo(conn, photo_id)))


@flows.route('/photos/<int:photo_id>', methods=['DELETE'])
def remove_photo(photo_id: int):
    """Remove a photo, and its stored file with it."""
    conn = get_db()
    try:
        filename = delete_photo(conn, photo_id)
    except ValueError as exc:
        raise ApiError(str(exc), status=404) from exc
    stored = Path(current_app.config['UPLOAD_IMAGE_PATH']) / filename
    try:
        stored.unlink(missing_ok=True)
    except OSError:
        log.warning('Could not remove photo file %s', stored, exc_info=True)
    _refresh()
    return ok('Photo removed', Photo={'id': photo_id})


def _refresh() -> None:
    """Refresh the tree's GEDCOM file after a change, never failing the request that caused it.

    Places belong in the exported GEDCOM (as ``PLAC``), so a place edit refreshes the file for
    the same reason a person edit does. A photo change refreshes it too, so ``family.ged`` and
    its media directory stay consistent. Import kept out of the module scope to avoid a cycle
    with :mod:`Tree.gedcom.store`.
    """
    from Tree.gedcom.store import TreeNotCreated, export
    try:
        export(get_db())
    except TreeNotCreated:
        pass
    except Exception:
        log.exception('Could not refresh the tree files after a places/photos change.')
