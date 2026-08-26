import logging

from flask import Blueprint

from Tree.relations.gremlin_Interface import RelationQueryError, searchRelations
from Tree.Utils.http import as_vertex_id, json_body, ok
from Tree.Utils.RelationReducer import reduce

log = logging.getLogger(__name__)

relations = Blueprint('relations', __name__)


def _reduce_path(path):
    """Split a path into its detail list and a short relation label."""
    relation_details = list(path)
    relation_chain = [item for index, item in enumerate(path) if index % 2 == 1]
    if not relation_chain:
        return None, relation_details
    if len(relation_chain) == 1:
        return relation_chain[0], relation_details
    short = reduce(relation_chain)
    if isinstance(short, list) and len(short) == 1:
        short = short[0]
    return short, relation_details


@relations.route('/search/relation', methods=['POST'])
def search_relation():
    req_dict = json_body(required=('start_id', 'end_id'))
    start_id = as_vertex_id(req_dict['start_id'], field='start_id')
    end_id = as_vertex_id(req_dict['end_id'], field='end_id')

    try:
        path = searchRelations(start_id=start_id, end_id=end_id)
    except RelationQueryError as exc:
        # Two people with no path between them exhaust the traversal and raise. That is an
        # answer, not a server error; the original indexed path[0] and raised IndexError.
        log.info('No relation between %s and %s: %s', start_id, end_id, exc)
        return ok('No relation found.', Data=[], Relation=None, status=404)

    if not path:
        return ok('No relation found.', Data=[], Relation=None, status=404)

    first = path[0] if isinstance(path[0], list) else path
    short_relation, relation_details = _reduce_path(first)
    return ok('Successfully found the relation.',
              Data=relation_details, Relation=short_relation)
