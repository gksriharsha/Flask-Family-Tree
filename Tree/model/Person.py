from gremlin_python.process.traversal import T

from Tree.model.Event import Event
from Tree.model.Occupation import Occupation

# The graph property names for birth and death facts.
#
# This is the single most consequential fix in this pass. The write path used to emit
# ``Date_of_Birth`` (capital B) while every reader -- functions.groovy's age check, the
# person-retrieval projection, and this class's own read-back -- looked for ``Date_of_birth``.
# With no declared schema, JanusGraph silently created two separate property keys, so the age
# check threw for every person the API created, ``child()`` wrote no edges, the bare ``except``
# swallowed it, and the endpoint still answered HTTP 200.
#
# Lowercase is the spelling chosen because it is what the readers, the Groovy helpers and the
# existing seed data all already use, so no stored data has to be migrated.
BIRTH_KEYS = {'Date': 'Date_of_birth', 'Time': 'Time_of_birth', 'Location': 'Place_of_birth'}
DEATH_KEYS = {'Date': 'Date_of_death', 'Time': 'Time_of_death', 'Location': 'Place_of_death'}


class Person:
    """A person vertex."""

    def __init__(self, Firstname=None, Gender=None, Lastname=None, Alive=None):
        self.ID = None
        self.Firstname = Firstname
        self.Lastname = Lastname
        self.Gender = Gender
        self.Alive = Alive

        self.Birth = None
        self.Death = None
        self.Occupation = None
        self.native_to = None

    @property
    def birth(self):
        return self.Birth

    @birth.setter
    def birth(self, value):
        if isinstance(value, Event):
            self.Birth = value

    @property
    def death(self):
        return self.Death

    @death.setter
    def death(self, value):
        if isinstance(value, Event):
            self.Death = value

    def convert_to_gremlin_node(self):
        """The property map to write to the graph. Only fields that were supplied are included,
        so a partial update does not blank out stored values or write the string ``'None'``."""
        properties = {}
        for name in ('Gender', 'Alive', 'Firstname', 'Lastname'):
            value = getattr(self, name)
            if value is not None and value != '':
                properties[name] = value

        occupation = Occupation.coerce(self.Occupation)
        if occupation is not None:
            properties['Occupation'] = str(occupation)

        for event, keys in ((self.Birth, BIRTH_KEYS), (self.Death, DEATH_KEYS)):
            if event is None:
                continue
            for attribute, property_name in keys.items():
                value = getattr(event, attribute, None)
                if value is not None and value != '':
                    properties[property_name] = value

        return properties

    def to_dict(self):
        """The JSON shape for API responses.

        Explicit rather than ``__dict__``: the original leaned on
        ``json.dumps(..., default=lambda o: o.__dict__)``, which silently produced a *different
        shape per record* because Event's fields were class attributes that never reached the
        instance dict. Every record now carries the same keys, with nulls where a fact is
        unknown, so the client can rely on the shape.
        """
        return {
            'ID': self.ID,
            'Firstname': self.Firstname,
            'Lastname': self.Lastname,
            'Gender': self.Gender,
            'Alive': self.Alive,
            'Occupation': self.Occupation,
            'Birth': self.Birth.to_dict() if self.Birth is not None else None,
            'Death': self.Death.to_dict() if self.Death is not None else None,
            'native_to': self.native_to,
        }

    @staticmethod
    def createPersonObject(attributes):
        """Rebuild a Person from a graph element map.

        The original read-back was dead code in both directions: the birth guard tested for the
        lowercase substring ``'birth'`` inside keys spelled ``Date_of_Birth``, and the death
        guard tested for a key literally named ``death``, which nothing ever wrote. Birth and
        death were therefore ``null`` in every response, for every person, always -- and the
        client dereferenced both without a guard.
        """
        attributes = dict(attributes)
        person = Person()
        person.ID = attributes.pop(T.id, None)

        for name in ('Gender', 'Alive', 'Firstname', 'Lastname', 'Occupation'):
            if name in attributes:
                setattr(person, name, attributes.pop(name))

        for keys, setter in ((BIRTH_KEYS, 'Birth'), (DEATH_KEYS, 'Death')):
            event = Event()
            for attribute, property_name in keys.items():
                if property_name in attributes:
                    setattr(event, attribute, attributes.pop(property_name))
            if not event.is_empty():
                setattr(person, setter, event)

        return person
