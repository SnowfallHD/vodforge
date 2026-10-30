"""Bounded production-QML geometry; native drag/pixels are separate gates."""

import sys
from pathlib import Path

import pytest
from PySide6.QtCore import QMetaObject, QObject, QPointF, Qt, QUrl
from PySide6.QtGui import QAccessible, QKeySequence, QWindow
from PySide6.QtQml import QQmlComponent, QQmlEngine
from PySide6.QtQuick import QQuickWindow
from PySide6.QtTest import QTest

from tests.test_qt_all_runs_hover_seam import run_scene  # noqa: F401
from tests.test_qt_scene_port import qt_app


def test_main_header_intent_survives_toolkit_fullscreen_style_reset(run_scene):  # noqa: F811
    _app, _bridge, window, _button, _popup = run_scene
    if sys.platform != "darwin":
        pytest.skip("Cocoa header flags are macOS-only")
    # Cocoa reconstructs native style and transparency from these flags on
    # BOTH fullscreen boundaries; an AppKit-only startup mutation is lost.
    required = (
        Qt.WindowType.ExpandedClientAreaHint | Qt.WindowType.NoTitleBarBackgroundHint
    )
    for transition in (window.showFullScreen, window.showNormal):
        transition()
        QTest.qWait(30)
        assert window.flags() & required == required


def test_main_fullscreen_escape_is_window_scoped_and_preserves_modal_priority(
    run_scene,  # noqa: F811
):
    _app, _bridge, window, _button, _popup = run_scene
    popup = window.findChild(QObject, "downloadSettingsPopup")
    shortcut = window.findChild(QObject, "mainFullscreenEscape")
    assert shortcut is not None
    assert shortcut.property("context") == Qt.ShortcutContext.WindowShortcut
    window.showNormal()
    QTest.qWait(30)
    assert not shortcut.property("enabled")
    window.showFullScreen()
    QTest.qWait(30)
    assert shortcut.property("enabled")
    assert QMetaObject.invokeMethod(popup, "open")
    QTest.qWait(30)
    assert not shortcut.property("enabled"), "Escape must dismiss a popup first"
    assert QMetaObject.invokeMethod(popup, "close")
    QTest.qWait(30)
    assert shortcut.property("enabled")
    window.requestActivate()
    QTest.qWait(30)
    QTest.keyClick(window, Qt.Key.Key_Escape)
    QTest.qWait(30)
    assert window.visibility() == QWindow.Visibility.Windowed


@pytest.mark.parametrize(
    "width,height",
    # None = the window's own minimum height (raised in fb858b9 so the dial
    # and deck fit). Offscreen windows do not enforce it, so a fixed smaller
    # height would test a size users cannot reach.
    [(820, None), (920, None), (1100, None), (1100, 640), (1100, 740), (1280, 800)],
)
@pytest.mark.parametrize("idle", [False, True])
def test_forge_fits_without_page_scroll(run_scene, width, height, idle):  # noqa: F811
    _app, bridge, window, _button, _popup = run_scene
    if idle:
        bridge._runtime.active_job = None
        bridge._runtime.history = []
        bridge.runDeckChanged.emit()
    window.resize(width, height or window.minimumHeight())
    QTest.qWait(100)
    viewport = window.findChild(QObject, "forgeViewport")
    scene = window.findChild(QObject, "forgeScene")
    deck = window.findChild(QObject, "forgeRunDeck")
    assert scene.height() <= viewport.height() + 0.5
    assert deck.y() + deck.height() <= viewport.height() + 0.5
    for child in scene.childItems():
        if child.isVisible():
            assert child.y() >= -0.5
            assert child.y() + child.height() <= viewport.height() + 0.5
    live = window.findChild(QObject, "forgeLivePane")
    for child in live.childItems():
        if child.isVisible():
            assert child.y() + child.height() <= live.height() + 0.5


@pytest.mark.parametrize(
    ("before", "after"),
    [
        ((919, 740), (920, 740)),
        ((959, 740), (960, 740)),
        ((1079, 800), (1080, 800)),
        ((1100, 689), (1100, 690)),
        ((1100, 759), (1100, 760)),
    ],
)
def test_growing_frame_never_shrinks_or_displaces_forge_content(
    run_scene,  # noqa: F811 - shared pytest fixture
    before,
    after,
):
    _app, _bridge, window, _button, _popup = run_scene
    viewport = window.findChild(QObject, "forgeViewport")
    measurements = []
    for width, height in (before, after, before):
        window.resize(width, height)
        QTest.qWait(100)
        measurements.append(
            (
                viewport.width(),
                viewport.mapToScene(viewport.boundingRect().topLeft()).x(),
            )
        )
    # A one-pixel larger frame must not remove tens of pixels of working area.
    assert measurements[1][0] >= measurements[0][0] - 0.25
    assert abs(measurements[1][1] - measurements[0][1]) <= 1.25
    # Reversing the resize must return to the same content owner and bounds.
    assert measurements[2] == pytest.approx(measurements[0], abs=0.25)


def test_accepted_default_forge_insets_remain_unchanged(run_scene):  # noqa: F811
    _app, _bridge, window, _button, _popup = run_scene
    window.resize(1100, 740)
    QTest.qWait(100)
    assert window.property("gutter") == pytest.approx(20)
    assert window.property("forgeHorizontalPad") == pytest.approx(42)
    assert window.property("forgeTopPad") == pytest.approx(26)


