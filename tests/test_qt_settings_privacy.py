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
        row = window.findChild(QObject, "settingsAnalyticsRow")
        toggle = window.findChild(QObject, "settingsAnalyticsToggle")
        shown = row
        assert row.isVisible()
        assert toggle.property("label") == ("On" if mode == "allowed" else "Off")
        assert toggle.property("enabled") == (mode != "forced_off")
        for name in (
            "settingsAnalyticsUnavailable",
            "settingsPosthogRow",
            "settingsPosthogToggle",
            "settingsPosthogDescription",
            "settingsInstallationLink",
            "settingsInstallationLinkDescription",
        ):
            assert window.findChild(QObject, name) is None
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


@pytest.mark.parametrize("height", [500, 1000])
def test_single_settings_toggle_saves_both_choices_without_network(
    tmp_path, monkeypatch, height
):
    from unittest.mock import Mock
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtTest import QTest
    from yt_downloader.analytics_consent import AnalyticsConsentOwner

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    app = qt_app()
    bridge = main.Bridge(None)
    owner = AnalyticsConsentOwner(tmp_path / "consent")
    owner.choose_data_sharing(False)
    bridge._analytics.owner = owner
    bridge._analytics.telemetry = Mock()
    bridge._analytics._opened = True
    # Prevent unrelated settings snapshot/first-launch work; test actual local save.
    monkeypatch.setattr(bridge, "_record_settings_snapshot", lambda: None)
    monkeypatch.setattr(bridge._analytics, "start_first_launch_delivery", lambda: None)
    engine = main.create_engine(bridge)
    window = engine.rootObjects()[0]
    try:
        window.resize(820, height)
        window.show()
        popup = window.findChild(QObject, "downloadSettingsPopup")
        popup.open()
        app.processEvents()
        body = window.findChild(QObject, "settingsBodyViewport").property("contentItem")
        body.setProperty(
            "contentY", max(0, body.property("contentHeight") - body.height())
        )
        app.processEvents()
        toggle = window.findChild(QObject, "settingsAnalyticsToggle")
        for enabled in (True, False):
            point = toggle.mapToScene(
                QPointF(toggle.width() / 2, toggle.height() / 2)
            ).toPoint()
            QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, point)
            app.processEvents()
            assert owner.allowed is enabled and owner.posthog_allowed is enabled
            assert toggle.property("label") == ("On" if enabled else "Off")
            saved = AnalyticsConsentOwner(owner.path.parent)
            assert saved.allowed is enabled and saved.posthog_allowed is enabled
    finally:
        popup.close()
        window.close()
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        bridge.close()
