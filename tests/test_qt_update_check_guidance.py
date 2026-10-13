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
    engine = qt_main.create_engine(bridge)
    window = engine.rootObjects()[0]
    bridge._window = window
    yield app, bridge, window
    window.close()
    engine.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    bridge.close()


def notice_click(window, item):
    polish_scene(window.contentItem())
    point = item.mapToScene(QPointF(item.width() / 2, item.height() / 2))
    assert 0 < point.x() < window.width()
    assert 0 < point.y() < window.height()
    QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, point.toPoint())
    QTest.qWait(180)


@pytest.mark.parametrize("width", [620, 1100])
def test_available_update_is_discoverable_without_automatic_popup(
    update_notice_scene, monkeypatch, width
):
    from yt_downloader.qt_quick import update_session

    app, bridge, window = update_notice_scene
    window.setWidth(width)
    window.setHeight(520)
    notice = window.findChild(QObject, "updateNoticeButton")
    popup = window.findChild(QObject, "updatePopup")
    assert notice is not None
    assert not notice.property("visible")
    session = bridge._updates
    start_inline(session, monkeypatch)
    release = updates.ReleaseInfo(
        "99.0.0",
        "v99.0.0",
        "Fixture update",
        "https://github.com/SnowfallHD/vodforge/releases/latest",
        "",
        (),
    )
    monkeypatch.setattr(update_session, "fetch_latest_release", lambda: release)
    monkeypatch.setattr(
        update_session, "release_asset_for_platform", lambda _: object()
    )
    assert session.check(automatic=True) and session.poll()
    assert session.available
    bridge.updateChanged.emit()
    app.processEvents()
    for route in ("Forge", "Library", "Watch", "Activity"):
        bridge.selectHome(route, False)
        polish_scene(window.contentItem())
        assert notice.property("visible") and notice.property("enabled")
        assert notice.property("label") == "Update available"
        point = notice.mapToScene(QPointF())
        assert 0 <= point.x() and point.x() + notice.width() <= window.width()
        assert 0 <= point.y() and point.y() + notice.height() <= window.height()
        assert not popup.property("visible")
        assert not window.findChild(QObject, "downloadSettingsPopup").property(
            "visible"
        )
    assert not bridge._updates._shown
    current = updates.ReleaseInfo(
        session.current_version,
        "v" + session.current_version,
        "Fixture current",
        "https://github.com/SnowfallHD/vodforge/releases/latest",
        "",
        (),
    )
    monkeypatch.setattr(update_session, "fetch_latest_release", lambda: current)
    assert session.check(automatic=True) and session.poll()
    bridge.updateChanged.emit()
    app.processEvents()
    assert not notice.property("visible")
    assert not popup.property("visible")


@pytest.mark.parametrize("width", [620, 1100])
def test_update_notice_later_reopens_without_starting_work(
    update_notice_scene, tmp_path, monkeypatch, width
):
    from tests.worker_fixtures import _worker_test_job
    from yt_downloader.qt_quick import update_session

    _app, bridge, window = update_notice_scene
    window.setWidth(width)
    window.setHeight(520)
    session = bridge._updates
    session.available = True
    session.status = "VODForge v0.2.6 is available."
    bridge.updateChanged.emit()
    starts = []
    monkeypatch.setattr(session, "_start", lambda *_: starts.append(True))
    observed = []
    monkeypatch.setattr(
        update_session,
        "operation",
        lambda _owner, _feature, action, *_args, **_kwargs: observed.append(action),
    )
    active = _worker_test_job(tmp_path)
    queued = _worker_test_job(tmp_path)
    bridge._runtime.active_job = active
    bridge._runtime.queued.append(queued)
    notice = window.findChild(QObject, "updateNoticeButton")
    popup = window.findChild(QObject, "updatePopup")
    assert notice is not None
    notice_click(window, notice)
    assert popup.property("visible")
    assert (
        window.findChild(QObject, "updatePrimary").property("label")
        == "Download update"
    )
    # A repeated background pointer click while the modal is open must not
    # start an operation, dismiss/reopen it or record another offer exposure.
    notice_click(window, notice)
    assert popup.property("visible")
    dismiss = window.findChild(QObject, "updateDismiss")
    assert dismiss.property("label") == "Later"
    notice_click(window, dismiss)
    assert not popup.property("visible") and notice.property("visible")
    notice_click(window, notice)
    assert popup.property("visible")
    notice_click(window, dismiss)
    assert not popup.property("visible") and notice.property("visible")
    assert starts == []
    assert session.available and not session.pending_install
    assert observed.count("shown") == 1
    assert observed.count("deferred") == 2
    assert bridge._runtime.active_job is active
    assert bridge._runtime.queued == [queued]
    assert bridge.selection == "Forge"
    assert not session.busy


@pytest.mark.parametrize("key", [Qt.Key_Return, Qt.Key_Space])
def test_update_notice_keyboard_opens_existing_offer(update_notice_scene, key):
    _app, bridge, window = update_notice_scene
    bridge._updates.available = True
    bridge.updateChanged.emit()
    polish_scene(window.contentItem())
    notice = window.findChild(QObject, "updateNoticeButton")
    assert notice.property("accessibilityLabel") == "Update available"
    assert notice.property("activeFocusOnTab")
    notice.forceActiveFocus(Qt.TabFocusReason)
    assert notice.property("activeFocus")
    QTest.keyClick(window, key)
    QTest.qWait(180)
    assert window.findChild(QObject, "updatePopup").property("visible")
    assert bridge._updates.available and not bridge._updates.pending_install


@pytest.mark.parametrize(
    "state, label, visible",
    [
        ("current", "Update available", False),
        ("check", "Checking for updates", False),
        ("available", "Update available", True),
        ("manual", "Update available", True),
        ("download", "Updating VODForge", True),
        ("repair", "Updating VODForge", True),
        ("recovery", "Update needs attention", True),
        ("check_failed", "Update check unavailable", True),
        ("ready", "Update ready", True),
        ("waiting", "Update ready", True),
        ("handoff", "Restarting VODForge", True),
    ],
)
def test_update_notice_tracks_existing_owner_states(
    update_notice_scene, tmp_path, state, label, visible
):
    _app, bridge, window = update_notice_scene
    session = bridge._updates
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
    bridge.updateChanged.emit()
    polish_scene(window.contentItem())
    notice = window.findChild(QObject, "updateNoticeButton")
    assert notice is not None
    assert notice.property("visible") == visible
    assert notice.property("label") == label
    popup = window.findChild(QObject, "updatePopup")
    assert not popup.property("visible")
    if visible:
        notice_click(window, notice)
        assert popup.property("visible")
        primary = window.findChild(QObject, "updatePrimary")
        assert primary.property("visible") == (
            state not in {"download", "repair", "manual", "waiting", "handoff"}
        )
        if state == "recovery":
            assert primary.property("label") == "Repair VODForge"
        if state == "check_failed":
            assert primary.property("label") == "Check again"
        assert session.pending_install == (state == "waiting")
        assert session.handoff_started == (state == "handoff")
