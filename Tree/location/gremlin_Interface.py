from gremlin_python.structure.graph import Vertex

from Tree import g
from Tree import client
from Tree.model.Location import Location


def add_location(location: Location, return_id=False):
    vert: Vertex = g.addV('Location').property('Country', location.country) \
        .property('State', location.state) \
        .property('Place', location.place).next()
    if return_id:
        return vert.id
    else:
        return True
