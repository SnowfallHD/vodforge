"""Update-service failures must not imply a damaged local installation."""

import ssl
import urllib.error

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QObject, QPointF, Qt
from PySide6.QtTest import QTest

from tests.test_qt_scene_port import qt_app
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
