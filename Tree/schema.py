"""Apply the JanusGraph schema declaration in schema.groovy."""

import logging
from pathlib import Path

from gremlin_python.driver import client

log = logging.getLogger(__name__)

SCHEMA_PATH = Path(__file__).resolve().parent.parent / 'schema.groovy'


def apply_schema(uri, traversal_source, wire=None, timeout_ms=60000, script_path=SCHEMA_PATH):
    """Declare property keys, labels and indexes. Idempotent.

    Returns ``(created, conflicts)``. A conflict means a key already exists with a different
    cardinality, which JanusGraph cannot alter in place -- so it is reported rather than
    silently ignored.
    """
    path = Path(script_path)
    if not path.is_file():
        raise FileNotFoundError(f'Schema script not found at {path}')

    cli = client.Client(uri, traversal_source,
                        **({'message_serializer': wire} if wire else {}))
    try:
        rows = cli.submit(
            path.read_text(encoding='utf-8'),
            request_options={'evaluationTimeout': timeout_ms},
        ).all().result()
    finally:
        cli.close()

    result = rows[0] if rows else {}
    created = list(result.get('created', []))
    conflicts = list(result.get('conflicts', []))
    log.info('Schema applied: %d objects created, %d conflicts.', len(created), len(conflicts))
    return created, conflicts
