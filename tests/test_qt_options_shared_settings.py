"""Quick Options and Settings bind the same existing preference owner."""

import json

import pytest
from PySide6.QtCore import QMetaObject, QObject, QPointF, Qt
from PySide6.QtTest import QTest

from tests.test_qt_interaction_invariants import _close, _launch
from tests.test_qt_scene_port import polish_scene, visual_item
from yt_downloader.settings_store import load_settings


def _subtitle_anchor_geometry(button, viewport):
    point = button.mapToItem(viewport, QPointF(0, 0))
    return {
        "anchor": [point.x(), point.y(), button.width(), button.height()],
        "viewport": [viewport.width(), viewport.height()],
        "contentY": viewport.property("contentY"),
        "contentHeight": viewport.property("contentHeight"),
    }


def _scroll_subtitle_button_into_view(app, root, button, viewport):
    polish_scene(root)
    app.processEvents()
    point = button.mapToItem(viewport, QPointF(0, button.height() / 2))
    maximum = max(0, viewport.property("contentHeight") - viewport.height())
    viewport.setProperty(
        "contentY",
        min(
            maximum,
            max(0, viewport.property("contentY") + point.y() - viewport.height() / 2),
        ),
    )
    polish_scene(root)
    app.processEvents()
    geometry = _subtitle_anchor_geometry(button, viewport)
    x, y, width, height = geometry["anchor"]
    assert width > 0 and height > 0 and button.isVisible() and button.isEnabled(), (
        geometry
    )
    assert 0 <= x + width / 2 < viewport.width(), geometry
    assert 0 <= y and y + height <= viewport.height(), geometry
    return geometry


@pytest.mark.parametrize("size", [(1100, 740), (820, 560)])
@pytest.mark.parametrize("custom", [False, True])
@pytest.mark.parametrize("reduced_motion", [False, True])
def test_options_subtitle_menu_remains_open_in_its_scroll_owner(
    tmp_path, monkeypatch, size, custom, reduced_motion
):
    from tests.test_qt_composer_custom_options import wait_for_reveal
    from yt_downloader.qt_quick import main

    monkeypatch.setattr(main, "_system_reduced_motion", lambda: reduced_motion)
    app, bridge, engine, window = _launch(tmp_path, monkeypatch, [])
    geometry = {}
    try:
        window.resize(*size)
        if custom:
            bridge.setExportMode("Manual Override")
        popup = window.findChild(QObject, "optionsMenu")
        popup.open()
        wait_for_reveal(popup, 1 if custom else 0, "customReveal")
        body = window.findChild(
            QObject,
            "composerExtrasScroll"
            if popup.property("sideBySideExtras")
            else "composerOptionsScroll",
        )
        viewport = body.property("contentItem")
        polish_scene(popup.property("contentItem"))
        app.processEvents()
        viewport.setProperty(
            "contentY", max(0, viewport.property("contentHeight") - viewport.height())
        )
        app.processEvents()
        button = window.findChild(QObject, "composerTranslatedSubtitleButton")
        geometry["bottom_before_targeting"] = _subtitle_anchor_geometry(
            button, viewport
        )
        geometry["trigger"] = _scroll_subtitle_button_into_view(
            app, popup.property("contentItem"), button, viewport
        )
        QTest.mouseClick(
            window,
            Qt.LeftButton,
            pos=button.mapToScene(
                QPointF(button.width() / 2, button.height() / 2)
            ).toPoint(),
        )
        QTest.qWait(150)
        menu = window.findChild(QObject, "translatedSubtitleMenu")
        assert menu.property("visible")
        assert menu.property("scrollViewport") == body
        assert not window.findChild(QObject, "downloadSettingsPopup").property(
            "visible"
        )
        choice = visual_item(
            menu.property("contentItem"), "translatedSubtitleChoice_el"
        )
        choice_viewport = choice.parentItem()
        while choice_viewport.property("contentY") is None:
            choice_viewport = choice_viewport.parentItem()
            assert choice_viewport is not None
        geometry["choice"] = _scroll_subtitle_button_into_view(
            app, menu.property("contentItem"), choice, choice_viewport
        )
        QTest.mouseClick(
            window,
            Qt.LeftButton,
            pos=choice.mapToScene(
                QPointF(choice.width() / 2, choice.height() / 2)
            ).toPoint(),
        )
        app.processEvents()
        assert bridge.translatedSubtitleLanguage == "el"
        assert "Greek" in button.property("label")
        assert not menu.property("visible")
        geometry["reopen_trigger"] = _scroll_subtitle_button_into_view(
            app, popup.property("contentItem"), button, viewport
        )
        QTest.mouseClick(
            window,
            Qt.LeftButton,
            pos=button.mapToScene(
                QPointF(button.width() / 2, button.height() / 2)
            ).toPoint(),
        )
        QTest.qWait(150)
        assert menu.property("visible")
        menu.close()
        popup.close()
        print(
            "SUBTITLE_GEOMETRY "
            + json.dumps({"size": size, "custom": custom, **geometry})
        )
    except Exception:
        (tmp_path / "subtitle-menu-geometry.json").write_text(
            json.dumps(geometry, indent=2)
        )
        print("SUBTITLE_FAILURE_GEOMETRY " + json.dumps(geometry))
        raise
    finally:
        _close(bridge, engine, window)


