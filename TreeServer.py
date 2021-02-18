import datetime
import json

from flask import Flask
from flask import request
from flask_cors import cross_origin
from gremlin_python.driver.driver_remote_connection import DriverRemoteConnection
from gremlin_python.process.graph_traversal import __
from gremlin_python.process.traversal import T, Cardinality
from gremlin_python.structure.graph import Graph

from Utils.Dictionary_converter import convert2dictionary

graph = Graph()
connection = DriverRemoteConnection('ws://localhost:8182/gremlin', 'g')
# The connection should be closed on shut down to close open connections with connection.close()
g = graph.traversal().withRemote(connection)
# Reuse 'g' across the application

app = Flask(__name__)


@app.route('/')
def hello_world():
    return 'Hello World!'


@app.route('/add/person', methods=['POST'])
def add_person():
    req_dict = eval(request.data.decode('ascii'))
    vert = g.addV('Person') \
        .property(Cardinality.single, 'Alive', req_dict.get('Alive')) \
        .property(Cardinality.set_, 'Firstname', req_dict.get('name')) \
        .property(Cardinality.set_, 'Firstname', req_dict.get('nickname', '')) \
        .property(Cardinality.single, 'Lastname', str(req_dict.get('name'))) \
        .property(Cardinality.single, 'DOB',
                  datetime.datetime(eval(req_dict.get('DOB-year')), eval(req_dict.get('DOB-month')),
                                    eval(req_dict.get('DOB-day')))) \
        .property(Cardinality.single, 'Gender', req_dict.get('Gender')) \
        .property(Cardinality.single, 'Education/Job', req_dict.get('E/J', "NULL")) \
        .property(Cardinality.single, 'Institute', req_dict.get('Institute', "NULL")) \
        .property(Cardinality.single, 'Marital Status', req_dict.get('Marital Status', "Single")) \
        .next()
    # .property('DOD', datetime.datetime(eval(req_dict.get('DOD-year')), eval(req_dict.get('DOD-month')),
    #                                    eval(req_dict.get('DOD-day')))) \
    # .property('DOD', req_dict.get('DOD-telugu')) \

    return json.dumps({'message': "Successfully added a person."}), 200, \
           {'ContentType': 'application/json'}


@app.route('/add/location', methods=['POST'])
def add_location():
    req_dict = eval(request.data.decode('ascii'))
    vert = g.addV('Location') \
        .property('Place', req_dict.get('Place')) \
        .property('State', req_dict.get('State')) \
        .property('Country', req_dict.get('Country')) \
        .next()
    print(vert)
    return json.dumps({'message': "Successfully added a location."}), 200, \
           {'ContentType': 'application/json'}


@app.route('/relate', methods=['POST'])
def relate():
    def marriage(Man_id, Woman_id):
        try:
            g.V(Man_id).addE('Husband_Of').to(g.V(Woman_id)).next()
            g.V(Woman_id).addE('Wife_Of').to(g.V(Man_id)).next()
            g.V(Man_id).property('Marital Status', 'Married').next()
            g.V(Woman_id).property('Marital Status', 'Married').next()
            return json.dumps({'Message': 'Relation Added'}), 200, \
                   {'ContentType': 'application/json'}
        except:
            return json.dumps({'Message': 'Error occured in marriage module'}), 400, \
                   {'ContentType': 'application/json'}

    def siblings(father_id, mother_id, son_id=None, daughter_id=None):

        list_offsprings = []

        id = g.V(father_id).outV('Husband_Of').get(T.id).next()

        if id == mother_id:  # The people are still married.
            list_offsprings = g.V(father_id).out('Father_Of').valueMap(True).toList()

        else:
            if son_id:
                list_offsprings = g.V(son_id).as_('Me').out('Son_Of').has('Gender', 'Male').as_('Father') \
                    .out('Father_Of').where(__.neq('Me')).out('Daughter_Of', 'Son_Of').where(__.neq('Father')).as_(
                    'Mother').out('Mother_Of').where(__.neq('Me')).valueMap(True).toList()
            if daughter_id:
                list_offsprings = g.V(daughter_id).as_('Me').out('Daughter_Of').has('Gender', 'Male').as_('Father') \
                    .out('Father_Of').where(__.neq('Me')).out('Daughter_Of', 'Son_Of').where(__.neq('Father')).as_(
                    'Mother').out('Mother_Of').where(__.neq('Me')).valueMap(True).toList()

        for i in list_offsprings:
            if i[T.id] != son_id and i[T.id] != daughter_id:
                if son_id:
                    g.V(son_id).addE('Brother_Of').to(i[T.id]).next()
                if daughter_id:
                    g.V(daughter_id).addE('Sister_Of').to(i[T.id]).next()

    def son(father_id, mother_id, son_id):
        try:
            g.V(father_id).addE('Father_Of').to(son_id).next()
            g.V(mother_id).addE('Mother_Of').to(son_id).next()
            g.V(son_id).addE('Son_Of').to(father_id).next()
            g.V(son_id).addE('Son_Of').to(mother_id).next()
            siblings(father_id, mother_id, son_id=son_id)
            return json.dumps({'Message': 'Successfully added child to the family tree'}), 200, \
                   {'ContentType': 'application/json'}
        except:
            return json.dumps({'Message': 'Error occured in son module'}), 400, \
                   {'ContentType': 'application/json'}

    def daughter(father_id, mother_id, daughter_id):
        try:
            g.V(father_id).addE('Father_Of').to(daughter_id).next()
            g.V(mother_id).addE('Mother_Of').to(daughter_id).next()
            g.V(daughter_id).addE('Daughter_Of').to(father_id).next()
            g.V(daughter_id).addE('Daughter_Of').to(mother_id).next()
            siblings(father_id, mother_id, daughter_id=daughter_id)
            return json.dumps({'Message': 'Successfully added child to the family tree'}), 200, \
                   {'ContentType': 'application/json'}
        except:
            return json.dumps({'Message': 'Error occured in daughter module'}), 400, \
                   {'ContentType': 'application/json'}

    req_dict = eval(request.data.decode('ascii'))

    if req_dict.get('A').get(T.label) == 'Person' and req_dict.get('B').get(T.label) == 'Person':

        if req_dict.get('A').get('Marital Status') != 'Married' and \
                req_dict.get('B').get('Marital Status') != 'Married' and \
                req_dict.get('Relation') == 'Marriage':

            return marriage(req_dict.get('A').get(T.id),req_dict.get('B').get(T.id))

        if req_dict.has_key('C'):

            if req_dict.get('C').get(T.label) == 'Person':

                if req_dict.get('Relation') == 'Child':

                    if req_dict.get('C').get('Gender') == 'Male':
                        return son(father_id=req_dict.get('A').get(T.id), mother_id=req_dict.get('B').get(T.id),
                            son_id=req_dict.get('C').get(T.id))

                    elif req_dict.get('C').get('Gender') == 'Female':
                        return daughter(father_id=req_dict.get('A').get(T.id), mother_id=req_dict.get('B').get(T.id),
                                 daughter_id=req_dict.get('C').get(T.id))
                    else:
                        return json.dumps({'Message': 'Invalid Gender Information in child module'}), 400, \
                               {'ContentType': 'application/json'}
                else:
                    return json.dumps({'Message': 'Invalid Relation encountered in child module'}), 400, \
                           {'ContentType': 'application/json'}
            else:
                return json.dumps({'Message': 'Invalid Type encountered in child module'}), 400, \
                       {'ContentType': 'application/json'}


    return json.dumps({'Message': 'Invalid Relation encountered - No option matched'}), 400, \
           {'ContentType': 'application/json'}





