"""Persistence for face encodings.

The original store was a JSON object whose *keys* were ``str(tuple(encoding))`` and which was
read back with ``eval(k)`` on every request. That made a single write to the file persistent code
execution: anything that could influence the file's contents could run code on each subsequent
face request. It was also read-modify-written with no locking on every recognition, and the
merge direction meant the on-disk value overwrote the new one -- so a face could never be
re-labelled once stored.

The format is now a list of records with the encoding as a JSON array, read with ``json.load``.
Files in the old format are converted on first read using ``ast.literal_eval``, which parses
literals without executing them.
"""

import ast
import json
import logging
import os
import tempfile
import threading

log = logging.getLogger(__name__)

_LOCK = threading.Lock()


def _read_raw(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding='utf-8') as handle:
        payload = json.load(handle)

    if isinstance(payload, list):
        return [
            {'vertex_id': record['vertex_id'], 'encoding': list(record['encoding'])}
            for record in payload
            if 'vertex_id' in record and 'encoding' in record
        ]

    # Legacy format: {"(0.1, 0.2, ...)": vertex_id}. literal_eval parses the tuple without
    # executing it, unlike the eval() this replaces.
    records = []
    for key, vertex_id in payload.items():
        try:
            encoding = ast.literal_eval(key)
        except (ValueError, SyntaxError):
            log.warning('Skipping unparseable legacy face-encoding key.')
            continue
        records.append({'vertex_id': vertex_id, 'encoding': [float(v) for v in encoding]})
    log.info('Converted %d legacy face encodings to the current format.', len(records))
    return records


def load(path):
    """Return ``(encodings, vertex_ids)`` as parallel lists."""
    with _LOCK:
        records = _read_raw(path)
    return [record['encoding'] for record in records], [record['vertex_id'] for record in records]


def save(path, encoding, vertex_id):
    """Associate one encoding with a person, replacing any previous label for that encoding.

    Written atomically so a crash or a concurrent reader never sees a truncated file. Note the
    remaining limitation: this is an in-process lock, so two worker processes can still
    interleave. A shared store is the real fix and is out of scope for this pass.
    """
    encoding = [float(value) for value in encoding]
    with _LOCK:
        records = _read_raw(path)
        records = [record for record in records if record['encoding'] != encoding]
        records.append({'vertex_id': vertex_id, 'encoding': encoding})

        os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
        # Not a context manager on purpose: the file must be closed before
        # os.replace() can move it into place atomically.
        handle = tempfile.NamedTemporaryFile(  # noqa: SIM115
            'w', encoding='utf-8', dir=os.path.dirname(path) or '.', delete=False, suffix='.tmp',
        )
        try:
            json.dump(records, handle, indent=1)
            handle.flush()
            os.fsync(handle.fileno())
        finally:
            handle.close()
        os.replace(handle.name, path)
    return len(records)
