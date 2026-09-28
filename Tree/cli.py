"""Maintenance commands.

    python -m Tree.cli tree        # create a tree and choose where its files live
    python -m Tree.cli import      # read a GEDCOM or GEDZIP file into the database
    python -m Tree.cli export      # write a copy in another format
    python -m Tree.cli seed        # create the 29-person demo family in the database
    python -m Tree.cli reset       # delete the database file (refuses without --yes)
    python -m Tree.cli check       # report the database path, schema version and counts

The destructive operations used to be HTTP endpoints: ``GET /spoc`` dropped the whole graph and
reseeded it, and ``DELETE /delete/nodes/all`` wiped it outright -- both unauthenticated. Neither
belongs on the network.
"""

import argparse
import os
import sys
from pathlib import Path


def _database_path() -> Path:
    from Tree.config import Configuration
    return Path(Configuration.DATABASE_PATH)


def _connect():
    """Open the configured database (creating it and its folder if missing)."""
    from Tree.storage import open_database
    path = _database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    return open_database(str(path))


def cmd_tree(args):
    from Tree.gedcom.store import create_tree, load_settings

    conn = _connect()
    if args.show:
        settings = load_settings(conn)
        if settings is None:
            print('No tree yet. Create one with:  python -m Tree.cli tree --name ... --at ...')
            return 1
        print(f'{settings.name}\n  files: {settings.location}\n  gedcom: {settings.gedcom}')
        return 0
    if not args.name or not args.at:
        print('Both --name and --at are required.', file=sys.stderr)
        return 2
    settings = create_tree(conn, args.name, args.at)
    print(f'Created {settings.name!r}. Its files live in {settings.location}.')
    return 0


def cmd_export(args):
    from Tree.gedcom.model import VERSION_7, VERSION_551
    from Tree.gedcom.store import export, export_as

    conn = _connect()
    version = {'gedcom7': VERSION_7, 'gedcom551': VERSION_551, 'gedzip': 'gedzip'}[args.format]
    written = export(conn) if args.format == 'current' else export_as(conn, version)
    print(f'Wrote {written} ({written.stat().st_size} bytes).')
    return 0


def cmd_import(args):
    from Tree.gedcom.store import export, import_file

    conn = _connect()
    summary = import_file(conn, args.path)
    print(f"Imported {summary['people']} people, {summary['parentLinks']} parent links, "
          f"{summary['unions']} unions.")
    try:
        export(conn)
    except Exception as exc:
        print(f'Imported, but could not refresh the tree files: {exc}', file=sys.stderr)
    return 0


def cmd_seed(_args):
    from Tree import seed as seed_module

    ids = seed_module.seed(_connect())
    print(f'Seeded {len(ids)} people and {len(seed_module.EDGES)} edges.')
    return 0


def cmd_reset(args):
    if not args.yes:
        print('Refusing to delete the database without --yes.', file=sys.stderr)
        return 2
    if os.environ.get('ENV', '').lower() in {'prod', 'production'}:
        print('Refusing to reset in a production environment.', file=sys.stderr)
        return 2
    path = _database_path()
    removed = 0
    # WAL and shared-memory sidecars are part of the database; remove them with the main file.
    for candidate in (path, path.with_name(path.name + '-wal'),
                      path.with_name(path.name + '-shm')):
        if candidate.exists():
            candidate.unlink()
            removed += 1
    if removed:
        print(f'Deleted the database at {path}.')
    else:
        print(f'No database file at {path}; nothing to delete.')
    return 0


def cmd_check(_args):
    from Tree.storage import SCHEMA_VERSION, count_people

    path = _database_path()
    if not path.exists():
        print(f'No database at {path}. Create a tree or seed one first.')
        return 1
    conn = _connect()
    people = count_people(conn)
    version = conn.execute('SELECT MAX(version) AS v FROM schema_version').fetchone()['v']
    print(f'Database: {path}\n  schema version: {version} (code expects {SCHEMA_VERSION})\n'
          f'  people: {people}')
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

    importer = sub.add_parser('import', help='read a GEDCOM or GEDZIP file into the database')
    importer.add_argument('path', help='the .ged or .gdz file to read')
    importer.set_defaults(func=cmd_import)

    sub.add_parser('seed', help='create the demo family').set_defaults(func=cmd_seed)

    reset = sub.add_parser('reset', help='delete the database file')
    reset.add_argument('--yes', action='store_true', help='confirm the destructive operation')
    reset.set_defaults(func=cmd_reset)

    sub.add_parser('check', help='report the database path, schema version and counts') \
        .set_defaults(func=cmd_check)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == '__main__':
    raise SystemExit(main())
