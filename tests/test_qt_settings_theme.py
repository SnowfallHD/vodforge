"""Settings-only accent hierarchy uses the live selected theme."""

import os
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QEvent, QObject
from PySide6.QtGui import QColor

from tests.test_qt_scene_port import qt_app
from yt_downloader.qt_quick import main as qt_main
from yt_downloader.ui_theme import THEME, THEME_NAMES


def contrast(first, second):
    def luminance(value):
        channels = [int(value[i : i + 2], 16) / 255 for i in (1, 3, 5)]
        linear = [
            v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
            for v in channels
        ]
        return sum(v * weight for v, weight in zip(linear, (0.2126, 0.7152, 0.0722)))

    values = sorted((luminance(first), luminance(second)))
    return (values[1] + 0.05) / (values[0] + 0.05)


def test_settings_live_accent_and_neutral_copy(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    app = qt_app()
    bridge = qt_main.Bridge(None)
    engine = qt_main.create_engine(bridge)
    window = engine.rootObjects()[0]
    output = os.environ.get("VODFORGE_THEME_EVIDENCE_DIR")
    try:
        window.resize(1100, 900)
        settings = window.findChild(QObject, "downloadSettingsPopup")
        settings.open()
        for name in THEME_NAMES:
            assert bridge.setAppearance(name, "#00ff00")
            for _ in range(20):
                app.processEvents()
            for object_name in ("settingsProVod", "settingsProSuffix"):
                item = window.findChild(QObject, object_name)
                assert item.property("color") == QColor(THEME["accent"])
            assert window.findChild(QObject, "settingsProForge").property(
                "color"
            ) == QColor(THEME["text"])
            headings = [
                item
                for item in settings.findChildren(QObject)
                if item.property("text")
                in (
                    "SAVE LOCATION",
                    "BATCH AND PLAYLISTS",
                    "YOUTUBE ACCESS",
                    "METADATA",
                    "MP4 VIDEO",
                    "MP4 OPTIONS",
                    "MP3 AUDIO",
                    "ORIGINAL AUDIO",
                    "APPEARANCE",
                    "PRIVACY",
                    "ENCODING",
                    "EMBED IN MP4",
                    "SAVE ALONGSIDE MP4",
                )
            ]
            assert len(headings) >= 10
            assert all(
                item.property("color") == QColor(THEME["accent"]) for item in headings
            )
            help_text = next(
                item
                for item in settings.findChildren(QObject)
                if item.property("text")
                == "Every option is available here; the main workspace stays focused."
            )
            assert help_text.property("color") == QColor(THEME["muted"])
            assert contrast(THEME["accent"], THEME["surface_2"]) >= 4.5
            frame = window.grabWindow()
            assert not frame.isNull()
            if output:
                Path(output).mkdir(parents=True, exist_ok=True)
                assert frame.save(str(Path(output) / (name.replace(" ", "-") + ".png")))
    finally:
        window.close()
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        bridge.close()
