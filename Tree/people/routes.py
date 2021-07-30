import json

from flask import request, Blueprint

from Tree.Utils.Dictionary_converter import *
from Tree.model.Event import Event
from Tree.people.gremlin_Interface import *
from Tree.people.people_Service import create_person_object, retrieve_person_service
from Tree.relations.gremlin_Interface import *

people = Blueprint('people', __name__)


@people.route('/add/person', methods=['POST'])
def add_person_endpoint():
    req_dict = eval(request.data.decode('ascii'))
    print('Request Dictionary is ---', req_dict)

    # Incoming request check
    if not (all(key in req_dict.keys() for key in ['Firstname', 'Lastname', 'Gender', 'Alive', 'Birth'])):
        return json.dumps({'Message': "Could not add a person. Firstname, Lastname, Gender, Alive and Date of Birth "
                                      "fields are required."}), 400, \
               {'ContentType': 'application/json'}

    # All the logic in creating the person object is present in the function.
    p = create_person_object(req_dict)

    if add_person(person=p):
        return json.dumps({'Message': "Successfully added a person."}), 200, \
               {'ContentType': 'application/json'}
    else:
        return json.dumps({'Message': "Could not add a person."}), 400, \
               {'ContentType': 'application/json'}


@people.route('/modify/person', methods=['POST'])
def modify():
    req_dict = eval(request.data.decode('ascii'))
    print('Request Dictionary is ---', req_dict)

    p = create_person_object(req_dict)

    modify_person(p, eval(req_dict['ID']))

    return json.dumps({'Message': "Successfully added a person."}), 200, \
           {'ContentType': 'application/json'}


@people.route('/relate/people', methods=['POST'])
def relate():
    print(request.data)
    req_dict = eval(request.data.decode('ascii'))

    if req_dict.get('Relation') == 'Marriage':

        if req_dict.get('Method') == 'Add-Relate':
            p = create_person_object(req_dict['B'])

            req_dict['B']['ID'] = add_person(person=p, return_id=True)

        if req_dict.get('A').get('Gender') == 'Female' and req_dict.get('B').get('Gender') == 'Male':
            marriage(req_dict.get('B').get('ID'), req_dict.get('A').get('ID'))
            return json.dumps({'Message': 'Marriage relation is added'}), 200, \
                   {'ContentType': 'application/json'}
        else:
            marriage(req_dict.get('A').get('ID'), req_dict.get('B').get('ID'))
            return json.dumps({'Message': 'Marriage relation is added'}), 200, \
                   {'ContentType': 'application/json'}

    if 'C' in req_dict.keys():

        if req_dict.get('Relation') == 'Parents' and req_dict.get('Method') == 'Add-Relate':
            p = Person(Firstname=req_dict['B']['Firstname'],
                       Lastname=req_dict['B']['Lastname'],
                       Gender=req_dict['B'].get('Gender'),
                       Alive=req_dict['B'].get('Alive', ''))
            p.Occupation = req_dict['B'].get('Occupation')
            e = Event()
            e.Date = req_dict['B'].get('Birth')['Date']
            p.Birth = e
            req_dict['B']['ID'] = add_person(person=p, return_id=True)

            q = Person(Firstname=req_dict['C']['Firstname'],
                       Lastname=req_dict['C']['Lastname'],
                       Gender=req_dict['C'].get('Gender'),
                       Alive=req_dict['C'].get('Alive', ''))
            q.Occupation = req_dict['C'].get('Occupation')
            e = Event()
            e.Date = req_dict['C'].get('Birth')['Date']
            q.Birth = e
            req_dict['C']['ID'] = add_person(person=q, return_id=True)

            if marriage(Person1_id=req_dict['B']['ID'], Person2_id=req_dict['C']['ID']):
                if req_dict.get('Relation') != 'Adoption':
                    if (not child(parent1_id=eval(str(req_dict['B'].get('ID'))),
                                  parent2_id=eval(str(req_dict['C'].get('ID'))),
                                  child_id=eval(str(req_dict['A'].get('ID'))))):
                        return json.dumps({'Message': 'Unable to add child'}), 400, \
                               {'ContentType': 'application/json'}
                else:
                    if (not Adoption(parent1_id=eval(str(req_dict['B'].get('ID'))),
                                     parent2_id=eval(str(req_dict['C'].get('ID'))),
                                     child_id=eval(str(req_dict['A'].get('ID'))))):
                        return json.dumps({'Message': 'Unable to add child'}), 400, \
                               {'ContentType': 'application/json'}
                return json.dumps({'Message': 'Successfully added child to the family tree'}), 200, \
                       {'ContentType': 'application/json'}
            else:
                return json.dumps({'Message': 'Unable to create marriage relation'}), 400, \
                       {'ContentType': 'application/json'}

        if req_dict.get('Relation') == 'Child' or req_dict.get('Relation') == 'Adoption':
            if req_dict.get('Method') == 'Add-Relate':
                q = Person(Firstname=req_dict['A']['Firstname'],
                           Lastname=req_dict['A']['Lastname'],
                           Gender=req_dict['A'].get('Gender'),
                           Alive=req_dict['A'].get('Alive', ''))
                q.Occupation = req_dict['A'].get('Occupation')
                e = Event()
                e.Date = req_dict['A'].get('Birth')['Date']
                q.Birth = e
                req_dict['A']['ID'] = add_person(person=q, return_id=True)

                if req_dict.get('Relation') != 'Adoption':
                    child(parent1_id=eval(str(req_dict['B'].get('ID'))), parent2_id=eval(str(req_dict['C'].get('ID'))),
                          child_id=eval(str(req_dict['A'].get('ID'))))
                else:
                    Adoption(parent1_id=eval(str(req_dict['B'].get('ID'))),
                             parent2_id=eval(str(req_dict['C'].get('ID'))),
                             child_id=eval(str(req_dict['A'].get('ID'))))

                return json.dumps({'Message': 'Successfully added child to the family tree'}), 200, \
                       {'ContentType': 'application/json'}


@people.route('/get/person', methods=['POST'])
def get_person():
    req_dict = eval(request.data.decode('ascii'))

    def by_id():
        if not isinstance(eval(req_dict['ID']), int):
            return json.dumps({'Message': "ID is invalid"}), 400, \
                   {'ContentType': 'application/json'}

        relations, person_dictionary = retrieve_person_service(eval(req_dict['ID']))
        return json.dumps({'Message': 'Person found',
                           'Data': json.loads(
                               json.dumps(Person.createPersonObject(person_dictionary),
                                          default=lambda o: o.__dict__)),
                           'Relations': relations}), 200, \
               {'ContentType': 'application/json'}

    def by_list():
        print(req_dict)
        if req_dict.get('Firstname') == 'all':
            ret_value = retrieve_person(all=True)
            return json.dumps({'Message': 'People found', 'Data': convert2dictionary(ret_value)}), 200, \
                   {'ContentType': 'application/json'}
        else:
            ret_value = retrieve_person(search_text=req_dict)
            return json.dumps({'Message': 'People found', 'Data': convert2dictionary(ret_value)}), 200, \
                   {'ContentType': 'application/json'}

    if 'Firstname' in req_dict.keys() or 'Search Text' in req_dict.keys():
        return by_list()
    if 'ID' in req_dict.keys():
        return by_id()
