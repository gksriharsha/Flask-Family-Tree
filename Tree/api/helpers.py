"""Request validation and response serialisation for the API.

Split out of :mod:`Tree.api.routes` so the route module stays under the project's file-length
limit and the pure helpers — no database, no store — can be read and tested on their own. The
route handlers import these; nothing here touches the connection.
"""

from flask import request

from Tree.kinship import explain, render_english, render_telugu
from Tree.kinship.dates import UNKNOWN_DATE, DateValue
from Tree.kinship.model import ADOPTIVE, BIOLOGICAL, FEMALE, INTERSEX, MALE, UNKNOWN
from Tree.kinship.vocabulary import MATERNAL, PATERNAL
from Tree.Utils.http import ApiError, as_vertex_id

SEXES = (MALE, FEMALE, INTERSEX, UNKNOWN)
ROLES = (BIOLOGICAL, ADOPTIVE)


def side_arg() -> str:
    side = (request.args.get('side') or PATERNAL).strip().lower()
    if side not in (PATERNAL, MATERNAL):
        raise ApiError(f"side must be '{PATERNAL}' or '{MATERNAL}'.")
    return side


def person_json(person) -> dict:
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


def sex_field(value, default=UNKNOWN):
    if value is None:
        return default
    text = str(value).strip().lower()
    if text not in SEXES:
        raise ApiError(f'sex must be one of: {", ".join(SEXES)}')
    return text


def date_field(payload, field):
    try:
        return DateValue.from_payload(payload)
    except ValueError as exc:
        raise ApiError(f'{field}: {exc}') from exc


def living_field(value):
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


def link_json(kinship, vocab, person_id, show_via: bool) -> dict:
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


def person_payload(body, creating: bool):
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
        fields['sex'] = sex_field(body.get('sex'))
    if 'birth' in body:
        fields['birth'] = date_field(body.get('birth'), 'birth')
    if 'death' in body:
        fields['death'] = date_field(body.get('death'), 'death')
    if 'living' in body:
        fields['living'] = living_field(body.get('living'))

    birth = fields.get('birth', UNKNOWN_DATE)
    death = fields.get('death', UNKNOWN_DATE)
    if (birth.is_known and death.is_known and birth.earliest and death.latest
            and death.latest < birth.earliest):
        raise ApiError('That death date falls before the birth date.')
    return fields


def link_request(body):
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
