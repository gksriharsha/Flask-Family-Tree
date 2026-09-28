import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent


def _env_bool(name, default=False):
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {'1', 'true', 'yes', 'on'}


def _env_int(name, default):
    raw = os.environ.get(name)
    if raw is None or raw.strip() == '':
        return default
    return int(raw)


def _env_list(name, default):
    raw = os.environ.get(name)
    if raw is None or raw.strip() == '':
        return list(default)
    return [item.strip() for item in raw.split(',') if item.strip()]


DATA_DIR = Path(os.environ.get('FAMILYTREE_DATA_DIR', PROJECT_ROOT / 'data')).expanduser().resolve()


class Configuration:
    """Application configuration. Every value is overridable through the environment so the
    same image can run locally and in a deployment without editing source."""

    # --- Storage -------------------------------------------------------------
    # One SQLite file is one family tree. The whole store — people, links, unions, birth
    # order, vocabulary, settings — lives in this file, so a backup is a copy of the folder it
    # sits in. Overridable so the same image can point at a mounted volume in a deployment and
    # a scratch file in a test.
    DATABASE_PATH = Path(
        os.environ.get('FAMILYTREE_DB_PATH', DATA_DIR / 'family.sqlite')
    ).expanduser()

    # --- Authentication ------------------------------------------------------
    # A single shared secret. Crude, but the difference between "anyone on the network" and
    # "people who were given the token". Absent => the app refuses to start unless
    # ALLOW_UNAUTHENTICATED is explicitly set (local development only).
    API_TOKEN = os.environ.get('FAMILYTREE_API_TOKEN')
    ALLOW_UNAUTHENTICATED = _env_bool('ALLOW_UNAUTHENTICATED', False)

    # --- CORS ----------------------------------------------------------------
    # An explicit allowlist. The previous wildcard let any site a family member visited read
    # and destroy the tree.
    CORS_ALLOWED_ORIGINS = _env_list('CORS_ALLOWED_ORIGINS', ['http://localhost:4200'])

    # --- Uploads and media ---------------------------------------------------
    DATA_DIR = DATA_DIR
    UPLOAD_IMAGE_PATH = DATA_DIR / 'uploads'
    FACES_DIR = DATA_DIR / 'faces'
    FACES_JSON_PATH = DATA_DIR / 'faces' / 'faces.json'
    MAX_CONTENT_LENGTH = _env_int('MAX_UPLOAD_BYTES', 10 * 1024 * 1024)
    ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'tiff'}
    RESIZED_IMAGE_HEIGHT = _env_int('RESIZED_IMAGE_HEIGHT', 800)

    # A bundled font is used when no override is supplied; label drawing falls back to Pillow's
    # built-in bitmap font rather than raising, so a missing font can never 500 an endpoint.
    FONT_PATH = os.environ.get('FONT_PATH')
    FONT_SIZE = _env_int('FONT_SIZE', 14)
    FACE_MATCH_THRESHOLD = float(os.environ.get('FACE_MATCH_THRESHOLD', '0.6'))

    # --- Limits --------------------------------------------------------------
    # Relationship fan-out is attacker-controlled, so it is capped at the route boundary.
    MAX_RELATION_TARGETS = _env_int('MAX_RELATION_TARGETS', 50)
    RELATION_SEARCH_WORKERS = _env_int('RELATION_SEARCH_WORKERS', 4)
    MAX_SEARCH_RESULTS = _env_int('MAX_SEARCH_RESULTS', 200)
    # How many people the whole-tree read (/api/v1/graph) loads. A family tree is small, so the
    # ceiling is high; it exists only so a pathological database cannot ask the process to build
    # an unbounded structure in memory. The four bulk SELECTs behind it stay fast well past this.
    MAX_GRAPH_PEOPLE = _env_int('MAX_GRAPH_PEOPLE', 100000)

    # --- Geocoding ------------------------------------------------------------
    # Off by default. Coordinate lookup used to happen inline inside POST /add/location by
    # scraping Google's search-results HTML and eval-ing the numbers out of it, with no
    # timeout, no user agent and a CSS selector that no longer matches -- so the endpoint made
    # a blocking third-party call it could not rely on, against terms of service that forbid
    # it. A location is now created without coordinates unless this is explicitly enabled.
    GEOCODING_ENABLED = _env_bool('GEOCODING_ENABLED', False)
    GEOCODING_URL = os.environ.get('GEOCODING_URL', 'https://nominatim.openstreetmap.org/search')
    # Nominatim's usage policy requires a descriptive User-Agent identifying the application
    # and a contact address. Set this before enabling geocoding.
    GEOCODING_USER_AGENT = os.environ.get(
        'GEOCODING_USER_AGENT', 'family-tree/0.1 (set GEOCODING_USER_AGENT with a contact address)'
    )
    GEOCODING_TIMEOUT_S = float(os.environ.get('GEOCODING_TIMEOUT_S', '5'))

    # The built interface. Served at the application root when present.
    WEB_DIST = Path(os.environ.get('WEB_DIST', PROJECT_ROOT / 'web' / 'dist'))

    LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')
