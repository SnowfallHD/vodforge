"""Menus fit their rows, line up with their trigger, open fast, and moving
around the Library does not rebuild hidden views.

Measured on the real app: menus had hard-coded heights a few pixels off their
rows (extra space at the bottom, or the last row clipped), six different
insets, row heights and gaps, value dropdowns narrower or wider than their
field, and a 240 ms ease-in-out reveal whose text stayed invisible for the
first ~130 ms. A Library section switch rebuilt Forge's hidden run deck 16-24
times, and every thumbnail that finished loading refreshed every view.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import QMetaObject, QObject, QPoint, QPointF, Qt, QUrl
from PySide6.QtQml import QQmlComponent, QQmlEngine
from PySide6.QtQuick import QQuickItem
from PySide6.QtTest import QTest

from tests.test_qt_interaction_invariants import _close, _launch
from tests.test_qt_scene_port import saved
from yt_downloader.qt_quick import main as qt_main

ROW = qt_main.MENU_METRICS["row"]
GAP = qt_main.MENU_METRICS["gap"]
PAD = qt_main.MENU_METRICS["padding"]
QML = Path(qt_main.__file__).with_name("Main.qml").parent


def _walk(item):
    yield item
    for child in item.childItems():
        yield from _walk(child)


def _shown(item):
    while item is not None:
        if not item.isVisible():
            return False
        item = item.parentItem()
    return True


def _rect(item, root):
    point = item.mapToItem(root, QPointF(0, 0))
    return point.x(), point.y(), item.width(), item.height()


def _popup_rect(popup, root):
    parent = popup.property("parent")
    origin = parent.mapToItem(root, QPointF(0, 0))
    return (
        popup.property("x") + origin.x(),
        popup.property("y") + origin.y(),
        popup.property("width"),
        popup.property("height"),
    )


def _records(tmp_path, count=6):
    rows = [
        saved(tmp_path, f"Video {index}", "MP4" if index % 2 else "MP3")
        for index in range(count)
    ]
    for row in rows:
        Path(row["vodforge_output_path"]).write_bytes(b"fixture")
    return rows


def _trigger(window, name):
    return next(
        item
        for item in _walk(window.contentItem())
        if item.objectName() == name and _shown(item)
    )


def _open_from(app, window, trigger_name, popup_name):
    trigger = _trigger(window, trigger_name)
    QMetaObject.invokeMethod(trigger, "activated")
    popup = window.findChild(QObject, popup_name)
    for _ in range(40):
        app.processEvents()
        if popup.property("visible") and popup.property("reveal") == 1:
            break
        QTest.qWait(10)
    assert popup.property("visible"), popup_name
    return trigger, popup


def _rows(popup):
    content = popup.property("contentItem")
    return [
        item
        for item in _walk(content)
        if item.metaObject().className().startswith("StoneButton") and item.isVisible()
    ]


# (view setup, trigger, popup, is a value dropdown)
MENUS = [
    ("Forge", "forgeFormatButton", "forgeFormatPopup", True),
    ("Library", "librarySortButton", "librarySortPopup", True),
    ("Library", "libraryFilterButton", "libraryFilterPopup", False),
    ("Library", "libraryGroupMore", "libraryGroupMenu", False),
    ("Watch", "watchHeroMoreButton", "watchHeroMorePopup", False),
    ("Settings", "settingsQualityButton", "settingsQualityMenu", True),
    ("Settings", "settingsOutputModeButton", "settingsOutputModeMenu", True),
    ("Settings", "settingsAppearanceThemeButton", "appearanceThemeMenu", True),
]


def _go(app, bridge, window, view):
    if view == "Settings":
        bridge.selectHome("Forge")
        app.processEvents()
        QMetaObject.invokeMethod(
            window.findChild(QObject, "downloadSettingsPopup"), "open"
        )
    else:
        bridge.selectHome(view)
    for _ in range(6):
        app.processEvents()
    QTest.qWait(150)


@pytest.mark.parametrize("view,trigger_name,popup_name,dropdown", MENUS)
def test_menu_fits_rows_uses_shared_inset_and_meets_its_trigger(
    tmp_path, monkeypatch, view, trigger_name, popup_name, dropdown
):
    app, bridge, engine, window = _launch(tmp_path, monkeypatch, _records(tmp_path))
    try:
        window.resize(1280, 800)
        _go(app, bridge, window, view)
        trigger, popup = _open_from(app, window, trigger_name, popup_name)
        root = window.contentItem()
        # One inset on every side, shared by every menu.
        for side in ("topPadding", "bottomPadding", "leftPadding", "rightPadding"):
            assert popup.property(side) == PAD, (popup_name, side)
        # Every row is the shared row height, and the menu is exactly its rows:
        # no leftover space at the bottom and no clipped last row.
        rows = _rows(popup)
        assert rows, popup_name
        assert {row.height() for row in rows} == {ROW}, popup_name
        expected = len(rows) * ROW + (len(rows) - 1) * GAP
        assert popup.property("availableHeight") == pytest.approx(expected), popup_name
        # Opens from the trigger's edge, touching it (overlap), and grows out
        # of that edge.
        px, py, pw, ph = _popup_rect(popup, root)
        ax, ay, aw, ah = _rect(trigger, root)
        overlap = popup.property("overlap")
        if popup.property("growUp"):
            assert py + ph == pytest.approx(ay + overlap, abs=0.5), popup_name
        else:
            assert py == pytest.approx(ay + ah - overlap, abs=0.5), popup_name
        # Lines up with one edge of its trigger.
        aligned_left = abs(px - ax) <= 0.5
        aligned_right = abs((px + pw) - (ax + aw)) <= 0.5
        assert aligned_left or aligned_right, (popup_name, px, ax, pw, aw)
        if dropdown:
            # A value dropdown is at least as wide as its field.
            assert pw >= aw - 0.5, (popup_name, pw, aw)
        # Never touches the window edge.
        margin = popup.property("edgeMargin")
        assert px >= margin - 0.5 and px + pw <= window.width() - margin + 0.5
        assert py >= margin - 0.5 and py + ph <= window.height() - margin + 0.5
    finally:
        _close(bridge, engine, window)


def test_sort_menu_names_choices_like_its_button_and_marks_the_current_one(
    tmp_path, monkeypatch
):
    app, bridge, engine, window = _launch(tmp_path, monkeypatch, _records(tmp_path))
    try:
        window.resize(1280, 800)
        _go(app, bridge, window, "Library")
        trigger, popup = _open_from(
            app, window, "librarySortButton", "librarySortPopup"
        )
        labels = {
            row.property("label"): row.property("selected") for row in _rows(popup)
        }
        assert labels == {"Newest first": True, "Title A–Z": False}
        assert trigger.property("label") == "Newest first  ▾"
    finally:
        _close(bridge, engine, window)


_COMPONENTS: list = []


def _component(engine, window, source):
    component = QQmlComponent(engine)
    component.setData(
        source.encode(), QUrl.fromLocalFile(str(QML / "menu_geometry_probe.qml"))
    )
    item = component.create(QQmlEngine.contextForObject(window))
    assert item is not None, [str(error) for error in component.errors()]
    QQmlEngine.setObjectOwnership(item, QQmlEngine.ObjectOwnership.CppOwnership)
    item.setParentItem(window.contentItem())
    # The component must outlive the object it created.
    _COMPONENTS.append(component)
    return item


def test_window_margin_applies_at_the_window_edge_only(tmp_path, monkeypatch):
    app, bridge, engine, window = _launch(tmp_path, monkeypatch, [])
    probe = None
    try:
        window.resize(900, 600)
        app.processEvents()
        probe = _component(
            engine,
            window,
            """import QtQuick
