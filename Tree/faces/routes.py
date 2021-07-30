import json
import os
import base64
import uuid

from flask import Blueprint, request, send_file, current_app
from werkzeug.utils import secure_filename

from Tree.Utils.ImageReducer import reduce
from Tree.faces.recognition import recognize_person, relate_person_to_face, draw_boxes
from Tree import g
from Tree.model.Person import Person
from Tree.people.people_Service import retrieve_person_service
from Tree.relations.gremlin_Interface import get_all_relations

faces = Blueprint('faces', __name__, url_prefix='/picture')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'tiff'}
file_path_dictionary = {}


def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@faces.route('/search', methods=['POST'])
def picture_search():
    filepath = current_app.config['UPLOAD_IMAGE_PATH']

    def send_response(response):
        if response == -1:
            return json.dumps({'Message': 'Selected person is not recognized'}), 404, {
                'ContentType': 'application/json'}
        if response > 0:
            relations, person_dictionary = retrieve_person_service(response)
            return json.dumps({'Message': 'Person found',
                               'Data': json.loads(
                                   json.dumps(Person.createPersonObject(person_dictionary),
                                              default=lambda o: o.__dict__)),
                               'Relations': relations}), 200, \
                   {'ContentType': 'application/json'}

    if 'image' not in request.files:
        if 'HTTP_TASK_ID' in request.headers.environ and 'HTTP_FACE_LOCATION' in request.headers.environ:
            response = recognize_person(file_path_dictionary[request.headers.environ['HTTP_TASK_ID']],
                                        face_location=eval(request.headers.environ['HTTP_FACE_LOCATION']))
            return send_response(response)
        else:
            return json.dumps({'Message': 'Picture not received/found'}), 404, {
                'ContentType': 'application/json'}
    else:
        search_image = request.files['image']
        if search_image and allowed_file(search_image.filename) and search_image.filename != '':
            filename = secure_filename(search_image.filename)
            full_filepath = os.path.join(filepath, filename)
            search_image.save(full_filepath)
            reduce(full_filepath)
        else:
            return json.dumps({'Message': 'Filename/Extension is invalid.'}), 406, {
                'ContentType': 'application/json'}

    response = recognize_person(img_path=full_filepath)
    if isinstance(response, tuple) and isinstance(response[1], list):
        random_value = str(uuid.uuid4())
        file_path_dictionary.update({random_value: full_filepath})
        return json.dumps({'Message': 'Multiple people detected', 'Image': str(response[0]),
                           'Face-locations': response[1], 'Task-id': random_value}), 200, {
                   'ContentType': 'application/json'
               }

    return send_response(response)


@faces.route('/recognize', methods=['POST'])
def recognize():
    filepath = current_app.config['UPLOAD_IMAGE_PATH']
    if 'image' in request.files:

        source_image = request.files['image']

        if source_image and allowed_file(source_image.filename):
            filename = secure_filename(source_image.filename)
            full_filepath = os.path.join(filepath, filename)
            source_image.save(full_filepath)
            reduce(full_filepath)
            value, file, image, face_locations = draw_boxes(full_filepath,encoded_Image=True,numbering=True)
            file_path_dictionary.update({str(value): full_filepath})
            return json.dumps({'Message': 'Multiple people detected', 'Image': str(image),
                               'Face-locations': face_locations, 'Task-id': str(value)}), 200, {
                       'ContentType': 'application/json'
                   }

        else:
            return json.dumps({'Message': 'Filename is invalid.'}), 406, {
                'ContentType': 'application/json'}
    else:
        try:
            filename = file_path_dictionary[request.headers.environ['HTTP_TASK_ID']]
            v_map = eval(request.headers.environ['HTTP_VERTEX_ID_MAP'])
            vertex_map = {}
            for i,item in enumerate(v_map):
                try:
                    if i%5 == 0:
                        vertex_map.update({(v_map[i],v_map[i+1],v_map[i+2],v_map[i+3]):v_map[i+4]})
                except:
                    break
            relate_person_to_face(image_path=filename, vertex_id_map=vertex_map,
                                  file_to_be_deleted=current_app.config['UPLOAD_IMAGE_PATH']+'/'+str(request.headers.environ['HTTP_TASK_ID'])+'.jpg')
            return json.dumps({'Message': 'Mapped the picture to faces'}), 200, {
                'ContentType': 'application/json'}
        except Exception as e:
            print(e)
            return json.dumps({'Message': 'Picture not received/found'}), 404, {
                'ContentType': 'application/json'}


@faces.route('/relate', methods=['POST'])
def relate():
    filepath = current_app.config['UPLOAD_IMAGE_PATH']

    if 'image' in request.files:
        source_image = request.files['image']

        if source_image and allowed_file(source_image.filename):
            filename = secure_filename(source_image.filename)
            full_filepath = os.path.join(filepath, filename)
            source_image.save(full_filepath)
            reduce(full_filepath)
            value, file, image, known_face_locations = draw_boxes(full_filepath,encoded_Image=True)
            file_path_dictionary.update({str(value):full_filepath})
            return json.dumps({'Message': 'Select the faces to relate to this person', 'Image': str(image),
                               'Face-locations': known_face_locations, 'Task-id': str(value)}), 200, {
                       'ContentType': 'application/json'
                   }
        else:
            return json.dumps({'Message': 'Filename is invalid.'}), 406, {
                'ContentType': 'application/json'}

    else:
        try:
            filename = file_path_dictionary[request.headers.environ['HTTP_TASK_ID']]
            relatives = get_all_relations(start_id=eval(request.headers.environ['HTTP_START_ID']),
                                          end_ids=eval(request.headers.environ['HTTP_END_IDS']))
            _, _, image, _ = draw_boxes(img_path=filename, relatives_dictionary=relatives,encoded_Image=True)
            return json.dumps({'Message': 'All selections related', 'Image': str(image)}), 200, {
                       'ContentType': 'application/json'
                   }
        except Exception as e:
            print(e)
            return json.dumps({'Message': 'Image not found.'}), 404, {
                'ContentType': 'application/json'}