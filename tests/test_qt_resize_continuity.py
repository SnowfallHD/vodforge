"""Bounded production-QML geometry; native drag/pixels are separate gates."""

from pathlib import Path

import pytest
from PySide6.QtCore import QMetaObject, QObject, QPointF, QUrl
from PySide6.QtGui import QKeySequence, QWindow
from PySide6.QtQml import QQmlComponent, QQmlEngine
from PySide6.QtQuick import QQuickWindow
from PySide6.QtTest import QTest

from tests.test_qt_all_runs_hover_seam import run_scene  # noqa: F401
from tests.test_qt_scene_port import qt_app


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


@pytest.mark.parametrize("height", [560, 640, 740, 900])
def test_run_deck_entire_content_fits_its_scroll_extent(run_scene, height):  # noqa: F811
    _app, _bridge, window, _button, _popup = run_scene
    window.resize(1100, height)
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
