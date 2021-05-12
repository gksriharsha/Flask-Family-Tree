from gremlin_python.process.traversal import Cardinality

import Tree.relations.gremlin_Interface as relator
from Tree import g
from Tree import client


# def add_person(person,quick_add=False):
#     additional_params = []
#     if not isinstance(person, Person):
#         return False
#     else:
#         vert = g.addV('Person')
#         person_properties = person.__dict__
#         if None in list(person_properties.values()):
#             return False
#         for (k, v) in person_properties.items():
#             if 'name' in k:
#                 vert.property(Cardinality.set_, k, v)
#             if isinstance(v, int):
#                 additional_params.append((k, v))
#             else:
#                 vert.property(Cardinality.single, k, v)
#         vert.next()
#
#         for additional_param in additional_params:
#             if additional_param[0] == 'place_of_work':
#                 relator.relate_locations(person, work=additional_param[1])
#             if additional_param[0] == 'place_of_death':
#                 relator.relate_locations(person, death=additional_param[1])
#             if additional_param[0] == 'native_to':
#                 relator.relate_locations(person, native=additional_param[1])
#             if additional_param[0] == 'place_of_birth':
#                 relator.relate_locations(person, birth=additional_param[1])
#         return True
from Tree.model.Location import Location
from Tree.model.Person import Person
import Tree.location.gremlin_Interface as locator

def add_person(person, location:Location=None):
    dict = person.convert_to_gremlin_node()
    vert = g.addV('Person')
    place = False
    for item in dict.items():
        if 'Place' in item[0]:
            place = True
        else:
            vert.property(item[0], item[1])

    vert.next()

    if place:
        relator.relate_locations(vert.id,person)

    return True


def modify_person(person: Person,ID):
    cli = client.Client('ws://localhost:8182/gremlin','g')
    query_string = f"g.V({ID})"
    for item in person.convert_to_gremlin_node().items():
        query_string = query_string+f".property('{item[0]}','{item[1]}')"
    print(query_string)
    result_set = cli.submit(query_string,request_options={'evaluationTimeout': 5000})
    future_results = result_set.all()
    results = future_results.result()
    print(results)
    return True

def retrieve_person(id=None, all=False, node=False):
    if all:
        return g.V().hasLabel('Person').elementMap('Firstname', 'DOB', 'Gender').toList()
    if id is not None and all == False:
        if node:
            return g.V().hasId(id).hasLabel('Person').next()
        val = g.V(id).elementMap().next()
        return val


if __name__ == '__main__':
    pass
