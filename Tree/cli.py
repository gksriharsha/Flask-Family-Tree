"""Maintenance commands.

    python -m Tree.cli tree        # create a tree and choose where its files live
    python -m Tree.cli export      # write a copy in another format
    python -m Tree.cli import      # read a GEDCOM or GEDZIP file in
    python -m Tree.cli schema      # declare property keys, labels and indexes
    python -m Tree.cli seed        # create the demo family
    python -m Tree.cli reset       # drop every vertex (refuses without --yes)
    python -m Tree.cli check       # report connectivity and counts

The destructive operations used to be HTTP endpoints: ``GET /spoc`` dropped the whole graph and
reseeded it, and ``DELETE /delete/nodes/all`` wiped it outright -- both unauthenticated. Neither
belongs on the network.
"""

import argparse
import os
import sys


def _traversal():
    from Tree import g
    return g


def cmd_tree(args):
    from Tree.gedcom.store import create_tree, load_settings

    g = _traversal()
    if args.show:
        settings = load_settings(g)
        if settings is None:
            print('No tree yet. Create one with:  python -m Tree.cli tree --name ... --at ...')
            return 1
        print(f'{settings.name}\n  files: {settings.location}\n  gedcom: {settings.gedcom}')
        return 0
    if not args.name or not args.at:
        print('Both --name and --at are required.', file=sys.stderr)
        return 2
    settings = create_tree(g, args.name, args.at)
    print(f'Created {settings.name!r}. Its files live in {settings.location}.')
    return 0


def cmd_export(args):
    from Tree.gedcom.model import VERSION_7, VERSION_551
    from Tree.gedcom.store import export, export_as

    g = _traversal()
    version = {'gedcom7': VERSION_7, 'gedcom551': VERSION_551, 'gedzip': 'gedzip'}[args.format]
    written = export(g) if args.format == 'current' else export_as(g, version)
    print(f'Wrote {written} ({written.stat().st_size} bytes).')
    return 0


def cmd_import(args):
    from Tree.gedcom.store import export, import_file

    g = _traversal()
    summary = import_file(g, args.path)
    print(f"Imported {summary['people']} people, {summary['parentLinks']} parent links, "
          f"{summary['unions']} unions.")
    try:
        export(g)
    except Exception as exc:
        print(f'Imported, but could not refresh the tree files: {exc}', file=sys.stderr)
    return 0


def cmd_schema(_args):
    from Tree import message_serializer
    from Tree.config import Configuration
    from Tree.schema import apply_schema

    created, conflicts = apply_schema(
        Configuration.GREMLIN_DATABASE_URI,
        Configuration.GREMLIN_TRAVERSAL_SOURCE,
        wire=message_serializer(Configuration.GREMLIN_SERIALIZER),
    )
    for item in created:
        print(f'  created {item}')
    print(f'Schema applied: {len(created)} object(s) created.')
    if conflicts:
        print('\nCardinality conflicts (JanusGraph cannot alter these in place):', file=sys.stderr)
        for item in conflicts:
            print(f'  {item}', file=sys.stderr)
        print('On a development graph: `reset --yes` then `schema`. On a real one, migrate the '
              'key.', file=sys.stderr)
        return 1
    return 0


def cmd_seed(_args):
    from Tree import seed as seed_module
    ids = seed_module.seed(_traversal())
    print(f'Seeded {len(ids)} people and {len(seed_module.EDGES)} edges.')
    return 0


def cmd_reset(args):
    if not args.yes:
        print('Refusing to drop every vertex without --yes.', file=sys.stderr)
        return 2
    if os.environ.get('ENV', '').lower() in {'prod', 'production'}:
        print('Refusing to reset in a production environment.', file=sys.stderr)
        return 2
    from Tree import seed as seed_module
    seed_module.reset(_traversal())
    print('Dropped every vertex.')
    return 0


def cmd_check(_args):
    g = _traversal()
    people = g.V().hasLabel('Person').count().next()
    locations = g.V().hasLabel('Location').count().next()
    print(f'Connected. Person vertices: {people}. Location vertices: {locations}.')
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(prog='python -m Tree.cli')
    sub = parser.add_subparsers(dest='command', required=True)

    tree = sub.add_parser('tree', help='create a tree and choose where its files live')
    tree.add_argument('--name', help='what to call the tree')
    tree.add_argument('--at', help='the folder its files should live in')
    tree.add_argument('--show', action='store_true', help='show the current tree instead')
    tree.set_defaults(func=cmd_tree)

    exporter = sub.add_parser('export', help='write a copy in another format')
    exporter.add_argument('--format', default='current',
                          choices=['current', 'gedcom7', 'gedcom551', 'gedzip'],
                          help='current refreshes the tree\'s own file; the rest go to exports/')
    exporter.set_defaults(func=cmd_export)

    importer = sub.add_parser('import', help='read a GEDCOM or GEDZIP file in')
    importer.add_argument('path', help='the .ged or .gdz file to read')
    importer.set_defaults(func=cmd_import)

    sub.add_parser('schema', help='declare property keys, labels and indexes') \
        .set_defaults(func=cmd_schema)

    sub.add_parser('seed', help='create the demo family').set_defaults(func=cmd_seed)

    reset = sub.add_parser('reset', help='drop every vertex')
    reset.add_argument('--yes', action='store_true', help='confirm the destructive operation')
    reset.set_defaults(func=cmd_reset)

    sub.add_parser('check', help='report connectivity and counts').set_defaults(func=cmd_check)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == '__main__':
    raise SystemExit(main())
