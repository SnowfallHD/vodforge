"""The shared QML button must expose its actual action to assistive input."""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QCoreApplication, QEvent, QObject, QPoint, QPointF, QUrl
from PySide6.QtGui import QAccessible, QAccessibleActionInterface, QGuiApplication
from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest

from tests.test_run_identity import make_job
from yt_downloader.qt_quick.main import Bridge, create_engine


def accessible_descendants(root):
    for index in range(root.childCount()):
        child = root.child(index)
        if child is None:
            continue
        yield child
        yield from accessible_descendants(child)


def hover_embedded_video(window_object) -> None:
    """Use real offscreen hit geometry to reveal the intentionally hover-only AX controls."""
    QTest.qWait(100)
    surface = window_object.findChild(QObject, "watchVideoSurface")
    assert surface is not None
    assert surface.isVisible() and surface.width() > 0 and surface.height() > 0
    point = surface.mapToScene(QPointF(surface.width() / 2, surface.height() / 2))
    assert 0 <= point.x() < window_object.width()
    assert 0 <= point.y() < window_object.height()
    overlay = window_object.findChild(QObject, "embeddedPlayerOverlay")
    # Each new window must receive an actual leave/enter transition even when
    # a previous test left the process-wide pointer at the same hit position.
    # Wait for the observed hover state instead of assuming an 80 ms schedule.
    QTest.mouseMove(window_object, QPoint(-20, -20))
    deadline = time.monotonic() + 2
    while overlay.property("controlsShown") and time.monotonic() < deadline:
        QTest.qWait(10)
    assert not overlay.property("controlsShown")
    QTest.mouseMove(window_object, QPoint(round(point.x()), round(point.y())))
    deadline = time.monotonic() + 2
    while not overlay.property("controlsShown") and time.monotonic() < deadline:
        QTest.qWait(10)
        # Layout and popup teardown can move the hit target after the first
        # event. Send adjacent in-surface moves through ordinary window routing;
        # never assign handler/overlay state or bypass hit testing.
        point = surface.mapToScene(QPointF(surface.width() / 2, surface.height() / 2))
        QTest.mouseMove(window_object, QPoint(round(point.x()) + 1, round(point.y())))
        QTest.mouseMove(window_object, QPoint(round(point.x()), round(point.y())))
    assert overlay.property("controlsShown"), {
        "surface_scene_center": (point.x(), point.y()),
        "surface_size": (surface.width(), surface.height()),
        "surface_visible": surface.isVisible(),
        "presentation_available": overlay.property("presentationAvailable"),
        "surface_hovered": overlay.property("surfaceHovered"),
        "window_visible": window_object.isVisible(),
        "window_exposed": window_object.isExposed(),
    }


