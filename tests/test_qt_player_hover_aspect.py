"""Floating controls and client geometry follow hover and displayed video."""

import pytest
from PySide6.QtCore import QObject, QPoint
from PySide6.QtTest import QTest

from tests.test_qt_floating_player_chrome import player_scene  # noqa: F401


def flush(app):
    for _ in range(12):
        app.processEvents()


def test_immediate_hover_and_menu_retention(player_scene):  # noqa: F811
    app, _, scene, floating = player_scene
    scene.setProperty("presentationMode", "floating")
    flush(app)
    overlay = floating.findChild(QObject, "presentationPlayerOverlay")
    QTest.mouseMove(floating, QPoint(100, 100))
    flush(app)
    assert overlay.isVisible()
    # Crossing the window boundary hides immediately; no three-second timer.
    QTest.mouseMove(floating, QPoint(-20, -20))
    flush(app)
    assert not overlay.isVisible()
    overlay.setProperty("menuOpen", True)
    flush(app)
    assert overlay.isVisible()
    overlay.setProperty("menuOpen", False)
    flush(app)
    assert not overlay.isVisible()
    seek = overlay.findChild(QObject, "playerOverlaySeek")
    seek.forceActiveFocus()
    flush(app)
    assert overlay.isVisible()


@pytest.mark.parametrize("width", [440, 450, 659, 660, 900])
def test_minimum_size_keeps_control_hit_rows_disjoint(player_scene, width):  # noqa: F811
    app, _, scene, floating = player_scene
    scene.setProperty("presentationMode", "floating")
    floating.resize(width, 300)
    flush(app)
    overlay = floating.findChild(QObject, "presentationPlayerOverlay")
    left = overlay.findChild(QObject, "playerOverlayLeftActions")
    right = overlay.findChild(QObject, "playerOverlayRightActions")
    assert floating.width() >= overlay.property("minimumControlsWidth")
    assert left.x() + left.width() + 12 <= right.x()
    assert floating.height() >= overlay.height()


def test_chapter_segments_titles_and_continuous_seek(player_scene):  # noqa: F811
    from PySide6.QtCore import Property, Qt
    from PySide6.QtTest import QSignalSpy

    class Timeline(QObject):
        duration = Property(int, lambda self: 120000, constant=True)
        position = Property(int, lambda self: 45000, constant=True)
        playbackState = Property(int, lambda self: 2, constant=True)

    app, _, scene, floating = player_scene
    scene.setProperty("presentationMode", "floating")
    flush(app)
    overlay = floating.findChild(QObject, "presentationPlayerOverlay")
    timeline = Timeline()
    overlay.setProperty("player", timeline)
    overlay.setProperty("surfaceHovered", True)
    overlay.setProperty(
        "chapters",
        [
            {"start_time": 0, "end_time": 30, "title": "Opening"},
            {"start_time": 30, "end_time": 90, "title": "Middle"},
            {"start_time": 90, "end_time": 90.001, "title": "Tiny"},
            {"start_time": 100, "end_time": 120, "title": "Closing"},
        ],
    )
    flush(app)
    track = overlay.findChild(QObject, "playerChapterTrack")
    assert track.property("currentChapter") == "Middle"
    assert track.chapterAt(90.0005) == "Tiny"
    assert track.chapterAt(95) == ""
    overlay.setProperty("hoverSeconds", 105)
    flush(app)
    assert (
        overlay.findChild(QObject, "playerHoverChapterTitle").property("text")
        == "Closing"
    )
    segments = [
        item
        for item in track.childItems()
        if item.objectName() == "playerChapterSegment"
    ]
    assert len(segments) == 4
    assert all(segment.width() > 0 for segment in segments)
    seek = overlay.findChild(QObject, "playerOverlaySeek")
    spy = QSignalSpy(overlay.seekRequested)
    seek.forceActiveFocus()
    QTest.keyClick(floating, Qt.Key_Right)
    flush(app)
    assert spy.count() == 1
    assert spy.at(0)[0] == pytest.approx(seek.property("value") / 1000)
    # No chapter snapping: the selected value is not a chapter boundary.
    assert spy.at(0)[0] not in {0, 30, 90, 100, 120}
    overlay.setProperty("player", None)
    flush(app)
    assert track.property("segments").toVariant() == []
