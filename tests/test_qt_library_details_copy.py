"""Annotation copy wiring and tag mutation feedback in an offscreen scene."""

import pytest
from PySide6.QtCore import (
    QCoreApplication,
    QEvent,
    QMetaObject,
    QObject,
    QPointF,
    QRectF,
    Qt,
)
from PySide6.QtTest import QTest

from tests.test_qt_library_window_model import cards, visual_descendants
from tests.test_qt_scene_port import qt_app, saved
from yt_downloader.qt_quick import main


@pytest.fixture
def detail(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    app = qt_app()
    bridge = main.Bridge(None)
    bridge._engagement.presented_welcome()
    bridge._runtime.history = [saved(tmp_path, "Saved", "MP4")]
    bridge.select("Library")
    bridge.navigateLibrary("all")
    owner = bridge.libraryScene["media"][0]["owner"]
    assert bridge.openLibraryDetails(owner)
    engine = main.create_engine(bridge)
    window = engine.rootObjects()[0]
    window.resize(1400, 1000)
    window.show()
    window.requestActivate()
    QTest.qWait(30)
    for _ in range(3):
        app.processEvents()
    yield app, bridge, owner, engine, window
    window.close()
    engine.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    bridge.close()


def test_distinct_copy_controls_use_annotations_and_displayed_note_without_save(
    detail, monkeypatch
):
    app, bridge, owner, _engine, window = detail
    tags = window.findChild(QObject, "libraryCopyTagsButton")
    note = window.findChild(QObject, "libraryCopyNoteButton")
    editor = window.findChild(QObject, "libraryNoteInput")
    clipboard = app.clipboard()
    clipboard.setText("sentinel")
    assert not tags.property("enabled")
    assert not note.property("enabled")
    assert not bridge.copyLibraryText(owner, "tags")
    assert clipboard.text() == "sentinel"
    assert bridge.editLibraryTag(owner, "first", False)
    assert bridge.editLibraryTag(owner, "second", False)
    editor.setProperty("text", "Saved note")
    assert bridge.saveLibraryNote(owner, "Saved note")
    for _ in range(3):
        app.processEvents()
    assert tags.property("enabled") and note.property("enabled")
    assert "tags" in tags.property("accessibilityLabel")
    assert "note" in note.property("accessibilityLabel")
    assert QMetaObject.invokeMethod(tags, "activated")
    assert clipboard.text() == "first, second"
    assert tags.property("label") == "Copied"
    assert bridge.status == "Copied tags."
    editor.setProperty("text", "Unsaved note\nwith lines")
    snapshot = bridge._annotations.snapshot
    raw_history = [dict(row) for row in bridge._runtime.history]
    events = []
    monkeypatch.setattr(
        bridge, "_record_update_feature", lambda *args: events.append(args)
    )
    assert QMetaObject.invokeMethod(note, "activated")
    assert clipboard.text() == "Unsaved note\nwith lines"
    assert note.property("label") == "Copied"
    assert bridge.status == "Copied note."
    assert bridge._annotations.snapshot == snapshot
    assert bridge._runtime.history == raw_history
    assert not events
    assert bridge.libraryDetail["note"] == "Saved note"
    assert not bridge.copyLibraryText("stale-owner", "note", "wrong")
    assert not bridge.copyLibraryText(owner, "tags", "wrong")
    assert clipboard.text() == "Unsaved note\nwith lines"
    editor.setProperty("text", "")
    app.processEvents()
    assert not note.property("enabled")
    assert bridge.editLibraryTag(owner, "first", True)
    assert bridge.editLibraryTag(owner, "second", True)
    app.processEvents()
    assert not tags.property("enabled")


def test_tag_bursts_retain_unrelated_chips_and_preserve_real_press_feedback(detail):
    app, bridge, owner, engine, window = detail
    repeater = window.findChild(QObject, "libraryTagRepeater")
    for tag in ["first", "middle", "last"]:
        assert bridge.editLibraryTag(owner, tag, False)
    for _ in range(3):
        app.processEvents()
    before = cards(engine, repeater)
    for index in range(12):
        assert bridge.editLibraryTag(owner, f"tag{index}", False)
        for _ in range(3):
            app.processEvents()
        after = cards(engine, repeater)
        assert all(after[tag] == before[tag] for tag in before)
    for tag in ["first", "middle", *[f"tag{i}" for i in range(12)]]:
        last = cards(engine, repeater)["last"]
        assert bridge.editLibraryTag(owner, tag, True)
        for _ in range(3):
            app.processEvents()
        assert cards(engine, repeater)["last"] == last
    chip = next(
        item
        for item in visual_descendants(window.contentItem())
        if item.objectName() == "libraryTagChip" and item.isVisible()
    )
    viewport = window.findChild(QObject, "libraryDetailViewport")
    flickable = viewport.property("contentItem")
    relative_y = chip.mapToItem(viewport, 0, 0).y()
    flickable.setProperty(
        "contentY",
        max(
            0,
            min(
                flickable.property("contentHeight") - viewport.height(),
                flickable.property("contentY") + relative_y - viewport.height() / 2,
            ),
        ),
    )
    for _ in range(3):
        app.processEvents()
    point = chip.mapToScene(QPointF(chip.width() / 2, chip.height() / 2)).toPoint()
    QTest.mouseMove(window, QPointF(2, 2).toPoint())
    QTest.qWait(30)
    QTest.mouseMove(window, point)
    QTest.qWait(30)
    app.processEvents()
    assert chip.property("hovered")
    assert chip.property("emphasized")  # Flat accent hover remains visible.
    assert not chip.property("activeFace")
    face = next(
        item
        for item in chip.childItems()
        if item.metaObject().className().startswith("QQuickImage")
    )
    QTest.mousePress(window, Qt.LeftButton, Qt.NoModifier, point)
    app.processEvents()
    assert "/pressed/" in face.property("source").toString()
    # Release away from the chip must retire press without deleting the tag.
    away = QPointF(window.width() - 5, window.height() - 5).toPoint()
    QTest.mouseMove(window, away)
    QTest.qWait(30)
    QTest.mouseRelease(window, Qt.LeftButton, Qt.NoModifier, away)
    for _ in range(3):
        app.processEvents()
    assert bridge.libraryDetail["tags"] == ["last"]
    assert not chip.property("hovered")
    assert "/pressed/" not in face.property("source").toString()
    assert not window.grabWindow().isNull()


@pytest.mark.parametrize("width", [820, 1400])
@pytest.mark.parametrize("wrapped", [False, True])
def test_fact_copy_targets_do_not_add_row_gaps_or_clip_wrapped_values(
    detail, monkeypatch, width, wrapped, tmp_path
):
    app, bridge, _owner, _engine, window = detail
    projection = bridge.libraryDetail
    if wrapped:
        projection["source"] = [
            dict(row, value="https://example.test/" + "part/" * 60)
            if row["label"] == "Source URL"
            else row
            for row in projection["source"]
        ]
        projection["output"] = [
            dict(row, value="/tmp/" + "folder/" * 60)
            if row["label"] == "Saved Location"
            else row
            for row in projection["output"]
        ]
    monkeypatch.setattr(bridge, "_library_detail_projection", lambda *_: projection)
    bridge.historyChanged.emit()
    window.resize(width, 1000)
    for _ in range(5):
        app.processEvents()
    for section, label, next_label in [
        ("source", "Source URL", "Original Title"),
        ("output", "Saved Location", "Frame rate"),
    ]:
        row = next(
            item
            for item in visual_descendants(window.contentItem())
            if item.objectName() == f"libraryFactRow_{section}_{label}"
        )
        following = next(
            item
            for item in visual_descendants(window.contentItem())
            if item.objectName() == f"libraryFactRow_{section}_{next_label}"
        )
        texts = [
            item
            for item in row.childItems()
            if item.metaObject().className().startswith("QQuickText")
        ]
        assert row.height() == max(
            30, *(item.property("implicitHeight") for item in texts)
        )
        assert abs(following.y() - row.y() - row.height()) < 0.1
        button = next(
            item for item in row.childItems() if item.property("accessibilityLabel")
        )
        assert button.height() == 30  # Existing copy target remains usable.
        assert abs(button.y() - (row.height() - 30) / 2) < 0.1
        panel_column = row.parentItem()
        target_point = button.mapToItem(panel_column, 0, 0)
        target = QRectF(target_point, button.size())
        assert button.y() >= 0 and button.y() + button.height() <= row.height()
        for neighbor in panel_column.childItems():
            if neighbor is row or not neighbor.objectName().startswith(
                "libraryFactRow_"
            ):
                continue
            assert not target.intersects(QRectF(neighbor.position(), neighbor.size()))
        # Actual offscreen hit delivery at both target edges proves that the
        # copy action isn't limited to the smaller label/value row rectangle.
        viewport = window.findChild(QObject, "libraryDetailViewport")
        flickable = viewport.property("contentItem")
        relative_y = button.mapToItem(viewport, 0, 0).y()
        flickable.setProperty(
            "contentY",
            max(
                0,
                min(
                    flickable.property("contentHeight") - viewport.height(),
                    flickable.property("contentY") + relative_y - viewport.height() / 2,
                ),
            ),
        )
        for _ in range(3):
            app.processEvents()
        for y in [2, 28]:
            app.clipboard().setText("sentinel")
            point = button.mapToScene(QPointF(button.width() / 2, y)).toPoint()
            QTest.mouseMove(window, QPointF(2, 2).toPoint())
            QTest.qWait(20)
            QTest.mouseMove(window, point)
            QTest.qWait(20)
            QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, point)
            QTest.qWait(20)
            app.processEvents()
            if app.clipboard().text() == "sentinel":
                window.grabWindow().save(str(tmp_path / "hit-failure.png"))
            assert app.clipboard().text() != "sentinel", (
                str(tmp_path / "hit-failure.png"),
                button.property("hovered"),
                bridge.status,
                section,
                wrapped,
                width,
                y,
                point,
                button.isVisible(),
                button.mapToItem(viewport, 0, 0),
            )
        if wrapped:
            assert row.height() > 30
    assert not window.grabWindow().isNull()
