"""The read side of the API: the endpoints that only ever look, never change.

Split out of :mod:`Tree.api.routes` so that module stays under the project's 500-line limit
and the read handlers — which this round makes windowed and paginated — sit together. They are
registered on the SAME ``api`` blueprint the write handlers use (imported from
:mod:`Tree.api.routes`), so the URL map is unchanged; ``routes.py`` imports this module at the
end of its own definition purely so the decorators below run and attach these routes.

What changed this round, and why:

* ``GET /graph`` gained an optional window. ``?around=<id>&generations=<n>`` returns only the
  people within ``n`` parent/child hops of the anchor (plus their spouses and the links among
  the included people), labelled from ``?root=`` (defaulting to the anchor). Without ``around``
  it still returns the whole tree — the client depends on that — but capped at
  ``MAX_GRAPH_PEOPLE`` with ``Counts.truncated`` rather than an unbounded payload.
* ``GET /people`` is new: opaque-cursor keyset pagination over people, for the list surfaces.
* ``GET /search`` and ``GET /people/<a>/relationship-to/<b>`` moved here unchanged in shape.

Every response keeps EXACTLY the keys it had; this round only ADDS keys (``Window``,
``Counts.truncated``, ``Counts.totalPeople``, and the ``/people`` envelope).
"""

from __future__ import annotations

import base64
import binascii
import json

from flask import current_app, request

from Tree.api.helpers import link_json, person_json, side_arg
from Tree.api.routes import api
from Tree.db import get_db
from Tree.kinship import relationships, relationships_from_root, unresolved_seniority
from Tree.kinship.model import FEMALE, MALE
from Tree.storage import (
    count_people,
    load_family_graph,
    load_vocabulary,
    page_people,
    search_people,
)
from Tree.storage.reads import load_windowed_graph
from Tree.Utils.http import ApiError, as_vertex_id, ok


def _generations_arg() -> int:
    """The window depth for /graph?around=, defaulted and clamped.

    Absent → ``GRAPH_DEFAULT_GENERATIONS``; present but not a non-negative integer → 400; above
    ``GRAPH_MAX_GENERATIONS`` → clamped down, because the walk is attacker-controlled and an
    unbounded depth is a request for the whole tree by another name.
    """
    raw = request.args.get('generations')
    if raw is None or raw.strip() == '':
        return current_app.config['GRAPH_DEFAULT_GENERATIONS']
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise ApiError('generations must be a non-negative integer.') from exc
    if value < 0:
        raise ApiError('generations must be a non-negative integer.')
    return min(value, current_app.config['GRAPH_MAX_GENERATIONS'])


def _labelled_people(family, root: int, vocab) -> tuple[list[dict], int]:
    """Every person in ``family`` labelled from ``root``, plus the open-birth-order count.

    The batch labeller (:func:`relationships_from_root`) computes the root's routes once and
    reuses them for every person, which is what keeps this O(N·degree) rather than O(N²). The
    per-person JSON shape — ``relationships`` and ``seniorityQuestion`` — is identical to what
    the whole-tree read produced before, so a windowed and a full read serialise a person the
    same way.
    """
    labels = relationships_from_root(family, root)
    people: list[dict] = []
    open_questions = 0
    for person in sorted(family.people.values(), key=lambda p: p.id):
        links = labels[person.id]
        pair = unresolved_seniority(links)
        if pair:
            open_questions += 1
        people.append({
            **person_json(person),
            'relationships': [
                link_json(k, vocab, person.id, show_via=len(links) > 1) for k in links
            ],
            'seniorityQuestion': (
                {'a': pair[0], 'b': pair[1],
                 'aName': family.people[pair[0]].full_name,
                 'bName': family.people[pair[1]].full_name}
                if pair else None
            ),
        })
    return people, open_questions


