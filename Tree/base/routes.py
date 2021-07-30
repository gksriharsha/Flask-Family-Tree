from flask import Blueprint, request, send_file
from Tree.relations.gremlin_Interface import searchRelations, parallelsearchRelation, get_all_relations
from Tree.faces.recognition import *
from Tree.Utils.ImageReducer import reduce
import json
import os
import time

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
    v1, file, locations, _ = draw_boxes(path)
    while not os.path.exists(file):
        time.sleep(1)

    if os.path.isfile(file):
        # read file
        resp = send_file(os.path.abspath(file), as_attachment=False)
        return resp
    else:
        raise ValueError("%s isn't a file!" % file)
    # value = g.V().has('Firstname', 'Krishna Sriharsha').id().next()
    # relate_person_to_face(vertex_id=value, image_path=path)
    # file2 = request.files['image-2']
    # file2.save('guess-img.jpg')
    # path2 = os.path.abspath('guess-img.jpg')
    # reduce(path2)
    # print(recognize_person(path2))
    # print(value)


@base.route('/spoc2', methods=['GET'])
def spoc2():
    a = g.V().has('Firstname', 'Krishna Sriharsha').id().next()
    b = g.V().has('Firstname', 'Abhiram').id().next()
    print(a)
    print(b)
    # print(searchRelation(a,b))
    # print(searchRelations(40964136, 4272))
    print(get_all_relations(4272, [40964136, 12312, 8216, 40964280]))
    return json.dumps({'Message': 'Searched'}), 200, {
        'ContentType': 'application/json'}


