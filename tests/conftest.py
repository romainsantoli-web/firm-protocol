"""Test configuration for FIRM Protocol."""

import sys
from pathlib import Path

# Ensure the src dir is on sys.path for imports
src_dir = Path(__file__).parent.parent / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))
