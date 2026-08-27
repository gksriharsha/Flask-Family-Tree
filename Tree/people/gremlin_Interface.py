import logging

import Tree.relations.gremlin_Interface as relator
from Tree import Cardinality, TextP, __, g
from Tree.Utils.http import ApiError

log = logging.getLogger(__name__)

# Cardinality per property key. The keys are the lowercase spellings the model now emits; the
# original map keyed on ``Date_of_Birth``/``Date_of_Death`` while the model wrote one casing and
# the readers expected another.
#
# Note on set_ cardinality: Notes.md deliberately chose set_ for birth dates and occupation so a
# person can carry the same fact in several calendars. A consequence to be aware of is that an
# edit through /modify/person therefore *appends* rather than replaces. Changing that safely
# means dropping the existing property values first, which would also discard legitimate
# multi-calendar entries -- so it needs an explicit product decision rather than a quiet change.
CARDINALITY = {
    'Firstname': Cardinality.single,
    'Lastname': Cardinality.single,
    'Gender': Cardinality.single,
    'Alive': Cardinality.single,
    'Date_of_birth': Cardinality.set_,
    'Date_of_death': Cardinality.set_,
    'Occupation': Cardinality.set_,
}


def _apply_properties(traversal, properties):
    for name, value in properties.items():
        # The original fallback for an unmapped key called ``property((Cardinality.single, k, v))``
        # -- one tuple argument instead of three -- which builds a traversal the server rejects.
        traversal = traversal.property(CARDINALITY.get(name, Cardinality.single), name, value)
    return traversal


def add_person(person, return_id=False):
    properties = person.convert_to_gremlin_node()
    if not properties:
        raise ApiError('No person fields supplied.')

    vertex = _apply_properties(g.addV('Person'), properties).next()

    # The birth place is written as a property *and*, when it resolves to a Location vertex, as
    # an edge. The original skipped writing the property whenever the key contained 'Place' and
    # relied only on the edge, while the read path looked for the property -- so the same fact
    # was stored one way and read another.
    try:
        relator.relate_locations(vertex.id, person)
    except Exception:
        log.warning('Could not link %s to its location vertices.', vertex.id, exc_info=True)

    return vertex.id if return_id else True


def modify_person(person, vertex_id):
    """Update a person's properties with a bytecode traversal.

    This replaces an f-string-built Gremlin script submitted through a raw client, which was a
    Groovy injection sink independent of the request-body ``eval`` -- any apostrophe in a name
    also broke the query -- and which created a client per request and never closed it, leaking
    a four-connection pool and four threads each time. It also hardcoded the server URI past the
    configured value.
    """
    properties = person.convert_to_gremlin_node()
    if not properties:
        raise ApiError('No fields to update.')
    if not g.V(vertex_id).hasNext():
        raise ApiError('No such person.', status=404)

    _apply_properties(g.V(vertex_id), properties).iterate()

    try:
        relator.relate_locations(vertex_id, person)
    except Exception:
        log.warning('Could not link %s to its location vertices.', vertex_id, exc_info=True)
    return True


def retrieve_person(id=None, all=False, search_text=None, limit=200):
    if all:
        # The original projection asked for a misspelled date key and omitted Lastname.
        return (
            g.V().hasLabel('Person')
            .limit(limit)
            .elementMap('Firstname', 'Lastname', 'Gender', 'Date_of_birth')
            .toList()
        )

    if id is not None:
        if not g.V(id).hasNext():
            # The original called .next() unconditionally, so an unknown id raised
            # StopIteration and returned a 500 rather than a 404.
            raise ApiError('No such person.', status=404)

        value = g.V(id).elementMap().next()
        projection = ('Firstname', 'Lastname')

        # Each of these is ONE round trip. The projection must be appended before the
        # traversal is executed: calling hasNext() first runs it, and appending elementMap()
        # afterwards silently returns the already-buffered Vertex objects instead, which then
        # fail with "'Vertex' object has no attribute 'items'" in the dictionary converter.
        def _one(step):
            rows = step.elementMap(*projection).limit(1).toList()
            return rows[0] if rows else None

        def _many(step):
            return step.elementMap(*projection).toList() or None

        return (
            value,
            _one(g.V(id).in_('Father_Of')),
            _one(g.V(id).in_('Mother_Of')),
            _many(g.V(id).in_('Brother_Of')),
            _many(g.V(id).in_('Sister_Of')),
            _many(g.V(id).out('Mother_Of', 'Father_Of')),
            _many(g.V(id).in_('Wife_Of', 'Husband_Of')),
        )

    if search_text is not None:
        # The original read search_text['Search Text'] while the route passed the whole body,
        # whose key is 'Firstname' -- so a name search sent TextP.containing(None) to the server.
        needle = search_text
        if isinstance(search_text, dict):
            needle = search_text.get('Search Text') or search_text.get('Firstname')
        if not needle:
            raise ApiError('A non-empty search term is required.')
        return (
            g.V().hasLabel('Person')
            .where(
                __.has('Firstname', TextP.containing(needle)).or_()
                .has('Lastname', TextP.containing(needle))
            )
            .limit(limit)
            .elementMap('Firstname', 'Lastname', 'Gender')
            .toList()
        )

    raise ApiError('One of id, all or search_text is required.')
