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
"""

import collections
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent


def collisions(path):
    source = path.read_text(encoding='utf-8')
    head = source.split('</helmet>')[0]
    css = '\n'.join(re.findall(r'<style>(.*?)</style>', head, re.S))

    blocks = set()
    variants = collections.defaultdict(set)
    for selector in re.findall(r'^\s*([.#][^{@]+?)\s*\{', css, re.M):
        for part in (p.strip() for p in selector.split(',')):
            single = re.fullmatch(r'\.([a-z0-9-]+)', part)
            if single:
                blocks.add(single.group(1))
            pair = re.fullmatch(r'\.([a-z0-9-]+)\.([a-z0-9-]+)', part)
            if pair:
                variants[pair.group(2)].add(pair.group(1))

    found = []
    for name in sorted(set(variants) & blocks):
        owners = ', '.join('.' + b for b in sorted(variants[name]))
        found.append(f'{path.name}: .{name} is a block AND a variant on {owners} '
                     f'— rename the variant to .is-{name}')
    return found


def main():
    targets = sorted((ROOT / 'design').glob('*.dc.html'))
    if not targets:
        print('no .dc.html artboards found', file=sys.stderr)
        return 0
    found = [line for path in targets for line in collisions(path)]
    for line in found:
        print('error: ' + line, file=sys.stderr)
    if found:
        print(f'\n{len(found)} class collision(s).', file=sys.stderr)
        return 1
    print(f'OK: no block/variant class collisions in {len(targets)} artboards.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
