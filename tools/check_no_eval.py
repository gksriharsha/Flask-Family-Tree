#!/usr/bin/env python3
"""Fail if `eval` or `exec` is actually *called* anywhere in the application.

The single highest-severity defect in this codebase was ``eval()`` on request bodies, URL path
segments, HTTP headers and file contents -- 31 call sites, any one of which was unauthenticated
remote code execution. This gate is what stops it coming back.

It parses the source rather than grepping, so the many comments and docstrings that *describe*
the old behaviour do not trip it.
"""

import ast
import pathlib
import sys

BANNED = {'eval', 'exec', 'literal_eval_unsafe'}
ROOT = pathlib.Path(__file__).resolve().parent.parent


def offenders(paths):
    found = []
    for path in paths:
        tree = ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = getattr(func, 'id', None) or getattr(func, 'attr', None)
            if name in BANNED:
                found.append(f'{path.relative_to(ROOT)}:{node.lineno}: calls {name}()')
    return found


def main():
    targets = sorted((ROOT / 'Tree').rglob('*.py'))
    targets += [p for p in (ROOT / 'wsgi.py', ROOT / 'TreeServer.py') if p.exists()]
    found = offenders(targets)
    for line in found:
        print(f'error: {line}', file=sys.stderr)
    if found:
        print(f'\n{len(found)} banned call(s) found.', file=sys.stderr)
        return 1
    print(f'OK: no eval/exec calls in {len(targets)} files.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
