import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Point runtime data at a temp location before Tree.config is imported.
os.environ.setdefault('FAMILYTREE_DATA_DIR', str(Path(__file__).resolve().parent / '_data'))
os.environ.setdefault('INJECT_GROOVY_AT_STARTUP', '0')

# Point the graph at an address nothing listens on.
#
# This is a guard, not a configuration. A developer running the stack locally has JanusGraph
# on 127.0.0.1:8182, and the default URI points straight at it -- so a test that reaches the
# database by mistake does not fail, it silently writes into a real family tree. That happened.
# Any test needing the store must mock it; anything that slips through now raises instead.
os.environ['GREMLIN_DATABASE_URI'] = 'ws://127.0.0.1:9/gremlin'
