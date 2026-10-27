"""Make the installer's Python package importable from the tests."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / "src" / "lib"

if str(LIB) not in sys.path:
    sys.path.insert(0, str(LIB))
