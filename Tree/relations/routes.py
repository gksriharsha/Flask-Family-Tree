import json
from flask import Blueprint, request
from Tree.Utils.RelationReducer import reduce
from Tree.relations.gremlin_Interface import *

relations = Blueprint('relations', __name__)


@relations.route('/search/relation', methods=['POST'])
def search_relation():
    def reduction(path):
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
        return short_relation, relation_details
    req_dict = eval(request.data.decode('ascii'))
    path = searchRelations(start_id=eval(str(req_dict['start_id'])), end_id=eval(str(req_dict['end_id'])))
    relation_details = []
    relation_chain = []
    if isinstance(path[0],list):
        short_relation,relation_details = reduction(path[0])
    else:
        short_relation, relation_details = reduction(path)

    return json.dumps(
        {'Message': "Successfully found the relation.", "Data": relation_details, "Relation": short_relation}), 200, \
           {'ContentType': 'application/json'}