@app.route('/get/person', methods=['POST'])
@cross_origin()
def get_person():
    req_dict = eval(request.data.decode('ascii'))

    def by_name():
        try:
            ret_value = g.V().has('Person', 'Name', req_dict.get('name')).elementMap().next()
            return json.dumps({'Message': 'Person found', 'value': convert2dictionary(ret_value)}), 200, \
                   {'ContentType': 'application/json'}
        except:
            pass

    def by_list():
        ret_value = g.V().elementMap().toList()
        return json.dumps({'Message': 'Person found', 'Data': convert2dictionary(ret_value)}), 200, \
               {'ContentType': 'application/json'}

    if 'name' in req_dict.keys():
        if req_dict.get('name') == 'all':
            return by_list()
        else:
            return by_name()

    return json.dumps({'Message': "No person found"}), 200, \
           {'ContentType': 'application/json'}


@app.route('/get/location', methods=['POST'])
def get_location():
    value = eval(request.data.decode('ascii'))
    if 'Place' in value.keys() and g.V().has('Location', 'Place', value.get('Place')).hasNext():
        ret_value = g.V().has('Location', 'Place', value.get('Place')).elementMap().next()
        print(ret_value)
        return_dictionary = {}
        for (k, v) in ret_value.items():
            if type(k) == str:
                return_dictionary.update({k: v})
            print(k, ': ', v)
        return json.dumps({'Message': "Successfully found a location.", 'value': return_dictionary}), 200, \
               {'ContentType': 'application/json'}
    elif 'State' in value.keys() and g.V().has('Location', 'State', value.get('State')).hasNext():
        ret_value = g.V().has('Location', 'State', value.get('State')).elementMap().toList()
        print(ret_value)
        return_dictionary = {}
        for (i, d) in enumerate(ret_value):
            ret = {}
            for (k, v) in d.items():
                if type(k) == str:
                    ret.update({k: v})
                print(k, ': ', v)
            return_dictionary.update({'Location ' + str(i): ret})
        return json.dumps({'Message': "Successfully found many locations.", 'value': return_dictionary}), 200, \
               {'ContentType': 'application/json'}
    elif 'Country' in value.keys() and g.V().has('Location', 'Country', value.get('Country')).hasNext():
        ret_value = g.V().has('Location', 'State', value.get('Country')).elementMap().toList()
        print(ret_value)
        return_dictionary = {}
        for (i, d) in enumerate(ret_value):
            ret = {}
            for (k, v) in d.items():
                if type(k) == str:
                    ret.update({k: v})
                print(k, ': ', v)
            return_dictionary.update({'Location ' + str(i): ret})
        return json.dumps({'Message': "Successfully found many locations.", 'value': return_dictionary}), 200, \
               {'ContentType': 'application/json'}

    else:
        return json.dumps({'Message': "No location found"}), 200, \
               {'ContentType': 'application/json'}


@app.route('/delete/nodes', methods=['DELETE'])
def delete_allnodes():
    g.V().drop().iterate()
    return json.dumps({'Message': 'Deleted all nodes'}), 200, \
           {'ContentType': 'application/json'}

@cross_origin()
@app.route('/query/<param>',methods=['GET'])
def query(param):
    if param == 'count_people':
        count = g.V.hasLabel().count()
        return json.dumps({'Message':'Fetched the count','Result':count}), 200,{'ContentType': 'application/json'}

if __name__ == '__main__':
    app.run(host='0.0.0.0')
