import Tree.relations.gremlin_Interface as relator
from Tree import Cardinality, __
from Tree import TextP
from Tree import client
from Tree import g
from Tree.model.Person import Person


def add_person(person, return_id=False):
    cardinality_Mapper = {
        'Firstname': Cardinality.single,
        'Lastname': Cardinality.single,
        'Gender': Cardinality.single,
        'Alive': Cardinality.single,

        'Date_of_Birth': Cardinality.set_,
        'Date_of_Death': Cardinality.set_,
        'Occupation': Cardinality.set_,

    }

    dict = person.convert_to_gremlin_node()
    vert = g.addV('Person')
    place = False
    for item in dict.items():
        if 'Place' in item[0]:
            place = True
        else:
            try:
                vert.property(cardinality_Mapper[item[0]], item[0], item[1])
            except KeyError as e:
                vert.property((Cardinality.single, item[0], item[1]))

    val = vert.next()

    if place:
        relator.relate_locations(val.id, person)

    if return_id:
        return val.id
    print('Run everython')
    return True


def modify_person(person: Person, ID):
    cli = client.Client('ws://localhost:8182/gremlin', 'g')
    place = False
    query_string = f"g.V({ID})"
    for item in person.convert_to_gremlin_node().items():
        query_string = query_string + f".property('{item[0]}','{item[1]}')"
        if 'Place' in item[0]:
            place = True
    result_set = cli.submit(query_string, request_options={'evaluationTimeout': 5000})
    future_results = result_set.all()
    results = future_results.result()
    if place:
        relator.relate_locations(ID, person)
        print('Added Location vertex')

    return True


def retrieve_person(id=None, all=False, search_text=None):
    if all:
        return g.V().hasLabel('Person').elementMap('Firstname', 'DOB', 'Gender').toList()
    if id is not None:
        Father = None
        Mother = None
        Brother = None
        Sister = None
        Children = None
        Spouse = None
        val = g.V(id).elementMap().next()
        if g.V(id).inE('Father_Of').hasNext():
            Father = g.V(id).in_('Father_Of').elementMap('Firstname', 'Lastname').next()
        if g.V(id).inE('Mother_Of').hasNext():
            Mother = g.V(id).in_('Mother_Of').elementMap('Firstname', 'Lastname').next()
        if g.V(id).inE('Brother_Of').hasNext():
            Brother = g.V(id).in_('Brother_Of').elementMap('Firstname', 'Lastname').toList()
        if g.V(id).inE('Sister_Of').hasNext():
            Sister = g.V(id).in_('Sister_Of').elementMap('Firstname', 'Lastname').toList()
        if g.V(id).outE('Mother_Of', 'Father_Of').hasNext():
            Children = g.V(id).out('Mother_Of', 'Father_Of').elementMap('Firstname', 'Lastname').toList()
        if g.V(id).inE('Wife_Of', 'Husband_Of').hasNext():
            Spouse = g.V(id).in_('Wife_Of', 'Husband_Of').elementMap('Firstname', 'Lastname').toList()
        return val, Father, Mother, Brother, Sister, Children, Spouse
    if search_text is not None:
        return g.V().where(__.has('Firstname', TextP.containing(search_text.get('Search Text'))).or_()
                           .has('Lastname', TextP.containing(search_text.get('Search Text')))) \
            .elementMap('Firstname', 'Lastname', 'Gender').toList()

## region gremlin script duplicate
# def son(father_id, mother_id, son_id, adopted=False):
#
#     if adopted:
#         g.V(father_id).addE('Father_Of*').to(g.V(son_id)).next()
#         g.V(mother_id).addE('Mother_Of*').to(g.V(son_id)).next()
#         g.V(son_id).addE('Son_Of*').to(g.V(father_id)).next()
#         g.V(son_id).addE('Son_Of*').to(g.V(mother_id)).next()
#     else:
#         g.V(father_id).addE('Father_Of').to(g.V(son_id)).next()
#         g.V(mother_id).addE('Mother_Of').to(g.V(son_id)).next()
#         g.V(son_id).addE('Son_Of').to(g.V(father_id)).next()
#         g.V(son_id).addE('Son_Of').to(g.V(mother_id)).next()
#     siblings(father_id, mother_id, son_id=son_id)
#
#
# def daughter(father_id, mother_id, daughter_id, adopted=False):
#     g.V(father_id).addE('Father_Of').to(g.V(daughter_id)).next()
#     g.V(mother_id).addE('Mother_Of').to(g.V(daughter_id)).next()
#     if adopted:
#         g.V(daughter_id).addE('Adopted_Daughter_Of').to(g.V(father_id)).next()
#         g.V(daughter_id).addE('Adopted_Daughter_Of').to(g.V(mother_id)).next()
#     else:
#         g.V(daughter_id).addE('Daughter_Of').to(g.V(father_id)).next()
#         g.V(daughter_id).addE('Daughter_Of').to(g.V(mother_id)).next()
#     siblings(father_id, mother_id, daughter_id=daughter_id)
#
#
# def siblings(father_id, mother_id, son_id=None, daughter_id=None):
#     list_offsprings = []
#
#     id = g.V(father_id).out('Husband_Of').next().id
#
#     if id == mother_id:  # The people are still married.
#         list_offsprings = g.V(father_id).in_('Father_Of').valueMap(True).toList()
#
#     else:
#         if son_id is not None:
#             list_offsprings = g.V(son_id).as_('Me').out('Son_Of').has('Gender', 'Male').as_('Father') \
#                 .out('Father_Of').where(__.neq('Me')).out('Daughter_Of', 'Son_Of').where(__.neq('Father')).as_(
#                 'Mother').out('Mother_Of').where(__.neq('Me')).valueMap(True).toList()
#         if daughter_id is not None:
#             list_offsprings = g.V(daughter_id).as_('Me').out('Daughter_Of').has('Gender', 'Male').as_('Father') \
#                 .out('Father_Of').where(__.neq('Me')).out('Daughter_Of', 'Son_Of').where(__.neq('Father')).as_(
#                 'Mother').out('Mother_Of').where(__.neq('Me')).valueMap(True).toList()
#
#     for i in list_offsprings:
#         if son_id is not None:
#             if i[T.id] != eval(str(son_id)):
#                 g.V(son_id).addE('Brother_Of').to(g.V(i[T.id])).next()
#                 if i['Gender'][0] == 'Male':
#                     g.V(i[T.id]).addE('Brother_Of').to(g.V(son_id)).next()
#                 else:
#                     g.V(i[T.id]).addE('Sister_Of').to(g.V(son_id)).next()
#         if daughter_id is not None:
#             if i[T.id] != eval(str(daughter_id)):
#                 g.V(daughter_id).addE('Sister_Of').to(g.V(i[T.id])).next()
#                 if i['Gender'][0] == 'Male':
#                     g.V(i[T.id]).addE('Brother_Of').to(g.V(daughter_id)).next()
#                 else:
#                     g.V(i[T.id]).addE('Sister_Of').to(g.V(daughter_id)).next()
## endregion
