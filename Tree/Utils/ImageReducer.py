"""Downscale an uploaded image in place."""

from PIL import Image


def reduce(path, fixed_height=800):
    """Resize so the image is ``fixed_height`` tall, preserving aspect ratio.

    ``Image.ANTIALIAS`` was removed in Pillow 10.0, so this raised AttributeError on the first
    upload with any current Pillow -- which meant every image endpoint 500'd before reaching
    any of its own logic.
    """
    with Image.open(path) as raw:
        raw.load()
        if raw.height == 0:
            return
        width = max(1, int(raw.width * (fixed_height / raw.height)))
        resized = raw.resize((width, fixed_height), Image.Resampling.LANCZOS)
        if resized.mode not in ('RGB', 'L'):
            resized = resized.convert('RGB')
        resized.save(path)
