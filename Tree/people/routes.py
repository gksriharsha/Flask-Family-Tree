"""Person and relationship endpoints.

Every body is parsed as JSON rather than ``eval``-ed, every identifier is coerced with
``int()``, and every branch returns a response -- the original had five reachable paths that
fell off the end of a view function and became HTTP 500s. The three divergent inline copies of
the request-to-Person mapper are replaced by the single one in ``people_Service``.
"""

import logging

from flask import Blueprint, current_app

from Tree.model.Person import Person
from Tree.people.gremlin_Interface import add_person, modify_person, retrieve_person
from Tree.people.people_Service import create_person_object, retrieve_person_service
from Tree.relations.gremlin_Interface import Adoption, child, marriage
from Tree.Utils.Dictionary_converter import convert2dictionary
from Tree.Utils.http import ApiError, as_vertex_id, fail, json_body, ok

log = logging.getLogger(__name__)

people = Blueprint('people', __name__)

# 'Alive' is deliberately not required. It used to be, which made the client's only "add a
# person" form permanently unusable: the form never assigns Alive, so JSON.stringify omits it
# and the endpoint answered 400 every time. No query in the application reads the field.
REQUIRED_ON_CREATE = ('Firstname', 'Lastname', 'Gender', 'Birth')


def _person_payload(person_dictionary, relations):
    return {
        'Data': Person.createPersonObject(person_dictionary).to_dict(),
        'Relations': relations,
    }


@people.route('/add/person', methods=['POST'])
def add_person_endpoint():
    req_dict = json_body(required=REQUIRED_ON_CREATE)
    person = create_person_object(req_dict)
    if person.Birth is None:
        raise ApiError('Birth must contain at least a Date.')

    vertex_id = add_person(person=person, return_id=True)
    log.info('Created person %s', vertex_id)
    return ok('Successfully added a person.', Result=vertex_id)


@people.route('/modify/person', methods=['POST'])
def modify():
    req_dict = json_body(required=('ID',))
    vertex_id = as_vertex_id(req_dict['ID'])
    person = create_person_object(req_dict)
    modify_person(person, vertex_id)
    # The client waits for the word 'Modified'; the original replied 'Successfully added a
    # person.', so the view never refreshed after an edit.
    return ok('Modified the person.', Result=vertex_id)


@people.route('/get/person', methods=['POST'])
def get_person():
    req_dict = json_body()

    if 'ID' in req_dict:
        vertex_id = as_vertex_id(req_dict['ID'])
        relations, person_dictionary = retrieve_person_service(vertex_id)
        return ok('Person found', **_person_payload(person_dictionary, relations))

    limit = current_app.config['MAX_SEARCH_RESULTS']
    if req_dict.get('Firstname') == 'all':
        rows = retrieve_person(all=True, limit=limit)
        return ok('People found', Data=convert2dictionary(rows) or [])

    if 'Search Text' in req_dict or 'Firstname' in req_dict:
        rows = retrieve_person(search_text=req_dict, limit=limit)
        # An empty result is an empty list, not null. The converter returned None for no
        # matches, and the client treats null as "not searching" and shows the whole directory.
        return ok('People found', Data=convert2dictionary(rows) or [])

    # Previously this fell off the end and returned None -> HTTP 500.
    raise ApiError("Provide 'ID', 'Firstname', or 'Search Text'.")


def _create_from(req_dict, key):
    body = req_dict.get(key)
    if not isinstance(body, dict):
        raise ApiError(f"'{key}' must be an object describing a person.")
    person = create_person_object(body)
    if not person.Firstname:
        raise ApiError(f"'{key}' requires a Firstname.")
    return add_person(person=person, return_id=True)


def _existing_id(req_dict, key):
    body = req_dict.get(key)
    if not isinstance(body, dict) or 'ID' not in body:
        raise ApiError(f"'{key}' must be an object containing an ID.")
    return as_vertex_id(body['ID'], field=f'{key}.ID')


@people.route('/relate/people', methods=['POST'])
def relate():
    req_dict = json_body(required=('Relation',))
    relation = req_dict.get('Relation')
    method = req_dict.get('Method')
    # The original had an unreachable adoption branch: it was guarded by Relation != 'Adoption'
    # inside a block only entered when Relation == 'Parents'. Adoption is now an explicit flag,
    # so the client's existing (unwired) "Adopted" toggle has something to bind to.
    adopted = bool(req_dict.get('Adopted')) or relation == 'Adoption'

    if relation == 'Marriage':
        if method == 'Add-Relate':
            req_dict.setdefault('B', {})['ID'] = _create_from(req_dict, 'B')
        a_id = _existing_id(req_dict, 'A')
        b_id = _existing_id(req_dict, 'B')
        # Husband first, as the Groovy helper expects.
        if req_dict['A'].get('Gender') == 'Female' and req_dict['B'].get('Gender') == 'Male':
            a_id, b_id = b_id, a_id
        marriage(a_id, b_id)
        return ok('Marriage relation is added')

    if relation == 'Parents':
        if method != 'Add-Relate':
            raise ApiError("Relation 'Parents' currently requires Method 'Add-Relate'.")
        child_id = _existing_id(req_dict, 'A')
        parent1_id = _create_from(req_dict, 'B')
        parent2_id = _create_from(req_dict, 'C')
        marriage(parent1_id, parent2_id)
        linker = Adoption if adopted else child
        linker(parent1_id=parent1_id, parent2_id=parent2_id, child_id=child_id)
        return ok('Successfully added parents to the family tree',
                  Result={'B': parent1_id, 'C': parent2_id})

    if relation in ('Child', 'Adoption'):
        parent1_id = _existing_id(req_dict, 'B')
        parent2_id = _existing_id(req_dict, 'C')
        child_id = _create_from(req_dict, 'A') if method == 'Add-Relate' \
            else _existing_id(req_dict, 'A')
        linker = Adoption if adopted else child
        # The return value is checked on every path now. The original ignored it in this
        # branch and replied 200 'Successfully added child' regardless.
        linker(parent1_id=parent1_id, parent2_id=parent2_id, child_id=child_id)
        return ok('Successfully added child to the family tree', Result=child_id)

    return fail(f"Unsupported Relation {relation!r}. "
                "Expected 'Marriage', 'Parents', 'Child' or 'Adoption'.")
