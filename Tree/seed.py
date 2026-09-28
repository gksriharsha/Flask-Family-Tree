"""The 29-person demo family used as the project's regression corpus.

This graph was previously built by ``GET /spoc``, a route whose first statement was
``g.V().drop().iterate()``. It is kept because it is the only known-good structure the
project has -- 29 people and 95 distinct edges, including adoptive links (the ``*``
suffixed labels) and a sibling set -- but it is reachable only through the CLI.

Two notes carried over from the original data, deliberately preserved so the fixture
stays faithful:

* One ``Son_Of`` edge was written twice in the original route; the duplicate is dropped.
* ``Hema Chowdary`` is recorded as Female while also carrying ``Son_Of`` and
  ``Husband_Of`` edges. That inconsistency is real test data -- it is exactly the kind of
  contradiction the planned data-quality checks should surface.

Every name here is invented. The graph *shape* is the real asset -- the adoption, the
sibling set, the cousin branches -- and that is what the kinship tests exercise; the
people are placeholders and refer to nobody. The birth dates are placeholders too: all
29 records carry ``1990-01-01``, which is why seniority is reported as unknown rather
than derived from them. Keep it that way. Real family data belongs in your own GEDCOM
directory, not in this repository.
"""

from Tree.kinship.dates import DateValue
from Tree.kinship.model import (
    ADOPTIVE,
    BIOLOGICAL,
    FEMALE,
    MALE,
    UNKNOWN,
    FamilyGraph,
    ParentLink,
    Person,
    Union,
)

# Every date uses the ``Date_of_birth`` spelling, which is the casing the readers and
# functions.groovy expect and which the write path now also uses.
PEOPLE = {
    'addV1': {'Date_of_birth': '1990-01-01', 'Firstname': 'Aditya Varun', 'Gender': 'Male', 'Lastname': 'Varma'},
    'addV2': {'Date_of_birth': '1990-01-01', 'Firstname': 'Bharath Kiran', 'Gender': 'Male', 'Lastname': 'Varma'},
    'addV3': {'Date_of_birth': '1990-01-01', 'Firstname': 'Chandra Mohan Babu', 'Gender': 'Male', 'Lastname': 'Varma'},
    'addV4': {'Date_of_birth': '1990-01-01', 'Firstname': 'Deepa Latha', 'Gender': 'Female', 'Lastname': 'Reddy'},
    'addV5': {'Date_of_birth': '1990-01-01', 'Firstname': 'Eshwar Datta', 'Gender': 'Male', 'Lastname': 'Varma'},
    'addV6': {'Date_of_birth': '1990-01-01', 'Firstname': 'Girija', 'Gender': 'Female', 'Lastname': 'Sharma'},
    'addV7': {'Adopted': 'Yes', 'Date_of_birth': '1990-01-01', 'Firstname': 'Harinath', 'Gender': 'Male', 'Lastname': 'Sharma'},
    'addV8': {'Date_of_birth': '1990-01-01', 'Firstname': 'Parent1', 'Gender': 'Male', 'Lastname': 'Varma'},
    'addV9': {'Date_of_birth': '1990-01-01', 'Firstname': 'Parent2', 'Gender': 'Female', 'Lastname': 'Varma'},
    'addV10': {'Date_of_birth': '1990-01-01', 'Firstname': 'Kalyani', 'Gender': 'Female', 'Lastname': 'Naidu'},
    'addV11': {'Date_of_birth': '1990-01-01', 'Firstname': 'Lokesh', 'Gender': 'Male', 'Lastname': 'Sharma'},
    'addV12': {'Date_of_birth': '1990-01-01', 'Firstname': 'Madhava', 'Gender': 'Male', 'Lastname': 'Varma'},
    'addV13': {'Date_of_birth': '1990-01-01', 'Firstname': 'Nirmala', 'Gender': 'Female', 'Lastname': 'Varma'},
    'addV14': {'Date_of_birth': '1990-01-01', 'Firstname': 'Padmini', 'Gender': 'Female', 'Lastname': 'Varma'},
    'addV15': {'Date_of_birth': '1990-01-01', 'Firstname': 'Raghava', 'Gender': 'Male', 'Lastname': 'Varma'},
    'addV16': {'Date_of_birth': '1990-01-01', 'Firstname': 'Sanjay', 'Gender': 'Male', 'Lastname': 'Varma'},
    'addV17': {'Date_of_birth': '1990-01-01', 'Firstname': 'Tarani', 'Gender': 'Female', 'Lastname': 'Varma'},
    'addV18': {'Date_of_birth': '1990-01-01', 'Firstname': 'Usha', 'Gender': 'Female', 'Lastname': 'Varma'},
    'addV19': {'Date_of_birth': '1990-01-01', 'Firstname': 'Vanaja', 'Gender': 'Female', 'Lastname': 'Varma'},
    'addV20': {'Date_of_birth': '1990-01-01', 'Firstname': 'Yeshwanth', 'Gender': 'Male', 'Lastname': 'Varma'},
    'addV21': {'Date_of_birth': '1990-01-01', 'Firstname': 'Bhavani', 'Gender': 'Female', 'Lastname': 'Varma'},
    'addV22': {'Date_of_birth': '1990-01-01', 'Firstname': 'Chandana Sri', 'Gender': 'Female', 'Lastname': 'Varma'},
    'addV23': {'Date_of_birth': '1990-01-01', 'Firstname': 'Dinesh', 'Gender': 'Male', 'Lastname': 'Chowdary'},
    'addV24': {'Date_of_birth': '1990-01-01', 'Firstname': 'Gowri', 'Gender': 'Female', 'Lastname': 'Varma'},
    'addV25': {'Date_of_birth': '1990-01-01', 'Firstname': 'Hema', 'Gender': 'Female', 'Lastname': 'Chowdary'},
    'addV26': {'Date_of_birth': '1990-01-01', 'Firstname': 'Indira', 'Gender': 'Female', 'Lastname': 'Chowdary'},
    'addV27': {'Date_of_birth': '1990-01-01', 'Firstname': 'Jagan', 'Gender': 'Male', 'Lastname': 'Prasad'},
    'addV28': {'Date_of_birth': '1990-01-01', 'Firstname': 'Keerthi', 'Gender': 'Female', 'Lastname': 'Chowdary'},
    'addV29': {'Date_of_birth': '1990-01-01', 'Firstname': 'Manoj', 'Gender': 'Male', 'Lastname': 'Sharma'},
}

