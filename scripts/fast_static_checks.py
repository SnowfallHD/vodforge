"""Run the FAST release gate's blocking static checks, the same commands FAST runs.

CI runs this on every push and the release draft workflow runs it before
building, so a formatting, type, security or dependency failure shows up on the
commit that caused it instead of during release testing. The pytest groups are
not repeated here: the Tests workflow already runs them on every platform.

    python scripts/fast_static_checks.py
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "engineering-quality"))

from quality_harness.release_gate import FAST_REQUIRED_COMMANDS
from quality_harness.static_analysis import tool_commands

# Run by the Tests workflow's pytest steps on all six jobs.
PYTEST_GROUPS = ("pytest", "pytest_qt_components", "pytest_qt_scene")


def selected_commands(python: str = sys.executable) -> list[tuple[str, list[str]]]:
    wanted = set(FAST_REQUIRED_COMMANDS) - set(PYTEST_GROUPS)
    commands = [(name, cmd) for name, cmd, _ in tool_commands(python) if name in wanted]
    missing = wanted - {name for name, _ in commands}
    if missing:
        raise SystemExit(f"FAST requires commands this script cannot find: {missing}")
    return commands


def main() -> int:
    failed = []
    for name, command in selected_commands():
        started = time.monotonic()
        result = subprocess.run(
            command, cwd=ROOT, capture_output=True, text=True, check=False
        )
        seconds = time.monotonic() - started
        status = "passed" if result.returncode == 0 else "FAILED"
        print(f"{status} {name} ({seconds:.0f}s)", flush=True)
        if result.returncode != 0:
            failed.append(name)
            output = (result.stdout + result.stderr).strip()
            print(output[-6000:], flush=True)
    if failed:
        print("FAST would fail on: " + ", ".join(failed))
        return 1
    print("All FAST static checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
