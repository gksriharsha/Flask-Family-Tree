"""Query and maintenance endpoints.

Removed from the original file:

* ``/spoc``, ``/spoc2``, ``/spoc3``, ``/spoc4`` -- leftover debug endpoints. ``GET /spoc``
  opened with ``g.V().drop().iterate()``, so a crawler, link preview, prefetcher or an
  ``<img>`` tag pointing at it destroyed the entire graph with no authentication and no POST.
  The 29-person seed it built has moved to ``Tree/seed.py`` and is reachable only through the
  CLI, because it is the project's only regression corpus.
* The ``all`` branch of ``/delete/nodes`` -- an unauthenticated whole-database wipe. Now a
  deliberate CLI command.
* ``eval`` on the ``<node>`` path segment. The route takes a typed integer converter, so a
  payload can no longer reach a code path that executes it.

``g`` is now imported explicitly. The original relied on a wildcard re-export from
``Tree.faces.recognition`` for the traversal source, so tidying imports anywhere would have
silently broken all nine endpoints here.
"""

import logging

from flask import Blueprint, current_app, request

from Tree import g
from Tree.Utils.http import ok

log = logging.getLogger(__name__)

base = Blueprint('base', __name__)


@base.route('/delete/nodes/<int:node>', methods=['DELETE'])
def delete_node(node):
    if not g.V(node).hasNext():
        return ok('No such node', status=404, Result=node)
    g.V(node).drop().iterate()
    log.info('Dropped vertex %s', node)
    return ok('Deleted node', Result=node)


@base.route('/query/count_people', methods=['GET'])
def query_people():
    count = g.V().hasLabel('Person').count().next()
    return ok('Fetched the people count', Result=count)


@base.route('/query/count_locations', methods=['GET'])
def query_locations():
    count = g.V().hasLabel('Location').count().next()
    return ok('Fetched the locations count', Result=count)


@base.route('/query/fetch_lastNames', methods=['GET'])
def get_lastNames():
    """Distinct surnames.

    Accepts an optional ``?prefix=`` filter and is capped, because the unfiltered version
    returned every surname in the family to any caller and the client refetched the whole list
    on each field blur.
    """
    limit = current_app.config['MAX_SEARCH_RESULTS']
    prefix = (request.args.get('prefix') or '').strip()
    lastnames = sorted(g.V().hasLabel('Person').values('Lastname').dedup().limit(limit).toList())
    if prefix:
        lowered = prefix.lower()
        lastnames = [name for name in lastnames if str(name).lower().startswith(lowered)]
    return ok('Fetched all the lastnames', Result=lastnames)
