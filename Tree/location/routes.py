import logging

from flask import Blueprint, current_app

from Tree import g
from Tree.location.gremlin_Interface import add_location
from Tree.model.Location import Location
from Tree.Utils.Dictionary_converter import convert2dictionary
from Tree.Utils.http import ApiError, json_body, ok

log = logging.getLogger(__name__)

locations = Blueprint('locations', __name__)


@locations.route('/add/location', methods=['POST'])
def add_location_endpoint():
    body = json_body(required=('Place',))
    place = (body.get('Place') or '').strip()
    if not place:
        raise ApiError('Place must not be empty.')

    location = Location(
        place=place,
        state=body.get('State'),
        country=body.get('Country'),
        geocoder=Location.geocoder_from_config(current_app.config),
    )
    vertex_id = add_location(location, return_id=True)
    return ok('Successfully added a location.', Result=vertex_id)


@locations.route('/get/location', methods=['POST'])
def get_location():
    body = json_body()
    limit = current_app.config['MAX_SEARCH_RESULTS']

    if 'all' in body.values():
        rows = g.V().hasLabel('Location').limit(limit).elementMap().toList()
        return ok('Successfully found a location.', Data=convert2dictionary(rows) or [])

    # Each field is matched against its own property. The original Country branch queried the
    # 'State' property with the Country value, so a country search silently matched nothing.
    for field, prop in (('Place', 'Place'), ('State', 'State'), ('Country', 'Country')):
        value = body.get(field)
        if value:
            rows = (
                g.V().hasLabel('Location').has(prop, value)
                .limit(limit).elementMap().toList()
            )
            if rows:
                return ok('Successfully found locations.', Data=convert2dictionary(rows))

    # Previously fell off the end for some inputs and returned None -> HTTP 500.
    return ok('No location found', Data=[], status=404)
