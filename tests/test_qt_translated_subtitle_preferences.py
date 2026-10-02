import pytest
from PySide6.QtCore import QObject
from PySide6.QtGui import QGuiApplication

from yt_downloader.qt_quick.main import Bridge, create_engine
from yt_downloader.settings_store import (
    load_settings,
    save_settings,
    settings_file_path,
)

_APP = None


@pytest.fixture
def profile(tmp_path, monkeypatch):
    global _APP
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("QT_QUICK_BACKEND", "software")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    _APP = QGuiApplication.instance() or QGuiApplication([])
    save_settings(
        settings_file_path(),
        {
            "output_dir": str(tmp_path),
            "embed_metadata": True,
            "unrelated_future": {"kept": True},
        },
    )
    return tmp_path


def test_optin_settings_persist_and_survive_restart(profile):
    bridge = Bridge(None)
    try:
        assert bridge.translatedSubtitleLanguage == ""
        assert bridge.translatedSubtitleLabel == "Off"
        choices = bridge.subtitleLanguageChoices
        assert choices[0] == {"code": "", "label": "Off"}
        assert any(
            choice["code"] == "en" and "en" in choice["label"] for choice in choices
        )
        bridge.setTranslatedSubtitleLanguage("en.*")
        assert bridge.translatedSubtitleLanguage == ""
        bridge.setTranslatedSubtitleLanguage("en")
        assert bridge.translatedSubtitleLanguage == "en"
        assert any(
            row["label"] == "Translated subtitles" and row["value"] == "en"
            for row in bridge.forgeSelectedFacts["rows"]
        )
        bridge._save_preferences()
    finally:
        bridge.close()
    saved = load_settings(settings_file_path())
    assert saved["translated_subtitle_language"] == "en"
    assert saved["embed_metadata"] is True
    assert saved["unrelated_future"] == {"kept": True}
    restored = Bridge(None)
    try:
        assert restored.translatedSubtitleLanguage == "en"
        restored.setTranslatedSubtitleLanguage("")
        restored._save_preferences()
    finally:
        restored.close()
    assert load_settings(settings_file_path())["translated_subtitle_language"] is None


def test_real_qml_setting_binding_loads(profile):
    bridge = Bridge(None)
    engine = create_engine(bridge)
    try:
        window = engine.rootObjects()[0]
        button = window.findChild(QObject, "translatedSubtitleButton")
        assert button is not None
        assert button.property("label") == "Off"
        bridge.setTranslatedSubtitleLanguage("en")
        for _ in range(10):
            _APP.processEvents()
        assert button.property("label") == bridge.translatedSubtitleLabel
        menu = window.findChild(QObject, "translatedSubtitleMenu")
        assert menu is not None
    finally:
        for window in engine.rootObjects():
            window.close()
        engine.deleteLater()
        bridge.close()
        _APP.processEvents()


def test_runtime_admission_preserves_explicit_language(profile, monkeypatch):
    from yt_downloader.qt_quick.runtime import DownloadRuntime

    runtime = DownloadRuntime()
    monkeypatch.setattr(runtime, "start_job", lambda job: job)
    try:
        job = runtime.start(
            "https://www.youtube.com/watch?v=abcdefghijk",
            profile,
            "MP4",
            "Streaming",
            translated_subtitle_language="en",
        )
        assert job.translated_subtitle_language == "en"
        audio = runtime.prepare_job(
            "https://www.youtube.com/watch?v=abcdefghijk",
            profile,
            "MP3",
            "Streaming",
            translated_subtitle_language="en",
        )
        assert audio.translated_subtitle_language is None
    finally:
        runtime.close()