def _graph_payload(family, root: int, side: str, *, window: dict | None,
                   truncated: bool, total_people: int) -> tuple:
    """Assemble the /graph response body, shared by the windowed and full paths."""
    vocab = load_vocabulary(get_db(), side=side)
    people, open_questions = _labelled_people(family, root, vocab)
    parent_links = [
        {'child': child_id, 'parent': link.parent_id, 'role': link.role}
        for child_id, links in family.parents.items() for link in links
    ]
    return ok(
        'Tree loaded',
        Root=root, Side=side,
        People=people,
        ParentLinks=parent_links,
        Unions=[{'a': u.a_id, 'b': u.b_id} for u in family.unions],
        Window=window,
        Counts={
            'people': len(family.people),
            'unions': len(family.unions),
            'openBirthOrderQuestions': open_questions,
            'truncated': truncated,
            'totalPeople': total_people,
        },
    )


@api.route('/graph', methods=['GET'])
def graph_view():
    """The tree, labelled from one person's point of view — windowed or whole.

    ``?around=<id>&generations=<n>`` returns only the window around the anchor. Without
    ``around`` the whole tree is returned (capped at ``MAX_GRAPH_PEOPLE``), which is what the
    client loads today. ``?root=`` chooses whose relationships are described (default: the
    anchor, or the lowest id for a full read); ``?side=`` chooses the vocabulary. Neither
    changes any stored data.
    """
    conn = get_db()
    side = side_arg()
    total_people = count_people(conn)
    around_param = request.args.get('around')

    if around_param is not None and around_param.strip() != '':
        around = as_vertex_id(around_param, field='around')
        generations = _generations_arg()
        family, _ = load_windowed_graph(conn, around, generations)
        if around not in family.people:
            raise ApiError('No such person.', status=404)
        root_param = request.args.get('root')
        root = as_vertex_id(root_param, field='root') if root_param else around
        if root not in family.people:
            # The root must be inside the window it is labelled against; a root outside the
            # window has no routes to the included people and would label them all 'none'.
            raise ApiError('root must be inside the window (within generations of around).',
                           status=400)
        return _graph_payload(
            family, root, side,
            window={'around': around, 'generations': generations},
            truncated=False, total_people=total_people)

    # Full read: capped, never 500. If the tree exceeds the cap, the first MAX_GRAPH_PEOPLE by
    # id are returned with truncated=true rather than an unbounded payload.
    cap = current_app.config['MAX_GRAPH_PEOPLE']
    family = load_family_graph(conn, limit=cap)
    if not family.people:
        return ok('Tree is empty', People=[], ParentLinks=[], Unions=[],
                  Root=None, Side=side, Window=None,
                  Counts={'people': 0, 'unions': 0, 'openBirthOrderQuestions': 0,
                          'truncated': False, 'totalPeople': total_people})

    root_param = request.args.get('root')
    root = as_vertex_id(root_param, field='root') if root_param else min(family.people)
    if root not in family.people:
        raise ApiError('No such person.', status=404)
    return _graph_payload(
        family, root, side, window=None,
        truncated=total_people > len(family.people), total_people=total_people)


@api.route('/people/<int:subject>/relationship-to/<int:other>', methods=['GET'])
def relationship(subject: int, other: int):
    """Every genuine relationship between two people, not only the closest.

    Loaded from a window around ``subject`` wide enough to reach ``other`` on a normal family
    tree, so this stays cheap even when the whole tree is huge. If the two are not connected
    within that window the answer is the same 'no relationship' the engine returns for
    genuinely unrelated people.
    """
    conn = get_db()
    generations = current_app.config['GRAPH_MAX_GENERATIONS']
    family, _ = load_windowed_graph(conn, subject, generations)
    if subject not in family.people:
        # Fall back to a whole-tree read so a request for a real person that a window somehow
        # missed still gets a definite answer rather than a spurious 404.
        family = load_family_graph(conn, limit=current_app.config['MAX_GRAPH_PEOPLE'])
    for person_id in (subject, other):
        if person_id not in family.people:
            raise ApiError('No such person.', status=404)

    side = side_arg()
    vocab = load_vocabulary(conn, side=side)
    links = relationships(family, subject, other)
    pair = unresolved_seniority(links)

    return ok(
        'Relationship found',
        Subject=person_json(family.people[subject]),
        Other=person_json(family.people[other]),
        Side=side,
        Relationships=[link_json(k, vocab, other, show_via=len(links) > 1) for k in links],
        SeniorityQuestion=(
            {'a': pair[0], 'b': pair[1],
             'aName': family.people[pair[0]].full_name,
             'bName': family.people[pair[1]].full_name}
            if pair else None
        ),
    )


