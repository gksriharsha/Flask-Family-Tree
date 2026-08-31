"""Render the app icon to PNG from the same geometry as web/public/favicon.svg.

An SVG favicon covers current browsers, but Safari's pinned tabs and iOS home-screen icons
still want raster, and there is no SVG rasteriser on this machine. Rather than commit opaque
binaries, the shapes are drawn here from the same numbers the SVG uses: change one, run this,
and the PNGs follow.

    python -m tools.make_icons

Curves are sampled and filled as polygons on a canvas 32x larger than the target, then
downsampled -- which is what gives the edges their antialiasing, since Pillow's own drawing
is aliased.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent.parent / 'web' / 'public'

#: The design grid. Every coordinate below is in these units, matching the SVG's viewBox.
GRID = 32
#: Supersampling factor. 32 gives a 1024px working canvas for a 32-unit grid.
SS = 32

TILE = '#3F6D14'      # olive: the app's primary
STEM = '#EFF1EA'      # paper: stem and upper leaf
LEAF = '#7FA352'      # olive-line: the lower leaf, as in the top-bar mark

#: The glyph is scaled about this point, exactly as the SVG's transform does.
PIVOT = (16.0, 16.6)
SCALE = 0.88

STEM_WIDTH = 3.4
STEM_TOP = (16.0, 14.4)
STEM_BOTTOM = (16.0, 26.5)

#: Each leaf is two cubic segments: (start, c1, c2, end) pairs forming a closed shape.
UPPER_LEAF = [
    ((16.0, 15.1), (16.0, 9.1), (11.3, 5.1), (6.0, 5.1)),
    ((6.0, 5.1), (6.0, 11.1), (10.0, 15.1), (16.0, 15.1)),
]
LOWER_LEAF = [
    ((16.0, 19.1), (16.0, 14.3), (19.7, 11.1), (24.0, 11.1)),
    ((24.0, 11.1), (24.0, 15.9), (20.8, 19.1), (16.0, 19.1)),
]


def _transform(point: tuple[float, float]) -> tuple[float, float]:
    """Apply the glyph's scale-about-pivot, then the supersample factor."""
    x = (point[0] - PIVOT[0]) * SCALE + PIVOT[0]
    y = (point[1] - PIVOT[1]) * SCALE + PIVOT[1]
    return x * SS, y * SS


def _cubic(p0, p1, p2, p3, steps: int = 96):
    """Sample one cubic bezier. Enough steps that the polygon edge is invisible once
    the canvas is downsampled."""
    for i in range(steps + 1):
        t = i / steps
        u = 1 - t
        yield (u * u * u * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t ** 3 * p3[0],
               u * u * u * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t ** 3 * p3[1])


def _leaf_points(segments) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    for seg in segments:
        points.extend(_transform(p) for p in _cubic(*seg))
    return points


def _draw_glyph(draw: ImageDraw.ImageDraw) -> None:
    # Stem: a stroked line with round caps is a capsule, so draw the bar and cap it.
    half = STEM_WIDTH * SCALE * SS / 2
    top, bottom = _transform(STEM_TOP), _transform(STEM_BOTTOM)
    draw.rectangle([top[0] - half, top[1], bottom[0] + half, bottom[1]], fill=STEM)
    for cx, cy in (top, bottom):
        draw.ellipse([cx - half, cy - half, cx + half, cy + half], fill=STEM)

    draw.polygon(_leaf_points(UPPER_LEAF), fill=STEM)
    draw.polygon(_leaf_points(LOWER_LEAF), fill=LEAF)


def render(size: int, rounded: bool) -> Image.Image:
    """One icon at `size` px. `rounded` is for browser tabs; iOS masks its own corners, so a
    home-screen icon must be full-bleed or it shows white wedges."""
    canvas = GRID * SS
    image = Image.new('RGBA', (canvas, canvas), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    if rounded:
        draw.rounded_rectangle([0, 0, canvas - 1, canvas - 1], radius=7 * SS, fill=TILE)
    else:
        draw.rectangle([0, 0, canvas - 1, canvas - 1], fill=TILE)
    _draw_glyph(draw)
    return image.resize((size, size), Image.LANCZOS)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    written = []
    for size in (16, 32, 180):
        # 180 is the iOS home-screen icon, which is masked by the system.
        image = render(size, rounded=size != 180)
        name = 'apple-touch-icon.png' if size == 180 else f'favicon-{size}.png'
        image.save(OUT / name)
        written.append(name)
    print('wrote ' + ', '.join(written) + f' to {OUT}')


if __name__ == '__main__':
    main()
