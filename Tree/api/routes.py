"""The API the interface is built on.

One call returns the whole tree already labelled. The old shape needed a round trip per
person and returned a flat relations dictionary, which is why a multi-generation chart was
never buildable against it.
"""

import logging

from flask import Blueprint, current_app, request

from Tree import g
from Tree.gedcom.model import VERSION_7, VERSION_551
from Tree.gedcom.store import (
    TreeNotCreated,
    create_tree,
    export,
    export_as,
    import_file,
    load_settings,
)
from Tree.kinship import (
    explain,
    relationships,
    render_english,
    render_telugu,
    unresolved_seniority,
)
from Tree.kinship.store import (
    add_word,
    load_family_graph,
    load_vocabulary,
    pin_term,
    record_birth_order,
    unpin_term,
)
from Tree.kinship.vocabulary import MATERNAL, PATERNAL
from Tree.Utils.http import ApiError, as_vertex_id, json_body, ok

log = logging.getLogger(__name__)

api = Blueprint('api', __name__, url_prefix='/api/v1')


def _refresh_files() -> None:
    """Keep the tree's folder current after a change.

    Never allowed to fail the request that caused it: a write that succeeded should not be
    reported as an error because a disk was full or a path went away.
    """
    try:
        export(g)
    except TreeNotCreated:
        pass
    except Exception:
        log.exception('Could not refresh the tree files.')


def _side() -> str:
    side = (request.args.get('side') or PATERNAL).strip().lower()
    if side not in (PATERNAL, MATERNAL):
        raise ApiError(f"side must be '{PATERNAL}' or '{MATERNAL}'.")
    return side


def _person_json(person) -> dict:
    return {
        'id': person.id,
        'given': person.given,
        'surname': person.surname,
        'name': person.full_name,
        'sex': person.sex,
        'birthYear': person.birth_year,
        'deathYear': person.death_year,
    }


def _link_json(kinship, vocab, person_id, show_via: bool) -> dict:
    term = vocab.apply(render_telugu(kinship), person_id=person_id)
    return {
        'en': render_english(kinship),
        'te': term.text,
        'roman': term.roman,
        'gloss': term.gloss,
        'unresolved': term.unresolved,
        'pinned': term.pinned,
        'bases': list(term.bases),
        'alternatives': list(term.alternatives),
        'adoptive': kinship.adoptive,
        'via': ('Through the adoption' if kinship.adoptive else 'By birth') if show_via else None,
        'why': explain(kinship),
        'kind': kinship.kind,
    }


@api.route('/trees', methods=['GET'])
def get_tree():
    """Where this tree keeps its files, and whether it has been created yet."""
    settings = load_settings(g)
    if settings is None:
        return ok('No tree yet', Tree=None)
    return ok('Tree found', Tree={
        'name': settings.name,
        'location': str(settings.location),
        'gedcom': str(settings.gedcom),
        'exists': settings.gedcom.is_file(),
    })


@api.route('/trees', methods=['POST'])
def post_tree():
    """Create a tree and choose where its files should live.

    Everything the tree holds is written there, so the folder can be backed up by copying it,
    opened in other genealogy software, and used to rebuild the database.
    """
    body = json_body(required=('name', 'location'))
    name = str(body['name']).strip()
    location = str(body['location']).strip()
    if not name or not location:
        raise ApiError('A tree needs a name and a location.')
    try:
        settings = create_tree(g, name, location)
    except (ValueError, OSError) as exc:
        raise ApiError(str(exc)) from exc
    return ok('Tree created', Tree={'name': settings.name,
                                    'location': str(settings.location),
                                    'gedcom': str(settings.gedcom)})


