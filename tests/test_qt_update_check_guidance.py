"""Update-service failures must not imply a damaged local installation."""

import ssl
import urllib.error

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QObject, QPointF, Qt
from PySide6.QtTest import QTest

from tests.test_qt_scene_port import polish_scene, qt_app
from yt_downloader import updates
from yt_downloader.qt_quick import main as qt_main
from yt_downloader.qt_quick.update_session import QtUpdateSession

PRIVATE = "sensitive-test-message /private/test-path https://invalid.example/private"
TLS_ERROR = ssl.SSLCertVerificationError(1, PRIVATE)
TLS_ERROR.verify_code = 20


def start_inline(session, monkeypatch):
    def start(target, _name):
        session.busy = True
        target()
        return True

    monkeypatch.setattr(session, "_start", start)


@pytest.mark.parametrize("automatic", [False, True])
@pytest.mark.parametrize(
    "error, expected",
    [
        (urllib.error.URLError(TimeoutError(PRIVATE)), "connection"),
        (
            urllib.error.HTTPError("https://invalid.example", 429, PRIVATE, {}, None),
            "limit",
        ),
        (
            urllib.error.HTTPError("https://invalid.example", 403, PRIVATE, {}, None),
            "declined",
        ),
        (
            urllib.error.HTTPError("https://invalid.example", 503, PRIVATE, {}, None),
            "unavailable",
        ),
        (
            urllib.error.HTTPError("https://invalid.example", 404, PRIVATE, {}, None),
            "unavailable",
        ),
        (urllib.error.URLError(TLS_ERROR), "secure connection"),
        (urllib.error.URLError(PRIVATE), "unknown"),
        (RuntimeError(PRIVATE), "unknown"),
    ],
)
def test_metadata_failure_retains_safe_retry_without_repair(
    monkeypatch, automatic, error, expected
):
    session = QtUpdateSession("0.2.5")
    start_inline(session, monkeypatch)

    def refuse(*_args, **_kwargs):
        raise error

    monkeypatch.setattr(updates, "_open_update_request", refuse)
    assert session.check(automatic=automatic)
    assert session.poll()
    assert not session.recovery
    assert session.check_failed
    assert not session.busy and not session.pending_install
    assert session.ready is None and session.release is None
    assert expected in session.status.lower()
    assert "again" in session.status.lower()
    assert "repair" not in session.status.lower()
    assert "private" not in session.status.lower()
    assert "invalid.example" not in session.status
    assert "sensitive-test-message" not in session.status


@pytest.mark.parametrize("automatic", [False, True])
def test_failed_check_popup_retries_and_clears_failure(
    tmp_path, monkeypatch, automatic
):
    from yt_downloader.qt_quick import update_session

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    app = qt_app()
    bridge = qt_main.Bridge(None)
    bridge._timer.stop()
    session = bridge._updates
    start_inline(session, monkeypatch)

    def refuse(*_args, **_kwargs):
        raise urllib.error.URLError(TimeoutError(PRIVATE))

    monkeypatch.setattr(updates, "_open_update_request", refuse)
    assert session.check(automatic=automatic)
    assert session.poll()
    engine = qt_main.create_engine(bridge)
    window = engine.rootObjects()[0]
    bridge._window = window
    try:
        popup = window.findChild(QObject, "updatePopup")
        popup.open()
        QTest.qWait(180)
        app.processEvents()
        primary = window.findChild(QObject, "updatePrimary")
        body = window.findChild(QObject, "updateBody")
        assert primary.property("label") == "Check again"
        assert primary.property("visible") and primary.property("enabled")
        assert not body.property("truncated")
        assert "repair" not in body.property("text").lower()
        assert "connection" in body.property("text").lower()
        assert window.findChild(QObject, "updateDownloadPage").property("visible")
        successful = updates.ReleaseInfo(
            session.current_version,
            "v" + session.current_version,
            "VODForge",
            "https://github.com/SnowfallHD/vodforge/releases/latest",
            "",
            (),
        )
        monkeypatch.setattr(update_session, "fetch_latest_release", lambda: successful)
        repair_calls = []
        monkeypatch.setattr(bridge, "repairUpdate", lambda: repair_calls.append(True))
        point = primary.mapToScene(QPointF(primary.width() / 2, primary.height() / 2))
        QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, point.toPoint())
        assert session.poll()
        bridge.updateChanged.emit()
        app.processEvents()
        assert not repair_calls
        assert not session.check_failed and not session.recovery
        assert session.status == "VODForge is up to date."
        assert not window.findChild(QObject, "updateDownloadPage").property("visible")
    finally:
        window.close()
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        bridge.close()


@pytest.fixture
def update_notice_scene(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    app = qt_app()
    bridge = qt_main.Bridge(None)
    bridge._timer.stop()
    bridge._engagement.presented_welcome()
    bridge._settings["whats_new_seen"] = qt_main.SHOWCASE_ID
    engine = qt_main.create_engine(bridge)
    window = engine.rootObjects()[0]
    bridge._window = window
    yield app, bridge, window
    window.close()
    engine.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    bridge.close()


def update_click(window, item):
    polish_scene(window.contentItem())
    point = item.mapToScene(QPointF(item.width() / 2, item.height() / 2))
    assert 0 < point.x() < window.width()
    assert 0 < point.y() < window.height()
    QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, point.toPoint())
    QTest.qWait(180)


UPDATER_STATES = (
    "current",
    "check",
    "available",
    "manual",
    "download",
    "repair",
    "recovery",
    "check_failed",
    "ready",
    "waiting",
    "handoff",
)