@pytest.mark.parametrize("size", [(1400, 900), (1100, 740), (820, 560)])
def test_options_retains_quick_surface_and_reaches_shared_controls(
    tmp_path, monkeypatch, size
):
    app, bridge, engine, window = _launch(tmp_path, monkeypatch, [])
    try:
        window.resize(*size)
        popup = window.findChild(QObject, "optionsMenu")
        settings = window.findChild(QObject, "downloadSettingsPopup")
        body = window.findChild(QObject, "composerExtrasScroll")
        tags = window.findChild(QObject, "composerExtraTagsInput")
        popup.open()
        QTest.qWait(100)
        assert popup.property("visible")
        assert not settings.property("visible")
        assert body.isVisible() and tags.isVisible()
        assert not window.findChild(QObject, "settingsBodyViewport").isVisible()
        assert popup.property("customReveal") == 0
        assert popup.property("width") == pytest.approx(
            min(3 * 250 + 2 * 16 + 16, size[0] - 40)
        )
        assert popup.property("topPadding") == 8
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


@pytest.mark.parametrize("size", [(900, 560), (1100, 740), (1400, 900)])
@pytest.mark.parametrize("custom", [False, True])
def test_options_places_groups_by_available_width(tmp_path, monkeypatch, size, custom):
    from tests.test_qt_composer_custom_options import wait_for_reveal

    _app, bridge, engine, window = _launch(tmp_path, monkeypatch, [])
    try:
        window.resize(*size)
        popup = window.findChild(QObject, "optionsMenu")
        popup.open()
        bridge.setExportMode("Manual Override" if custom else "Everyday")
        wait_for_reveal(popup, int(custom), "customReveal")
        QTest.qWait(40)
        mode = visual_item(window.contentItem(), "composerOutputModes")
        quality = visual_item(window.contentItem(), "composerQualities")
        extras = visual_item(window.contentItem(), "composerQuickExtras")
        manual = visual_item(window.contentItem(), "customOptionsColumn")

        def point(item, x=0, y=0):
            return item.mapToScene(QPointF(x, y))

        assert popup.property("topPadding") == 8
        assert point(mode).y() - popup.property("y") <= 10
        assert point(quality).x() >= point(mode, mode.width()).x() + 15
        enough = (
            size[0] - 40
            >= 4 * popup.property("columnMinimum")
            + 3 * popup.property("columnGap")
            + 16
        )
        side_by_side = not custom or enough
        assert popup.property("sideBySideExtras") == side_by_side
        if side_by_side:
            assert point(extras).x() >= point(quality, quality.width()).x() + 15
            assert abs(point(extras).y() - point(mode).y()) < 1
            assert window.findChild(QObject, "composerExtrasScroll").isVisible()
        else:
            right = window.findChild(QObject, "composerOptionsScroll")
            assert manual.width() == pytest.approx(right.width(), abs=1)
            assert point(extras).x() == pytest.approx(point(mode).x(), abs=1)
            assert point(extras).y() > point(mode).y() + 339
            assert not window.findChild(QObject, "composerExtrasScroll").isVisible()
        if custom:
            assert manual.isVisible()
            assert point(mode).x() >= point(manual, manual.width()).x() + 15
        for item in (mode, quality, extras):
            assert item.width() > 100
            assert (
                point(item, item.width()).x()
                <= popup.property("x") + popup.property("width") - 7
            )
        assert not window.findChild(QObject, "downloadSettingsPopup").property(
            "visible"
        )
    finally:
        _close(bridge, engine, window)


