"""Application factory.

Changes from the original, all of them things that made the app unsafe or unstartable:

* No filesystem mutation at import time. The original deleted every file in the upload
  directory during ``import Tree``, which fired on each worker start, each ``flask shell``, and
  each test collection -- and, under the spawn start method, inside live requests in pool
  children.
* Gremlin script injection and directory creation happen in the factory, not at import.
* A failed injection leaves the app *degraded* rather than calling ``sys.exit(1)``, which under
  gunicorn was a respawn loop.
* CORS is registered inside the factory against an explicit origin allowlist. It used to be
  attached inside ``if __name__ == '__main__'``, so no WSGI deployment emitted CORS headers at
  all, and the allowlist was ``*``.
* A shared-secret gate stands in front of every route except the health probes.
"""

import hmac
import logging
import os
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory
from gremlin_python.driver import client, serializer
from gremlin_python.driver.driver_remote_connection import DriverRemoteConnection
from gremlin_python.process.graph_traversal import __
from gremlin_python.process.traversal import Cardinality, T, TextP
from gremlin_python.structure.graph import Graph

from Tree.config import Configuration as General_Configuration
from Tree.Utils.GremlinFunction import GroovyInjectionError, inject_functions
from Tree.Utils.http import ApiError

log = logging.getLogger(__name__)

# DriverRemoteConnection does not open a socket in its constructor -- it stores state and
# connects lazily on first write -- so building the traversal source at import time is cheap
# and does not require the database to be up.
def message_serializer(name):
    """Resolve the configured wire serializer. See Configuration.GREMLIN_SERIALIZER."""
    if str(name).lower() in ('graphbinary', 'binary'):
        return None                      # gremlinpython's default
    return serializer.GraphSONSerializersV3d0()


graph = Graph()
_serializer = message_serializer(General_Configuration.GREMLIN_SERIALIZER)
connection = DriverRemoteConnection(
    General_Configuration.GREMLIN_DATABASE_URI,
    General_Configuration.GREMLIN_TRAVERSAL_SOURCE,
    **({'message_serializer': _serializer} if _serializer is not None else {}),
)
g = graph.traversal().withRemote(connection)

__all__ = ['Cardinality', 'T', 'TextP', '__', 'client', 'connection', 'create_app', 'g', 'graph']

from Tree.api.routes import api  # noqa: E402  (needs `g` defined above)
from Tree.base.routes import base  # noqa: E402  (needs `g` defined above)
from Tree.location.routes import locations  # noqa: E402
from Tree.people.routes import people  # noqa: E402
from Tree.relations.routes import relations  # noqa: E402

# The interface shell and its assets: not sensitive, and gating them would mean the
# browser could never load the page that asks for a token. Every /api call stays gated.
PUBLIC_ENDPOINTS = {'health', 'ready', 'web'}


def _configure_logging(app):
    level = getattr(logging, str(app.config.get('LOG_LEVEL', 'INFO')).upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format='%(asctime)s %(levelname)-8s %(name)s: %(message)s',
    )
    app.logger.setLevel(level)


def _ensure_directories(app):
    for key in ('UPLOAD_IMAGE_PATH', 'FACES_DIR'):
        path = app.config.get(key)
        if path is not None:
            os.makedirs(path, exist_ok=True)


def _register_auth(app):
    token = app.config.get('API_TOKEN')
    if not token and not app.config.get('ALLOW_UNAUTHENTICATED'):
        raise RuntimeError(
            'FAMILYTREE_API_TOKEN is not set. Every route in this application can read, '
            'rewrite or delete family records, so it refuses to start without a token. '
            'Set FAMILYTREE_API_TOKEN, or set ALLOW_UNAUTHENTICATED=1 for local development '
            'on a loopback-only bind.'
        )
    if not token:
        app.logger.warning(
            'Running with ALLOW_UNAUTHENTICATED=1. Every endpoint is open. Bind to 127.0.0.1 only.'
        )

    @app.before_request
    def _require_token():
        if request.method == 'OPTIONS':
            return ('', 204)
        if request.endpoint in PUBLIC_ENDPOINTS:
            return None
        if not token:
            return None
        supplied = request.headers.get('X-API-Token')
        if supplied is None:
            header = request.headers.get('Authorization', '')
            if header.startswith('Bearer '):
                supplied = header[len('Bearer '):]
        # Compared with a constant-time helper so the token cannot be recovered by timing.
        if supplied is None or not hmac.compare_digest(supplied, token):
            return jsonify({'Message': 'Unauthorized.'}), 401
        return None


def _register_cors(app):
    allowed = set(app.config.get('CORS_ALLOWED_ORIGINS') or ())

    @app.after_request
    def _cors(response):
        origin = request.headers.get('Origin')
        if origin and origin in allowed:
            response.headers['Access-Control-Allow-Origin'] = origin
            response.headers['Access-Control-Allow-Credentials'] = 'true'
            response.headers['Access-Control-Allow-Headers'] = (
                'Content-Type,Authorization,X-API-Token,Task-id,face-location,start_id,'
                'end_ids,Vertex-id-map'
            )
            response.headers['Access-Control-Allow-Methods'] = 'GET,POST,PATCH,PUT,DELETE,OPTIONS'
            response.headers['Access-Control-Max-Age'] = '600'
        response.headers['Vary'] = 'Origin'
        return response


