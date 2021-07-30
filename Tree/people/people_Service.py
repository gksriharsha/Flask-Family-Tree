from Tree.Utils.Dictionary_converter import convert2dictionary
from Tree.model.Event import Event
from Tree.model.Person import Person
from Tree.people.gremlin_Interface import retrieve_person


def create_person_object(req_dict):
    p = Person(Firstname=req_dict['Firstname'],
               Lastname=req_dict['Lastname'],
               Gender=req_dict.get('Gender'),
               Alive=req_dict.get('Alive', ''))
    p.Occupation = req_dict.get('Occupation')
    e = Event()
    if 'Location' in req_dict.get('Birth').keys():
        e.Location = req_dict.get('Birth')['Location']
    if 'Time' in req_dict.get('Birth').keys():
        e.Time = req_dict.get('Birth')['Time']
    if 'Date' in req_dict.get('Birth').keys():
        e.Date = req_dict.get('Birth')['Date']
    p.Birth = e
    return p


def retrieve_person_service(id):
    ret_value, father, mother, brother, sister, child, spouse = retrieve_person(id=id)
    relations = {}
    if father is not None:
        relations.update({'Father': convert2dictionary(father)})
    if mother is not None:
        relations.update({'Mother': convert2dictionary(mother)})
    if brother is not None:
        relations.update({'Brother': convert2dictionary(brother)})
    if sister is not None:
        relations.update({'Sister': convert2dictionary(sister)})
    if child is not None:
        relations.update({'Children': convert2dictionary(child)})
    if spouse is not None:
        relations.update({'Spouse': convert2dictionary(spouse)})

    return relations, ret_value