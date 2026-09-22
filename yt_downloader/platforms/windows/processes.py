"""Windows child-process presentation; callers own execution authority."""

from __future__ import annotations

import subprocess  # nosec B404 - native startup structures only
from typing import Any


def hidden_window_subprocess_kwargs() -> dict[str, Any]:
    startupinfo = subprocess.STARTUPINFO()  # type: ignore[attr-defined]
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW  # type: ignore[attr-defined]
    return {
        "startupinfo": startupinfo,
        "creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0),
    }