def set_update_state(session, tmp_path, state):
    session.available = state in {"available", "download"}
    session.manual = state == "manual"
    session.recovery = state == "recovery"
    session.check_failed = state == "check_failed"
    session.busy = state in {"check", "download", "repair"}
    session.stage = (
        "check"
        if state == "check"
        else "downloading_repair"
        if state == "repair"
        else "download"
    )
    session.ready = tmp_path / "verified" if state in {"ready", "waiting"} else None
    session.pending_install = state == "waiting"
    session.handoff_started = state == "handoff"


@pytest.mark.parametrize("size", [(1100, 740), (820, 560)])
@pytest.mark.parametrize("route", ["Forge", "Library", "Watch", "Activity"])
def test_update_states_never_insert_row_or_reflow_body(
    update_notice_scene, tmp_path, size, route
):
    app, bridge, window = update_notice_scene
    window.resize(*size)
    bridge.selectHome(route, False)
    viewport = window.findChild(QObject, "forgeViewport")
    layout = viewport.parentItem()

    def geometry():
        polish_scene(window.contentItem())
        app.processEvents()
        items = list(layout.childItems())
        items.extend(
            window.findChild(QObject, name)
            for name in ("forgeComposerShell", "forgeCommandRow", "forgeScene")
        )
        result = [
            (
                item.objectName(),
                item.mapToScene(QPointF()).x(),
                item.mapToScene(QPointF()).y(),
                item.width(),
                item.height(),
            )
            for item in items
            if item.isVisible() and item.objectName() != "updateNoticeRow"
        ]
        if route == "Forge":
            result.append(
                (
                    "forgeScroll",
                    viewport.property("contentItem").property("contentY"),
                    viewport.property("contentHeight"),
                )
            )
        return result

    set_update_state(bridge._updates, tmp_path, "current")
    bridge.updateChanged.emit()
    baseline = geometry()
    changes = {}
    for state in UPDATER_STATES:
        set_update_state(bridge._updates, tmp_path, state)
        bridge.updateChanged.emit()
        current = geometry()
        if current != baseline:
            changes[state] = {"before": baseline, "after": current}
        assert not window.findChild(QObject, "updatePopup").property("visible")
    assert not changes, changes
    assert window.findChild(QObject, "updateNoticeRow") is None
    assert window.findChild(QObject, "updateNoticeButton") is None


@pytest.mark.parametrize("state", UPDATER_STATES)
def test_settings_check_opens_existing_popup_for_every_update_state(
    update_notice_scene, tmp_path, monkeypatch, state
):
    app, bridge, window = update_notice_scene
    set_update_state(bridge._updates, tmp_path, state)
    bridge.updateChanged.emit()
    checks = []
    monkeypatch.setattr(bridge._updates, "check", lambda: checks.append(True) or False)
    # Reach the real Settings form using its existing header action.
    update_click(window, window.findChild(QObject, "headerSettingsButton"))
    settings = window.findChild(QObject, "downloadSettingsPopup")
    assert settings.property("visible")
    update_click(window, window.findChild(QObject, "settingsCheckForUpdatesButton"))
    app.processEvents()
    assert checks == [True]
    assert not settings.property("visible")
    popup = window.findChild(QObject, "updatePopup")
    assert popup.property("visible")
    primary = window.findChild(QObject, "updatePrimary")
    assert primary.property("visible") == (
        state not in {"check", "download", "repair", "manual", "waiting", "handoff"}
    )
    assert window.findChild(QObject, "updateProgress").property("visible") == (
        state in {"check", "download", "repair"}
    )
    if state == "check":
        assert "Looking for the latest" in window.findChild(
            QObject, "updateBody"
        ).property("text")
    if state == "recovery":
        assert primary.property("label") == "Repair VODForge"
    if state == "check_failed":
        assert primary.property("label") == "Check again"
    assert bridge._updates.pending_install == (state == "waiting")
    assert bridge._updates.handoff_started == (state == "handoff")
    update_click(window, window.findChild(QObject, "updateDismiss"))
    assert not popup.property("visible")


@pytest.mark.parametrize(
    "state,expected",
    [
        ("current", "check"),
        ("check_failed", "check"),
        ("available", "download"),
        ("recovery", "repair"),
        ("ready", "install"),
    ],
)
def test_update_popup_primary_keeps_existing_dispatch(
    update_notice_scene, tmp_path, monkeypatch, state, expected
):
    _app, bridge, window = update_notice_scene
    session = bridge._updates
    set_update_state(session, tmp_path, state)
    calls = []
    monkeypatch.setattr(session, "check", lambda: calls.append("check") or False)
    monkeypatch.setattr(
        session,
        "download",
        lambda **kwargs: (
            calls.append("repair" if kwargs.get("repair") else "download") or False
        ),
    )
    monkeypatch.setattr(
        session, "request_install_now", lambda: calls.append("install") or False
    )
    bridge.updateChanged.emit()
    window.findChild(QObject, "updatePopup").open()
    QTest.qWait(100)
    update_click(window, window.findChild(QObject, "updatePrimary"))
    assert calls == [expected]


@pytest.mark.parametrize("key", [Qt.Key_Return, Qt.Key_Space])
def test_settings_check_keyboard_dispatch(update_notice_scene, monkeypatch, key):
    _app, bridge, window = update_notice_scene
    calls = []
    monkeypatch.setattr(bridge._updates, "check", lambda: calls.append(True) or False)
    window.findChild(QObject, "downloadSettingsPopup").open()
    QTest.qWait(100)
    button = window.findChild(QObject, "settingsCheckForUpdatesButton")
    button.forceActiveFocus(Qt.TabFocusReason)
    QTest.keyClick(window, key)
    QTest.qWait(100)
    assert calls == [True]
    assert window.findChild(QObject, "updatePopup").property("visible")
