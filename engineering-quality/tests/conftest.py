from __future__ import annotations

import sys
from pathlib import Path

HARNESS_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = HARNESS_ROOT.parent
for path in (str(HARNESS_ROOT), str(REPO_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)
