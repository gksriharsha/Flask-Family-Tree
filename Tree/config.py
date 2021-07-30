import os


class Configuration:
    FONT_PATH = "~/usr/share/fonts/truetype/freefont/FreeMonoBold.ttf"
    FONT_SIZE = 14
    UPLOAD_IMAGE_PATH = os.path.abspath('Tree/faces/unknown')
    FACES_JSON_PATH = os.path.abspath('Tree/faces/known/faces.json')
    GROOVY_FUNCTIONS_PATH = os.path.abspath('config.py')
    GREMLIN_DATABASE_URI = 'ws://localhost:8182/gremlin'
    ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'tiff'}
    RESIZED_IMAGE_HEIGHT = 800