@base.route('/spoc', methods=['GET'])  # This is a testing end point. Should be removed in the final version.
def spoc():
    delete = g.V().drop().iterate()
    addV1 = g.addV("Person").property("Firstname", "Krishna Sriharsha").property("Lastname", "Gundu") \
        .property("Gender", "Male").property("Date_of_birth","1990-01-01").next()
    addV2 = g.addV("Person").property("Firstname", "Surya Deepak").property("Lastname", "Gundu") \
        .property("Gender", "Male").property("Date_of_birth","1990-01-01").next()

    addV3 = g.addV("Person").property("Firstname", "Naga Venkata RamanaRao").property("Lastname", "Gundu") \
        .property("Gender", "Male").property("Date_of_birth","1990-01-01").next()

    addV4 = g.addV("Person").property("Firstname", "Lakshmi Padmaja").property("Lastname", "Dhyaram") \
        .property("Gender", "Female").property("Date_of_birth","1990-01-01").next()

    addV5 = g.addV("Person").property("Firstname", "Krishna Murthy").property("Lastname", "Gundu") \
        .property("Gender", "Male").property("Date_of_birth","1990-01-01").next()
    addV6 = g.addV("Person").property("Firstname", "Parvathi").property("Lastname", "Medavarapu") \
        .property("Gender", "Female").property("Date_of_birth","1990-01-01").next()

    addV7 = g.addV("Person").property("Firstname", "Sitaramayya").property("Lastname", "Medavarapu") \
        .property("Gender", "Male").property("Adopted", "Yes").property("Date_of_birth","1990-01-01").next()
    addV8 = g.addV("Person").property("Firstname", "Parent1").property("Lastname", "Gundu") \
        .property("Gender", "Male").property("Date_of_birth","1990-01-01").next()
    addV9 = g.addV("Person").property("Firstname", "Parent2").property("Lastname", "Gundu") \
        .property("Gender", "Female").property("Date_of_birth","1990-01-01").next()
    addV10 = g.addV("Person").property("Firstname", "Lakshmi").property("Lastname", "Mutya") \
        .property("Gender", "Female").property("Date_of_birth","1990-01-01").next()
    addV11 = g.addV("Person").property("Firstname", "Abhiram").property("Lastname", "Medavarapu") \
        .property("Gender", "Male").property("Date_of_birth","1990-01-01").next()
    addV29 = g.addV("Person").property("Firstname", "Anirudh").property("Lastname", "Medavarapu") \
        .property("Gender", "Male").property("Date_of_birth","1990-01-01").next()
    addV12 = g.addV("Person").property("Firstname", "Narasayya").property("Lastname", "Gundu") \
        .property("Gender", "Male").property("Date_of_birth", "1990-01-01").next()
    addV13 = g.addV("Person").property("Firstname", "Rani").property("Lastname", "Gundu") \
        .property("Gender", "Female").property("Date_of_birth", "1990-01-01").next()
    addV14 = g.addV("Person").property("Firstname", "Gayathri").property("Lastname", "Gundu") \
        .property("Gender", "Female").property("Date_of_birth", "1990-01-01").next()
    addV15 = g.addV("Person").property("Firstname", "Prahallad").property("Lastname", "Gundu") \
        .property("Gender", "Male").property("Date_of_birth", "1990-01-01").next()
    addV16 = g.addV("Person").property("Firstname", "Kampandu").property("Lastname", "Gundu") \
        .property("Gender", "Male").property("Date_of_birth", "1990-01-01").next()
    addV17 = g.addV("Person").property("Firstname", "Tayi").property("Lastname", "Gundu") \
        .property("Gender", "Female").property("Date_of_birth", "1990-01-01").next()
    addV18 = g.addV("Person").property("Firstname", "Snehitha").property("Lastname", "Gundu") \
        .property("Gender", "Female").property("Date_of_birth", "1990-01-01").next()
    addV19 = g.addV("Person").property("Firstname", "Saranya").property("Lastname", "Gundu") \
        .property("Gender", "Female").property("Date_of_birth", "1990-01-01").next()
    addV20 = g.addV("Person").property("Firstname", "Sathish").property("Lastname", "Gundu") \
        .property("Gender", "Male").property("Date_of_birth", "1990-01-01").next()
    addV21 = g.addV("Person").property("Firstname", "Devi").property("Lastname", "Gundu") \
        .property("Gender", "Female").property("Date_of_birth", "1990-01-01").next()
    addV22 = g.addV("Person").property("Firstname", "Krishna Kumar").property("Lastname", "Gundu") \
        .property("Gender", "Female").property("Date_of_birth", "1990-01-01").next()
    addV23 = g.addV("Person").property("Firstname", "Mavayya").property("Lastname", "Amanchi") \
        .property("Gender", "Male").property("Date_of_birth", "1990-01-01").next()
    addV24 = g.addV("Person").property("Firstname", "Brahmaramba").property("Lastname", "Gundu") \
        .property("Gender", "Female").property("Date_of_birth", "1990-01-01").next()
    addV25 = g.addV("Person").property("Firstname", "Seshu").property("Lastname", "Amanchi") \
        .property("Gender", "Female").property("Date_of_birth", "1990-01-01").next()
    addV26 = g.addV("Person").property("Firstname", "Srikala").property("Lastname", "Amanchi") \
        .property("Gender", "Female").property("Date_of_birth", "1990-01-01").next()
    addV27 = g.addV("Person").property("Firstname", "Anajana").property("Lastname", "Yanamandra") \
        .property("Gender", "Male").property("Date_of_birth", "1990-01-01").next()
    addV28 = g.addV("Person").property("Firstname", "Manojna").property("Lastname", "Amanchi") \
        .property("Gender", "Female").property("Date_of_birth", "1990-01-01").next()

    print('Harsha - '+ str(addV1.id))
    print('Abhiram - '+ str(addV11.id))
    print('Deepak - '+ str(addV2.id))
    print('Anirudh - '+ str(addV29.id))
    print('Gayathri - ' + str(addV14.id))
    print('Prahallad - '+ str(addV15.id))
    print('Snehitha - '+ str(addV18.id))
    print('Saranya - '+ str(addV19.id))
    print('Krishna Kumar - '+ str(addV22.id))
    print('Manojna - '+ str(addV28.id))


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
    Edge21 = g.V(addV7.id).addE("Father_Of").to(g.V(addV29.id).next()).next()
    Edge22 = g.V(addV11.id).addE("Son_Of").to(g.V(addV7.id).next()).next()
    Edge23 = g.V(addV10.id).addE("Mother_Of").to(g.V(addV11.id).next()).next()
    Edge23 = g.V(addV10.id).addE("Mother_Of").to(g.V(addV29.id).next()).next()
    Edge24 = g.V(addV11.id).addE("Son_Of").to(g.V(addV7.id).next()).next()
    Edge24 = g.V(addV29.id).addE("Son_Of").to(g.V(addV7.id).next()).next()
    Edge25 = g.V(addV29.id).addE("Son_Of").to(g.V(addV10.id).next()).next()
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

    Edge39 = g.V(addV12.id).addE("Husband_Of").to(g.V(addV13.id).next()).next()
    Edge40 = g.V(addV13.id).addE("Wife_Of").to(g.V(addV12.id).next()).next()
    Edge41 = g.V(addV12.id).addE("Father_Of").to(g.V(addV14.id).next()).next()
    Edge42 = g.V(addV13.id).addE("Mother_Of").to(g.V(addV14.id).next()).next()
    Edge43 = g.V(addV14.id).addE("Daughter_Of").to(g.V(addV12.id).next()).next()
    Edge44 = g.V(addV14.id).addE("Daughter_Of").to(g.V(addV13.id).next()).next()
    Edge45 = g.V(addV12.id).addE("Father_Of").to(g.V(addV15.id).next()).next()
    Edge46 = g.V(addV13.id).addE("Mother_Of").to(g.V(addV15.id).next()).next()
    Edge47 = g.V(addV15.id).addE("Son_Of").to(g.V(addV12.id).next()).next()
    Edge48 = g.V(addV15.id).addE("Son_Of").to(g.V(addV13.id).next()).next()
    Edge49 = g.V(addV12.id).addE("Brother_Of").to(g.V(addV3.id).next()).next()
    Edge50 = g.V(addV3.id).addE("Brother_Of").to(g.V(addV12.id).next()).next()

    Edge50 = g.V(addV16.id).addE("Husband_Of").to(g.V(addV17.id).next()).next()
    Edge51 = g.V(addV17.id).addE("Wife_Of").to(g.V(addV16.id).next()).next()
    Edge52 = g.V(addV16.id).addE("Father_Of").to(g.V(addV18.id).next()).next()
    Edge53 = g.V(addV17.id).addE("Mother_Of").to(g.V(addV18.id).next()).next()
    Edge54 = g.V(addV18.id).addE("Daughter_Of").to(g.V(addV16.id).next()).next()
    Edge55 = g.V(addV18.id).addE("Daughter_Of").to(g.V(addV17.id).next()).next()
    Edge56 = g.V(addV16.id).addE("Father_Of").to(g.V(addV19.id).next()).next()
    Edge57 = g.V(addV17.id).addE("Mother_Of").to(g.V(addV19.id).next()).next()
    Edge58 = g.V(addV19.id).addE("Daughter_Of").to(g.V(addV16.id).next()).next()
    Edge59 = g.V(addV19.id).addE("Daughter_Of").to(g.V(addV17.id).next()).next()
    Edge60 = g.V(addV16.id).addE("Brother_Of").to(g.V(addV3.id).next()).next()
    Edge61 = g.V(addV3.id).addE("Brother_Of").to(g.V(addV16.id).next()).next()



    Edge62 = g.V(addV20.id).addE("Husband_Of").to(g.V(addV21.id).next()).next()
    Edge63 = g.V(addV21.id).addE("Wife_Of").to(g.V(addV20.id).next()).next()
    Edge64 = g.V(addV20.id).addE("Father_Of").to(g.V(addV22.id).next()).next()
    Edge65 = g.V(addV21.id).addE("Mother_Of").to(g.V(addV22.id).next()).next()
    Edge66 = g.V(addV22.id).addE("Son_Of").to(g.V(addV20.id).next()).next()
    Edge67 = g.V(addV22.id).addE("Son_Of").to(g.V(addV21.id).next()).next()
    Edge68 = g.V(addV20.id).addE("Brother_Of").to(g.V(addV3.id).next()).next()
    Edge69 = g.V(addV3.id).addE("Brother_Of").to(g.V(addV20.id).next()).next()

    Edge70 = g.V(addV23.id).addE("Husband_Of").to(g.V(addV24.id).next()).next()
    Edge71 = g.V(addV24.id).addE("Wife_Of").to(g.V(addV23.id).next()).next()
    Edge72 = g.V(addV23.id).addE("Father_Of").to(g.V(addV25.id).next()).next()
    Edge73 = g.V(addV24.id).addE("Mother_Of").to(g.V(addV25.id).next()).next()
    Edge74 = g.V(addV25.id).addE("Son_Of").to(g.V(addV23.id).next()).next()
    Edge75 = g.V(addV25.id).addE("Son_Of").to(g.V(addV24.id).next()).next()
    Edge76 = g.V(addV24.id).addE("Sister_Of").to(g.V(addV3.id).next()).next()
    Edge77 = g.V(addV3.id).addE("Brother_Of").to(g.V(addV24.id).next()).next()
    Edge78 = g.V(addV26.id).addE("Daughter_Of").to(g.V(addV23.id).next()).next()
    Edge79 = g.V(addV26.id).addE("Daughter_Of").to(g.V(addV24.id).next()).next()
    Edge80 = g.V(addV23.id).addE("Father_Of").to(g.V(addV26.id).next()).next()
    Edge81 = g.V(addV24.id).addE("Mother_Of").to(g.V(addV26.id).next()).next()

    Edge82 = g.V(addV25.id).addE("Husband_Of").to(g.V(addV27.id).next()).next()
    Edge83 = g.V(addV27.id).addE("Wife_Of").to(g.V(addV25.id).next()).next()
    Edge84 = g.V(addV25.id).addE("Father_Of").to(g.V(addV28.id).next()).next()
    Edge85 = g.V(addV27.id).addE("Mother_Of").to(g.V(addV28.id).next()).next()
    Edge86 = g.V(addV28.id).addE("Daughter_Of").to(g.V(addV25.id).next()).next()
    Edge87 = g.V(addV28.id).addE("Daughter_Of").to(g.V(addV27.id).next()).next()


    return json.dumps({'Message': 'Added all people and relations'}), 200, {
            'ContentType': 'application/json'}