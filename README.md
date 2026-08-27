# Flask-Family-Tree

An API for storing a family tree and traversing the relationships in it, backed by JanusGraph.
The companion UI is at [Family-Tree-UI](https://github.com/gksriharsha/Family-Tree-UI).

Design reasoning for the domain decisions — occupation as a history, birth dates from multiple
calendars, adoption and surname rules, why birth facts sit on the vertex rather than the edge —
is in [Notes.md](Notes.md).

## Run it

Requires Docker. Two containers: JanusGraph (BerkeleyJE + Lucene, one JVM) and the API.

```bash
cp .env.example .env
python -c "import secrets; print('FAMILYTREE_API_TOKEN=' + secrets.token_urlsafe(32))" >> .env
docker compose up -d --build

# Declare the schema. Do this before any data exists — see "Schema" below.
docker compose exec api python -m Tree.cli schema

# Optional: load the 29-person demo family used as the test fixture.
docker compose exec api python -m Tree.cli seed
```

Then:

```bash
curl localhost:5000/health                                    # liveness, no token needed
curl localhost:5000/ready                                     # readiness: DB + Groovy helpers
curl -H "X-API-Token: $TOKEN" localhost:5000/query/count_people
```

The API is published on `127.0.0.1` only. Put a TLS-terminating reverse proxy in front of it
before it is reachable from anywhere else.

### Without Docker

```bash
python -m venv venv && ./venv/bin/pip install -r requirements.txt
export FAMILYTREE_API_TOKEN=$(python -c "import secrets;print(secrets.token_urlsafe(32))")
export GREMLIN_DATABASE_URI=ws://localhost:8182/gremlin
./venv/bin/gunicorn --bind 127.0.0.1:5000 --workers 2 wsgi:app
```

`python TreeServer.py` also works for development. It binds to loopback and does not enable
debug mode.

## Configuration

Everything is read from the environment; see [Tree/config.py](Tree/config.py) for the full list
and the defaults.

| Variable | Default | Notes |
| --- | --- | --- |
| `FAMILYTREE_API_TOKEN` | — | **Required.** The app refuses to start without it, because every route can read, rewrite or delete family records. Set `ALLOW_UNAUTHENTICATED=1` instead only for local work on a loopback bind. |
| `GREMLIN_DATABASE_URI` | `ws://localhost:8182/gremlin` | |
| `GREMLIN_SERIALIZER` | `graphson` | GraphSON 3.0, not GraphBinary — see "Serializer" below. |
| `CORS_ALLOWED_ORIGINS` | `http://localhost:4200` | Comma-separated exact origins. Not a wildcard. |
| `FAMILYTREE_DATA_DIR` | `./data` | Uploads and the face store. Never inside the source tree. |
| `MAX_UPLOAD_BYTES` | `10485760` | Requests above this get a 413. |
| `GEOCODING_ENABLED` | `0` | Off by default; a location is created without coordinates. |
| `INJECT_GROOVY_AT_STARTUP` | `1` | Set to `0` when the server loads `functions.groovy` itself. |

## Schema

`python -m Tree.cli schema` applies [schema.groovy](schema.groovy): property keys with explicit
cardinality, vertex and edge labels, three composite indexes, and one mixed index that makes the
substring name search indexed rather than a full graph walk.

**Apply it to an empty graph, before seeding.** Two reasons:

- Without a declared schema, JanusGraph creates each property key from whatever the first write
  implies. The seed writes dates with a plain `property()` call, creating them as `SINGLE`; the
  API writes them with `SET` cardinality, and the server then rejects the write with
  `Key is defined for SINGLE cardinality which conflicts with specified: set`. Cardinality
  cannot be altered in place afterwards.
- An index built over a key that already holds data is left `INSTALLED` rather than `ENABLED` and
  needs a reindex job.

The command is idempotent and reports any cardinality conflict it cannot fix rather than failing
silently.

## Serializer

The driver is configured for GraphSON 3.0 rather than gremlinpython's default GraphBinary.
JanusGraph returns the id of a vertex property as a GraphBinary *custom* type (its
`RelationIdentifier`), and gremlinpython's GraphBinary reader has no deserializer for custom
types — so any traversal returning a vertex with properties, which includes every
`addV(...).next()`, fails with `KeyError: <DataType.custom: 0>` *after* the write has already been
applied. GraphSON renders the same value as a string.

## Server-side Groovy

[functions.groovy](functions.groovy) holds the relationship-writing and path-finding helpers.

The application submits it at startup by default, which works only as a side effect of Gremlin
Server keeping one script engine for all sessionless requests and caching script methods as
global closures. The definitions are therefore lost on every Gremlin Server restart, and exist on
only one node behind a load balancer. The supported mechanism is to let the server load the file
itself:

```yaml
scriptEngines:
  gremlin-groovy:
    plugins:
      org.apache.tinkerpop.gremlin.jsr223.ScriptFileGremlinPlugin:
        files: [/opt/janusgraph/scripts/familytree.groovy]
```

`docker-compose.yml` already mounts the file at that path. Add the block to the server's
`janusgraph-server.yaml` and set `INJECT_GROOVY_AT_STARTUP=0`.

The file's header comment lists the defects still outstanding in it — the `T.ID` token, the
`adoption()` ordering bug, `child()` writing one parent's edge twice, and the `siblings()` call
sites. Those affect the adoption and consanguinity branches; the ordinary relationship path works.

## Optional: face recognition

The photo endpoints depend on `dlib`, which is a source-only build needing cmake and a C++
toolchain. They are registered only when the import succeeds, so the core API installs and runs
in one command without them.

```bash
pip install -r requirements-faces.txt
```

Before enabling this in anything shared, read the note in `Tree/faces/` about consent: a face
template tied to a named living person is special-category biometric data under GDPR Article 9
and a biometric identifier under Illinois BIPA, which requires written consent before collection
and a published retention schedule. A family tree intrinsically contains third parties who never
used the app.

## Development

```bash
./venv/bin/python -m pytest tests -q     # unit tests, no database needed
./venv/bin/ruff check .                  # lint
./venv/bin/python tools/check_no_eval.py # fails if eval/exec reappears in the app
```

`python -m Tree.cli` also has `reset --yes` (drops every vertex; refuses when `ENV=production`)
and `check` (reports connectivity and counts).

## Debugging Gremlin

```
:remote connect tinkerpop.server conf/remote.yaml
:remote console
```