@pytest.mark.parametrize("touchpad", [False, True])
def test_custom_resize_relocates_extras_and_keeps_scroll_owners_independent(
    tmp_path, monkeypatch, touchpad
):
    from tests.test_qt_composer_custom_options import wait_for_reveal
    from tests.test_qt_watch_scroll_extent import gesture

    _app, bridge, engine, window = _launch(tmp_path, monkeypatch, [])
    try:
        popup = window.findChild(QObject, "optionsMenu")
        bridge.setExportMode("Manual Override")
        window.resize(1400, 900)
        popup.open()
        wait_for_reveal(popup, 1, "customReveal")
        QTest.qWait(40)
        extras = visual_item(window.contentItem(), "composerQuickExtras")
        wide_parent = extras.parentItem()
        assert popup.property("sideBySideExtras")
        window.resize(900, 560)
        QTest.qWait(100)
        assert not popup.property("sideBySideExtras")
        assert extras.parentItem() is not wide_parent
        left = window.findChild(QObject, "composerManualScroll").property("contentItem")
        right = window.findChild(QObject, "composerOptionsScroll").property(
            "contentItem"
        )
        preset = window.findChild(QObject, "composerManualMp4").findChild(
            QObject, "manualPresetSelector"
        )
        preset.setProperty("expanded", True)
        wait_for_reveal(preset, 1)
        QTest.qWait(40)
        assert left.property("contentHeight") > left.height()
        assert right.property("contentHeight") > right.height()
        left.setProperty("contentY", 0)
        right.setProperty("contentY", 0)
        gesture(
            window, left.mapToScene(QPointF(4, left.height() / 2)), touchpad=touchpad
        )
        assert left.property("contentY") > 0
        assert right.property("contentY") == 0
        left_before = left.property("contentY")
        gesture(
            window, right.mapToScene(QPointF(4, right.height() / 2)), touchpad=touchpad
        )
        assert right.property("contentY") > 0
        assert left.property("contentY") == pytest.approx(left_before)
        right.setProperty("contentY", right.property("contentHeight") - right.height())
        QTest.qWait(30)
        tags = visual_item(window.contentItem(), "composerExtraTagsInput")
        bottom = tags.mapToItem(right, QPointF(0, tags.height())).y()
        assert 0 <= bottom <= right.height() + 1
        window.resize(1400, 900)
        QTest.qWait(100)
        assert popup.property("sideBySideExtras")
        assert extras.parentItem() is wide_parent
        for viewport in (left, right):
            assert (
                0
                <= viewport.property("contentY")
                <= max(0, viewport.property("contentHeight") - viewport.height()) + 1
            )
        assert len(window.findChildren(QObject, "composerExtraTagsInput")) == 1
    finally:
        _close(bridge, engine, window)
