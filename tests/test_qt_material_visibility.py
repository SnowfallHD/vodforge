"""Hidden material admission and visible pixel parity; no native latency verdict."""

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QPointF, QUrl
from PySide6.QtQml import QQmlComponent
from PySide6.QtQuick import QQuickItem
from PySide6.QtTest import QTest

from tests.test_qt_scene_port import qt_app
from yt_downloader.qt_quick import main


@pytest.fixture
def material_field(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    app = qt_app()
    requests = []
    original = main.Materials.requestImage

    def request(provider, image_id, size, requested_size):
        requests.append(image_id)
        return original(provider, image_id, size, requested_size)

    monkeypatch.setattr(main.Materials, "requestImage", request)
    bridge = main.Bridge(None)
    bridge._engagement.presented_welcome()
    bridge._settings["whats_new_seen"] = main.SHOWCASE_ID
    engine = main.create_engine(bridge)
    window = engine.rootObjects()[0]
    component = QQmlComponent(engine)
    component.setData(
        b"""import QtQuick
import "."
Rectangle {
    width: 420; height: 180; color: "#142842"
    StoneField { objectName: "materialProbeField"; x: 20; y: 20; width: 317; height: 79 }
}""",
        QUrl.fromLocalFile(
            str(main.SOURCE / "yt_downloader/qt_quick/material-probe.qml")
        ),
    )
    holder = component.create()
    assert holder is not None, component.errors()
    holder.setParentItem(window.contentItem())
    holder.setPosition(QPointF(30, 100))
    holder.setZ(1000)
    field = holder.findChild(QQuickItem, "materialProbeField")
    image = next(
        item for item in field.childItems() if item.property("source") is not None
    )
    window.show()
    QTest.qWait(100)
    yield app, bridge, window, holder, field, image, requests
    holder.deleteLater()
    window.close()
    engine.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    bridge.close()


def _crop(window, field):
    image = window.grabWindow()
    assert not image.isNull()
    scale = image.devicePixelRatio()
    point = field.mapToScene(QPointF(0, 0))
    crop = image.copy(
        round(point.x() * scale),
        round(point.y() * scale),
        round(field.width() * scale),
        round(field.height() * scale),
    )
    return bytes(crop.constBits())


def test_hidden_ancestor_blocks_resize_material_requests_and_show_uses_latest_size(
    material_field,
):
    app, _bridge, _window, holder, field, image, requests = material_field
    holder.setVisible(False)
    app.processEvents()
    requests.clear()
    for index in range(20):
        field.setWidth(318 + index)
        field.setHeight(80 + index)
        app.processEvents()
    assert image.property("source").isEmpty()
    assert not [item for item in requests if item.startswith("field/")]
    holder.setVisible(True)
    QTest.qWait(50)
    assert "/field/337/99/normal/" in image.property("source").toString()
    assert any(item.startswith("field/337/99/normal/") for item in requests)


def test_hide_show_preserves_pixels_and_hidden_focus_theme_changes_apply_on_show(
    material_field,
):
    app, bridge, window, holder, field, image, requests = material_field
    before = _crop(window, field)
    holder.setVisible(False)
    app.processEvents()
    holder.setVisible(True)
    QTest.qWait(50)
    assert _crop(window, field) == before
    holder.setVisible(False)
    app.processEvents()
    requests.clear()
    field.setProperty("focused", True)
    revision = bridge.themeRevision
    target = next(
        name for name in bridge.appearanceThemes if name != bridge.appearanceTheme
    )
    assert bridge.setAppearance(target, "#7170ff")
    for _ in range(20):
        if bridge.themeRevision > revision:
            break
        QTest.qWait(50)
    assert bridge.themeRevision > revision
    assert image.property("source").isEmpty()
    assert not [item for item in requests if item.startswith("field/317/79/")]
    holder.setVisible(True)
    QTest.qWait(50)
    assert (
        f"/field/317/79/focus/r{bridge.themeRevision}"
        in image.property("source").toString()
    )
    focused = _crop(window, field)
    assert focused != before
    holder.setVisible(False)
    app.processEvents()
    holder.setVisible(True)
    QTest.qWait(50)
    assert _crop(window, field) == focused
