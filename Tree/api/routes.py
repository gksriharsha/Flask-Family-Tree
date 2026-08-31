"""The API the interface is built on.

One call returns the whole tree already labelled. The old shape needed a round trip per
person and returned a flat relations dictionary, which is why a multi-generation chart was
never buildable against it.
"""

import logging
from pathlib import Path

from flask import Blueprint, current_app, request

from Tree import g
from Tree.gedcom.model import VERSION_7, VERSION_551
from Tree.gedcom.store import (
    ARCHIVE_SUFFIXES,
    GEDCOM_SUFFIXES,
    TreeNotCreated,
    create_tree,
    export,
    export_as,
    import_document,
    import_file,
    load_settings,
    read_gedcom_text,
)
from Tree.kinship import (
    explain,
    relationships,
    render_english,
    render_telugu,
    unresolved_seniority,
)
from Tree.kinship.dates import UNKNOWN_DATE, DateValue
from Tree.kinship.model import ADOPTIVE, BIOLOGICAL, FEMALE, INTERSEX, MALE, UNKNOWN
from Tree.kinship.store import (
    add_word,
    create_person,
    delete_person,
    link_parent,
    link_union,
    load_family_graph,
    load_vocabulary,
    pin_term,
    record_birth_order,
    unlink_parent,
    unlink_union,
    unpin_term,
    update_person,
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
        # The full recorded precision, so the interface can show "about 1955" as approximate
        # rather than rendering it identically to a date somebody actually has a document for.
        'birth': person.birth_date.to_payload(),
        'death': person.death_date.to_payload(),
        'living': person.living,
    }


SEXES = (MALE, FEMALE, INTERSEX, UNKNOWN)
ROLES = (BIOLOGICAL, ADOPTIVE)


def _sex_field(value, default=UNKNOWN):
    if value is None:
        return default
    text = str(value).strip().lower()
    if text not in SEXES:
        raise ApiError(f'sex must be one of: {", ".join(SEXES)}')
    return text


def _date_field(payload, field):
    try:
        return DateValue.from_payload(payload)
    except ValueError as exc:
        raise ApiError(f'{field}: {exc}') from exc


def _living_field(value):
    if value is None or value == 'unknown':
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in ('yes', 'true'):
        return True
    if text in ('no', 'false'):
        return False
    raise ApiError("living must be true, false, or 'unknown'.")


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


def _ensure_schema() -> None:
    """Declare the property keys, labels and indexes before writing an imported tree.

    Without a declared schema JanusGraph invents one at write time and guesses cardinality,
    which is what produced SINGLE/SET conflicts on any property legitimately holding several
    values. Applying it here is idempotent -- it creates only what is missing -- so an import
    into an empty database lands in exactly the shape the rest of the app expects rather than
    in whatever the first write happened to imply.
    """
    from Tree import message_serializer
    from Tree.schema import apply_schema
    created, conflicts = apply_schema(
        current_app.config['GREMLIN_DATABASE_URI'],
        current_app.config['GREMLIN_TRAVERSAL_SOURCE'],
        wire=message_serializer(current_app.config['GREMLIN_SERIALIZER']),
    )
    if created:
        log.info('Import declared %d missing schema object(s).', len(created))
    if conflicts:
        # Writing anyway would half-import and fail partway, which is worse than not starting.
        raise ApiError(
            'The database has property keys that conflict with this schema, so an import '
            'would fail partway through: ' + ', '.join(conflicts), status=409)


@api.route('/trees/import', methods=['POST'])
def post_import():
    """Read a GEDCOM or GEDZIP into the tree, as an upload or from a path on the server.

    ``mode=replace`` clears the existing people first. That is the usual intent -- an imported
    file is normally *the* tree rather than an addition to one -- but it is never the default,
    because silently deleting somebody's records because they wanted to look at a file is not
    a recoverable mistake.
    """
    upload = request.files.get('file')
    mode = (request.form.get('mode') if upload else None) or ''
    replace = mode.strip().lower() == 'replace'

    if upload is not None:
        name = upload.filename or ''
        suffix = Path(name).suffix.lower()
        if suffix not in GEDCOM_SUFFIXES + ARCHIVE_SUFFIXES:
            raise ApiError('Expected a .ged, .gedcom or .gdz file, got ' + (name or 'no name'))
        data = upload.read()
        if not data:
            raise ApiError('That file is empty.')
        _ensure_schema()
        try:
            summary = import_document(g, read_gedcom_text(data, name), replace=replace)
        except ValueError as exc:
            raise ApiError(str(exc)) from exc
        summary['source'] = name
    else:
        body = json_body(required=('path',))
        replace = str(body.get('mode') or '').strip().lower() == 'replace'
        _ensure_schema()
        try:
            summary = import_file(g, str(body['path']).strip(), replace=replace)
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


# ── people ──────────────────────────────────────────────────────────────────────
def _person_payload(body, creating: bool):
    """Read the fields a person write accepts, validating each one.

    On create, a given name is required and nothing else is. On update, every field is
    optional and an absent field means "leave this as it was" -- which is why clearing a date
    has to be said explicitly, as ``{"mode": "unknown"}``, rather than by omission.
    """
    fields = {}
    if creating or 'given' in body:
        given = str(body.get('given') or '').strip()
        if creating and not given:
            raise ApiError('A person needs a given name.')
        fields['given'] = given
    if 'surname' in body:
        fields['surname'] = str(body.get('surname') or '').strip()
    if creating or 'sex' in body:
        fields['sex'] = _sex_field(body.get('sex'))
    if 'birth' in body:
        fields['birth'] = _date_field(body.get('birth'), 'birth')
    if 'death' in body:
        fields['death'] = _date_field(body.get('death'), 'death')
    if 'living' in body:
        fields['living'] = _living_field(body.get('living'))

    birth = fields.get('birth', UNKNOWN_DATE)
    death = fields.get('death', UNKNOWN_DATE)
    if (birth.is_known and death.is_known and birth.earliest and death.latest
            and death.latest < birth.earliest):
        raise ApiError('That death date falls before the birth date.')
    return fields