def _register_error_handlers(app):
    @app.errorhandler(ApiError)
    def _api_error(exc):
        return jsonify({'Message': exc.message}), exc.status

    @app.errorhandler(413)
    def _too_large(_exc):
        limit = app.config.get('MAX_CONTENT_LENGTH')
        return jsonify({'Message': f'Upload exceeds the {limit} byte limit.'}), 413

    @app.errorhandler(404)
    def _not_found(_exc):
        return jsonify({'Message': 'Not found.'}), 404

    @app.errorhandler(500)
    def _server_error(exc):
        # Logged with a stack trace; the client is told nothing about internals.
        app.logger.exception('Unhandled error: %s', exc)
        return jsonify({'Message': 'Internal server error.'}), 500


def _register_health(app):
    @app.route('/health')
    def health():
        """Liveness. Deliberately does not touch the database, so a database outage does not
        cause an orchestrator to kill and respawn healthy workers."""
        return jsonify({'Message': 'ok'}), 200

    @app.route('/ready')
    def ready():
        """Readiness. One cheap round-trip plus the Groovy-injection state."""
        problems = []
        try:
            g.V().limit(1).toList()
        except Exception as exc:
            problems.append(f'gremlin: {exc.__class__.__name__}')
        if not app.config.get('GROOVY_LOADED', False):
            problems.append('groovy functions not loaded')
        if problems:
            return jsonify({'Message': 'not ready', 'Problems': problems}), 503
        return jsonify({'Message': 'ready'}), 200


def _load_groovy(app):
    """Load the server-side Groovy helpers, without making startup fatal.

    Note on deployment: submitting these definitions through a sessionless client works only
    because Gremlin Server keeps one script engine for all sessionless requests and caches
    script methods as global closures. That means the definitions are lost whenever Gremlin
    Server restarts, and are present on only one node behind a load balancer. The supported
    mechanism is to ship functions.groovy with the server and load it through
    ScriptFileGremlinPlugin -- see docker-compose.yml. Startup injection is kept for local
    development against a stock server image.
    """
    app.config['GROOVY_LOADED'] = False
    if not app.config.get('INJECT_GROOVY_AT_STARTUP'):
        app.logger.info('Startup Groovy injection disabled; expecting server-side init script.')
        app.config['GROOVY_LOADED'] = True
        return
    try:
        inject_functions(
            app.config['GREMLIN_DATABASE_URI'],
            app.config['GREMLIN_TRAVERSAL_SOURCE'],
            app.config['GROOVY_FUNCTIONS_PATH'],
            timeout_ms=app.config['GREMLIN_WRITE_TIMEOUT_MS'],
            wire=message_serializer(app.config['GREMLIN_SERIALIZER']),
        )
        app.config['GROOVY_LOADED'] = True
        app.logger.info('Loaded server-side Groovy helpers.')
    except (GroovyInjectionError, OSError) as exc:
        # Degraded, not dead: /health stays green so the process is not respawn-looped,
        # /ready reports 503 so no traffic is routed here.
        app.logger.error(
            'Could not load server-side Groovy helpers (%s). Relationship endpoints will '
            'fail until Gremlin Server is reachable and the script is loaded.', exc,
        )


def _register_web(app):
    """Serve the built interface from the same origin as the API.

    Same-origin is what removes the CORS problem class rather than configuring around it:
    the browser never makes a cross-origin request, so no allowlist has to be right.
    """
    dist = Path(app.config['WEB_DIST'])
    index = dist / 'index.html'
    if not index.is_file():
        app.logger.info('No built interface at %s — run `npm run build` in web/.', dist)
        return

    # The interface's own routes. Deliberately a list rather than a catch-all: a catch-all
    # answers 200 for every mistyped path, which hides typos and quietly resurrects URLs
    # that were removed on purpose.
    client_routes = ('', 'person', 'vocabulary', 'photos', 'places', 'add')

    methods = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE']

    @app.route('/', defaults={'path': ''}, methods=methods)
    @app.route('/<path:path>', methods=methods)
    def web(path):
        if request.method != 'GET':
            return jsonify({'Message': 'Not found.'}), 404
        candidate = dist / path
        if path and candidate.is_file():
            return send_from_directory(dist, path)
        if path.split('/', 1)[0] in client_routes:
            return send_from_directory(dist, 'index.html')
        return jsonify({'Message': 'Not found.'}), 404

    app.logger.info('Serving the interface from %s', dist)


def create_app(configuration=General_Configuration):
    app = Flask(__name__)
    app.config.from_object(configuration)

    _configure_logging(app)
    _ensure_directories(app)
    _register_error_handlers(app)
    _register_cors(app)
    _register_auth(app)
    _register_health(app)
    _register_web(app)

    app.register_blueprint(api)
    app.register_blueprint(base)
    app.register_blueprint(people)
    app.register_blueprint(relations)
    app.register_blueprint(locations)

    # The face feature depends on dlib, which is a source-only build. Registering it
    # conditionally is what lets the core application install and run in one command.
    try:
        from Tree.faces.routes import faces
    except ImportError as exc:
        app.logger.warning(
            'Face endpoints disabled: %s. Install requirements-faces.txt to enable them.', exc,
        )
    else:
        app.register_blueprint(faces)

    _load_groovy(app)
    return app
