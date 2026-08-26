from Tree.model.Event import Event
from Tree.model.Person import Person
from Tree.people.gremlin_Interface import retrieve_person
from Tree.Utils.Dictionary_converter import convert2dictionary


def _event_from(payload):
    """Build an Event from a client payload, tolerating absence and either place key.

    The client sends the birth place as ``Birth.Place`` while the server only ever read
    ``Birth['Location']``, so birth place was silently discarded on every write. Both keys are
    accepted now.
    """
    if not isinstance(payload, dict):
        return None
    event = Event(
        Date=payload.get('Date'),
        Time=payload.get('Time'),
        Location=payload.get('Location', payload.get('Place')),
    )
    return None if event.is_empty() else event


def create_person_object(req_dict):
    """Map a request body onto a Person.

    Previously this indexed ``req_dict['Firstname']`` and called ``.keys()`` on
    ``req_dict.get('Birth')`` unconditionally, so any partial body -- which is exactly what the
    client's ``modifyPartial`` sends -- raised KeyError or AttributeError and returned a 500.
    """
    person = Person(
        Firstname=req_dict.get('Firstname'),
        Lastname=req_dict.get('Lastname'),
        Gender=req_dict.get('Gender'),
        Alive=req_dict.get('Alive'),
    )
    person.Occupation = req_dict.get('Occupation')
    person.Birth = _event_from(req_dict.get('Birth'))
    # A death write path now exists. There was none at all before: this mapper was the single
    # request-to-model function and it never read a Death key, so date, place and time of death
    # were unrecordable through every endpoint.
    person.Death = _event_from(req_dict.get('Death'))
    return person


def retrieve_person_service(person_id):
    ret_value, father, mother, brother, sister, child, spouse = retrieve_person(id=person_id)
    relations = {}
    for label, value in (
        ('Father', father), ('Mother', mother), ('Brother', brother),
        ('Sister', sister), ('Children', child), ('Spouse', spouse),
    ):
        if value is not None:
            relations[label] = convert2dictionary(value)
    return relations, ret_value
