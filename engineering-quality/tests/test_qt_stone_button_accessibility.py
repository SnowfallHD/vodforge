"""The shared QML button must expose its actual action to assistive input."""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QCoreApplication, QEvent, QObject, QPointF, QUrl
from PySide6.QtGui import QAccessible, QAccessibleActionInterface, QGuiApplication
from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtQuickControls2 import QQuickStyle

from yt_downloader.qt_quick.main import Bridge, create_engine


def accessible_descendants(root):
    for index in range(root.childCount()):
        child = root.child(index)
        if child is None:
            continue
        yield child
        yield from accessible_descendants(child)


def test_stone_buttons_expose_named_press_actions_and_hide_other_views(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    application = QGuiApplication.instance() or QGuiApplication([])
    QQuickStyle.setStyle("Basic")
    bridge = Bridge(None)
    engine = create_engine(bridge)
    try:
        assert engine.rootObjects()
        application.processEvents()
        window = QAccessible.queryAccessibleInterface(engine.rootObjects()[0])
        assert window is not None
        buttons = {
            child.text(QAccessible.Name): child
            for index in range(window.childCount())
            if (child := window.child(index)) is not None
            and child.role() == QAccessible.Button
        }
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
            child for name, child in buttons.items() if name.startswith("All Media, ")
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
        for name in ("Folders", "All media", "Runs & previews", "Back to Library"):
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
        for _ in range(5):
            application.processEvents()
        assert inside(visible_button("All 1 runs"))
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
        assert inside(visible_button("Back to Watch"))
        assert inside(visible_button("Play"))
    finally:
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        application.processEvents()
        bridge.close()
