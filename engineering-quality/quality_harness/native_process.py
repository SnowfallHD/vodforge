"""Process-local startup for native QA; never changes persistent OS preferences."""

from __future__ import annotations

import sys
from collections.abc import Sequence

_MAC_STARTUP = (
    "from Foundation import NSUserDefaults; "
    "NSUserDefaults.standardUserDefaults().registerDefaults_({"
    "'ApplePersistenceIgnoreState': True, 'NSQuitAlwaysKeepsWindows': False}); "
)


def native_python_command(
    script: str,
    arguments: Sequence[str] = (),
    *,
    platform: str | None = None,
) -> list[str]:
    """Keep caller argument positions; macOS startup flags follow caller data."""
    mac = (platform or sys.platform) == "darwin"
    return [
        sys.executable,
        "-c",
        (_MAC_STARTUP if mac else "") + script,
        *arguments,
        *(
            ["-ApplePersistenceIgnoreState", "YES", "-NSQuitAlwaysKeepsWindows", "NO"]
            if mac
            else []
        ),
    ]


def native_pytest_command(arguments: Sequence[str]) -> list[str]:
    if sys.platform != "darwin":
        return [sys.executable, "-m", "pytest", *arguments]
    # The AppKit launch flags belong to this process, not pytest's option parser.
    return native_python_command(
        "import sys; sys.argv=sys.argv[:-4]; "
        "import pytest; raise SystemExit(pytest.main(sys.argv[1:]))",
        arguments,
    )


if __name__ == "__main__":
    import subprocess

    raise SystemExit(subprocess.call(native_pytest_command(sys.argv[1:])))
