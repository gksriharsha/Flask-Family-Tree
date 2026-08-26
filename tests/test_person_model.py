from gremlin_python.process.traversal import T

from Tree.model.Event import Event
from Tree.model.Person import Person


def _round_trip(person):
    written = person.convert_to_gremlin_node()
    return written, Person.createPersonObject({T.id: 1, T.label: 'Person', **written})


def test_birth_and_death_survive_the_round_trip():
    """Previously impossible: the write path emitted Date_of_Birth while the read guard tested
    for the lowercase substring 'birth', and the death guard tested for a key named 'death'."""
    person = Person(Firstname='A', Lastname='B', Gender='Male', Alive='No')
    person.Birth = Event(Date='1901-02-03', Location='Vijayawada')
    person.Death = Event(Date='1975-06-07')

    written, back = _round_trip(person)
    assert written['Date_of_birth'] == '1901-02-03'
    assert written['Place_of_birth'] == 'Vijayawada'
    assert written['Date_of_death'] == '1975-06-07'
    assert back.Birth is not None and back.Birth.Date == '1901-02-03'
    assert back.Death is not None and back.Death.Date == '1975-06-07'


def test_non_ascii_names_survive():
    person = Person(Firstname='కృష్ణ', Lastname='José')
    _written, back = _round_trip(person)
    assert back.Firstname == 'కృష్ణ'
    assert back.Lastname == 'José'


def test_partial_update_does_not_blank_unsupplied_fields():
    written = Person(Firstname='OnlyThis').convert_to_gremlin_node()
    assert written == {'Firstname': 'OnlyThis'}
    assert 'None' not in written.values()


def test_occupation_accepts_a_dict_without_raising():
    """A dict used to reach `.Organization` on a raw JSON value and return HTTP 500."""
    person = Person(Firstname='A')
    person.Occupation = {'Organization': 'ASU', 'Job': 'Engineer',
                         'Start_year': 2015, 'End_year': 2020}
    assert person.convert_to_gremlin_node()['Occupation'] == '(ASU,Engineer,2015,2020)'


def test_event_fields_are_instance_attributes():
    """Both serialisation sites use o.__dict__, which reads only the instance dict."""
    assert set(Event().__dict__) == {'Date', 'Time', 'Location'}