@api.route('/trees/export', methods=['POST'])
def post_export():
    """Write a copy in another format, for handing to another program.

    ``gedcom7`` is the durable one, ``gedzip`` bundles the media with it, and ``gedcom551``
    is for older desktop software that has never been taught to read 7.0.
    """
    body = json_body()
    fmt = str(body.get('format') or 'gedcom7').strip().lower()
    version = {'gedcom7': VERSION_7, 'gedcom551': VERSION_551, 'gedzip': 'gedzip'}.get(fmt)
    if version is None:
        raise ApiError("format must be 'gedcom7', 'gedcom551' or 'gedzip'.")
    try:
        written = export_as(g, version)
    except TreeNotCreated as exc:
        raise ApiError(str(exc), status=409) from exc
    return ok('Export written', Path=str(written), Format=fmt,
              Bytes=written.stat().st_size)


@api.route('/trees/import', methods=['POST'])
def post_import():
    """Read a GEDCOM or GEDZIP file into the tree."""
    body = json_body(required=('path',))
    try:
        summary = import_file(g, str(body['path']).strip())
    except (ValueError, OSError) as exc:
        raise ApiError(str(exc)) from exc
    _refresh_files()
    return ok('Imported', Result=summary)


@api.route('/session', methods=['GET'])
def session():
    """Confirm the token works, without loading anything.

    The interface calls this before asking for the tree, so a bad token gives an immediate,
    clear answer instead of a failed graph load.
    """
    return ok('Signed in')


@api.route('/graph', methods=['GET'])
def graph_view():
    """Everything the tree needs, labelled from one person's point of view.

    ``?root=`` chooses whose relationships are described; ``?side=`` chooses which branch of
    the family's vocabulary to speak in. Neither changes any stored data.
    """
    family = load_family_graph(g)
    if not family.people:
        return ok('Tree is empty', People=[], ParentLinks=[], Unions=[],
                  Root=None, Side=_side())

    side = _side()
    root_param = request.args.get('root')
    root = as_vertex_id(root_param, field='root') if root_param else min(family.people)
    if root not in family.people:
        raise ApiError('No such person.', status=404)

    vocab = load_vocabulary(g, side=side)

    people = []
    open_questions = 0
    for person in sorted(family.people.values(), key=lambda p: p.id):
        links = relationships(family, root, person.id)
        pair = unresolved_seniority(links)
        if pair:
            open_questions += 1
        people.append({
            **_person_json(person),
            'relationships': [
                _link_json(k, vocab, person.id, show_via=len(links) > 1) for k in links
            ],
            'seniorityQuestion': (
                {'a': pair[0], 'b': pair[1],
                 'aName': family.people[pair[0]].full_name,
                 'bName': family.people[pair[1]].full_name}
                if pair else None
            ),
        })

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
        Counts={
            'people': len(family.people),
            'unions': len(family.unions),
            'openBirthOrderQuestions': open_questions,
        },
    )


@api.route('/people/<int:subject>/relationship-to/<int:other>', methods=['GET'])
def relationship(subject: int, other: int):
    """Every genuine relationship between two people, not only the closest."""
    family = load_family_graph(g)
    for person_id in (subject, other):
        if person_id not in family.people:
            raise ApiError('No such person.', status=404)

    side = _side()
    vocab = load_vocabulary(g, side=side)
    links = relationships(family, subject, other)
    pair = unresolved_seniority(links)

    return ok(
        'Relationship found',
        Subject=_person_json(family.people[subject]),
        Other=_person_json(family.people[other]),
        Side=side,
        Relationships=[_link_json(k, vocab, other, show_via=len(links) > 1) for k in links],
        SeniorityQuestion=(
            {'a': pair[0], 'b': pair[1],
             'aName': family.people[pair[0]].full_name,
             'bName': family.people[pair[1]].full_name}
            if pair else None
        ),
    )


