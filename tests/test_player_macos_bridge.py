"""Fresh-process bridge registration; no window or real playback required."""

from __future__ import annotations

import subprocess
import sys

import pytest


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS Core Graphics bridge")
def test_player_overlay_registers_color_bridge_without_import_order_dependency():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import warnings; warnings.simplefilter('error'); "
                "import yt_downloader.platforms.macos.player_overlay; "
                "from AppKit import NSColor; "
                "color=NSColor.colorWithCalibratedWhite_alpha_(0.035,0.96).CGColor(); "
                "assert type(color).__name__ == 'CGColorRef', type(color).__name__"
            ),
        ],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