@api.route('/search', methods=['GET'])
def search():
    """Typeahead across both scripts, served by an index.

    Prefix matching on given/surname (see :func:`Tree.storage.search_people`), so the NOCASE
    name indexes are used instead of a full scan. The response shape is byte-for-byte the
    historical one: an element-map-style dict per person with ``ID``/``Firstname`` and optional
    ``Lastname``/``Gender``.
    """
    query = (request.args.get('q') or '').strip()
    limit = min(int(request.args.get('limit') or 20),
                current_app.config['MAX_SEARCH_RESULTS'])
    if not query:
        return ok('People found', Data=[])

    people = search_people(get_db(), query, limit=limit)
    data = []
    for person in people:
        row = {'ID': person.id, 'Firstname': person.given}
        if person.surname:
            row['Lastname'] = person.surname
        gender = {MALE: 'Male', FEMALE: 'Female'}.get(person.sex)
        if gender:
            row['Gender'] = gender
        data.append(row)
    return ok('People found', Data=data)


def _encode_cursor(person) -> str:
    """Opaque base64 of the keyset tuple a page ended on: (given, surname, id)."""
    raw = json.dumps([person.given, person.surname, person.id], ensure_ascii=False)
    return base64.urlsafe_b64encode(raw.encode('utf-8')).decode('ascii')


def _decode_cursor(cursor: str) -> tuple[str, str, int]:
    """Decode a cursor back to ``(given, surname, id)``; 400 on anything malformed.

    The cursor is opaque to the client, so any tampering — bad base64, bad JSON, the wrong
    shape, a non-integer id — is a client mistake and answered with 400 rather than trusted.
    """
    try:
        raw = base64.urlsafe_b64decode(cursor.encode('ascii'))
        parsed = json.loads(raw.decode('utf-8'))
    except (binascii.Error, ValueError, UnicodeDecodeError) as exc:
        raise ApiError('Malformed cursor.') from exc
    if (not isinstance(parsed, list) or len(parsed) != 3
            or not isinstance(parsed[0], str) or not isinstance(parsed[1], str)
            or not isinstance(parsed[2], int) or isinstance(parsed[2], bool)):
        raise ApiError('Malformed cursor.')
    return parsed[0], parsed[1], parsed[2]


@api.route('/people', methods=['GET'])
def people_page():
    """One keyset page of people for the list surfaces.

    ``?cursor=<opaque>`` continues after a previous page; ``?limit=<n>`` caps the page size at
    ``MAX_PAGE_SIZE``; ``?q=<prefix>`` restricts to a name prefix. The response is
    ``{People: [...person_json], NextCursor: str|null, Total: int}`` — ``NextCursor`` is null on
    the last page. The cursor is an opaque base64 of the keyset; garbage in it is a 400.
    """
    conn = get_db()
    try:
        limit = int(request.args.get('limit') or current_app.config['MAX_PAGE_SIZE'])
    except (TypeError, ValueError) as exc:
        raise ApiError('limit must be an integer.') from exc
    if limit < 1:
        raise ApiError('limit must be a positive integer.')
    limit = min(limit, current_app.config['MAX_PAGE_SIZE'])

    cursor = request.args.get('cursor')
    after = _decode_cursor(cursor) if cursor else None
    q = request.args.get('q')

    people, has_more = page_people(conn, limit, after=after, q=q)
    next_cursor = _encode_cursor(people[-1]) if (has_more and people) else None
    return ok(
        'People found',
        People=[person_json(p) for p in people],
        NextCursor=next_cursor,
        Total=count_people(conn),
    )
