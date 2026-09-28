# Flask-Family-Tree

An API for storing a family tree and traversing the relationships in it, backed by a single
**SQLite** file. The companion UI is at
[Family-Tree-UI](https://github.com/gksriharsha/Family-Tree-UI).

Design reasoning for the domain decisions — occupation as a history, birth dates from multiple
calendars, adoption and surname rules, why a birth order is stored as its own fact rather than a
placeholder date — is in [Notes.md](Notes.md), including a short **Storage** section on the
pivot away from JanusGraph.

## Run it

No database server to install: the whole tree is one SQLite file, created on first use.

```bash
python -m venv venv && ./venv/bin/pip install -r requirements.txt
export FAMILYTREE_API_TOKEN=$(python -c "import secrets;print(secrets.token_urlsafe(32))")
export FAMILYTREE_DB_PATH=./data/family.sqlite      # optional; this is the default location

# Optional: load the 29-person demo family used as the test fixture.
./venv/bin/python -m Tree.cli seed

./venv/bin/gunicorn --bind 127.0.0.1:5000 --workers 2 wsgi:app
```

`python TreeServer.py` also works for development. It binds to loopback and does not enable
debug mode.

Then:

```bash
curl localhost:5000/health                                 # liveness, no token needed
curl localhost:5000/ready                                  # readiness: opens the SQLite store
curl -H "X-API-Token: $FAMILYTREE_API_TOKEN" "localhost:5000/api/v1/graph"
```

The API is published on `127.0.0.1` only. Put a TLS-terminating reverse proxy in front of it
before it is reachable from anywhere else.

### With Docker

Requires Docker. One container — the API. The SQLite file lives on a mounted volume.

```bash
cp .env.example .env
python -c "import secrets; print('FAMILYTREE_API_TOKEN=' + secrets.token_urlsafe(32))" >> .env
docker build -t familytree-api .
docker run -d -p 127.0.0.1:5000:5000 \
  -e FAMILYTREE_API_TOKEN="$(grep FAMILYTREE_API_TOKEN .env | cut -d= -f2)" \
  -v "$PWD/data:/data" \
  familytree-api
```

The image sets `FAMILYTREE_DB_PATH=/data/family.sqlite`, so the tree persists on the `data`
volume across container restarts and rebuilds.

## Configuration

Everything is read from the environment; see [Tree/config.py](Tree/config.py) for the full list
and the defaults.

| Variable | Default | Notes |
| --- | --- | --- |
| `FAMILYTREE_API_TOKEN` | — | **Required.** The app refuses to start without it, because every route can read, rewrite or delete family records. Set `ALLOW_UNAUTHENTICATED=1` instead only for local work on a loopback bind. |
| `FAMILYTREE_DB_PATH` | `<data>/family.sqlite` | The SQLite database file — the whole tree. |
| `FAMILYTREE_DATA_DIR` | `./data` | Uploads, media and the face store. Never inside the source tree. |
| `CORS_ALLOWED_ORIGINS` | `http://localhost:4200` | Comma-separated exact origins. Not a wildcard. |
| `MAX_UPLOAD_BYTES` | `10485760` | Requests above this get a 413. |
| `MAX_GRAPH_PEOPLE` | `100000` | Ceiling on the whole-tree read. |
| `GEOCODING_ENABLED` | `0` | Off by default; a location is created without coordinates. |

## Managing the tree — `python -m Tree.cli`

| Command | What it does |
| --- | --- |
| `tree --name NAME --at DIR` | Create a tree and choose the folder its portable files live in (`--show` prints the current one). |
| `import PATH.ged` \| `PATH.gdz` | Read a GEDCOM or GEDZIP file into the database. |
| `export [--format gedcom7\|gedcom551\|gedzip]` | Write a copy in another format; `current` (default) refreshes the tree's own `family.ged`. |
| `seed` | Create the 29-person demo family in the database. |
| `reset --yes` | **Delete the database file** (and its `-wal`/`-shm` siblings). Refuses without `--yes`, and refuses when `ENV=production`. |
| `check` | Report the database path, its schema version, and the person count. |

### Importing a GEDCOM

```bash
./venv/bin/python -m Tree.cli import /path/to/family.ged
```

or over HTTP, as an upload or a server-side path:

```bash
curl -H "X-API-Token: $FAMILYTREE_API_TOKEN" -F file=@family.ged \
     localhost:5000/api/v1/trees/import
```

`mode=replace` clears the existing people first; the default adds. A 10 000-person GEDCOM
imports in one transaction, in seconds.

## Backup

The tree is one SQLite file. **Back it up by copying it** — copy `FAMILYTREE_DB_PATH` (and its
`-wal`/`-shm` siblings if they exist), or simply copy the whole `FAMILYTREE_DATA_DIR` folder,
which also carries the exported `family.ged`, the vocabulary sidecar, and the media. Restoring
is copying the folder back. There is no server to dump and no schema migration to run: opening
an existing file applies any pending schema step idempotently.

## Photos and places

Every person can record **where they were born and died** and can have **photographs**
attached — both work with no extra dependency and are stored in the same SQLite file and
media folder as the rest of the tree.

* **Places** are free text (e.g. `Hyderabad, India`), edited in the add/edit person form and
  travelling in the exported GEDCOM as a `PLAC` under the birth and death events, so they
  survive an export/import round-trip and open correctly in other genealogy software.
* **Photos** are uploaded, captioned, attached to a person and served back through the
  `/api/v1/photos` endpoints. A photo of a gathering is kept even after one of the people in
  it is removed — deleting a person detaches their photos rather than destroying them.

Face *recognition* (below) is an optional layer on top of this; the plain photo and place
features do not need it.

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
./venv/bin/python -m pytest tests -q     # unit tests, each against its own temp SQLite file
./venv/bin/ruff check Tree wsgi.py TreeServer.py
./venv/bin/python tools/check_no_eval.py # fails if eval/exec reappears in the app
```
