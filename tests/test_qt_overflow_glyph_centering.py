"""Rendered overflow-ink bounds in shared buttons, not native GUI acceptance."""

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QPoint, QPointF, QUrl
from PySide6.QtQml import QQmlComponent
from PySide6.QtQuick import QQuickItem
from PySide6.QtTest import QTest

from tests.test_qt_scene_port import qt_app
from yt_downloader.qt_quick import main


@pytest.mark.parametrize("label", ["⋯", "⋮", "…"])
@pytest.mark.parametrize("hover", [False, True])
def test_overflow_visible_ink_centered_in_button_face(
    tmp_path, monkeypatch, label, hover
):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    qt_app()
    bridge = main.Bridge(None)
    engine = main.create_engine(bridge)
    window = engine.rootObjects()[0]
    theme = dict(main.THEME)
    theme["text"] = "#ff00ff"
    engine.rootContext().setContextProperty("theme", theme)
    component = QQmlComponent(engine)
    component.setData(
        b"""import QtQuick
import "."
Rectangle {
    width: 120; height: 80; color: "#142842"
    StoneButton { objectName: "glyphProbe"; x: 30; y: 20; width: 32; height: 28; size: "inline" }
}""",
        QUrl.fromLocalFile(str(main.SOURCE / "yt_downloader/qt_quick/glyph-probe.qml")),
    )
    holder = component.create()
    assert holder is not None, component.errors()
    holder.setParentItem(window.contentItem())
    holder.setPosition(QPointF(30, 100))
    holder.setZ(1000)
    button = holder.findChild(QQuickItem, "glyphProbe")
    button.setProperty("label", label)
    window.show()
    center = button.mapToScene(QPointF(button.width() / 2, button.height() / 2))
    QTest.mouseMove(
        window, QPoint(round(center.x()), round(center.y())) if hover else QPoint(2, 2)
    )
    QTest.qWait(100)
    try:
        image = window.grabWindow()
        assert not image.isNull()
        ratio = image.width() / window.width()
        assert image.height() / window.height() == pytest.approx(ratio, abs=0.01)
        origin = button.mapToScene(QPointF(0, 0))
        crop = image.copy(
            round(origin.x() * ratio),
            round(origin.y() * ratio),
            round(button.width() * ratio),
            round(button.height() * ratio),
        )
        points = []
        for y in range(crop.height()):
            for x in range(crop.width()):
                color = crop.pixelColor(x, y)
                if color.red() > 130 and color.blue() > 130 and color.green() < 90:
                    points.append((x, y))
        assert points
        ink_x = (min(p[0] for p in points) + max(p[0] for p in points) + 1) / (
            2 * ratio
        )
        ink_y = (min(p[1] for p in points) + max(p[1] for p in points) + 1) / (
            2 * ratio
        )
        print(
            f"glyph={label} hover={hover} dpr={ratio} ink-center=({ink_x},{ink_y}) face-center=(16,14)"
        )
        assert abs(ink_x - button.width() / 2) <= 0.75
        assert abs(ink_y - button.height() / 2) <= 0.75
    finally:
        holder.deleteLater()
        window.close()
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        bridge.close()
