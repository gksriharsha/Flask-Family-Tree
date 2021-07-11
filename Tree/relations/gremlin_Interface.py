from Tree import T, __
from Tree import client
from Tree import g
from Tree.model.Person import Person


def relate_locations(person_id, person: Person):
    rel = g.V(person_id)
    if person.Birth.Location is not None:
        rel.addE('BORN_IN').to(g.V(person.Birth.Location['ID']))
    # if person.Occupation.Location is not None:
    #     rel.addE('WORKS_IN').to(g.V(person.Occupation.Location)).and_()
    # if person.Death.Location is not None:
    #     rel.addE('DIED_IN').to(g.V(person.Death.Location)).and_()
    if person.native_to is not None:
        rel.addE('NATIVE_TO').to(g.V(person.native_to)).and_()
    rel.next()


def marriage(Person1_id, Person2_id):
    cli = client.Client('ws://localhost:8182/gremlin', 'g')
    query_string = f"relationship({g},{Person1_id} , {Person2_id})"
    result_set = cli.submit(query_string, request_options={'evaluationTimeout': 1000})
    future_results = result_set.all()
    try:
        results = future_results.result()
        return True
    except:
        return False


def searchRelation(start_id, end_id):
    path = g.V(start_id).repeat(__.outE().otherV().dedup()).until(__.has(T.id, end_id)).path().by(
        __.elementMap()).by(__.elementMap()).next()
    return path
