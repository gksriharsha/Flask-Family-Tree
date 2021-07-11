from Tree.Utils.GremlinFunction import injectFunctions
from Tree.relations.relation_routes import *
from Tree.people.people_routes import *

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
    lastnames = g.V().hasLabel('Person').values('Lastname').toSet()
    return json.dumps({'Message': 'Fetched all the lastnames', 'Result': list(lastnames)}), 200, {
        'ContentType': 'application/json'}


@app.route('/spoc', methods=['GET']) # This is a testing end point. Should be removed in the final version.
def spoc():
    cli = client.Client('ws://localhost:8182/gremlin', 'g')
    query_string = "relationship(g, 28760, 4144)"
    result_set = cli.submit(query_string, request_options={'evaluationTimeout': 1000})
    future_results = result_set.all()
    try:
        results = future_results.result()
        print(results)
    except:
        injectFunctions(cli)
    return json.dumps({'Message': 'Fetched all the lastnames'}), 200, {
        'ContentType': 'application/json'}


@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE')
    return response


if __name__ == '__main__':
    app.run(host='0.0.0.0')
