import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Point runtime data at a temp location before Tree.config is imported.
os.environ.setdefault('FAMILYTREE_DATA_DIR', str(Path(__file__).resolve().parent / '_data'))
os.environ.setdefault('INJECT_GROOVY_AT_STARTUP', '0')
