#!/bin/bash
#
# start_family_tree.sh
#
# Launched at login by the com.kgundu1.familytree LaunchAgent (macOS). Ensures
# Docker Desktop is running, waits for the engine to be ready, then brings up the
# family-tree docker-compose stack -- JanusGraph plus the Flask API.
#
# The compose services use `restart: unless-stopped`, so once they are up Docker
# keeps them alive; this script's job is to guarantee they get started in the
# first place after a reboot, even if the Docker engine isn't running yet.
#
# The script derives its own location rather than hardcoding a home directory, so
# the checkout can be moved or cloned elsewhere without editing this file. Only
# the LaunchAgent plist names an absolute path, and that file is machine-local.

set -u

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DOCKER_BIN="${DOCKER_BIN:-/usr/local/bin/docker}"
WAIT_TIMEOUT="${WAIT_TIMEOUT:-180}"   # max seconds to wait for the Docker engine

log() {
  printf '%s %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"
}

log "=== family-tree autostart triggered ==="
log "Project directory: $PROJECT_DIR"

# The API refuses to start without a token, and compose interpolates it from .env
# in the project directory. Fail loudly here rather than leaving a cryptic compose
# error in a log nobody reads.
if [ ! -f "$PROJECT_DIR/.env" ]; then
  log "ERROR: $PROJECT_DIR/.env is missing. Copy .env.example to .env and set"
  log "       FAMILYTREE_API_TOKEN before this stack can start."
  exit 1
fi

if ! command -v "$DOCKER_BIN" >/dev/null 2>&1 && [ ! -x "$DOCKER_BIN" ]; then
  log "ERROR: docker not found at $DOCKER_BIN. Set DOCKER_BIN to its path."
  exit 1
fi

# 1. If the Docker engine isn't responding, launch Docker Desktop.
if ! "$DOCKER_BIN" info >/dev/null 2>&1; then
  log "Docker engine not responding; launching Docker Desktop..."
  /usr/bin/open --background -a Docker
fi

# 2. Wait for the engine to become ready.
waited=0
until "$DOCKER_BIN" info >/dev/null 2>&1; do
  if [ "$waited" -ge "$WAIT_TIMEOUT" ]; then
    log "ERROR: Docker engine not ready after ${WAIT_TIMEOUT}s; giving up."
    exit 1
  fi
  sleep 3
  waited=$((waited + 3))
done
log "Docker engine is ready (waited ${waited}s)."

# 3. Bring up the stack (idempotent: a no-op if already running).
#    Run from the project directory so compose picks up .env and resolves the
#    pinned project name, keeping the existing named volumes.
cd "$PROJECT_DIR" || { log "ERROR: cannot cd to $PROJECT_DIR"; exit 1; }

log "Starting family-tree stack: docker compose up -d"
if "$DOCKER_BIN" compose up -d; then
  log "docker compose up -d succeeded."
else
  log "ERROR: docker compose up -d failed."
  exit 1
fi

# 4. Record the resulting container state for the log.
"$DOCKER_BIN" compose ps
log "=== family-tree autostart finished ==="
