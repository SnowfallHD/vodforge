"""Quick Options and Settings bind the same existing preference owner."""

import pytest
from PySide6.QtCore import QMetaObject, QObject
from PySide6.QtTest import QTest

from tests.test_qt_interaction_invariants import _close, _launch
from tests.test_qt_scene_port import visual_item
from yt_downloader.settings_store import load_settings


@pytest.mark.parametrize("size", [(1400, 900), (1100, 740), (820, 560)])
def test_options_retains_quick_surface_and_reaches_shared_controls(
    tmp_path, monkeypatch, size
):
    app, bridge, engine, window = _launch(tmp_path, monkeypatch, [])
    try:
        window.resize(*size)
        popup = window.findChild(QObject, "optionsMenu")
        settings = window.findChild(QObject, "downloadSettingsPopup")
        body = window.findChild(QObject, "composerOptionsScroll")
        tags = window.findChild(QObject, "composerExtraTagsInput")
        popup.open()
        QTest.qWait(100)
        assert popup.property("visible")
        assert not settings.property("visible")
        assert body.isVisible() and tags.isVisible()
        assert not window.findChild(QObject, "settingsBodyViewport").isVisible()
        assert popup.property("customReveal") == 0
        assert popup.property("width") == pytest.approx(min(550, size[0] - 40))
        assert popup.property("height") <= size[1] - popup.property("y")
        for name in (
            "composerYouTubeAccessButton",
            "composerDownloadOption_embed_thumbnail",
            "composerDownloadOption_write_thumbnail",
            "composerDownloadOption_embed_metadata",
            "composerDownloadOption_write_info_json",
            "composerDownloadOption_use_nvenc",
        ):
            assert visual_item(window.contentItem(), name) is not None
        viewport = body.property("contentItem")
        assert viewport.property("contentWidth") <= viewport.width() + 1
        maximum = max(0, viewport.property("contentHeight") - viewport.height())
        viewport.setProperty("contentY", maximum)
        app.processEvents()
        assert viewport.property("contentY") == pytest.approx(maximum, abs=1)
        popup.close()
        settings.open()
        QTest.qWait(100)
        assert not body.isVisible() and not tags.isVisible()
        assert window.findChild(QObject, "settingsBodyViewport").isVisible()
        assert window.findChild(QObject, "settingsTitle").property("text") == "Settings"
        assert len(window.findChildren(QObject, "extraTagsInput")) == 1
    finally:
        _close(bridge, engine, window)


def test_options_toggles_shared_preferences_without_changing_active_job(
    tmp_path, monkeypatch
):
    from tests.test_run_identity import make_job

    app, bridge, engine, window = _launch(tmp_path, monkeypatch, [])
    try:
        active = make_job(tmp_path)
        bridge._runtime.active_job = active
        before = active.embed_thumbnail, active.write_thumbnail, active.embed_metadata
        popup = window.findChild(QObject, "optionsMenu")
        popup.open()
        QTest.qWait(100)
        expected = {}
        for key in (
            "embed_thumbnail",
            "write_thumbnail",
            "embed_metadata",
            "write_info_json",
        ):
            expected[key] = not bridge.downloadOptions[key]
            assert QMetaObject.invokeMethod(
                visual_item(window.contentItem(), "composerDownloadOption_" + key),
                "activated",
            )
            app.processEvents()
            assert bridge.downloadOptions[key] == expected[key]
        bridge._save_preferences()
        assert all(
            load_settings(bridge._settings_path)[key] == value
            for key, value in expected.items()
        )
        assert (
            active.embed_thumbnail,
            active.write_thumbnail,
            active.embed_metadata,
        ) == before
        assert popup.property("visible")
    finally:
        _close(bridge, engine, window)


def test_youtube_access_returns_to_options_without_reading_browser_store(
    tmp_path, monkeypatch
):
    app, bridge, engine, window = _launch(tmp_path, monkeypatch, [])
    try:
        popup = window.findChild(QObject, "optionsMenu")
        popup.open()
        QTest.qWait(100)
        assert QMetaObject.invokeMethod(
            window.findChild(QObject, "composerYouTubeAccessButton"), "activated"
        )
        app.processEvents()
        access = window.findChild(QObject, "youtubeAccessPopup")
        assert access.property("visible") and not popup.property("visible")
        bridge.setCookieSource("Browser")
        bridge.setCookieBrowser("Firefox")
        bridge.setCookieSource("cookies.txt")
        assert bridge.cookieSource == "cookies.txt"
        access.close()
        QTest.qWait(100)
        assert popup.property("visible")
        assert (
            window.findChild(QObject, "composerYouTubeAccessButton")
            .property("label")
            .endswith("cookies.txt")
        )
    finally:
        _close(bridge, engine, window)
