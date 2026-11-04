from __future__ import annotations

from yt_downloader.platform_services import (
    hidden_window_subprocess_kwargs,
)


def test_hidden_window_subprocess_policy_is_empty_off_windows():
    assert hidden_window_subprocess_kwargs("darwin") == {
        "startupinfo": None,
        "creationflags": 0,
    }


def test_named_native_adapters_import_without_loading_foreign_native_libraries():
    """Import dispatch never initializes the other OS's native runtime."""
    import subprocess
    import sys
    from pathlib import Path

    script = """
import importlib
import importlib.abc
import subprocess  # Standard library probes msvcrt availability itself.
import sys
class ForeignNativeImport(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        forbidden = {"AppKit", "Foundation", "objc", "Quartz"} if sys.platform == "win32" else {"msvcrt", "win32api", "win32gui"}
        if fullname.split(".")[0] in forbidden:
            raise AssertionError("foreign native import: " + fullname)
sys.meta_path.insert(0, ForeignNativeImport())
for name in sys.argv[1:]:
    importlib.import_module(name)
"""
    # Every Windows module, plus the macOS modules that must import anywhere.
    root = Path(__file__).resolve().parents[1] / "yt_downloader/platforms"
    modules = [
        f"yt_downloader.platforms.windows.{path.stem}"
        for path in sorted((root / "windows").glob("*.py"))
        if path.stem != "__init__"
    ]
    modules.append("yt_downloader.platforms.macos.filesystem")
    assert len(modules) > 3
    result = subprocess.run(
        [sys.executable, "-c", script, *modules],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_relocated_native_failure_keeps_closed_diagnostic_label():
    from yt_downloader.failure_diagnostics import _first_party_location

    namespace = {"__name__": "yt_downloader.platforms.macos.player_overlay"}
    exec(  # noqa: S102 - fixed synthetic traceback fixture
        compile(
            "def fail():\n    raise RuntimeError('private-path-sentinel')\n",
            "private-file-sentinel",
            "exec",
        ),
        namespace,
    )
    try:
        namespace["fail"]()
    except RuntimeError as error:
        detail = _first_party_location(error)
    assert detail == {
        "source_module": "player_overlay_macos",
        "source_trace": "player_overlay_macos:2",
        "source_line": 2,
        "source_scope": "first_party_frame",
    }
    assert "sentinel" not in str(detail)
    namespace["__name__"] = "yt_downloader.platforms.macos.private_user_module"
    try:
        namespace["fail"]()
    except RuntimeError as error:
        assert _first_party_location(error) == {}


def test_qt_failure_location_keeps_closed_module_without_private_context():
    from yt_downloader.failure_diagnostics import _first_party_location

    namespace = {"__name__": "yt_downloader.qt_quick.local_conversion"}
    exec(  # noqa: S102 - fixed synthetic traceback fixture
        compile(
            "def fail():\n    raise RuntimeError('private-path-sentinel')\n",
            "private-file-sentinel",
            "exec",
        ),
        namespace,
    )
    try:
        namespace["fail"]()
    except RuntimeError as error:
        detail = _first_party_location(error)
    assert detail == {
        "source_module": "qt_quick.local_conversion",
        "source_trace": "qt_quick.local_conversion:2",
        "source_line": 2,
        "source_scope": "first_party_frame",
    }
    assert "sentinel" not in str(detail)
    namespace["__name__"] = "yt_downloader.qt_quick.private_user_module"
    try:
        namespace["fail"]()
    except RuntimeError as error:
        assert _first_party_location(error) == {}
