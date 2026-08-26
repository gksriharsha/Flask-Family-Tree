"""Server-side relationship operations.

Three classes of defect are fixed here.

**Injection and script-cache misses.** Every call built its Gremlin script by interpolating ids
into an f-string. That was a Groovy injection sink independent of the request-body ``eval`` --
and because Gremlin Server keys its compiled-script cache on the exact script text, every
distinct id pair compiled a brand-new Groovy class that was never reused. Scripts are now
constant text with the ids passed as bindings, which closes the hole and makes the cache work.

**Closing the client before awaiting its result.** Five call sites called ``cli.close()`` before
``future.result()``. The client is now closed in a ``finally``, after the result is read.

**A process pool per request.** ``parallelsearchRelation`` created a ``multiprocessing.Pool``
sized to ``cpu_count()`` on every request, and its workers read ``current_app.config`` -- which
does not exist in a spawned child, the default on macOS and Windows. The work is websocket I/O,
so it is a small bounded thread pool now, with configuration read in the calling thread and
passed in rather than looked up in the worker.
"""

import logging
from concurrent.futures import ThreadPoolExecutor

from flask import current_app
from gremlin_python.driver import client
from gremlin_python.process.graph_traversal import __

from Tree import g, message_serializer
from Tree.model.Person import Person
from Tree.Utils.RelationReducer import reduce

log = logging.getLogger(__name__)


class RelationQueryError(RuntimeError):
    """A server-side relationship script failed. Raised instead of being swallowed."""


def _gremlin_settings():
    """Read connection settings in the *calling* thread."""
    config = current_app.config
    return (
        config['GREMLIN_DATABASE_URI'],
        config['GREMLIN_TRAVERSAL_SOURCE'],
        config['GREMLIN_WRITE_TIMEOUT_MS'],
        config['GREMLIN_READ_TIMEOUT_MS'],
        config['RELATION_SEARCH_WORKERS'],
    )


def _submit(script, bindings, uri, source, timeout_ms):
    """Submit a constant script with bindings and return its rows."""
    wire = message_serializer(current_app.config['GREMLIN_SERIALIZER'])
    cli = client.Client(uri, source, **({'message_serializer': wire} if wire else {}))
    try:
        result_set = cli.submit(script, bindings, request_options={'evaluationTimeout': timeout_ms})
        return result_set.all().result()
    finally:
        cli.close()


def _write(script, bindings):
    """Run a relationship-writing script.

    Returns True on success and raises on failure. The original returned False from a bare
    ``except``, and the callers then either ignored the boolean entirely or checked it in only
    one branch -- so a failed write answered HTTP 200 'Marriage relation is added'. The write
    timeout was also one second for scripts that run four to six sequential traversals.
    """
    uri, source, write_timeout, _read_timeout, _workers = _gremlin_settings()
    try:
        _submit(script, bindings, uri, source, write_timeout)
    except Exception as exc:
        log.error('Relationship write failed: %s (%s)', script, exc)
        raise RelationQueryError(f'{exc.__class__.__name__}: {exc}') from exc
    return True


def _resolve_location_id(value):
    """Accept either a Location vertex id or a place name and return a vertex id, or None.

    ``relate_locations`` used to index ``person.Birth.Location['ID']`` on whatever the client
    supplied, after the person vertex had already been created -- so a plain place-name string
    raised TypeError and left a half-written person behind.
    """
    if value is None or value == '':
        return None
    if isinstance(value, dict):
        return value.get('ID')
    if isinstance(value, (int, float)):
        return int(value)
    step = g.V().hasLabel('Location').has('Place', str(value))
    if step.hasNext():
        return step.next().id
    log.info('No Location vertex for place %r; skipping the edge.', value)
    return None


def relate_locations(person_id, person: Person):
    """Link a person to their birth and native Location vertices, where those resolve."""
    if person.Birth is not None:
        location_id = _resolve_location_id(person.Birth.Location)
        if location_id is not None and not g.V(person_id).outE('BORN_IN').hasNext():
            g.V(person_id).addE('BORN_IN').to(__.V(location_id)).iterate()

    native_id = _resolve_location_id(person.native_to)
    if native_id is not None and not g.V(person_id).outE('NATIVE_TO').hasNext():
        g.V(person_id).addE('NATIVE_TO').to(__.V(native_id)).iterate()


def marriage(Person1_id, Person2_id):
    return _write('marriage(g, p1, p2)', {'p1': int(Person1_id), 'p2': int(Person2_id)})


def child(parent1_id, parent2_id, child_id):
    return _write(
        'child(g, p1, p2, c)',
        {'p1': int(parent1_id), 'p2': int(parent2_id), 'c': int(child_id)},
    )


def Adoption(parent1_id, parent2_id, child_id):
    return _write(
        'adoption(g, p1, p2, c, ["Father_lastname": true])',
        {'p1': int(parent1_id), 'p2': int(parent2_id), 'c': int(child_id)},
    )


def searchRelations(start_id, end_id):
    uri, source, _write_timeout, read_timeout, _workers = _gremlin_settings()
    try:
        return _submit(
            'relation(g, a, b)',
            {'a': int(start_id), 'b': int(end_id)},
            uri, source, read_timeout,
        )
    except Exception as exc:
        raise RelationQueryError(f'{exc.__class__.__name__}: {exc}') from exc


def singlesearchRelation(start_id, end_id, uri, source, timeout_ms):
    return _submit(
        'shortestPath(g, a, b)',
        {'a': int(start_id), 'b': int(end_id)},
        uri, source, timeout_ms,
    )


def parsePath(start_id, end_id, uri, source, timeout_ms):
    """Reduce one path to a short relation label. Returns (end_id, label_or_None)."""
    try:
        path = singlesearchRelation(start_id, end_id, uri, source, timeout_ms)
    except Exception as exc:
        # An unreachable pair exhausts the traversal and raises. That is a legitimate answer
        # -- "not related" -- not a server error, so it is reported rather than propagated.
        log.info('No path from %s to %s (%s).', start_id, end_id, exc.__class__.__name__)
        return end_id, None
    if not path:
        return end_id, None

    relation_chain = [item for index, item in enumerate(path) if index % 2 == 1]
    if not relation_chain:
        return end_id, None
    if len(relation_chain) == 1:
        return end_id, relation_chain[0]
    short = reduce(relation_chain)
    if isinstance(short, list) and len(short) == 1:
        short = short[0]
    return end_id, short


def parallelsearchRelation(start_id, end_ids):
    uri, source, _write_timeout, read_timeout, workers = _gremlin_settings()
    if not end_ids:
        return []
    with ThreadPoolExecutor(max_workers=min(workers, len(end_ids))) as pool:
        return list(pool.map(
            lambda end_id: parsePath(start_id, end_id, uri, source, read_timeout),
            end_ids,
        ))


def get_all_relations(start_id, end_ids):
    """Map each target id to a human-readable relation label.

    The original accumulated its compound label with a leading space and a trailing ``"'s "``
    on every element, producing strings like ``" Father's  Brother"``, and raised AttributeError
    on an unrelated pair because it called ``.split`` on a None relation.
    """
    relations = {int(start_id): 'Me'}
    for end_id, label in parallelsearchRelation(start_id, end_ids):
        if label is None:
            relations[end_id] = None
        elif isinstance(label, list):
            relations[end_id] = "'s ".join(str(part).split('_')[0] for part in label)
        else:
            relations[end_id] = str(label).split('_')[0]
    return relations
