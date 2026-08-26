"""Face detection, labelling and recognition.

Fixes in this pass: the three removed Pillow APIs (``textsize``, ``getsize``, and the
``ANTIALIAS`` constant in ImageReducer), the unbound-local crash when the first detected face is
unknown, a default code path that returned ``None`` while its caller unpacked four values, the
missing font falling back instead of raising, base64 payloads that shipped the Python bytes
repr, and the encoding store described in ``encoding_store``.
"""

import base64
import io
import logging
import math
import textwrap
import uuid
from pathlib import Path

import face_recognition as FR
import numpy as np
from flask import current_app
from PIL import Image, ImageDraw, ImageFont

from Tree import g
from Tree.faces import encoding_store

log = logging.getLogger(__name__)

UNKNOWN = -1


def _load_font():
    """Resolve a drawing font, never raising.

    ``FONT_PATH`` defaulted to ``"~/usr/share/fonts/truetype/freefont/FreeMonoBold.ttf"`` -- a
    tilde glued to an absolute path, Linux-specific, and expanded by nothing -- so
    ``ImageFont.truetype`` raised on every call and no face endpoint could ever draw a label.
    """
    size = current_app.config['FONT_SIZE']
    candidates = []
    configured = current_app.config.get('FONT_PATH')
    if configured:
        candidates.append(Path(configured).expanduser())
    candidates.append(Path(__file__).resolve().parent / 'fonts' / 'DejaVuSansMono-Bold.ttf')
    candidates += [
        Path('/System/Library/Fonts/Supplemental/DejaVuSansMono-Bold.ttf'),
        Path('/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf'),
        Path('/usr/share/fonts/truetype/freefont/FreeMonoBold.ttf'),
    ]
    for candidate in candidates:
        try:
            if candidate.is_file():
                return ImageFont.truetype(str(candidate), size)
        except OSError:
            continue
    log.info('No TrueType font available; using the built-in bitmap font.')
    return ImageFont.load_default()


def _text_height(draw, font, text):
    """Pillow 10 removed ``draw.textsize`` and ``font.getsize``."""
    try:
        box = draw.textbbox((0, 0), text, font=font)
        return box[3] - box[1]
    except AttributeError:
        box = font.getbbox(text)
        return box[3] - box[1]


def _encode_jpeg(pil_image):
    buffer = io.BytesIO()
    pil_image.convert('RGB').save(buffer, 'JPEG')
    buffer.seek(0)
    # ``str(b64encode(...))`` shipped "b'...'" to clients, which no base64 decoder accepts.
    return base64.b64encode(buffer.read()).decode('ascii')


def number_of_faces(img_path):
    """Count faces. The original computed the encodings twice -- each of which re-runs the
    detector internally -- purely to test emptiness and then return a length."""
    image = FR.load_image_file(img_path)
    return len(FR.face_locations(image))


def recognize_encoding(encoding):
    """Return the vertex id of the closest stored match, or -1."""
    known, vertex_ids = encoding_store.load(current_app.config['FACES_JSON_PATH'])
    if not known:
        return UNKNOWN
    distances = FR.face_distance(np.asarray(known), np.asarray(encoding))
    if distances.size == 0:
        return UNKNOWN
    best = int(np.argmin(distances))
    if float(distances[best]) < current_app.config['FACE_MATCH_THRESHOLD']:
        return vertex_ids[best]
    return UNKNOWN


def _person_label(vertex_id, relatives_dictionary):
    """The caption for a recognised face."""
    if relatives_dictionary is None:
        first = g.V(vertex_id).values('Firstname')
        last = g.V(vertex_id).values('Lastname')
        parts = []
        if first.hasNext():
            parts.append(str(first.next()))
        if last.hasNext():
            parts.append(str(last.next()))
        return ' '.join(parts)

    if vertex_id not in relatives_dictionary:
        return ''
    relation = relatives_dictionary[vertex_id]
    if relation is None:
        return ''
    nickname = g.V(vertex_id).values('Nickname')
    if nickname.hasNext():
        return f'{nickname.next()}-{relation}'
    return str(relation)