@pytest.mark.parametrize("height", [None, 640, 740, 900])  # None: window minimum
def test_run_deck_entire_content_fits_its_scroll_extent(run_scene, height):  # noqa: F811
    _app, _bridge, window, _button, _popup = run_scene
    window.resize(1100, height or window.minimumHeight())
    QTest.qWait(100)
    deck = window.findChild(QObject, "forgeRunDeck")
    layout = next(
        child
        for child in deck.childItems()
        if child.metaObject().className().startswith("QQuickColumnLayout")
    )
    assert layout.implicitHeight() <= deck.height() + 0.5
    for child in layout.childItems():
        if child.isVisible():
            assert child.y() + child.height() <= deck.height() + 0.5
    viewport = window.findChild(QObject, "forgeViewport")
    flick = viewport.property("contentItem")
    flick.setProperty(
        "contentY", max(0, flick.property("contentHeight") - flick.height())
    )
    QTest.qWait(50)
    bottom = deck.mapToItem(flick, QPointF(0, deck.height())).y()
    assert bottom <= flick.height() + 0.5


@pytest.mark.parametrize("navigation_allowed", [True, False])
def test_main_menu_can_enter_and_leave_native_fullscreen(navigation_allowed):
    app = qt_app()
    engine = QQmlEngine()
    window = QQuickWindow()
    controller = QObject()
    component = QQmlComponent(
        engine,
        QUrl.fromLocalFile(
            str(
                Path(__file__).resolve().parents[1]
                / "yt_downloader/qt_quick/ApplicationMenuBar.qml"
            )
        ),
    )
    menu = component.createWithInitialProperties(
        {
            "appWindow": window,
            "controller": controller,
            "navigationAllowed": navigation_allowed,
        }
    )
    assert menu is not None, component.errors()
    try:
        action = menu.findChild(QObject, "mainFullscreenAction")
        assert action is not None, "Native fullscreen has no application return command"
        assert action.property("enabled")
        view_menu = action.parent()
        assert view_menu.property("enabled")
        navigation = [
            child
            for child in view_menu.children()
            if child.metaObject().className() == action.metaObject().className()
            and child.property("text") in ("Forge", "Library", "Watch", "Activity")
        ]
        assert len(navigation) == 4
        assert all(
            child.property("enabled") == navigation_allowed for child in navigation
        )
        assert action.property("text") == "Enter Full Screen"
        assert action.property("shortcut") == QKeySequence.StandardKey.FullScreen.value
        assert QMetaObject.invokeMethod(action, "trigger")
        app.processEvents()
        assert window.visibility() == QWindow.Visibility.FullScreen
        assert action.property("text") == "Exit Full Screen"
        # Also cover fullscreen entered by the native green button: the command
        # observes window visibility rather than an application-only toggle bit.
        window.showNormal()
        window.showFullScreen()
        app.processEvents()
        assert action.property("text") == "Exit Full Screen"
        assert QMetaObject.invokeMethod(action, "trigger")
        app.processEvents()
        assert window.visibility() == QWindow.Visibility.Windowed
        assert action.property("text") == "Enter Full Screen"
    finally:
        window.close()
        menu.deleteLater()
        engine.deleteLater()
        app.processEvents()


@pytest.mark.skipif(sys.platform != "darwin", reason="Native menu loader is macOS-only")
def test_native_menu_proxy_has_no_in_window_visual_or_accessible_allocation(
    tmp_path, monkeypatch
):
    from tests.test_qt_interaction_invariants import _close, _launch
    from tests.test_qt_scene_port import polish_scene

    app, bridge, engine, window = _launch(tmp_path, monkeypatch, [])
    try:
        QTest.qWait(80)
        for _ in range(3):
            app.processEvents()
            polish_scene(window.contentItem())
        menu = next(
            item
            for item in window.findChildren(QObject)
            if item.metaObject().className().startswith("ApplicationMenuBar_QMLTYPE")
        )
        loader = menu.parentItem()
        assert menu.isVisible() and menu.isEnabled()
        assert menu.width() == menu.height() == 0
        assert loader.width() == loader.height() == 0
        assert menu.clip()
        assert menu.property("count") == 5
        action = window.findChild(QObject, "mainFullscreenAction")
        assert action is not None and action.property("enabled")
        assert action.property("shortcut") == QKeySequence.StandardKey.FullScreen.value
        interface = QAccessible.queryAccessibleInterface(menu)
        assert interface is not None
        assert interface.rect().isEmpty()
        # A clipped zero allocation must not expose overflowing descendants at
        # the titlebar gap. Actual OS-menu accessibility remains a native gate.
        point = window.mapToGlobal(QPointF(88, 26).toPoint())
        assert interface.childAt(point.x(), point.y()) is None
    finally:
        _close(bridge, engine, window)


@pytest.mark.skipif(sys.platform != "darwin", reason="Native menu loader is macOS-only")
def test_native_menu_allocation_stays_empty_when_style_padding_changes(
    tmp_path, monkeypatch
):
    from tests.test_qt_interaction_invariants import _close, _launch
    from tests.test_qt_scene_port import polish_scene

    app, bridge, engine, window = _launch(tmp_path, monkeypatch, [])
    try:
        menu = next(
            item
            for item in window.findChildren(QObject)
            if item.metaObject().className().startswith("ApplicationMenuBar_QMLTYPE")
        )
        loader = menu.parentItem()
        for width, padding in ((820, 52), (1440, 0)):
            window.resize(width, 740)
            menu.setProperty("topPadding", padding)
            app.processEvents()
            polish_scene(window.contentItem())
            assert menu.isVisible() and menu.isEnabled()
            assert menu.width() == menu.height() == 0
            assert menu.implicitWidth() == menu.implicitHeight() == 0
            assert loader.width() == loader.height() == 0
            interface = QAccessible.queryAccessibleInterface(menu)
            assert interface is not None and interface.rect().isEmpty()
            point = window.mapToGlobal(QPointF(88, 26).toPoint())
            assert interface.childAt(point.x(), point.y()) is None
            assert menu.property("count") == 5
    finally:
        _close(bridge, engine, window)
