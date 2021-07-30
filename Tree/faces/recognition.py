import base64
import io
import math
import uuid
import numpy as np
import face_recognition as FR
import json, os
import textwrap
import numpy
from ttictoc import tic, toc
from PIL import Image, ImageDraw, ImageFont
from flask import current_app
from Tree import g


def number_of_faces(img_path):
    image = FR.load_image_file(img_path)
    encodings = FR.face_encodings(image)
    if not encodings:
        return 0
    return len(FR.face_encodings(image))


def open_encodings_dict():
    dictionary = {}
    if os.path.exists(current_app.config['FACES_JSON_PATH']):
        with open(current_app.config['FACES_JSON_PATH'], 'r') as json_file:
            d = json.load(json_file)
            dictionary = {eval(k): v for (k, v) in d.items()}
    return dictionary


def save_encodings_dict(face_encoding_dictionary):
    if os.path.exists(current_app.config['FACES_JSON_PATH']):
        for item in open_encodings_dict().items():
            face_encoding_dictionary.update({item[0]:item[1]})
        with open(current_app.config['FACES_JSON_PATH'], 'w') as json_file:
            face_encoding_dictionary = {str(k): v for (k, v) in face_encoding_dictionary.items()}
            json.dump(face_encoding_dictionary, json_file, indent=4)
    else:
        with open(current_app.config['FACES_JSON_PATH'], 'w+') as json_file:
            face_encoding_dictionary = {str(k): v for (k, v) in face_encoding_dictionary.items()}
            json.dump(face_encoding_dictionary, json_file, indent=4)


def draw_boxes(img_path, relatives_dictionary=None,encoded_Image=False,numbering=False ):
    img = FR.load_image_file(img_path)

    face_locations = FR.face_locations(img)
    face_encodings = FR.face_encodings(img, face_locations)

    pil_image = Image.fromarray(img)

    draw = ImageDraw.Draw(pil_image)

    font = ImageFont.truetype(current_app.config['FONT_PATH'], current_app.config['FONT_SIZE'])
    unknown_face_locations = []
    known_face_location_tuples = []
    face_number = 0
    for i, ((top, right, bottom, left), face_encoding) in enumerate(zip(face_locations, face_encodings)):

        vertex_id = recognize_encoding(face_encoding)

        if vertex_id != -1:
            if relatives_dictionary is None:
                i = g.V(vertex_id).values('Firstname').next() + ' ' + g.V(vertex_id).values('Lastname').next()
                known_face_location_tuples.append(((top, right, bottom, left), vertex_id, i))
            else:
                if vertex_id in relatives_dictionary.keys():
                    i = g.V(vertex_id).values('Nickname')
                    if i.hasNext():
                        i = i.next() + '-' + relatives_dictionary[vertex_id]
                    else:
                        try:
                            i = relatives_dictionary[vertex_id]
                        except KeyError:
                            i = ''
                else:
                    i = ''
        else:
            unknown_face_locations.append([(top, right, bottom, left), face_number+1])

        if i != '':
            if isinstance(i,int):
                if not numbering:
                    continue
                else:
                    face_number = face_number + 1
                    i = face_number
            if i == 'Me':
                draw.rectangle(((left - 15, top - 15), (right + 15, bottom + 15)), outline=(95, 31, 211))
            else:
                draw.rectangle(((left - 15, top - 15), (right + 15, bottom + 15)), outline=(255, 255, 0))

            text_width, text_height = draw.textsize(str(i))
            lines = textwrap.wrap(str(i), width=math.floor((right - left + 30) / 8))
            offset = 0
            for line in lines:
                if i == 'Me':
                    draw.rectangle(
                        ((left - 15, bottom + 15 + offset - text_height - 10 + 5), (right + 15, bottom + 25 + offset)),
                        fill=(95,31,211),
                        outline=(95,31,211))
                    draw.text((left - 15 + 6, bottom + 15 - text_height - 5 + offset), line, fill=(255, 255, 255),
                              font=font)
                    offset += font.getsize(line)[1]
                else:
                    draw.rectangle(
                        ((left - 15, bottom + 15 + offset - text_height - 10 + 5), (right + 15, bottom + 25 + offset)),
                        fill=(255, 255, 0),
                        outline=(255, 255, 0))
                    draw.text((left - 15 + 6, bottom + 15 - text_height - 5 + offset), line, fill=(0, 0, 0),
                              font=font)
                    offset += font.getsize(line)[1]

    del draw
    random_value = uuid.uuid4()
    filename = current_app.config['UPLOAD_IMAGE_PATH'] + f'/{random_value}.jpg'
    pil_image.save(os.path.abspath(filename))
    pil_image.close()
    if encoded_Image:
        img2 = Image.fromarray(FR.load_image_file(filename).astype('uint8'))
        rawBytes = io.BytesIO()
        img2.save(rawBytes, "JPEG")
        rawBytes.seek(0)
        img_base64 = base64.b64encode(rawBytes.read())
        if numbering:
            return random_value, filename, img_base64, unknown_face_locations
        else:
            return random_value, filename, img_base64, known_face_location_tuples


def relate_person_to_face(image_path=None, vertex_id_map=None, file_to_be_deleted=None):
    if file_to_be_deleted is not None:
        os.remove(file_to_be_deleted)
    face_locations = FR.face_locations(FR.load_image_file(image_path))
    face_encodings = FR.face_encodings(FR.load_image_file(image_path))
    face_encoding_dict = open_encodings_dict()

    for location, encoding in zip(face_locations, face_encodings):
        if location in vertex_id_map.keys():
            face_encoding_dict.update({tuple(encoding): vertex_id_map[location]})
    save_encodings_dict(face_encoding_dict)


def recognize_encoding(encoding):
    dictionary = open_encodings_dict()
    distances = FR.face_distance([k for (k, v) in dictionary.items()], numpy.asarray(encoding))
    if distances.size != 0:
        if np.min(distances) < 0.6:
            return list(dictionary.values())[np.argmin(distances)]

    return -1


def recognize_person(img_path, face_location=None):  ## Face Search
    face_encoding_dictionary = {}
    num_faces = number_of_faces(img_path)
    img = FR.load_image_file(img_path)

    def recognize_core(face_encoding):
        vertex_id = -1
        if os.path.exists(current_app.config['FACES_JSON_PATH']):
            vertex_id = recognize_encoding(face_encoding)
            if vertex_id != -1:
                face_encoding_dictionary.update({face_encoding: vertex_id})
                save_encodings_dict(face_encoding_dictionary)
        return vertex_id

    if num_faces == 1 and face_location is None:
        face_enc = tuple(FR.face_encodings(img)[0])
        v_id = recognize_core(face_enc)
        return v_id
    elif face_location is None:
        img2 = Image.fromarray(img.astype('uint8'))
        rawBytes = io.BytesIO()
        img2.save(rawBytes,"JPEG")
        rawBytes.seek(0)
        img_base64 = base64.b64encode(rawBytes.read())
        return img_base64, FR.face_locations(img)
    else:
        locations = FR.face_locations(img)
        encodings = FR.face_encodings(img)
        for location, encoding in zip(locations, encodings):
            if location == tuple(face_location):
                v_id = recognize_core(tuple(encoding))
                return v_id


if __name__ == '__main__':
    from Tree.Utils.ImageReducer import reduce

    reduce('../people/faces/pending/Picture.JPG')
    tic()
    print(number_of_faces('../people/faces/pending/Picture.JPG'))
    print(toc())
