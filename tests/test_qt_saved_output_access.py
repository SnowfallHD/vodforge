"""An unavailable configured folder must not prevent opening retained Library data."""

from pathlib import Path

import pytest
from PySide6.QtGui import QGuiApplication

from yt_downloader.qt_quick.main import Bridge
from yt_downloader.settings_store import (
    load_settings,
    save_settings,
    settings_file_path,
)

_APP = None


@pytest.mark.parametrize("failure", [PermissionError("denied"), OSError("offline")])
def test_saved_output_probe_failure_preserves_configuration_and_opens_app(
    tmp_path, monkeypatch, failure
):
    global _APP
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("QT_QUICK_BACKEND", "software")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    _APP = QGuiApplication.instance() or QGuiApplication([])
    folder = tmp_path / "temporarily-unavailable"
    folder.mkdir()
    settings = settings_file_path()
    save_settings(settings, {"output_dir": str(folder), "quality": "720p HD"})
    original = settings.read_bytes()
    is_dir = Path.is_dir

    def observed_access(path):
        if path == folder:
            raise failure
        return is_dir(path)

    monkeypatch.setattr(Path, "is_dir", observed_access)
    bridge = Bridge(None)
    try:
        assert bridge.outputPath == str(folder)
        assert "output folder" in bridge.status.lower()
        assert settings.read_bytes() == original
        bridge.setQuality("480p")
        bridge._save_preferences()
        assert load_settings(settings)["output_dir"] == str(folder)
    finally:
        bridge.close()
