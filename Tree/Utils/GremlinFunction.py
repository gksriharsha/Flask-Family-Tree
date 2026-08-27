"""Loader for the server-side Groovy helper functions in functions.groovy."""

import logging
from pathlib import Path

from gremlin_python.driver import client

log = logging.getLogger(__name__)


class GroovyInjectionError(RuntimeError):
    """Raised when the helper script cannot be loaded into Gremlin Server."""


def inject_functions(uri, traversal_source, script_path, timeout_ms=10000, wire=None):
    """Submit functions.groovy to Gremlin Server.

    Differences from the original ``injectFunctions``:

    * The path is absolute and package-relative, so the process no longer has to be launched
      from the repository root.
    * The file handle is closed (``with``), and the client is closed in a ``finally``.
    * Failure raises instead of calling ``sys.exit(1)``, which under gunicorn respawn-looped.
    * The original success test was ``if results[0] is None: return`` followed by an exit on
      every other outcome -- inverted logic that also raised IndexError on an empty result.
    """
    path = Path(script_path)
    if not path.is_file():
        raise GroovyInjectionError(f'Groovy helper script not found at {path}')

    script = path.read_text(encoding='utf-8')

    cli = client.Client(uri, traversal_source,
                        **({'message_serializer': wire} if wire else {}))
    try:
        cli.submit(script, request_options={'evaluationTimeout': timeout_ms}).all().result()
    except Exception as exc:
        raise GroovyInjectionError(f'{exc.__class__.__name__}: {exc}') from exc
    finally:
        try:
            cli.close()
        except Exception:
            log.debug('Ignoring error while closing the injection client.', exc_info=True)
    log.info('Injected %s (%d bytes) into Gremlin Server.', path.name, len(script))
