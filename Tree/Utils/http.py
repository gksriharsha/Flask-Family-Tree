"""Request parsing and response helpers.

Every endpoint used to parse its body with ``eval(request.data.decode('ascii'))``, which made
the request body executable code and rejected any non-ASCII name. These helpers are the
replacement: bodies are parsed as JSON, and identifiers are coerced with ``int()`` rather than
``eval``, so a malformed value produces a 400 instead of running.
"""

import json

from flask import jsonify, request


class ApiError(Exception):
    """Raised for a client mistake. The app's error handler turns it into a JSON response."""

    def __init__(self, message, status=400):
        super().__init__(message)
        self.message = message
        self.status = status


def json_body(required=()):
    """Parse the request body as JSON and check that ``required`` keys are present.

    Accepts UTF-8, so Telugu and accented names round-trip. The previous
    ``.decode('ascii')`` raised UnicodeDecodeError on any name outside ASCII.
    """
    body = request.get_json(silent=True)
    if body is None:
        raise ApiError('Request body must be JSON.')
    if not isinstance(body, dict):
        raise ApiError('Request body must be a JSON object.')
    missing = [key for key in required if key not in body]
    if missing:
        raise ApiError('Missing required field(s): ' + ', '.join(missing))
    return body


def json_header(name, required=True, default=None):
    """Parse a JSON-encoded request header. Replaces ``eval`` on header values."""
    raw = request.headers.get(name)
    if raw is None or raw == '':
        if required:
            raise ApiError(f'Missing required header: {name}')
        return default
    try:
        return json.loads(raw)
    except (TypeError, ValueError) as exc:
        raise ApiError(f'Header {name} must be valid JSON.') from exc


def as_vertex_id(value, field='ID'):
    """Coerce a graph identifier to int. Replaces ``eval(str(...))``.

    ``eval`` was accidentally rejecting non-numeric ids here, so removing it without adding
    this coercion would widen the Gremlin injection hole rather than close it.
    """
    if isinstance(value, bool) or value is None:
        raise ApiError(f'{field} must be an integer.')
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ApiError(f'{field} must be an integer, got {value!r}.') from exc


def as_vertex_ids(values, max_items, field='ids'):
    """Coerce and cap a list of graph identifiers.

    The cap matters: this list drives a fan-out of graph traversals, so an unbounded list is a
    denial-of-service lever for any caller.
    """
    if not isinstance(values, (list, tuple)):
        raise ApiError(f'{field} must be a JSON array.')
    if len(values) > max_items:
        raise ApiError(f'{field} may contain at most {max_items} entries, got {len(values)}.')
    return [as_vertex_id(value, field) for value in values]


def ok(message, status=200, **extra):
    """A success response with the historical body shape, served as real JSON.

    Every previous response set a header literally named ``ContentType``, which is not a header
    Flask recognises, so JSON was served as ``text/html``.
    """
    payload = {'Message': message}
    payload.update(extra)
    return jsonify(payload), status


def fail(message, status=400, **extra):
    payload = {'Message': message}
    payload.update(extra)
    return jsonify(payload), status
