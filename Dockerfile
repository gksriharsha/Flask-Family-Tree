# Build the interface here, so a fresh clone can build the image without needing node
# installed and without web/dist being committed.
FROM node:22-alpine AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build


FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Dependencies first, so a source change does not invalidate the dependency layer.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY Tree ./Tree
COPY wsgi.py TreeServer.py ./
# The interface built in the stage above, served same-origin at the application root.
COPY --from=web /web/dist ./web/dist

# The SQLite database and the media/upload store live on a volume, never inside the source
# tree. The database file is FAMILYTREE_DB_PATH; everything else hangs off FAMILYTREE_DATA_DIR.
ENV FAMILYTREE_DATA_DIR=/data \
    FAMILYTREE_DB_PATH=/data/family.sqlite
RUN mkdir -p /data && useradd --create-home --uid 10001 app && chown -R app:app /app /data
USER app
VOLUME ["/data"]

EXPOSE 5000

# Liveness deliberately does not touch the database, so a database outage cannot cause healthy
# workers to be killed and respawned.
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:5000/health', timeout=2).status==200 else 1)"

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--timeout", "60", \
     "--access-logfile", "-", "wsgi:app"]
