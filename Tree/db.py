"""The per-request database connection.

One SQLite file is one family tree, and one HTTP request gets one connection to it. The
connection is opened lazily the first time a request asks for it, cached on Flask's request
globals (:data:`flask.g`) so repeated calls within the request share it, and closed when the
request ends.

There is deliberately no module-level connection. The Gremlin version built a traversal source
at import time, which meant importing the package touched configuration and a network address;
here the file is opened per request, against ``app.config['DATABASE_PATH']``, so importing the
package does nothing and a test can point each request at its own scratch database.

SQLite connection objects are not safe to share across threads, and a threaded WSGI server runs
requests on different threads — so a shared connection would be a latent corruption bug. A
connection per request sidesteps that entirely: nothing is shared, and the file's own locking
(WAL, set in :func:`Tree.storage.open_database`) coordinates concurrent writers.
"""

from __future__ import annotations

import sqlite3

from flask import current_app, g

from Tree.storage import open_database


def get_db() -> sqlite3.Connection:
    """The current request's connection, opening one on first use.

    Cached on :data:`flask.g` so every call within a request returns the same connection, and
    closed by :func:`_close_db` when the request ends.
    """
    if 'db' not in g:
        g.db = open_database(str(current_app.config['DATABASE_PATH']))
    return g.db


def _close_db(_exc: BaseException | None = None) -> None:
    """Close the request's connection, if one was opened. Registered as a teardown."""
    db = g.pop('db', None)
    if db is not None:
        db.close()


def init_app(app) -> None:
    """Wire the teardown that closes the per-request connection."""
    app.teardown_appcontext(_close_db)
