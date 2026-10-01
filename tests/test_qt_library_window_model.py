"""Card lifetime and viewport admission regressions, not visual certification."""

import math

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QObject
from PySide6.QtQml import QQmlExpression
from shiboken6 import getCppPointer

from tests.test_qt_scene_port import qt_app, saved
from yt_downloader.qt_quick import main
from yt_downloader.qt_quick.library_window_model import LibraryWindowModel


def cards(engine, repeater):
    result = {}
    for index in range(repeater.property("count")):
        expression = QQmlExpression(engine.rootContext(), repeater, f"itemAt({index})")
        item, _undefined = expression.evaluate()
        value = item.property("modelData")
        row = value.toVariant() if hasattr(value, "toVariant") else value
        result[row["owner"]] = getCppPointer(item)[0]
    return result


def visual_descendants(item):
    yield item
    for child in item.childItems():
        yield from visual_descendants(child)


def test_window_model_edges_reorder_updates_and_ambiguous_owner(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    qt_app()
    model = LibraryWindowModel()
    resets = []
    model.modelReset.connect(lambda: resets.append(True))
    rows = [{"owner": str(index), "title": str(index)} for index in range(8)]
    model.replace(rows[:6])
    model.replace(rows[2:])
    assert [model.data(model.index(i), 256) for i in range(6)] == rows[2:]
    updated = [dict(rows[7], title="New title"), *rows[2:7]]
    model.replace(updated)
    assert [model.data(model.index(i), 256) for i in range(6)] == updated
    assert not resets
    with pytest.raises(ValueError, match="unique"):
        model.replace([rows[0], rows[0]])
    assert model.rowCount() == 6
    model.replace([])
    assert model.rowCount() == 0


@pytest.mark.parametrize(
    "scene_name, route, flow_name, repeater_name",
    [
        ("Library", "all", "libraryMediaFlow", "libraryMediaRepeater"),
        ("Library", "channels", "libraryGroupFlow", "libraryGroupRepeater"),
        ("Watch", "videos", "watchMediaFlow", "watchMediaRepeater"),
        ("Watch", "channels", "watchGroupFlow", "watchGroupRepeater"),
    ],
)
def test_row_window_retains_surviving_cards_and_responsive_buffer(
    tmp_path, monkeypatch, scene_name, route, flow_name, repeater_name
):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    app = qt_app()
    bridge = main.Bridge(None)
    bridge._runtime.history = [
        dict(
            saved(tmp_path, f"Item {i:03d}", "MP4"),
            channel=f"Channel {i:03d}",
            playlist_id=f"list-{i}",
        )
        for i in range(120)
    ]
    engine = main.create_engine(bridge)
    window = engine.rootObjects()[0]
    try:
        bridge.select(scene_name)
        (bridge.navigateLibrary if scene_name == "Library" else bridge.navigateWatch)(
            route
        )
        for _ in range(3):
            app.processEvents()

        flow = next(
            item
            for item in visual_descendants(window.contentItem())
            if item.objectName() == flow_name and item.isVisible()
        )
        repeater = next(
            item for item in flow.childItems() if item.objectName() == repeater_name
        )
        viewport = window.findChild(
            QObject, "libraryViewport" if scene_name == "Library" else "watchViewport"
        )
        flickable = viewport.property("contentItem")
        before = cards(engine, repeater)
        changes = []
        repeater.itemRemoved.connect(lambda *_: changes.append(True))
        start = flickable.property("contentY")
        flickable.setProperty(
            "contentY", start + 4 * flow.property("rowStride") + flow.y()
        )
        for _ in range(3):
            app.processEvents()
        after = cards(engine, repeater)
        survivors = set(before) & set(after)
        assert survivors
        assert all(before[owner] == after[owner] for owner in survivors)
        assert len(changes) < len(before)
        columns = flow.property("columns")
        assert (
            repeater.property("count")
            <= (math.ceil(viewport.height() / flow.property("rowStride")) + 3) * columns
        )
        # Resize changes geometry and admission, not surviving owner identity.
        window.resize(820, 500)
        for _ in range(3):
            app.processEvents()
        resized = cards(engine, repeater)
        survivors = set(after) & set(resized)
        assert all(after[owner] == resized[owner] for owner in survivors)
        assert flow.property("lastRow") - flow.property("firstRow") >= 2
        assert flickable.property("contentHeight") >= viewport.height()
    finally:
        window.close()
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        bridge.close()


@pytest.mark.parametrize("width", [820, 1400])
@pytest.mark.parametrize("route", ["channels", "playlists"])
def test_watch_horizontal_window_is_responsive_bounded_and_retains_cards(
    tmp_path, monkeypatch, width, route
):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    app = qt_app()
    bridge = main.Bridge(None)
    bridge._runtime.history = [
        dict(
            saved(tmp_path, f"Item {i:03d}", "MP4"),
            channel=f"Channel {i:03d}",
            playlist_id=f"list-{i}",
            playlist_title=f"List {i:03d}",
        )
        for i in range(120)
    ]
    engine = main.create_engine(bridge)
    window = engine.rootObjects()[0]
    try:
        window.resize(width, 740)
        bridge.selectHome("Watch")
        for _ in range(3):
            app.processEvents()
        rail = next(
            item
            for item in visual_descendants(window.contentItem())
            if item.objectName() == "watchHomeRail_" + route
        )
        repeater = next(
            item
            for item in visual_descendants(rail)
            if item.objectName() == "watchHomeGroupRepeater"
        )
        view = rail.property("contentItem")
        stride = rail.property("cardStride")
        bound = math.ceil(rail.width() / stride) + 3
        assert 2 <= repeater.property("count") <= bound
        extent = view.property("contentWidth")
        assert extent == 120 * stride - 12
        before = cards(engine, repeater)
        # Cold traversal adds only entering cards, preserving visible owners.
        view.setProperty("contentX", 2 * stride)
        for _ in range(3):
            app.processEvents()
        after = cards(engine, repeater)
        survivors = set(before) & set(after)
        assert survivors
        assert all(before[owner] == after[owner] for owner in survivors)
        for position in [extent - rail.width(), 0, 2 * stride, 0]:
            view.setProperty("contentX", position)
            for _ in range(3):
                app.processEvents()
            assert 0 < repeater.property("count") <= bound
            assert view.property("contentWidth") == extent
        # Repeated traversal is bounded too; no cumulative six-card growth.
        assert len(cards(engine, repeater)) == len(before)
    finally:
        window.close()
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        bridge.close()