Item {
    anchors.fill: parent
    Item { id: edgeAnchor; objectName: "edgeAnchor"; x: 0; y: 100; width: 60; height: 30 }
    AnchoredPopup { id: edgePopup; objectName: "edgeProbePopup"; anchorItem: edgeAnchor; width: 200
        Column { width: parent.width
            Rectangle { width: parent.width; height: menuMetrics.row } } }
    // A page inset inside the window: its own left edge is not the window edge.
    Item { id: page; x: 120; y: 0; width: 600; height: 500
        Item { id: innerAnchor; x: 0; y: 100; width: 60; height: 30 }
        AnchoredPopup { id: innerPopup; objectName: "innerProbePopup"; parent: page; anchorItem: innerAnchor; width: 200
            Column { width: parent.width
                Rectangle { width: parent.width; height: menuMetrics.row } } } }
}""",
        )
        edge = probe.findChild(QObject, "edgeProbePopup")
        inner = probe.findChild(QObject, "innerProbePopup")
        for popup in (edge, inner):
            popup.open()
        QTest.qWait(250)
        app.processEvents()
        # Pushed 8 px off the window edge...
        assert edge.property("x") == edge.property("edgeMargin")
        # ...but flush with an anchor at a page edge inside the window.
        assert inner.property("x") == 0
        # Sized to its one row plus the shared inset.
        assert edge.property("height") == ROW + 2 * PAD
    finally:
        if probe is not None:
            probe.deleteLater()
        _close(bridge, engine, window)


def test_reveal_shows_text_once_the_surface_has_its_shape(tmp_path, monkeypatch):
    monkeypatch.setattr(qt_main, "_system_reduced_motion", lambda: False)
    app, bridge, engine, window = _launch(tmp_path, monkeypatch, [])
    try:
        motion = engine.rootContext().contextProperty("motion")
        # Menus appear quickly and leave faster.
        assert motion["menuIn"] <= 160 and motion["menuOut"] < motion["menuIn"]
        assert motion["tipIn"] <= motion["menuIn"]
        popup = window.findChild(QObject, "forgeFormatPopup")
        popup.setProperty("anchorItem", window.findChild(QObject, "forgeFormatButton"))
        popup.open()
        QTest.qWait(250)
        content = popup.property("contentItem")
        surface = popup.property("background")
        for reveal, opacity in ((0.3, 0.0), (0.6, 0.0), (0.8, 0.5), (1.0, 1.0)):
            popup.setProperty("reveal", reveal)
            app.processEvents()
            assert content.property("opacity") == pytest.approx(opacity)
            if reveal >= 0.6:
                # Fully shaped before any text shows.
                assert surface.property("height") == pytest.approx(
                    popup.property("height")
                )
                assert surface.property("width") == pytest.approx(
                    popup.property("width")
                )
    finally:
        _close(bridge, engine, window)


def test_reduced_motion_makes_every_timing_instant(tmp_path, monkeypatch):
    monkeypatch.setattr(qt_main, "_system_reduced_motion", lambda: True)
    _app, bridge, engine, window = _launch(tmp_path, monkeypatch, [])
    try:
        motion = engine.rootContext().contextProperty("motion")
        assert set(motion.values()) == {0}
    finally:
        _close(bridge, engine, window)


def test_interface_motion_uses_the_shared_timing_table():
    # Every reveal reads its duration from the one table; none keeps the old
    # slow ease-in-out curve that holds a menu still for its first frames.
    for name in (
        "StonePopup.qml",
        "LiquidToolTip.qml",
        "InlineSelector.qml",
        "ComposerNotice.qml",
    ):
        source = (QML / name).read_text(encoding="utf-8")
        assert "InOutCubic" not in source, name
        assert "motion." in source, name
    main = (QML / "Main.qml").read_text(encoding="utf-8")
    assert "duration: bridge.reducedMotion ? 0 : 280" not in main


@pytest.mark.parametrize("where", ["deck", "library"])
def test_right_click_opens_its_menu_at_the_pointer_on_press(
    tmp_path, monkeypatch, where
):
    app, bridge, engine, window = _launch(tmp_path, monkeypatch, _records(tmp_path))
    try:
        window.resize(1400, 900)
        if where == "deck":
            bridge.selectHome("Forge")
            area_name, popup_name = "runCardContextArea", "runActionsPopup"
        else:
            bridge.selectHome("Library")
            bridge.navigateLibrary("all")
            area_name, popup_name = (
                "libraryMediaContextArea",
                "librarySavedActionsPopup",
            )
        for _ in range(6):
            app.processEvents()
        QTest.qWait(200)
        area = next(
            item
            for item in _walk(window.contentItem())
            if item.objectName() == area_name and _shown(item)
        )
        root = window.contentItem()
        point = area.mapToItem(root, QPointF(area.width() / 3, area.height() / 2))
        press = QPoint(round(point.x()), round(point.y()))
        QTest.mousePress(window, Qt.RightButton, Qt.NoModifier, press)
        app.processEvents()
        popup = window.findChild(QObject, popup_name)
        # Opens on the press, before the button comes back up.
        assert popup.property("visible")
        QTest.qWait(250)
        px, py, pw, ph = _popup_rect(popup, root)
        # Like a native context menu: a corner at the pointer.
        assert min(abs(px - press.x()), abs(px + pw - press.x())) <= 1
        assert min(abs(py - press.y()), abs(py + ph - press.y())) <= 1
        QTest.mouseRelease(window, Qt.RightButton, Qt.NoModifier, press)
        app.processEvents()
        assert popup.property("visible"), "the release must not close it again"
    finally:
        _close(bridge, engine, window)


def test_category_list_is_not_offered_when_there_are_no_categories(
    tmp_path, monkeypatch
):
    _app, bridge, engine, window = _launch(tmp_path, monkeypatch, _records(tmp_path))
    try:
        owner = bridge._projected_library()[0]["vodforge_projection_owner"]
        assert bridge.openAnnotationOwner(owner)
        QMetaObject.invokeMethod(
            window.findChild(QObject, "libraryAnnotationPopup"), "open"
        )
        QTest.qWait(200)
        assert len(bridge.libraryCategories) <= 1
        button = window.findChild(QQuickItem, "annotationCategoryButton")
        assert not button.isVisible()
    finally:
        _close(bridge, engine, window)


def _count_deck_builds(bridge, monkeypatch):
    count = [0]
    build = bridge._build_run_deck

    def counted():
        count[0] += 1
        return build()

    monkeypatch.setattr(bridge, "_build_run_deck", counted)
    return count


@pytest.mark.parametrize(
    "move",
    [
        lambda bridge: bridge.navigateLibraryFolders("folders"),
        lambda bridge: bridge.navigateLibraryFolders("issues"),
        lambda bridge: bridge.navigateLibraryFolders("all"),
        lambda bridge: bridge.navigateLibrary("videos"),
        lambda bridge: bridge.navigateLibrary("home"),
        lambda bridge: bridge.setLibrarySort("title"),
        lambda bridge: bridge.navigateWatch("channels"),
    ],
)
def test_moving_around_library_and_watch_does_not_rebuild_forge(
    tmp_path, monkeypatch, move
):
    app, bridge, engine, window = _launch(tmp_path, monkeypatch, _records(tmp_path))
    try:
        bridge.selectHome("Library")
        for _ in range(4):
            app.processEvents()
        builds = _count_deck_builds(bridge, monkeypatch)
        history = []
        bridge.historyChanged.connect(lambda: history.append(True))
        move(bridge)
        # Navigation is not a change to saved history, so Forge's run deck,
        # Watch and the player are not rebuilt.
        assert builds[0] == 0
        assert history == []
    finally:
        _close(bridge, engine, window)


def test_one_run_deck_build_per_change_and_never_a_stale_one(tmp_path, monkeypatch):
    from dataclasses import replace

    from tests.test_run_identity import make_job

    app, bridge, engine, window = _launch(tmp_path, monkeypatch, _records(tmp_path))
    try:
        bridge.selectHome("Forge")
        app.processEvents()
        builds = _count_deck_builds(bridge, monkeypatch)
        bridge._emit_run_deck()
        # Forge reads the deck through several properties; one build serves all.
        assert builds[0] == 1
        builds[0] = 0
        bridge._emit_activity()
        assert builds[0] == 1
        # A change made without any signal is still seen by the next read.
        job = make_job(tmp_path)
        bridge._runtime.queued = [replace(job, run_id="queued-probe")]
        assert any(
            record["runId"] == "queued-probe" for record in bridge.runDeck["records"]
        )
        bridge._runtime.queued = []
        assert not any(
            record["runId"] == "queued-probe" for record in bridge.runDeck["records"]
        )
    finally:
        _close(bridge, engine, window)


def test_thumbnails_arriving_one_by_one_refresh_the_library_once_per_burst(
    tmp_path, monkeypatch
):
    app, bridge, engine, window = _launch(tmp_path, monkeypatch, _records(tmp_path))
    try:
        bridge.selectHome("Library")
        bridge.navigateLibraryFolders("folders")
        app.processEvents()
        # Start between bursts, with no real thumbnail work arriving meanwhile.
        bridge._timer.stop()
        bridge._artwork_view_timer.stop()
        bridge._artwork_view_pending = False
        app.processEvents()
        refreshes = []
        bridge.libraryViewChanged.connect(lambda: refreshes.append(True))
        for _ in range(8):
            bridge._refresh_library_for_artwork()
        # The first arrival shows at once; the rest wait for one more refresh.
        assert len(refreshes) == 1
        QTest.qWait(160)
        app.processEvents()
        assert len(refreshes) == 2
    finally:
        _close(bridge, engine, window)
