from Tree.people.people_routes import *
from Tree.location.location_routes import add_location, get_location

@app.route('/')
def hello_world():
    return 'Hello World!'


@app.route('/delete/nodes/<node>', methods=['DELETE'])
def delete_allnodes(node):
    if node == 'all':
        g.V().drop().iterate()
        return json.dumps({'Message': 'Deleted all nodes'}), 200, \
               {'ContentType': 'application/json'}
    else:
        g.V(eval(node)).drop().iterate()
        return json.dumps({'Message': 'Deleted node number' + node}), 200, \
               {'ContentType': 'application/json'}


@app.route('/query/count_people', methods=['GET'])
def query_people():
    count = g.V().hasLabel("Person").count().next()
    return json.dumps({'Message': 'Fetched the people count', 'Result': count}), 200, {
        'ContentType': 'application/json'}


@app.route('/query/count_locations', methods=['GET'])
def query_locations():
    count = g.V().hasLabel("Location").count().next()
    return json.dumps({'Message': 'Fetched the locations count', 'Result': count}), 200, {
        'ContentType': 'application/json'}


@app.route('/query/fetch_lastNames', methods=['GET'])
def get_lastNames():
    lastnames = g.V().hasLabel('Person').values('Lastname').toList()
    print(lastnames)
    return json.dumps({'Message': 'Fetched all the lastnames', 'Result': lastnames}), 200, {
        'ContentType': 'application/json'}


@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE')
    return response


if __name__ == '__main__':
    app.run(host='0.0.0.0')