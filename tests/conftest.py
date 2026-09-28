import os
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Point runtime data at a temp location before Tree.config is imported.
os.environ.setdefault('FAMILYTREE_DATA_DIR', str(Path(__file__).resolve().parent / '_data'))

# One SQLite file per test session, in a temp directory that goes away with the process.
#
# This is set before Tree.config is imported, so Configuration.DATABASE_PATH reads it. A test
# that needs an isolated database opens its own via Tree.storage.open_database or points the
# app config at a tmp_path; this default keeps a test that boots the app from ever touching a
# developer's real family tree.
_DB_DIR = tempfile.mkdtemp(prefix='familytree-tests-')
os.environ.setdefault('FAMILYTREE_DB_PATH', str(Path(_DB_DIR) / 'family.sqlite'))


@pytest.fixture()
def make_synthetic_family():
    """Factory fixture: call ``make_synthetic_family(n_people, seed=0)`` for a fresh tree.

    A factory rather than a fixed graph, because different tests want different sizes -- a
    correctness test wants a few dozen people, a perf test wants ten thousand -- and building
    the ten-thousand-person tree for every test that only needs a small one would be waste.
    See :func:`tests.fixtures.synthetic_tree.build_synthetic_family`.
    """
    from tests.fixtures.synthetic_tree import build_synthetic_family

    return build_synthetic_family
