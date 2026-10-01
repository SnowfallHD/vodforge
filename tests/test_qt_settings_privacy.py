"""Privacy presentation never changes consent to inspect a view state."""

from types import SimpleNamespace

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QObject

from tests.test_qt_scene_port import qt_app
from yt_downloader.qt_quick import main


@pytest.mark.parametrize("mode", ["forced_off", "denied", "allowed"])
@pytest.mark.parametrize("height", [500, 1000])
def test_privacy_has_truthful_body_and_scroll_reachability(
    tmp_path, monkeypatch, mode, height
):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    app = qt_app()
    bridge = main.Bridge(None)
    assert bridge._analytics.owner is None and bridge._analytics.telemetry is None
    # Inert owner states render the normal availability branches; they do not
    # enable collection, create consent, or activate a transport.
    if mode != "forced_off":
        bridge._analytics.owner = SimpleNamespace(allowed=mode == "allowed")
    engine = main.create_engine(bridge)
    window = engine.rootObjects()[0]
    try:
        window.resize(820, height)
        popup = window.findChild(QObject, "downloadSettingsPopup")
        popup.open()
        for _ in range(5):
            app.processEvents()
        body = window.findChild(QObject, "settingsBodyViewport")
        view = body.property("contentItem")
        view.setProperty(
            "contentY", max(0, view.property("contentHeight") - view.height())
        )
        for _ in range(3):
            app.processEvents()
        heading = window.findChild(QObject, "settingsPrivacyHeading")
        message = window.findChild(QObject, "settingsAnalyticsUnavailable")
        row = window.findChild(QObject, "settingsAnalyticsRow")
        toggle = window.findChild(QObject, "settingsAnalyticsToggle")
        shown = message if mode == "forced_off" else row
        assert shown.isVisible()
        assert message.isVisible() == (mode == "forced_off")
        assert row.isVisible() == (mode != "forced_off")
        if mode == "forced_off":
            assert "disabled for this session" in message.property("text")
        else:
            assert toggle.property("label") == ("On" if mode == "allowed" else "Off")
        for item in [heading, shown]:
            point = item.mapToItem(body, 0, 0)
            assert point.y() >= -1
            assert point.y() + item.height() <= body.height() + 1
        assert bridge._analytics.telemetry is None
        assert not window.grabWindow().isNull()
    finally:
        popup.close()
        # Restore the real forced-off owner before its normal close lifecycle.
        bridge._analytics.owner = None
        window.close()
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        bridge.close()