@api.route('/birth-order', methods=['POST'])
def set_birth_order():
    """Record which of two people was born first.

    The one fact Telugu needs and most records do not hold. Stored as its own fact rather
    than as an invented date.
    """
    body = json_body(required=('elder_id', 'younger_id'))
    elder = as_vertex_id(body['elder_id'], field='elder_id')
    younger = as_vertex_id(body['younger_id'], field='younger_id')
    if elder == younger:
        raise ApiError('A person cannot be elder than themselves.')
    for person_id in (elder, younger):
        if not g.V(person_id).hasNext():
            raise ApiError('No such person.', status=404)

    record_birth_order(g, elder, younger)
    log.info('Recorded birth order: %s is elder than %s', elder, younger)
    _refresh_files()
    return ok('Birth order recorded', Elder=elder, Younger=younger)


@api.route('/vocabulary', methods=['GET'])
def get_vocabulary():
    side = _side()
    vocab = load_vocabulary(g, side=side)
    return ok(
        'Vocabulary loaded', Side=side,
        Added={base: [
            {'term': v.term, 'roman': v.roman, 'usage': v.usage} for v in variants
        ] for base, variants in vocab.added.items()},
        Pins=[{'person': pid, 'baseTerm': base, 'term': v.term, 'roman': v.roman}
              for (pid, base), v in vocab.pins.items()],
    )


@api.route('/vocabulary', methods=['POST'])
def post_vocabulary():
    """Record a word the family uses. The built-in list is a starting point, not authority."""
    body = json_body(required=('base_term', 'term'))
    base_term = str(body['base_term']).strip()
    term = str(body['term']).strip()
    if not base_term or not term:
        raise ApiError('base_term and term must not be empty.')
    side = str(body.get('side') or PATERNAL).strip().lower()
    if side not in (PATERNAL, MATERNAL):
        raise ApiError(f"side must be '{PATERNAL}' or '{MATERNAL}'.")

    term_id = add_word(g, base_term, term,
                       roman=str(body.get('roman') or ''),
                       usage=str(body.get('usage') or ''), side=side)
    _refresh_files()
    return ok('Word added', Result=term_id, BaseTerm=base_term, Term=term, Side=side)


@api.route('/people/<int:person_id>/pinned-term', methods=['POST'])
def post_pin(person_id: int):
    """Always use one particular word for one particular person.

    Optional: the vocabulary already gives everyone else a sensible default. This is for the
    exceptions — the uncle everybody happens to call something else.
    """
    if not g.V(person_id).hasNext():
        raise ApiError('No such person.', status=404)
    body = json_body(required=('base_term', 'term'))
    base_term = str(body['base_term']).strip()
    term = str(body['term']).strip()
    if not base_term or not term:
        raise ApiError('base_term and term must not be empty.')
    side = str(body.get('side') or PATERNAL).strip().lower()

    term_id = add_word(g, base_term, term, roman=str(body.get('roman') or ''),
                       usage=str(body.get('usage') or ''), side=side)
    pin_term(g, person_id, base_term, term_id)
    _refresh_files()
    return ok('Term pinned', Person=person_id, BaseTerm=base_term, Term=term)


@api.route('/people/<int:person_id>/pinned-term', methods=['DELETE'])
def delete_pin(person_id: int):
    body = json_body(required=('base_term',))
    unpin_term(g, person_id, str(body['base_term']).strip())
    _refresh_files()
    return ok('Pin removed', Person=person_id)


@api.route('/search', methods=['GET'])
def search():
    """Typeahead across both scripts."""
    query = (request.args.get('q') or '').strip()
    limit = min(int(request.args.get('limit') or 20),
                current_app.config['MAX_SEARCH_RESULTS'])
    if not query:
        return ok('People found', Data=[])

    from gremlin_python.process.graph_traversal import __ as anon
    from gremlin_python.process.traversal import TextP
    rows = (g.V().hasLabel('Person')
            .where(anon.has('Firstname', TextP.containing(query)).or_()
                   .has('Lastname', TextP.containing(query)))
            .limit(limit)
            .elementMap('Firstname', 'Lastname', 'Gender').toList())
    from Tree.Utils.Dictionary_converter import convert2dictionary
    return ok('People found', Data=convert2dictionary(rows) or [])
