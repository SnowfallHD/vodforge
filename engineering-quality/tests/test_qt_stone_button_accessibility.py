"""The shared QML button must expose its actual action to assistive input."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QCoreApplication, QEvent, QUrl
from PySide6.QtGui import QAccessible, QAccessibleActionInterface, QGuiApplication
from PySide6.QtQuickControls2 import QQuickStyle

from yt_downloader.qt_quick.main import Bridge, create_engine


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
        assert buttons["Play"].state().invisible
        # The Run Deck replaced the old idle "Ready" button with status text;
        # Download remains the reachable idle action.
        assert not buttons["Download"].state().disabled
        buttons["Library"].actionInterface().doAction(
            QAccessibleActionInterface.pressAction()
        )
        assert bridge.selection == "Library"
        application.processEvents()
        library_nav = next(
            child for name, child in buttons.items() if name.startswith("All Media  ")
        )
        assert not library_nav.state().invisible
        buttons["Watch"].actionInterface().doAction(
            QAccessibleActionInterface.pressAction()
        )
        application.processEvents()
        assert bridge.selection == "Watch"
        assert buttons["Play"].state().invisible
        # Browsing precedes playback in the port. Expose transport sliders only
        # when a media source has opened, while retaining their AX names.
        bridge._playback_url = QUrl.fromLocalFile(str(tmp_path / "fixture.mp4"))
        bridge.playbackUrlChanged.emit()
        application.processEvents()
        sliders = {
            child.text(QAccessible.Name)
            for index in range(window.childCount())
            if (child := window.child(index)) is not None
            and child.role() == QAccessible.Slider
            and not child.state().invisible
        }
        assert {"Playback position", "Volume"} <= sliders
    finally:
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        application.processEvents()
        bridge.close()