def draw_boxes(img_path, relatives_dictionary=None, encoded_Image=False, numbering=False):
    """Annotate an image and return ``(token, filename, base64_or_None, locations)``.

    The original returned ``None`` whenever ``encoded_Image`` was False, and one caller
    unpacked that into four names. It also referenced the caption variable before assignment
    whenever the first detected face was unknown, raising UnboundLocalError.
    """
    image = FR.load_image_file(img_path)
    face_locations = FR.face_locations(image)
    face_encodings = FR.face_encodings(image, face_locations)

    pil_image = Image.fromarray(image)
    draw = ImageDraw.Draw(pil_image)
    font = _load_font()

    unknown_face_locations = []
    known_face_location_tuples = []
    face_number = 0

    faces_found = zip(face_locations, face_encodings, strict=True)
    for (top, right, bottom, left), face_encoding in faces_found:
        vertex_id = recognize_encoding(face_encoding)
        label = ''

        if vertex_id != UNKNOWN:
            label = _person_label(vertex_id, relatives_dictionary)
            if relatives_dictionary is None:
                known_face_location_tuples.append(
                    ((top, right, bottom, left), vertex_id, label)
                )
        else:
            face_number += 1
            unknown_face_locations.append([(top, right, bottom, left), face_number])
            if numbering:
                label = str(face_number)

        if not label:
            continue

        highlight = (95, 31, 211) if label == 'Me' else (255, 255, 0)
        text_colour = (255, 255, 255) if label == 'Me' else (0, 0, 0)
        draw.rectangle(((left - 15, top - 15), (right + 15, bottom + 15)), outline=highlight)

        text_height = _text_height(draw, font, label)
        wrap_width = max(1, math.floor((right - left + 30) / 8))
        offset = 0
        for line in textwrap.wrap(label, width=wrap_width):
            draw.rectangle(
                ((left - 15, bottom + 15 + offset - text_height - 5),
                 (right + 15, bottom + 25 + offset)),
                fill=highlight, outline=highlight,
            )
            draw.text((left - 9, bottom + 15 - text_height - 5 + offset), line,
                      fill=text_colour, font=font)
            offset += text_height + 4

    del draw
    token = str(uuid.uuid4())
    filename = Path(current_app.config['UPLOAD_IMAGE_PATH']) / f'{token}.jpg'
    pil_image.convert('RGB').save(filename)
    encoded = _encode_jpeg(pil_image) if encoded_Image else None
    pil_image.close()

    locations = unknown_face_locations if numbering else known_face_location_tuples
    return token, str(filename), encoded, locations


def relate_person_to_face(image_path, vertex_id_map=None, file_to_be_deleted=None):
    """Associate detected faces with person vertices.

    ``vertex_id_map`` used to be dereferenced unconditionally, so the one caller that passed
    only an image path raised TypeError. The file deletion also happened *before* any work, so
    a later failure destroyed the upload with nothing recorded.
    """
    if not vertex_id_map:
        log.info('No face-to-person mapping supplied; nothing to record.')
        return 0

    image = FR.load_image_file(image_path)
    face_locations = FR.face_locations(image)
    face_encodings = FR.face_encodings(image, face_locations)

    recorded = 0
    for location, encoding in zip(face_locations, face_encodings, strict=True):
        if location in vertex_id_map:
            encoding_store.save(
                current_app.config['FACES_JSON_PATH'], encoding, vertex_id_map[location],
            )
            recorded += 1

    if file_to_be_deleted:
        try:
            Path(file_to_be_deleted).unlink(missing_ok=True)
        except OSError:
            log.warning('Could not remove %s', file_to_be_deleted, exc_info=True)
    return recorded


def recognize_person(img_path, face_location=None):
    """Identify a face.

    Returns a vertex id, ``-1`` when unrecognised, or ``(base64_image, locations)`` when the
    image holds several faces and no specific one was selected. The original returned ``None``
    on its final path, and the caller then compared that with ``>``.

    Note: this no longer writes the query encoding back into the store. The original did, so
    every search -- including an unauthenticated one -- enlarged the biometric database with
    caller-supplied templates.
    """
    image = FR.load_image_file(img_path)
    locations = FR.face_locations(image)
    encodings = FR.face_encodings(image, locations)

    if not encodings:
        return UNKNOWN

    if len(encodings) == 1 and face_location is None:
        return recognize_encoding(encodings[0])

    if face_location is None:
        return _encode_jpeg(Image.fromarray(image)), locations

    wanted = tuple(face_location)
    for location, encoding in zip(locations, encodings, strict=True):
        if tuple(location) == wanted:
            return recognize_encoding(encoding)
    return UNKNOWN
