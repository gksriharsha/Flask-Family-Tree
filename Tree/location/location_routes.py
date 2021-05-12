import json

from Tree import app, request, g
from Tree.Utils.Dictionary_converter import convert2dictionary
from Tree.model.Location import Location
from Tree.location.gremlin_Interface import add_location


@app.route('/add/location', methods=['POST'])
def add_location():
    req_dict = eval(request.data.decode('ascii'))
    location = Location(place=req_dict.get('Place',''),state=req_dict.get('State'),country=req_dict.get('Country'))
    add_location(location)
    return json.dumps({'Message': "Successfully added a location."}), 200, \
           {'ContentType': 'application/json'}


@app.route('/get/location', methods=['POST'])
def get_location():
    value = eval(request.data.decode('ascii'))
    if 'all' in value.values():
        ret_value = g.V().hasLabel('Location').elementMap().toList()
        return json.dumps({'Message': "Successfully found a location.", 'Data': convert2dictionary(ret_value)}), 200, \
               {'ContentType': 'application/json'}
    if 'Place' in value.keys() and g.V().has('Location', 'Place', value.get('Place')).hasNext():
        ret_value = g.V().has('Location', 'Place', value.get('Place')).elementMap().toList()
        return json.dumps({'Message': "Successfully found a location.", 'Data': convert2dictionary(ret_value)}), 200, \
               {'ContentType': 'application/json'}
    elif 'State' in value.keys() and g.V().has('Location', 'State', value.get('State')).hasNext():
        ret_value = g.V().has('Location', 'State', value.get('State')).elementMap().toList()
        return json.dumps({'Message': "Successfully found many locations.", 'Data': convert2dictionary(ret_value)}), 200, \
               {'ContentType': 'application/json'}
    elif 'Country' in value.keys() and g.V().has('Location', 'Country', value.get('Country')).hasNext():
        ret_value = g.V().has('Location', 'State', value.get('Country')).elementMap().toList()
        return json.dumps({'Message': "Successfully found many locations.", 'Data': convert2dictionary(ret_value)}), 200, \
               {'ContentType': 'application/json'}
    else:
        return json.dumps({'Message': "No location found"}), 200, \
               {'ContentType': 'application/json'}
