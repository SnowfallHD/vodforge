"""Qt must apply the shared v1 fixed-preset migration before reading inputs.

Earlier coverage tested the pure migration and current Streaming restart
separately, missing the Qt startup route. No historical alias/schema is invented.
"""

import pytest
from PySide6.QtGui import QGuiApplication

from yt_downloader.export_planning import migrate_export_preferences
from yt_downloader.models import ExportMode, ManualAudioCodec, OutputType
from yt_downloader.qt_quick.main import Bridge
from yt_downloader.settings_store import (
    load_settings,
    save_settings,
    settings_file_path,
)

_APP = None


@pytest.fixture
def settings(tmp_path, monkeypatch):
    global _APP
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("QT_QUICK_BACKEND", "software")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    _APP = QGuiApplication.instance() or QGuiApplication([])
    return settings_file_path(), {
        "output_dir": str(tmp_path),
        "quality": "720p HD",
        "embed_metadata": False,
        "write_thumbnail": False,
        "unrelated_future_preference": {"kept": True},
        "manual_video_bitrate": 8300,
        "manual_audio_bitrate": 128,
        "manual_audio_codec": "MP3",
        "manual_sample_rate": "44100",
        "manual_channels": "Mono",
        "manual_preset": "veryfast",
        "manual_rate_control": "Quality",
        "manual_crf": "19",
    }


def test_strict_v1_preferences_reach_custom_inputs_and_survive_restart(settings):
    path, original = settings
    original["export_mode"] = "Strict Compliance"
    save_settings(path, original)
    disk_before = path.read_bytes()
    expected = migrate_export_preferences(original)
    bridge = Bridge(None)
    try:
        assert bridge.exportModeLabel == "Custom"
        assert bridge._settings == expected
        manual, _ = bridge._current_export_inputs(OutputType.MP4)
        assert manual.video_bitrate_kbps == 10000
        assert manual.audio_bitrate_kbps == 320
        assert manual.audio_codec is ManualAudioCodec.AAC
        assert manual.audio_sample_rate == "48000"
        assert manual.audio_channels == "2"
        assert manual.x264_preset == "medium"
        assert manual.video_crf is None
        assert path.read_bytes() == disk_before  # Startup is read-only.
        bridge.setQuality("480p")  # An ordinary save persists normalized values.
    finally:
        bridge.close()
    persisted = load_settings(path)
    assert persisted["export_mode"] == "Manual Override"
    for key in (
        "output_dir",
        "embed_metadata",
        "write_thumbnail",
        "unrelated_future_preference",
        "manual_crf",
    ):
        assert persisted[key] == original[key]
    restored = Bridge(None)
    try:
        assert restored.exportModeLabel == "Custom"
        assert restored._settings == persisted
        assert migrate_export_preferences(persisted) == persisted
    finally:
        restored.close()


@pytest.mark.parametrize(
    "mode",
    [mode.value for mode in ExportMode if mode is not ExportMode.STRICT_COMPLIANCE],
)
def test_current_canonical_preferences_and_custom_fields_are_unchanged(settings, mode):
    path, original = settings
    original["export_mode"] = mode
    save_settings(path, original)
    bridge = Bridge(None)
    try:
        assert bridge.exportMode == mode
        assert bridge._settings == original
        assert bridge.manualValues["manual_video_bitrate"] == "8300"
        assert bridge.manualValues["manual_audio_codec"] == "MP3"
        assert bridge.manualValues["manual_rate_control"] == "Quality"
    finally:
        bridge.close()
    assert load_settings(path) == original


@pytest.mark.parametrize("name", ["Unknown", "Auto CBR (Recommended)", "CTV", "Custom"])
def test_unrecognized_persisted_names_keep_existing_safe_fallback(settings, name):
    path, original = settings
    original["export_mode"] = name
    save_settings(path, original)
    bridge = Bridge(None)
    try:
        assert bridge.exportModeLabel == "Everyday"
        assert bridge._settings == original
    finally:
        bridge.close()
    assert load_settings(path) == original
