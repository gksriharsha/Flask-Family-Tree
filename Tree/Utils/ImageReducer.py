from PIL import Image


def reduce(path):
    fixed_height = 1000
    raw_img = Image.open(path)
    width = int(float(raw_img.size[0]) * float(fixed_height / float(raw_img.size[1])))
    raw_img = raw_img.resize((width, fixed_height), Image.ANTIALIAS)
    raw_img.save(path)
