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
import main
import qt_main
assert 'tkinter' not in sys.modules
assert not hasattr(sys.modules['yt_downloader.app'], 'DownloadWorkerCore')
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


def test_non_gui_artwork_dispatch_preserved(monkeypatch) -> None:
    from yt_downloader import app, channel_artwork_worker

    monkeypatch.setattr(sys, "argv", ["VODForge", "--channel-artwork-worker"])
    monkeypatch.setattr(channel_artwork_worker, "main", lambda: 7)
    assert app.main() == 7


def test_non_gui_preflight_dispatch_preserved(monkeypatch) -> None:
    from yt_downloader import app, download_service

    seen = []
    monkeypatch.setattr(
        sys, "argv", ["VODForge", "--debug-preflight", "https://example.test/a", "b"]
    )
    monkeypatch.setattr(
        download_service, "debug_preflight", lambda url: seen.append(url) or 3
    )
    assert app.main() == 3
    assert seen == ["https://example.test/a b"]
