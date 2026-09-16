"""Compatibility entry point for the shared native resize QA driver."""

import runpy
from pathlib import Path

runpy.run_path(
    str(Path(__file__).with_name("native-resize-probe.py")), run_name="__main__"
)
