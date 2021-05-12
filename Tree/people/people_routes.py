import json

from flask import request
from gremlin_python.process.graph_traversal import __

from Tree import app, g
from Tree.Utils.Dictionary_converter import *
from Tree.model.Event import Event
from Tree.model.Person import Person
from Tree.people.gremlin_Interface import *


@app.route('/add/person', methods=['POST'])
def add_person_endpoint():
    req_dict = eval(request.data.decode('ascii'))
    print(req_dict)
    p = Person(Firstname=req_dict['Firstname'],
               Lastname=req_dict['Lastname'],
               Gender=req_dict.get('Gender'),
               Alive=req_dict.get('Alive', ''))
    p.Occupation = req_dict.get('Occupation')
    e = Event()
    e.Date = req_dict.get('Birth')['Date']
    p.Birth = e

    if add_person(person=p):
        return json.dumps({'Message': "Successfully added a person."}), 200, \
               {'ContentType': 'application/json'}
    else:
        return json.dumps({'Message': "Could not add a person."}), 404, \
               {'ContentType': 'application/json'}

@app.route('/modify/person',methods=['POST'])
def modify():
    print(request)
    req_dict = eval(request.data.decode('ascii'))
    print(req_dict)
    p = Person(Firstname=req_dict['Firstname'],
               Lastname=req_dict['Lastname'],
               Gender=req_dict.get('Gender'),
               Alive=req_dict.get('Alive', ''))
    p.Occupation = req_dict.get('Occupation')
    e = Event()
    if 'Place' in req_dict.get('Birth').keys():
        e.Location = req_dict.get('Birth')['Place']
    e.Date = req_dict.get('Birth')['Date']
    p.Birth = e
    modify_person(p,eval(req_dict['ID']))
    return json.dumps({'Message': "Successfully added a person."}), 200, \
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
            return marriage(req_dict.get('A').get(T.id), req_dict.get('B').get(T.id))

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
def get_person():
    req_dict = eval(request.data.decode('ascii'))
    print('-------------')
    def by_id():
        if not isinstance(eval(req_dict['ID']), int):
            return json.dumps({'Message': "ID is invalid"}), 400, \
                   {'ContentType': 'application/json'}

        ret_value = retrieve_person(id=eval(req_dict['ID']))
        return json.dumps({'Message': 'Person found', 'Data': json.loads(json.dumps(Person.createPersonObject(ret_value), default=lambda o: o.__dict__))}), 200, \
               {'ContentType': 'application/json'}

    def by_list():
        ret_value = retrieve_person(all = True)
        return json.dumps({'Message': 'People found', 'Data': convert2dictionary(ret_value)}), 200, \
               {'ContentType': 'application/json'}

    if 'ID' in req_dict.keys() or 'Firstname' in req_dict.keys():
        if req_dict.get('Firstname') == 'all':
            return by_list()
        else:
            return by_id()
