"""The maintained Qt application imports without loading legacy widget owners."""

import subprocess
import sys
from pathlib import Path


def test_qt_entry_imports_with_tk_unavailable() -> None:
    script = """
import builtins, sys
original_import = builtins.__import__
def refuse_tk(name, *args, **kwargs):
    if name == 'tkinter' or name.startswith('tkinter.') or name == 'PIL.ImageTk':
        raise ImportError('Tk is unavailable: ' + name)
    return original_import(name, *args, **kwargs)
builtins.__import__ = refuse_tk
import yt_downloader.qt_quick.main
assert 'tkinter' not in sys.modules
assert 'yt_downloader.app' not in sys.modules
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        check=False,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
