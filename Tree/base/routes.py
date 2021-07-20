from flask import Blueprint, request
from Tree.relations.gremlin_Interface import searchRelation
from Tree.faces.recognition import *
from Tree.Utils.ImageReducer import reduce
import json
import os

base = Blueprint('base', __name__)


@base.route('/')
def hello_world():
    return 'Hello World!'


@base.route('/delete/nodes/<node>', methods=['DELETE'])
def delete_allnodes(node):
    if node == 'all':
        g.V().drop().iterate()
        return json.dumps({'Message': 'Deleted all nodes'}), 200, \
               {'ContentType': 'application/json'}
    else:
        g.V(eval(node)).drop().iterate()
        return json.dumps({'Message': 'Deleted node number' + node}), 200, \
               {'ContentType': 'application/json'}


@base.route('/query/count_people', methods=['GET'])
def query_people():
    count = g.V().hasLabel("Person").count().next()
    return json.dumps({'Message': 'Fetched the people count', 'Result': count}), 200, {
        'ContentType': 'application/json'}


@base.route('/query/count_locations', methods=['GET'])
def query_locations():
    count = g.V().hasLabel("Location").count().next()
    return json.dumps({'Message': 'Fetched the locations count', 'Result': count}), 200, {
        'ContentType': 'application/json'}


@base.route('/query/fetch_lastNames', methods=['GET'])
def get_lastNames():
    lastnames = g.V().hasLabel('Person').values('Lastname').toSet()
    return json.dumps({'Message': 'Fetched all the lastnames', 'Result': list(lastnames)}), 200, {
        'ContentType': 'application/json'}


@base.route('/spoc4', methods=['POST'])
def spoc4():
    try:
        if request.headers['faces'] is not None:
            pass
    except:
        file = request.files['image']
        file.save('spoc4.jpg')
        path = os.path.abspath('spoc4.jpg')
        reduce(path)
        val = relate_person_to_face(image_path=path)
        return json.dumps({'Message': 'Recognized', 'Data': val}), 200, {
            'ContentType': 'application/json'}


@base.route('/spoc3', methods=['POST'])
def spoc3():
    file = request.files['image']
    file.save('incoming-img.jpg')
    path = os.path.abspath('incoming-img.jpg')
    reduce(path)
    value = g.V().has('Firstname', 'Krishna Sriharsha').id().next()
    relate_person_to_face(vertex_id=value, image_path=path)
    file2 = request.files['image-2']
    file2.save('guess-img.jpg')
    path2 = os.path.abspath('guess-img.jpg')
    reduce(path2)
    print(recognize_person(path2))
    print(value)
    return json.dumps({'Message': 'Recognized'}), 200, {
        'ContentType': 'application/json'}


@base.route('/spoc2', methods=['GET'])
def spoc2():
    a = g.V().has('Firstname', 'Krishna Sriharsha').id().next()
    b = g.V().has('Firstname', 'Abhiram').id().next()
    print(a)
    print(b)
    # print(searchRelation(a,b))
    print(searchRelation(94352, 86160))
    return json.dumps({'Message': 'Searched'}), 200, {
        'ContentType': 'application/json'}


