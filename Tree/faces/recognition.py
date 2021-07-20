import face_recognition as FR
import json, os
import textwrap
import numpy
from ttictoc import tic, toc
from PIL import Image, ImageDraw, ImageFont

from Tree import g


def number_of_faces(img_path):
    image = FR.load_image_file(img_path)
    encodings = FR.face_encodings(image)
    if not encodings:
        return 0
    return len(FR.face_encodings(image))


def open_encodings_dict():
    dictionary = {}
    if os.path.exists(os.path.abspath('Tree/people/faces/known/faces.json')):
        with open(os.path.abspath('Tree/people/faces/known/faces.json'), 'r') as json_file:
            d = json.load(json_file)
            dictionary = {eval(k): v for (k, v) in d.items()}
    return dictionary


def save_encodings_dict(face_encoding_dictionary):
    with open(os.path.abspath('Tree/people/faces/known/faces.json'), 'w+') as json_file:
        face_encoding_dictionary = {str(k): v for (k, v) in face_encoding_dictionary.items()}
        json.dump(face_encoding_dictionary, json_file)


def draw_boxes(img_path):
    img = FR.load_image_file(img_path)

    face_locations = FR.face_locations(img)
    face_encodings = FR.face_encodings(img, face_locations)

    pil_image = Image.fromarray(img)

    draw = ImageDraw.Draw(pil_image)

    font = ImageFont.truetype("~/usr/share/fonts/truetype/freefont/FreeMonoBold.ttf", 14)
    unknown_face_locations = []
    for i, ((top, right, bottom, left), face_encoding) in enumerate(zip(face_locations, face_encodings)):

        vertex_id = recognize_encoding(face_encoding)

        if vertex_id != -1:
            i = g.V(vertex_id).values('Firstname').next() + ' ' + g.V(vertex_id).values('Lastname').next()
        else:
            unknown_face_locations.append([(top, right, bottom, left), i])

        draw.rectangle(((left - 10, top - 10), (right + 10, bottom + 10)), outline=(255, 255, 0))

        text_width, text_height = draw.textsize(str(i))
        lines = textwrap.wrap(str(i), width=12)
        offset = 0
        for line in lines:
            draw.rectangle(
                ((left - 10, bottom + 10 + offset - text_height - 10 + 5), (right + 10, bottom + 20 + offset)),
                fill=(255, 255, 0),
                outline=(255, 255, 0))
            draw.text((left - 10 + 6, bottom + 10 - text_height - 5 + offset), line, fill=(0, 0, 0),
                      font=font)
            offset += font.getsize(line)[1]

    del draw

    pil_image.show()
    return unknown_face_locations


def relate_person_to_face(vertex_id=None, image_path=None, vertex_id_map={}):
    face_locations = FR.face_locations(FR.load_image_file(image_path))
    face_encodings = FR.face_encodings(FR.load_image_file(image_path))[0]
    face_encoding_dict = open_encodings_dict()

    if vertex_id_map is None:
        if len(face_encodings) == 1:
            for (k, v) in face_encoding_dict.items():
                if FR.compare_faces([k], face_encodings)[0]:
                    face_encoding_dict.update({k: vertex_id})
                    break
            face_encoding_dict.update({tuple(face_encodings): vertex_id})
            save_encodings_dict(face_encoding_dict)
        else:
            val = draw_boxes(image_path)
            return val
    else:
        for location, encoding in zip(face_locations, face_encodings):
            if location in vertex_id_map.keys():
                face_encoding_dict.update({tuple(encoding): vertex_id_map[location]})
        save_encodings_dict(face_encoding_dict)


def recognize_encoding(encoding):
    dictionary = open_encodings_dict()
    for (k, v) in dictionary.items():
        face_encoding_list = [list(k) for (i, j) in dictionary.items() if j == v]
        match = FR.compare_faces(face_encoding_list, numpy.asarray(encoding))
        if True in match:
            return v
    return -1


def recognize_person(img_path, face_location=None):  ## Face Search
    face_encoding_dictionary = {}
    num_faces = number_of_faces(img_path)
    img = FR.load_image_file(img_path)

    def recognize_core(face_encoding):
        vertex_id = -1
        if os.path.exists(os.path.abspath('Tree/people/faces/known/faces.json')):
            vertex_id = recognize_encoding(face_encoding)
            face_encoding_dictionary.update({face_encoding: vertex_id})
        else:
            face_encoding_dictionary.update({face_encoding: -1})
        save_encodings_dict(face_encoding_dictionary)
        return vertex_id

    if num_faces == 1 and face_location is None:
        face_enc = tuple(FR.face_encodings(img)[0])
        v_id = recognize_core(face_enc)
        return v_id
    elif face_location is None:
        return FR.face_locations(img)
    else:
        locations = FR.face_locations(img)
        encodings = FR.face_encodings(img)[0]
        for location, encoding in zip(locations, encodings):
            if location == face_location:
                v_id = recognize_core(encoding)
                return v_id


if __name__ == '__main__':
    from Tree.Utils.ImageReducer import reduce

    reduce('../people/faces/pending/Picture.JPG')
    tic()
    print(number_of_faces('../people/faces/pending/Picture.JPG'))
    print(toc())