# (source, edge label, target)
EDGES = [
    ('addV4', 'Mother_Of', 'addV1'),
    ('addV1', 'Son_Of', 'addV4'),
    ('addV4', 'Mother_Of', 'addV2'),
    ('addV2', 'Son_Of', 'addV4'),
    ('addV3', 'Father_Of', 'addV1'),
    ('addV1', 'Son_Of', 'addV3'),
    ('addV3', 'Father_Of', 'addV2'),
    ('addV2', 'Son_Of', 'addV3'),
    ('addV1', 'Brother_Of', 'addV2'),
    ('addV2', 'Brother_Of', 'addV1'),
    ('addV3', 'Husband_Of', 'addV4'),
    ('addV4', 'Wife_Of', 'addV3'),
    ('addV6', 'Mother_Of', 'addV7'),
    ('addV7', 'Son_Of', 'addV6'),
    ('addV6', 'Mother_Of', 'addV3'),
    ('addV3', 'Son_Of', 'addV6'),
    ('addV5', 'Father_Of', 'addV3'),
    ('addV3', 'Son_Of', 'addV5'),
    ('addV5', 'Father_Of', 'addV7'),
    ('addV7', 'Son_Of', 'addV5'),
    ('addV3', 'Brother_Of', 'addV7'),
    ('addV7', 'Brother_Of', 'addV3'),
    ('addV5', 'Husband_Of', 'addV6'),
    ('addV6', 'Wife_Of', 'addV5'),
    ('addV7', 'Father_Of', 'addV11'),
    ('addV7', 'Father_Of', 'addV29'),
    ('addV11', 'Son_Of', 'addV7'),
    ('addV10', 'Mother_Of', 'addV11'),
    ('addV10', 'Mother_Of', 'addV29'),
    ('addV29', 'Son_Of', 'addV7'),
    ('addV29', 'Son_Of', 'addV10'),
    ('addV7', 'Husband_Of', 'addV10'),
    ('addV10', 'Wife_Of', 'addV7'),
    ('addV8', 'Husband_Of', 'addV9'),
    ('addV9', 'Wife_Of', 'addV8'),
    ('addV8', 'Father_Of', 'addV6'),
    ('addV9', 'Mother_Of', 'addV6'),
    ('addV6', 'Daughter_Of', 'addV8'),
    ('addV6', 'Daughter_Of', 'addV9'),
    ('addV7', 'Son_Of*', 'addV8'),
    ('addV7', 'Son_Of*', 'addV9'),
    ('addV8', 'Father_Of*', 'addV7'),
    ('addV9', 'Mother_Of*', 'addV7'),
    ('addV7', 'Brother_Of*', 'addV6'),
    ('addV6', 'Sister_Of*', 'addV7'),
    ('addV12', 'Husband_Of', 'addV13'),
    ('addV13', 'Wife_Of', 'addV12'),
    ('addV12', 'Father_Of', 'addV14'),
    ('addV13', 'Mother_Of', 'addV14'),
    ('addV14', 'Daughter_Of', 'addV12'),
    ('addV14', 'Daughter_Of', 'addV13'),
    ('addV12', 'Father_Of', 'addV15'),
    ('addV13', 'Mother_Of', 'addV15'),
    ('addV15', 'Son_Of', 'addV12'),
    ('addV15', 'Son_Of', 'addV13'),
    ('addV12', 'Brother_Of', 'addV3'),
    ('addV3', 'Brother_Of', 'addV12'),
    ('addV16', 'Husband_Of', 'addV17'),
    ('addV17', 'Wife_Of', 'addV16'),
    ('addV16', 'Father_Of', 'addV18'),
    ('addV17', 'Mother_Of', 'addV18'),
    ('addV18', 'Daughter_Of', 'addV16'),
    ('addV18', 'Daughter_Of', 'addV17'),
    ('addV16', 'Father_Of', 'addV19'),
    ('addV17', 'Mother_Of', 'addV19'),
    ('addV19', 'Daughter_Of', 'addV16'),
    ('addV19', 'Daughter_Of', 'addV17'),
    ('addV16', 'Brother_Of', 'addV3'),
    ('addV3', 'Brother_Of', 'addV16'),
    ('addV20', 'Husband_Of', 'addV21'),
    ('addV21', 'Wife_Of', 'addV20'),
    ('addV20', 'Father_Of', 'addV22'),
    ('addV21', 'Mother_Of', 'addV22'),
    ('addV22', 'Son_Of', 'addV20'),
    ('addV22', 'Son_Of', 'addV21'),
    ('addV20', 'Brother_Of', 'addV3'),
    ('addV3', 'Brother_Of', 'addV20'),
    ('addV23', 'Husband_Of', 'addV24'),
    ('addV24', 'Wife_Of', 'addV23'),
    ('addV23', 'Father_Of', 'addV25'),
    ('addV24', 'Mother_Of', 'addV25'),
    ('addV25', 'Son_Of', 'addV23'),
    ('addV25', 'Son_Of', 'addV24'),
    ('addV24', 'Sister_Of', 'addV3'),
    ('addV3', 'Brother_Of', 'addV24'),
    ('addV26', 'Daughter_Of', 'addV23'),
    ('addV26', 'Daughter_Of', 'addV24'),
    ('addV23', 'Father_Of', 'addV26'),
    ('addV24', 'Mother_Of', 'addV26'),
    ('addV25', 'Husband_Of', 'addV27'),
    ('addV27', 'Wife_Of', 'addV25'),
    ('addV25', 'Father_Of', 'addV28'),
    ('addV27', 'Mother_Of', 'addV28'),
    ('addV28', 'Daughter_Of', 'addV25'),
    ('addV28', 'Daughter_Of', 'addV27'),
]

