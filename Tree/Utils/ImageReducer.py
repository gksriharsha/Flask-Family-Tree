from PIL import Image
from Tree.config import Configuration

def reduce(path):
    fixed_height = Configuration.RESIZED_IMAGE_HEIGHT
    raw_img = Image.open(path)
    width = int(float(raw_img.size[0]) * float(fixed_height / float(raw_img.size[1])))
    raw_img = raw_img.resize((width, fixed_height), Image.ANTIALIAS)
    raw_img.save(path)
