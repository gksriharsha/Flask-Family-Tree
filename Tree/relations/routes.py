import json
from flask import Blueprint
from Tree import request
from Tree.Utils.RelationReducer import reduce
from Tree.relations.gremlin_Interface import *

relations = Blueprint('relations', __name__)


@relations.route('/search/relation', methods=['POST'])
def search_relation():
    req_dict = eval(request.data.decode('ascii'))
    path = searchRelation(start_id=eval(str(req_dict['start_id'])), end_id=eval(str(req_dict['end_id'])))
    relation_details = []
    relation_chain = []
    for thing in path:
        if thing[T.label] == 'Person':
            print(thing['Firstname'])
            relation_details.append(thing['Firstname'])
        else:
            print(thing[T.label])
            relation_chain.append(thing[T.label])
            relation_details.append(thing[T.label])
    if len(relation_chain) == 1:
        short_relation = relation_chain[0]
    else:
        short_relation = reduce(relation_chain[::-1])
        if len(short_relation) == 1:
            short_relation = short_relation[0]
    return json.dumps(
        {'Message': "Successfully found the relation.", "Data": relation_details, "Relation": short_relation}), 200, \
           {'ContentType': 'application/json'}
