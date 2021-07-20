import json
import os
from flask import Blueprint, request
from werkzeug.utils import secure_filename
from Tree.faces.recognition import recognize_person
from Tree import g

faces = Blueprint('faces', __name__)
ALLOWED_EXTENSIONS = {'txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif'}
filepath = os.path.abspath('Tree/faces/unknown')


def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@faces.route('/search_picture', methods=['POST'])
def picture_search():
    if 'image' not in request.files:
        return json.dumps({'Message': 'Picture not received/found'}), 404, {
            'ContentType': 'application/json'}
    search_image = request.files['image']
    if search_image.filename == '':
        return json.dumps({'Message': 'Filename is invalid.'}), 406, {
            'ContentType': 'application/json'}

    if request.headers['image-location'] is None:
        if search_image and allowed_file(search_image.filename):
            filename = secure_filename(search_image.filename)
            full_filepath = os.path.join(filepath, filename)
            search_image.save(full_filepath)
            response = recognize_person(full_filepath)
            if response == -1:
                return json.dumps({'Message': 'Person not recognized'}), 404, {
                    'ContentType': 'application/json'}
            if isinstance(response, list):
                return json.dumps({'Message': 'Multiple faces detected', 'Face location': response}), 404, {
                    'ContentType': 'application/json'}
            if response > 0:
                person = dict(g.V(response).elementMap('Firstname', 'Lastname', 'Gender'))
                return json.dumps({'Message': 'Person has been recognized', 'Person': person}), 200, {
                    'ContentType': 'application/json'}
        else:
            json.dumps({'Message': 'Corrupted Image or unaccepted filetype detected'}), 400, {
                'ContentType': 'application/json'}
    else:
        # User has made a choice about which face should be searched.
        v_id = recognize_person(search_image, face_location=request.headers['image-location'])
        if v_id > 0:
            person = dict(g.V(v_id).elementMap('Firstname', 'Lastname', 'Gender'))
            return json.dumps({'Message': 'Person has been recognized', 'Person': person}), 200, {
                'ContentType': 'application/json'}
        else:
            return json.dumps({'Message': 'Person not recognized'}), 404, {
                'ContentType': 'application/json'}


@faces.route('/relate/picture', methods=['POST'])
def relate():
    pass
