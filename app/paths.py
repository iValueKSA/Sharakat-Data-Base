"""Location of files shipped with the application package.

Resolved from this module's own location so the API serves the same UI no
matter which working directory, launcher or service manager started it.
"""
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_DIR.parent
STATIC_DIR = PACKAGE_DIR / "static"
INDEX_HTML = STATIC_DIR / "index.html"