@api.route('/people', methods=['POST'])
def post_person():
    """Add a person, optionally attaching them to somebody already in the tree.

    Only a name is required. Nothing here invents a date, a sex or a link to stand in for a
    fact that is not known -- an unattached person with no dates is a perfectly valid record,
    and is a great deal more useful than one padded out with guesses.
    """
    body = json_body(required=('given',))
    fields = _person_payload(body, creating=True)
    try:
        person_id = create_person(g, **fields)
    except ValueError as exc:
        raise ApiError(str(exc)) from exc

    attached = None
    attach = body.get('attachTo')
    if attach:
        if not isinstance(attach, dict):
            raise ApiError('attachTo must be an object.')
        other_id = as_vertex_id(attach.get('personId'), 'attachTo.personId')
        relation = str(attach.get('relation') or '').strip().lower()
        role = str(attach.get('role') or BIOLOGICAL).strip().lower()
        if role not in ROLES:
            raise ApiError(f'attachTo.role must be one of: {", ".join(ROLES)}')
        try:
            if relation == 'parent':          # the new person is a parent of `personId`
                link_parent(g, child_id=other_id, parent_id=person_id, role=role)
            elif relation == 'child':         # the new person is a child of `personId`
                link_parent(g, child_id=person_id, parent_id=other_id, role=role)
            elif relation == 'spouse':
                link_union(g, person_id, other_id)
            else:
                raise ApiError("attachTo.relation must be 'parent', 'child' or 'spouse'.")
        except ValueError as exc:
            # The person was created; only the link failed. Say so precisely rather than
            # reporting a total failure the caller would retry and duplicate.
            _refresh_files()
            raise ApiError(f'The person was added, but the link failed: {exc}') from exc
        attached = {'personId': other_id, 'relation': relation, 'role': role}

    _refresh_files()
    return ok('Person added', Person={'id': person_id}, Attached=attached, status=201)


@api.route('/people/<int:person_id>', methods=['PATCH'])
def patch_person(person_id: int):
    """Change some of a person's details. Absent fields are left alone."""
    body = json_body()
    fields = _person_payload(body, creating=False)
    if not fields:
        raise ApiError('Nothing to change.')
    try:
        update_person(g, person_id, **fields)
    except ValueError as exc:
        raise ApiError(str(exc), status=404) from exc
    _refresh_files()
    return ok('Person updated', Person={'id': person_id})


@api.route('/people/<int:person_id>', methods=['DELETE'])
def remove_person(person_id: int):
    """Remove a person and every link that referred to them.

    Irreversible in the database, but not in the tree: the folder's ``family.ged`` is
    rewritten from the graph after the change, so the copy from before it is whatever backup
    of that folder exists. That is the honest position -- there is no undo here yet.
    """
    try:
        delete_person(g, person_id)
    except ValueError as exc:
        raise ApiError(str(exc), status=404) from exc
    _refresh_files()
    return ok('Person removed', Person={'id': person_id})


# ── relationships ───────────────────────────────────────────────────────────────
def _link_request(body):
    kind = str(body.get('type') or '').strip().lower()
    if kind == 'parent':
        role = str(body.get('role') or BIOLOGICAL).strip().lower()
        if role not in ROLES:
            raise ApiError(f'role must be one of: {", ".join(ROLES)}')
        return kind, {
            'child_id': as_vertex_id(body.get('childId'), 'childId'),
            'parent_id': as_vertex_id(body.get('parentId'), 'parentId'),
        }, role
    if kind == 'union':
        return kind, {
            'a_id': as_vertex_id(body.get('aId'), 'aId'),
            'b_id': as_vertex_id(body.get('bId'), 'bId'),
        }, None
    raise ApiError("type must be 'parent' or 'union'.")


@api.route('/links', methods=['POST'])
def post_link():
    """Connect two people who are already in the tree.

    A parent link refuses to close an ancestry loop: if the proposed parent is already a
    descendant of the proposed child, the link is rejected rather than making somebody their
    own ancestor and sending every ancestor walk to its depth cap.
    """
    body = json_body(required=('type',))
    kind, args, role = _link_request(body)
    try:
        if kind == 'parent':
            link_parent(g, role=role, **args)
        else:
            link_union(g, **args)
    except ValueError as exc:
        raise ApiError(str(exc)) from exc
    _refresh_files()
    return ok('Link added', Link={'type': kind, **args, 'role': role}, status=201)


@api.route('/links', methods=['DELETE'])
def delete_link():
    """Disconnect two people, leaving both of them in the tree."""
    body = json_body(required=('type',))
    kind, args, _role = _link_request(body)
    try:
        if kind == 'parent':
            unlink_parent(g, **args)
        else:
            unlink_union(g, **args)
    except ValueError as exc:
        raise ApiError(str(exc)) from exc
    _refresh_files()
    return ok('Link removed', Link={'type': kind, **args})
