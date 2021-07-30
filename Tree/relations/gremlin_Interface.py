from Tree import client
from Tree import g
from Tree.Utils.RelationReducer import reduce
from Tree.model.Person import Person
import multiprocessing as mp
from itertools import repeat
from flask import current_app


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
    cli = client.Client(current_app.config['GREMLIN_DATABASE_URI'], 'g')
    query_string = f"marriage(g,{Person1_id} , {Person2_id})"
    result_set = cli.submit(query_string, request_options={'evaluationTimeout': 1000})
    future_results = result_set.all()
    cli.close()
    try:
        results = future_results.result()
        return True
    except:
        return False


def child(parent1_id, parent2_id, child_id):
    cli = client.Client(current_app.config['GREMLIN_DATABASE_URI'], 'g')
    query_string = f"child(g,{parent1_id} , {parent2_id}, {child_id})"
    result_set = cli.submit(query_string, request_options={'evaluationTimeout': 1000})
    future_results = result_set.all()
    cli.close()
    try:
        results = future_results.result()
        return True
    except:
        return False


def Adoption(parent1_id, parent2_id, child_id):
    cli = client.Client(current_app.config['GREMLIN_DATABASE_URI'], 'g')
    query_string = f"adoption(g,{parent1_id} , {parent2_id}, {child_id}, [\"Father_lastname\":true])"
    result_set = cli.submit(query_string, request_options={'evaluationTimeout': 1000})
    future_results = result_set.all()
    cli.close()
    try:
        results = future_results.result()
        return True
    except:
        return False


def searchRelations(start_id, end_id):
    cli = client.Client(current_app.config['GREMLIN_DATABASE_URI'], 'g')
    query_string = f"relation(g,{start_id} , {end_id})"
    result_set = cli.submit(query_string, request_options={'evaluationTimeout': 10000})
    future_results = result_set.all()
    paths = ''
    cli.close()
    paths = future_results.result()

    return paths


def get_all_relations(start_id, end_ids):
    dictionary = {}
    compound_relation = ''
    for (k, v) in dict(parallelsearchRelation(start_id, end_ids=end_ids)).items():
        if isinstance(v, list):
            for i, elt in enumerate(v):
                try:
                    v[i + 1]
                    compound_relation = compound_relation + ' ' + elt.split('_')[0] + "'s "
                except:
                    compound_relation = compound_relation + elt.split('_')[0]
            dictionary.update({k: compound_relation})
            compound_relation = ''
        else:
            dictionary.update({k: v.split('_')[0]})
        dictionary.update({start_id:'Me'})
    return dictionary


def parallelsearchRelation(start_id, end_ids):
    sub_processes = mp.cpu_count()
    with mp.Pool(processes=sub_processes) as pool:
        relations = pool.starmap(parsePath, zip(repeat(start_id), end_ids))
    return relations


def parsePath(start_id, end_id):
    path = singlesearchRelation(start_id, end_id)
    relation_details = []
    relation_chain = []
    for i, thing in enumerate(path):
        if i % 2 == 0:
            relation_details.append(thing)
        else:
            relation_chain.append(thing)
            relation_details.append(thing)
    if len(relation_chain) == 1:
        short_relation = relation_chain[0]
    else:
        short_relation = reduce(relation_chain)
        if len(short_relation) == 1:
            short_relation = short_relation[0]
    return end_id, short_relation


def singlesearchRelation(start_id, end_id):
    cli = client.Client(current_app.config['GREMLIN_DATABASE_URI'], 'g')
    query_string = f"shortestPath(g,{start_id} , {end_id})"
    result_set = cli.submit(query_string, request_options={'evaluationTimeout': 100000})
    future_results = result_set.all()
    cli.close()
    path = future_results.result()
    return path
