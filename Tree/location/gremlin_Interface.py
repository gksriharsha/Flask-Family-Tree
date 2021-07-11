from Tree import g
from Tree.model.Location import Location


def add_location(location: Location, return_id=False):
    vert = g.addV('Location').property('Country', location.country) \
        .property('State', location.state) \
        .property('Place', location.place)
    if location.longitude is not None:
        vert.property('Longitude', location.longitude)
    if location.latitude is not None:
        vert.property('Latitude', location.latitude)

    vert.next()
    if return_id:
        return vert.id
    else:
        return True


def retrieve_location(all=False, location_ID=None, location_Place=None):
    if all:
        return g.V().hasLabel('Location').elementMap('Place').toList()
    if location_Place is None and location_ID is None:
        return False
    if location_ID is not None:
        return g.V(location_ID).elementMap().next()
    if location_Place is not None:
        return g.V().hasLabel('Location').has('Place', location_Place).next()
