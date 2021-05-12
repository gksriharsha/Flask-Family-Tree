from Tree import g
from Tree.model.Person import Person


def relate_people():
    pass


def relate_locations(person_id,person: Person):
    rel = g.V(person_id)
    if person.Birth.Location is not None:
        rel.addE('BORN_IN').to(g.V(person.Birth.Location)).and_()
    if person.Occupation.Location is not None:
        rel.addE('WORKS_IN').to(g.V(person.Occupation.Location)).and_()
    if person.Death.Location is not None:
        rel.addE('DIED_IN').to(g.V(person.Death.Location)).and_()
    if person.native_to is not None:
        rel.addE('NATIVE_TO').to(g.V(person.native_to)).and_()
    rel.next()

def relate_caste():
    pass

if __name__ == '__main__':
    pass