@base.route('/spoc', methods=['GET'])  # This is a testing end point. Should be removed in the final version.
def spoc():
    delete = g.V().drop().iterate()
    addV1 = g.addV("Person").property("Firstname", "Krishna Sriharsha").property("Lastname", "Gundu") \
        .property("Gender", "Male").next()
    addV2 = g.addV("Person").property("Firstname", "Surya Deepak").property("Lastname", "Gundu") \
        .property("Gender", "Male").next()

    addV3 = g.addV("Person").property("Firstname", "Naga Venkata RamanaRao").property("Lastname", "Gundu") \
        .property("Gender", "Male").next()

    addV4 = g.addV("Person").property("Firstname", "Lakshmi Padmaja").property("Lastname", "Dhyaram") \
        .property("Gender", "Female").next()

    addV5 = g.addV("Person").property("Firstname", "Krishna Murthy").property("Lastname", "Gundu") \
        .property("Gender", "Male").next()
    addV6 = g.addV("Person").property("Firstname", "Parvathi").property("Lastname", "Medavarapu") \
        .property("Gender", "Female").next()

    addV7 = g.addV("Person").property("Firstname", "Sitaramayya").property("Lastname", "Medavarapu") \
        .property("Gender", "Male").property("Adopted", "Yes").next()
    addV8 = g.addV("Person").property("Firstname", "Parent1").property("Lastname", "Gundu") \
        .property("Gender", "Male").next()
    addV9 = g.addV("Person").property("Firstname", "Parent2").property("Lastname", "Gundu") \
        .property("Gender", "Female").next()
    addV10 = g.addV("Person").property("Firstname", "Lakshmi").property("Lastname", "Mutya") \
        .property("Gender", "Female").next()
    addV11 = g.addV("Person").property("Firstname", "Abhiram").property("Lastname", "Medavarapu") \
        .property("Gender", "Male").next()

    print(addV1.id)

    Edge1 = g.V(addV4.id).addE("Mother_Of").to(g.V(addV1.id).next()).next()
    Edge2 = g.V(addV1.id).addE("Son_Of").to(g.V(addV4.id).next()).next()
    Edge3 = g.V(addV4.id).addE("Mother_Of").to(g.V(addV2.id).next()).next()
    Edge4 = g.V(addV2.id).addE("Son_Of").to(g.V(addV4.id).next()).next()

    Edge5 = g.V(addV3.id).addE("Father_Of").to(g.V(addV1.id).next()).next()
    Edge6 = g.V(addV1.id).addE("Son_Of").to(g.V(addV3.id).next()).next()
    Edge7 = g.V(addV3.id).addE("Father_Of").to(g.V(addV2.id).next()).next()
    Edge8 = g.V(addV2.id).addE("Son_Of").to(g.V(addV3.id).next()).next()

    E1 = g.V(addV1.id).addE("Brother_Of").to(g.V(addV2.id).next()).next()
    E2 = g.V(addV2.id).addE("Brother_Of").to(g.V(addV1.id).next()).next()
    Edge17 = g.V(addV3.id).addE("Husband_Of").to(g.V(addV4.id).next()).next()
    Edge18 = g.V(addV4.id).addE("Wife_Of").to(g.V(addV3.id).next()).next()

    ## My family complete

    Edge9 = g.V(addV6.id).addE("Mother_Of").to(g.V(addV7.id).next()).next()
    Edge10 = g.V(addV7.id).addE("Son_Of").to(g.V(addV6.id).next()).next()
    Edge11 = g.V(addV6.id).addE("Mother_Of").to(g.V(addV3.id).next()).next()
    Edge12 = g.V(addV3.id).addE("Son_Of").to(g.V(addV6.id).next()).next()

    Edge13 = g.V(addV5.id).addE("Father_Of").to(g.V(addV3.id).next()).next()
    Edge14 = g.V(addV3.id).addE("Son_Of").to(g.V(addV5.id).next()).next()
    Edge15 = g.V(addV5.id).addE("Father_Of").to(g.V(addV7.id).next()).next()
    Edge16 = g.V(addV7.id).addE("Son_Of").to(g.V(addV5.id).next()).next()

    E3 = g.V(addV3.id).addE("Brother_Of").to(g.V(addV7.id).next()).next()
    E4 = g.V(addV7.id).addE("Brother_Of").to(g.V(addV3.id).next()).next()
    Edge19 = g.V(addV5.id).addE("Husband_Of").to(g.V(addV6.id).next()).next()
    Edge20 = g.V(addV6.id).addE("Wife_Of").to(g.V(addV5.id).next()).next()

    ## Dad's family complete

    Edge21 = g.V(addV7.id).addE("Father_Of").to(g.V(addV11.id).next()).next()
    Edge22 = g.V(addV11.id).addE("Son_Of").to(g.V(addV7.id).next()).next()
    Edge23 = g.V(addV10.id).addE("Mother_Of").to(g.V(addV11.id).next()).next()
    Edge24 = g.V(addV11.id).addE("Son_Of").to(g.V(addV7.id).next()).next()
    Edge25 = g.V(addV7.id).addE("Husband_Of").to(g.V(addV10.id).next()).next()
    Edge26 = g.V(addV10.id).addE("Wife_Of").to(g.V(addV7.id).next()).next()

    Edge27 = g.V(addV8.id).addE("Husband_Of").to(g.V(addV9.id).next()).next()
    Edge28 = g.V(addV9.id).addE("Wife_Of").to(g.V(addV8.id).next()).next()
    Edge29 = g.V(addV8.id).addE("Father_Of").to(g.V(addV6.id).next()).next()
    Edge30 = g.V(addV9.id).addE("Mother_Of").to(g.V(addV6.id).next()).next()
    Edge31 = g.V(addV6.id).addE("Daughter_Of").to(g.V(addV8.id).next()).next()
    Edge32 = g.V(addV6.id).addE("Daughter_Of").to(g.V(addV9.id).next()).next()

    Edge33 = g.V(addV7.id).addE("Son_Of*").to(g.V(addV8.id).next()).next()
    Edge34 = g.V(addV7.id).addE("Son_Of*").to(g.V(addV9.id).next()).next()
    Edge35 = g.V(addV8.id).addE("Father_Of*").to(g.V(addV7.id).next()).next()
    Edge36 = g.V(addV9.id).addE("Mother_Of*").to(g.V(addV7.id).next()).next()
    Edge37 = g.V(addV7.id).addE("Brother_Of*").to(g.V(addV6.id).next()).next()
    Edge38 = g.V(addV6.id).addE("Sister_Of*").to(g.V(addV7.id).next()).next()

    return json.dumps({'Message': 'Added all people and relations'}), 200, {
        'ContentType': 'application/json'}


@base.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE')
    return response