def reset(conn):
    """Delete every person, and with them every link. Used by ``familytree reset`` and tests."""
    with conn:
        conn.execute('DELETE FROM person')


# Which gedcom-style edge labels the seed graph uses, and what each means to the store.
# The gendered/reverse labels (Son_Of, Daughter_Of, Brother_Of, …) are redundant with these
# and derivable from shared parents, so only the authoritative direction is written.
_BIOLOGICAL_PARENT = {'Father_Of', 'Mother_Of'}
_ADOPTIVE_PARENT = {'Father_Of*', 'Mother_Of*'}
_UNION = {'Husband_Of'}

_SEX = {'Male': MALE, 'Female': FEMALE}


def _family_graph():
    """Build the demo :class:`FamilyGraph` from PEOPLE and EDGES.

    Ids are assigned in PEOPLE insertion order (1-based), so the fixture keys map to stable
    integer ids. Parent links come from the ``*_Of`` (parent -> child) labels; unions from
    ``Husband_Of``; the reverse and sibling labels are ignored because the store derives those
    facts rather than storing them.
    """
    graph = FamilyGraph()
    key_to_id = {key: index for index, key in enumerate(PEOPLE, start=1)}

    for key, props in PEOPLE.items():
        graph.add_person(Person(
            id=key_to_id[key],
            given=str(props.get('Firstname') or ''),
            surname=str(props.get('Lastname') or ''),
            sex=_SEX.get(props.get('Gender'), UNKNOWN),
            birth=DateValue.parse(props.get('Date_of_birth')),
        ))

    for source, label, target in EDGES:
        src, dst = key_to_id[source], key_to_id[target]
        if label in _BIOLOGICAL_PARENT:
            graph.add_parent_link(ParentLink(child_id=dst, parent_id=src, role=BIOLOGICAL))
        elif label in _ADOPTIVE_PARENT:
            graph.add_parent_link(ParentLink(child_id=dst, parent_id=src, role=ADOPTIVE))
        elif label in _UNION:
            graph.add_union(Union(a_id=src, b_id=dst))

    return graph


def seed(conn):
    """Create the demo family in the database and return a mapping of fixture key -> db id."""
    from Tree.gedcom.store import write_family_graph

    graph = _family_graph()
    key_to_file_id = {key: index for index, key in enumerate(PEOPLE, start=1)}
    file_to_db = write_family_graph(conn, graph)
    return {key: file_to_db[file_id] for key, file_id in key_to_file_id.items()}