def test_stone_buttons_expose_named_press_actions_and_hide_other_views(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    application = QGuiApplication.instance() or QGuiApplication([])
    if QQuickStyle.name() != "Basic":
        QQuickStyle.setStyle("Basic")
    bridge = Bridge(None)
    engine = create_engine(bridge)
    try:
        assert engine.rootObjects()
        application.processEvents()
        window = QAccessible.queryAccessibleInterface(engine.rootObjects()[0])
        assert window is not None
        # Basic controls may expose nested accessible wrappers. Find the real
        # named buttons recursively; prefer a visible instance over a hidden alias.
        buttons = {}
        for child in accessible_descendants(window):
            if child.role() != QAccessible.Button:
                continue
            name = child.text(QAccessible.Name)
            if name not in buttons or buttons[name].state().invisible:
                buttons[name] = child
        for label in ("Forge", "Library", "Watch", "Activity", "Settings", "Download"):
            assert label in buttons
            assert not buttons[label].state().invisible
            actions = buttons[label].actionInterface()
            assert actions is not None
            assert QAccessibleActionInterface.pressAction() in actions.actionNames()
        assert "Play" not in buttons or buttons["Play"].state().invisible
        # The Run Deck replaced the old idle "Ready" button with status text;
        # Download remains the reachable idle action.
        assert not buttons["Download"].state().disabled
        buttons["Settings"].actionInterface().doAction(
            QAccessibleActionInterface.pressAction()
        )
        application.processEvents()
        pro = next(
            child
            for child in accessible_descendants(window)
            if child.role() == QAccessible.Button
            and child.text(QAccessible.Name) == "VODForge PRO"
            and not child.state().invisible
        )
        assert pro.actionInterface() is not None
        assert pro.rect().intersects(window.rect())
        help_button = next(
            child
            for child in accessible_descendants(window)
            if child.role() == QAccessible.Button
            and child.text(QAccessible.Name) == "Help"
            and not child.state().invisible
        )
        assert help_button.actionInterface() is not None
        done = next(
            child
            for child in accessible_descendants(window)
            if child.role() == QAccessible.Button
            and child.text(QAccessible.Name) == "Done"
            and not child.state().invisible
        )
        done.actionInterface().doAction(QAccessibleActionInterface.pressAction())
        application.processEvents()
        buttons["Library"].actionInterface().doAction(
            QAccessibleActionInterface.pressAction()
        )
        assert bridge.selection == "Library"
        application.processEvents()
        library_nav = next(
            child
            for child in accessible_descendants(window)
            if child.role() == QAccessible.Button
            and child.text(QAccessible.Name).startswith("All Media, ")
        )
        assert not library_nav.state().invisible
        buttons["Watch"].actionInterface().doAction(
            QAccessibleActionInterface.pressAction()
        )
        application.processEvents()
        assert bridge.selection == "Watch"
        assert "Play" not in buttons or buttons["Play"].state().invisible
        # Browsing precedes playback in the port. Expose transport sliders only
        # when a media source has opened, while retaining their AX names.
        bridge._playback_url = QUrl.fromLocalFile(str(tmp_path / "fixture.mp4"))
        bridge.playbackUrlChanged.emit()
        application.processEvents()
        hover_embedded_video(engine.rootObjects()[0])
        transport = [
            child
            for child in accessible_descendants(window)
            if child.role() == QAccessible.Button
            and child.text(QAccessible.Name) == "Play"
        ]
        assert any(not child.state().invisible for child in transport)
        sliders = {
            child.text(QAccessible.Name)
            for child in accessible_descendants(window)
            if child.role() == QAccessible.Slider and not child.state().invisible
        }
        assert {"Playback position", "Volume"} <= sliders
    finally:
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        application.processEvents()
        bridge.close()


def test_compact_header_and_player_transport_stay_inside_minimum_window(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    application = QGuiApplication.instance() or QGuiApplication([])
    if QQuickStyle.name() != "Basic":
        QQuickStyle.setStyle("Basic")
    bridge = Bridge(None)
    engine = create_engine(bridge)
    try:
        window_object = engine.rootObjects()[0]
        window_object.resize(820, 560)
        for _ in range(5):
            application.processEvents()
        window = QAccessible.queryAccessibleInterface(window_object)
        assert window is not None

        def visible_button(name: str):
            return next(
                child
                for child in accessible_descendants(window)
                if child.role() == QAccessible.Button
                and child.text(QAccessible.Name) == name
                and not child.state().invisible
            )

        def inside(button) -> bool:
            bounds = button.rect()
            frame = window.rect()
            return (
                bounds.left() >= frame.left()
                and bounds.top() >= frame.top()
                and bounds.right() <= frame.right()
                and bounds.bottom() <= frame.bottom()
            )

        for name in ("Forge", "Library", "Watch", "Activity", "Settings"):
            assert inside(visible_button(name)), name
        for name in ("focusHeader", "forgeScene", "forgeCommandRow", "forgeLocalRow"):
            item = window_object.findChild(QObject, name)
            assert item is not None, name
            origin = item.mapToScene(QPointF(0, 0))
            assert (
                origin.x() >= 0 and origin.x() + item.width() <= window_object.width()
            ), name
        for name in (
            "forgeUrlField",
            "forgeOptionsButton",
            "forgeDownloadButton",
            "forgeLoadListButton",
            "forgeDestinationField",
            "forgeCreateVideoButton",
        ):
            item = window_object.findChild(QObject, name)
            assert item is not None, name
            origin = item.mapToScene(QPointF(0, 0))
            assert (
                origin.x() >= 0 and origin.x() + item.width() <= window_object.width()
            ), name
        for name in ("Forge", "Library", "Watch", "Activity"):
            bounds = visible_button(name).rect()
            assert bounds.height() == 44, name
            assert bounds.width() >= 86, name
        bridge.select("Library")
        bridge.navigateLibrary("folders")
        for _ in range(5):
            application.processEvents()
        for name in (
            "My Files",
            "All media",
            "Issues & Recovery",
            "Parent folder",
            "← Library",
        ):
            assert inside(visible_button(name)), name
        bridge.navigateLibrary("home")
        bridge.select("Forge")
        media = tmp_path / "fixture.mp4"
        media.write_bytes(b"fixture")
        bridge._runtime.history = [
            {
                "id": "fixture",
                "title": "Fixture",
                "channel": "Channel",
                "vodforge_output_dir": str(tmp_path),
                "vodforge_output_path": str(media),
                "vodforge_output_type": "MP4",
            }
        ]
        bridge.historyChanged.emit()
        bridge._runtime.active_job = make_job(tmp_path)
        bridge.runDeckChanged.emit()
        for _ in range(5):
            application.processEvents()
        assert inside(visible_button("All 2 runs"))
        bridge._runtime.active_job = None
        bridge.runDeckChanged.emit()
        assert bridge.openLibraryItem(0)
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            application.processEvents()
            player = window_object.property("mediaPlayer")
            if player and player.mediaStatus() == QMediaPlayer.InvalidMedia:
                break
            time.sleep(0.01)
        assert player.mediaStatus() == QMediaPlayer.InvalidMedia
        for _ in range(5):
            application.processEvents()
        assert inside(visible_button("← Back"))
        hover_embedded_video(window_object)
        assert inside(visible_button("Play"))
    finally:
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        application.processEvents()
        bridge.close()
