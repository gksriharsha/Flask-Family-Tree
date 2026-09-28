#!/usr/bin/env python3
"""Fail when a CSS class is used both as a block and as a variant on another block.

This catches a bug that is invisible in review and obvious on screen. `.pill.ways` and a
separate `.ways` panel both matched `<span class="pill ways">`, so the panel's
`margin-top:18px` and border landed on a chip and made it a different height from its
neighbours. The same collision put the top bar's `height:60px`, background and border-bottom
onto `<div class="genrow top">`.

The convention this enforces: a block is a plain class (`.pill`, `.ways`), and a variant or
state is prefixed `is-` (`.pill.is-rel`, `.genrow.is-first`). A prefixed variant can never
collide with a block name.

Two source shapes are scanned:

  * the design artboards under ``design/*.dc.html``, where the CSS lives in a ``<style>`` block
    inside the ``<helmet>`` (the runtime never sees it, but it is the reference the shipped app
    is judged against); and
  * the shipped web stylesheet(s) under ``web/src/**/*.css``, which is what the browser
    actually loads. The class convention has to hold there too, or the collision the artboards
    are kept clean of simply reappears in the file that ships.
"""

import collections
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent


def analyse(css):
    """Return (blocks, variants) for a blob of CSS.

    ``blocks`` is the set of names used as a bare single-class selector (``.pill``); ``variants``
    maps a name used as the second class of a compound selector (``.pill.ways`` -> ``ways``) to
    the set of blocks it qualifies. A name appearing in both is the collision this file exists
    to catch.
    """
    blocks = set()
    variants = collections.defaultdict(set)
    for selector in re.findall(r'([.#][^{@}]+?)\s*\{', css):
        for part in (p.strip() for p in selector.split(',')):
            single = re.fullmatch(r'\.([a-z0-9-]+)', part)
            if single:
                blocks.add(single.group(1))
            pair = re.fullmatch(r'\.([a-z0-9-]+)\.([a-z0-9-]+)', part)
            if pair:
                variants[pair.group(2)].add(pair.group(1))
    return blocks, variants


def report(path, blocks, variants):
    """The collision lines for one file, empty when it is clean."""
    found = []
    for name in sorted(set(variants) & blocks):
        owners = ', '.join('.' + b for b in sorted(variants[name]))
        found.append(f'{path.name}: .{name} is a block AND a variant on {owners} '
                     f'— rename the variant to .is-{name}')
    return found


def collisions(path):
    """Artboard: pull the CSS out of the <style> block inside <helmet>."""
    source = path.read_text(encoding='utf-8')
    head = source.split('</helmet>')[0]
    css = '\n'.join(re.findall(r'<style>(.*?)</style>', head, re.S))
    return report(path, *analyse(css))


def collisions_css(path):
    """Web stylesheet: the whole file is CSS; strip /* */ comments first so a commented-out
    selector cannot register as a block or variant."""
    css = re.sub(r'/\*.*?\*/', '', path.read_text(encoding='utf-8'), flags=re.S)
    return report(path, *analyse(css))


def main():
    artboards = sorted((ROOT / 'design').glob('*.dc.html'))
    web_css = sorted((ROOT / 'web' / 'src').rglob('*.css'))
    if not artboards and not web_css:
        print('no .dc.html artboards or web/src CSS found', file=sys.stderr)
        return 0

    found = [line for path in artboards for line in collisions(path)]
    found += [line for path in web_css for line in collisions_css(path)]

    for line in found:
        print('error: ' + line, file=sys.stderr)
    if found:
        print(f'\n{len(found)} class collision(s).', file=sys.stderr)
        return 1
    print(f'OK: no block/variant class collisions in '
          f'{len(artboards)} artboards and {len(web_css)} web stylesheet(s).')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
