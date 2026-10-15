"""Run one build with a private, disposable PyInstaller binary cache.

Never retire caller-owned caches, build work files, packages or receipts.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile


def main() -> int:
    if len(sys.argv) < 2:
        raise SystemExit("Expected a build command")
    with tempfile.TemporaryDirectory(prefix="vodforge-pyinstaller-") as cache:
        environment = {**os.environ, "PYINSTALLER_CONFIG_DIR": cache}
        return subprocess.run(sys.argv[1:], env=environment, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
