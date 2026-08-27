import logging

from Tree import g
from Tree.model.Location import Location

log = logging.getLogger(__name__)


def find_location(place, state=None, country=None):
    """Return an existing Location vertex id for this place, or None."""
    step = g.V().hasLabel('Location').has('Place', place)
    if state:
        step = step.has('State', state)
    if country:
        step = step.has('Country', country)
    return step.next().id if step.hasNext() else None


def add_location(location: Location, return_id=False):
    """Create a Location, reusing an existing vertex for the same place.

    The original created a vertex unconditionally with no existence check and no unique index,
    so every call to ``POST /add/location`` accumulated another duplicate for the same place --
    fragmenting the born-in edges across them. It also returned ``vert.id``, a *bound method* on
    the traversal object rather than the new vertex's id, whenever ``return_id`` was set.
    """
    existing = find_location(location.place, location.state, location.country)
    if existing is not None:
        log.info('Reusing existing Location %s for %r', existing, location.place)
        return existing if return_id else True

    traversal = (
        g.addV('Location')
        .property('Place', location.place)
        .property('State', location.state or '')
        .property('Country', location.country or '')
    )
    if location.latitude is not None:
        traversal = traversal.property('Latitude', location.latitude)
    if location.longitude is not None:
        traversal = traversal.property('Longitude', location.longitude)

    vertex = traversal.next()
    return vertex.id if return_id else True


def retrieve_location(all=False, location_ID=None, location_Place=None, limit=200):
    if all:
        return g.V().hasLabel('Location').limit(limit).elementMap().toList()
    # Same rule as retrieve_person: append the projection before executing, never after.
    if location_ID is not None:
        rows = g.V(location_ID).elementMap().limit(1).toList()
        return rows[0] if rows else None
    if location_Place is not None:
        rows = (g.V().hasLabel('Location').has('Place', location_Place)
                .elementMap().limit(1).toList())
        return rows[0] if rows else None
    return None
