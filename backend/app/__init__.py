import sys
import os

# Add this package directory to sys.path so the verbatim-copied modules
# (db.py, mappingEngine.py, contextService.py, llmService.py) can resolve
# each other via bare `import db` / `import mappingEngine` etc.
_pkg_dir = os.path.dirname(__file__)
if _pkg_dir not in sys.path:
    sys.path.insert(0, _pkg_dir)
