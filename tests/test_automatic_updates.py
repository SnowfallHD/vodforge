"""Automatic updates stage while open and hand off only after normal shutdown."""

import hashlib
import io
import subprocess
import sys
from pathlib import Path

import pytest
from PySide6.QtCore import QObject

from tests.test_qt_update_check_guidance import (
    update_notice_scene as _update_notice_scene,
)
from tests.test_updates import _write_mac_app
from yt_downloader import updates
from yt_downloader.qt_quick import main as qt_main
from yt_downloader.qt_quick import update_session
from yt_downloader.settings_store import (
    SettingsError,
    load_settings,
    save_settings,
    update_automatic_updates_setting,
)


@pytest.fixture
def update_notice_scene(tmp_path, monkeypatch):
    for scene in _update_notice_scene.__wrapped__(tmp_path, monkeypatch):
        monkeypatch.setattr(scene[1]._updates, "check", lambda **_: False)
        yield scene


def test_default_and_explicit_preference_is_durable(update_notice_scene):
    _, bridge, _ = update_notice_scene
    assert bridge.automaticUpdates
    bridge.setAutomaticUpdates(False)
    assert not bridge.automaticUpdates
    assert load_settings(bridge._settings_path)["automatic_updates"] is False
    bridge._save_preferences()
    assert load_settings(bridge._settings_path)["automatic_updates"] is False
    bridge.setAutomaticUpdates(True)
    assert load_settings(bridge._settings_path)["automatic_updates"] is True


def test_preference_write_failure_cannot_grant_auto_install(
    update_notice_scene, monkeypatch
):
    _, bridge, _ = update_notice_scene
    bridge.setAutomaticUpdates(False)

    def fail(*_):
        raise SettingsError("fixture write refusal")

    monkeypatch.setattr(qt_main, "update_automatic_updates_setting", fail)
    bridge.setAutomaticUpdates(True)
    assert not bridge.automaticUpdates
    assert load_settings(bridge._settings_path)["automatic_updates"] is False


@pytest.mark.parametrize("automatic", [False, True])
def test_check_result_downloads_only_for_automatic_check(
    update_notice_scene, monkeypatch, automatic
):
    _, bridge, _ = update_notice_scene
    session = bridge._updates
    session._trigger = "automatic" if automatic else "manual"
    session.events.put(
        ("checked", updates.ReleaseInfo("99.0.0", "v99.0.0", "fixture", "", "", ()))
    )
    monkeypatch.setattr(
        update_session, "release_asset_for_platform", lambda _: object()
    )
    starts = []
    monkeypatch.setattr(
        session, "_start", lambda worker, name: starts.append(name) or True
    )
    bridge._pump()
    assert bool(starts) == automatic
    assert not session.pending_install


def test_off_during_download_revokes_automatic_install_of_late_ready(
    update_notice_scene, tmp_path
):
    _, bridge, _ = update_notice_scene
    session = bridge._updates
    session.busy = True
    session.automatic_download = True
    bridge.setAutomaticUpdates(False)
    session.events.put(("ready", tmp_path / "verified.exe"))
    session.poll()
    assert session.ready is not None  # manual action remains possible
    assert not session.automatic_download and not session.pending_install


@pytest.mark.parametrize(
    "blocked, saved_off, flush_fails",
    [
        (False, False, False),
        (True, False, False),
        (False, True, False),
        (False, False, True),
    ],
)
def test_close_only_handoff_after_flush_and_fresh_choice(
    update_notice_scene, monkeypatch, tmp_path, blocked, saved_off, flush_fails
):
    _, bridge, _ = update_notice_scene
    calls = []
    bridge._updates.automatic_download = True
    bridge._updates.ready = tmp_path / "installer.exe"
    monkeypatch.setattr(bridge, "_update_work_pending", lambda: blocked)
    monkeypatch.setattr(
        bridge._updates, "install", lambda **kw: calls.append(("install", kw)) or True
    )
    if saved_off:
        update_automatic_updates_setting(bridge._settings_path, False)
    if flush_fails:

        def refuse():
            raise OSError("fixture flush failure")

        monkeypatch.setattr(bridge._runtime, "close", refuse)
        with pytest.raises(OSError):
            bridge.close(normal_quit=True)
    else:
        monkeypatch.setattr(
            bridge._runtime, "close", lambda: calls.append(("flush", {}))
        )
        bridge.close(normal_quit=True)
    installs = [entry for entry in calls if entry[0] == "install"]
    assert bool(installs) == (not blocked and not saved_off and not flush_fails)
    if installs:
        assert calls.index(installs[0]) > calls.index(("flush", {}))
        assert installs[0][1]["relaunch_after_install"] is False
    bridge.close()
    assert len([entry for entry in calls if entry[0] == "install"]) == len(installs)


def test_cancelled_window_close_does_not_handoff(
    update_notice_scene, monkeypatch, tmp_path
):
    _, bridge, window = update_notice_scene
    bridge._updates.automatic_download = True
    bridge._updates.ready = tmp_path / "installer.exe"
    bridge._runtime.active_job = object()
    shutdowns = []
    monkeypatch.setattr(
        bridge._runtime, "begin_shutdown", lambda: shutdowns.append(True)
    )
    handoffs = []
    monkeypatch.setattr(bridge._updates, "install", lambda **kw: handoffs.append(kw))
    assert window.close() is False
    assert shutdowns and not bridge._closed and not handoffs
    bridge._runtime.active_job = None
    bridge._updates.automatic_download = False


def test_single_settings_control_is_bound(update_notice_scene):
    _, bridge, window = update_notice_scene
    button = window.findChild(QObject, "settingsAutomaticUpdatesToggle")
    assert button is not None and button.property("label") == "On"
    button.activated.emit()
    assert button.property("label") == "Off"
    assert load_settings(bridge._settings_path)["automatic_updates"] is False
    button.activated.emit()
    assert button.property("label") == "On"
    assert load_settings(bridge._settings_path)["automatic_updates"] is True


def test_helpers_close_mode_preserves_signatures_and_never_reopens(tmp_path):
    source = tmp_path / "staged-test/VODForge.app"
    target = tmp_path / "VODForge.app"
    _write_mac_app(source)
    _write_mac_app(target)
    script_path = updates.write_macos_swap_script(
        updates.MacUpdatePlan(source, target, source.parent),
        relaunch_after_install=False,
    )
    script = script_path.read_text()
    assert '"status":"installed"' in script
    assert "/usr/bin/open --env" not in script
    assert (
        "lockf -kn" in script
        and "stapler validate" in script
        and "spctl --assess" in script
    )
    if sys.platform != "win32":
        assert (
            subprocess.run(
                ["/bin/bash", "-n", str(script_path)], capture_output=True, check=False
            ).returncode
            == 0
        )
    windows = updates.windows_update_script(
        tmp_path / "VODForge-Windows-Setup-v1.2.3.exe",
        tmp_path / "VODForge.exe",
        123,
        tmp_path / "receipt",
        tmp_path / "ready",
        relaunch_after_install=False,
    )
    assert "$result.status = 'installed'" in windows
    assert "$updateLock.Lock(0, 1)" in windows
    assert "if ($false) {\n" in windows
    assert (
        "TimeStamperCertificate" in windows
        and "Staged installer version mismatch" in windows
    )


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="POSIX lease; Windows exercised by actual Windows suite",
)
def test_running_app_shared_lease_excludes_detached_installer(tmp_path):
    exe = tmp_path / "VODForge.app/Contents/MacOS/VODForge"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"fixture")
    lease = updates.acquire_update_lease(exe)
    lock = Path(str(tmp_path / "VODForge.app") + ".vodforge-update-lock")
    command = [
        sys.executable,
        "-c",
        "import fcntl,sys; f=open(sys.argv[1],'a+b'); fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)",
        str(lock),
    ]
    try:
        assert subprocess.run(command, capture_output=True, check=False).returncode != 0
    finally:
        lease.close()
    assert subprocess.run(command, capture_output=True, check=False).returncode == 0


def test_staged_cache_reuse_requires_fresh_manifest_and_exact_bytes(
    tmp_path, monkeypatch
):
    name = "VODForge-Windows-Setup-v1.2.3.exe"
    content = b"verified fixture payload"
    digest = hashlib.sha256(content).hexdigest()
    release = updates.ReleaseInfo(
        "1.2.3",
        "v1.2.3",
        "fixture",
        "",
        "",
        (
            updates.ReleaseAsset(
                name,
                f"https://github.com/SnowfallHD/vodforge/releases/download/v1.2.3/{name}",
                len(content),
            ),
            updates.ReleaseAsset(
                "SHA256SUMS.txt",
                "https://github.com/SnowfallHD/vodforge/releases/download/v1.2.3/SHA256SUMS.txt",
                100,
            ),
        ),
    )
    (tmp_path / name).write_bytes(content)
    requests = []

    def get(request, **_):
        requests.append(request.full_url)
        return io.BytesIO(
            f"{digest}  {name}\n".encode()
            if request.full_url.endswith("SHA256SUMS.txt")
            else content
        )

    monkeypatch.setattr(updates, "_open_update_request", get)
    assert (
        updates.download_verified_update(
            release, tmp_path, platform_name="win32", machine="AMD64"
        ).read_bytes()
        == content
    )
    assert len(requests) == 1 and requests[0].endswith("SHA256SUMS.txt")
    (tmp_path / name).write_bytes(b"X" * len(content))
    updates.download_verified_update(
        release, tmp_path, platform_name="win32", machine="AMD64"
    )
    assert len(requests) == 3 and not requests[-1].endswith("SHA256SUMS.txt")


def test_cleanup_close_without_normal_quit_cannot_install(
    update_notice_scene, monkeypatch, tmp_path
):
    _, bridge, _ = update_notice_scene
    bridge._updates.ready = tmp_path / "installer.exe"
    bridge._updates.automatic_download = True
    calls = []
    monkeypatch.setattr(bridge._updates, "install", lambda **kw: calls.append(kw))
    bridge.close()
    assert not calls


def test_flush_creating_uncertain_state_blocks_install(
    update_notice_scene, monkeypatch, tmp_path
):
    _, bridge, _ = update_notice_scene
    bridge._updates.ready = tmp_path / "installer.exe"
    bridge._updates.automatic_download = True
    state = {"uncertain": False}
    monkeypatch.setattr(bridge, "_update_work_pending", lambda: state["uncertain"])
    monkeypatch.setattr(bridge._runtime, "close", lambda: state.update(uncertain=True))
    calls = []
    monkeypatch.setattr(bridge._updates, "install", lambda **kw: calls.append(kw))
    bridge.close(normal_quit=True)
    assert not calls


def test_off_cancels_inflight_automatic_download_without_recovery_warning(monkeypatch):
    session = update_session.QtUpdateSession("0.2.5")
    session.automatic_download = True
    session.busy = True
    session.cancel_automatic_download()
    release = updates.ReleaseInfo("0.2.6", "v0.2.6", "fixture", "", "", ())

    def download(*_, cancelled):
        assert cancelled()
        raise InterruptedError("fixture canceled")

    monkeypatch.setattr(update_session, "download_verified_update", download)
    session._download_worker(release, automatic=True)
    session.poll()
    assert not session.busy and not session.recovery and session.ready is None
    assert not session.pending_install


def test_malformed_settings_fail_closed(tmp_path, monkeypatch):
    from tests.test_qt_scene_port import qt_app

    qt_app()
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")

    def refuse(_):
        raise SettingsError("fixture malformed settings")

    monkeypatch.setattr(qt_main, "load_settings", refuse)
    bridge = qt_main.Bridge(None)
    try:
        assert not bridge.automaticUpdates
        bridge.setAutomaticUpdates(True)
        assert not bridge.automaticUpdates
    finally:
        bridge.close()


def test_explicit_on_reauthorizes_existing_stage_but_never_installs_while_open(
    update_notice_scene, monkeypatch, tmp_path
):
    _, bridge, _ = update_notice_scene
    bridge.setAutomaticUpdates(False)
    session = bridge._updates
    session.ready = tmp_path / "verified.exe"
    session.available = True
    session.repair = False
    calls = []
    monkeypatch.setattr(session, "install", lambda **kw: calls.append(kw))
    bridge.setAutomaticUpdates(True)
    assert bridge.automaticUpdates and session.automatic_download
    assert not session.pending_install and not calls


def test_explicit_on_checks_immediately_when_no_stage(update_notice_scene, monkeypatch):
    _, bridge, _ = update_notice_scene
    bridge.setAutomaticUpdates(False)
    calls = []
    monkeypatch.setattr(bridge._updates, "check", lambda **kw: calls.append(kw))
    bridge.setAutomaticUpdates(True)
    assert calls == [{"automatic": True}]


@pytest.mark.skipif(
    sys.platform != "darwin", reason="uses actual macOS lockf/file tools"
)
def test_auto_helper_defers_to_reopened_app_then_installs_without_relaunch(tmp_path):
    import json
    import plistlib
    import shlex

    source = tmp_path / "staged-fixture/VODForge.app"
    target = tmp_path / "installed/VODForge.app"
    for app, data, version in ((source, b"new", "1.2.3"), (target, b"old", "1.2.2")):
        (app / "Contents/MacOS").mkdir(parents=True)
        (app / "Contents/MacOS/VODForge").write_bytes(data)
        (app / "Contents/Info.plist").write_bytes(
            plistlib.dumps(
                {
                    "CFBundleIdentifier": updates.MACOS_BUNDLE_ID,
                    "CFBundleShortVersionString": version,
                }
            )
        )
    verify = tmp_path / "verify"
    verify.write_text(
        "#!/bin/bash\nprintf '%s\\n' 'Identifier=com.snowfallhd.vodforge' 'TeamIdentifier=76G5W4954G'\n"
    )
    verify.chmod(0o700)
    plan = updates.MacUpdatePlan(source, target, source.parent)
    script = updates.write_macos_swap_script(
        plan,
        relaunch_after_install=False,
        expected_digest=hashlib.sha256(b"new").hexdigest(),
        expected_version="1.2.3",
    )
    script.write_text(
        script.read_text()
        .replace("/usr/bin/codesign", shlex.quote(str(verify)))
        .replace("/usr/bin/xcrun stapler", "/usr/bin/true")
        .replace("/usr/sbin/spctl", "/usr/bin/true")
        .replace("/usr/bin/logger", "/usr/bin/true")
    )
    command = [
        "/bin/bash",
        str(script),
        "99999999",
        str(source),
        str(target),
        str(source.parent),
    ]
    lease = updates.acquire_update_lease(target / "Contents/MacOS/VODForge")
    try:
        refused = subprocess.run(command, capture_output=True, check=False, timeout=15)
        assert refused.returncode != 0
        assert (target / "Contents/MacOS/VODForge").read_bytes() == b"old"
        assert source.exists()
    finally:
        lease.close()
    installed = subprocess.run(command, capture_output=True, check=False, timeout=15)
    assert installed.returncode == 0, installed.stderr
    assert (target / "Contents/MacOS/VODForge").read_bytes() == b"new"
    receipt = json.loads(next(tmp_path.glob("handoff-*.json")).read_text())
    assert receipt["status"] == "installed"
    assert "pid" not in receipt


@pytest.mark.skipif(sys.platform != "darwin", reason="uses actual macOS lockf")
def test_install_exclusive_lease_refuses_new_app_until_release(tmp_path):
    exe = tmp_path / "VODForge.app/Contents/MacOS/VODForge"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"fixture")
    lock = Path(str(tmp_path / "VODForge.app") + ".vodforge-update-lock")
    lock.touch()
    process = subprocess.Popen(
        [
            "/usr/bin/lockf",
            "-kn",
            "-t",
            "0",
            str(lock),
            sys.executable,
            "-c",
            "import sys; print('ready',flush=True); sys.stdin.read()",
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        assert process.stdout.readline() == b"ready\n"
        with pytest.raises(RuntimeError, match="finishing an update"):
            updates.acquire_update_lease(exe)
    finally:
        process.stdin.close()
        assert process.wait(timeout=5) == 0
    lease = updates.acquire_update_lease(exe)
    lease.close()


def test_stale_ordinary_settings_save_cannot_undo_latest_explicit_off(tmp_path):
    path = tmp_path / "settings.json"
    save_settings(path, {"automatic_updates": True, "quality": "old"})
    stale = load_settings(path)
    update_automatic_updates_setting(path, False)
    save_settings(path, {**stale, "quality": "new"})
    assert load_settings(path) == {"automatic_updates": False, "quality": "new"}


def test_automatic_off_preserves_explicit_manual_restart(
    update_notice_scene, monkeypatch, tmp_path
):
    _, bridge, _ = update_notice_scene
    session = bridge._updates
    session.pending_install = True
    session.ready = tmp_path / "verified.exe"
    session.automatic_download = False
    calls = []
    monkeypatch.setattr(update_session, "is_windows", lambda: True)
    monkeypatch.setattr(
        update_session, "launch_windows_update", lambda *_, **kw: calls.append(kw)
    )
    bridge.setAutomaticUpdates(False)
    assert session.pending_install and session.ready is not None
    assert session.install(downloads_busy=False, telemetry_permitted=False)
    assert calls[0]["relaunch_after_install"] is True


@pytest.mark.parametrize("enabled", [False, True])
def test_startup_check_and_notice_are_independent_of_automatic_preference(
    update_notice_scene, monkeypatch, enabled
):
    from tests.test_qt_scene_port import polish_scene

    _, bridge, window = update_notice_scene
    bridge.setAutomaticUpdates(enabled)
    checks = []
    monkeypatch.setattr(
        bridge._updates, "check", lambda **kw: checks.append(kw) or True
    )
    monkeypatch.setattr(qt_main.QTimer, "singleShot", lambda *_: None)
    bridge._auto_check_updates()
    assert checks == [{"automatic": True}]
    release = updates.ReleaseInfo("99.0.0", "v99.0.0", "fixture", "", "", ())
    monkeypatch.setattr(
        update_session, "release_asset_for_platform", lambda _: object()
    )
    monkeypatch.setattr(bridge._updates, "download", lambda **_: False)
    for _ in range(2):
        bridge._updates.events.put(("checked", release))
        bridge._pump()
        polish_scene(window.contentItem())
        assert bridge._updates.ready is None
        assert window.findChild(QObject, "updateNoticeButton").property("visible")
        assert not window.findChild(QObject, "updatePopup").property("visible")


def test_general_preferences_write_failure_updates_visible_auto_choice(
    update_notice_scene, monkeypatch
):
    _, bridge, window = update_notice_scene
    button = window.findChild(QObject, "settingsAutomaticUpdatesToggle")
    assert button.property("label") == "On"
    bridge._updates.automatic_download = True

    def refuse(*_):
        raise SettingsError("fixture general preferences failure")

    monkeypatch.setattr(qt_main, "save_settings", refuse)
    bridge._save_preferences()
    assert not bridge.automaticUpdates
    assert button.property("label") == "Off"
    assert not bridge._updates.automatic_download


@pytest.mark.parametrize("ready", [False, True])
def test_install_now_promotes_same_payload_without_second_download(
    update_notice_scene, monkeypatch, tmp_path, ready
):
    from tests.test_qt_scene_port import polish_scene

    _, bridge, window = update_notice_scene
    session = bridge._updates
    session.automatic_download = True
    session.stage = "download"
    session.busy = not ready
    session.available = True
    session.ready = tmp_path / "verified.exe" if ready else None
    installs = []
    monkeypatch.setattr(bridge, "installUpdate", lambda: installs.append(True))
    monkeypatch.setattr(
        session, "download", lambda **_: pytest.fail("duplicate download")
    )
    bridge.updateChanged.emit()
    window.findChild(QObject, "updateNoticeButton").activated.emit()
    polish_scene(window.contentItem())
    primary = window.findChild(QObject, "updatePrimary")
    assert primary.property("visible") and primary.property("label") == "Install now"
    primary.activated.emit()
    assert session.pending_install and not session.automatic_download
    assert len(installs) == int(ready)
    assert not session.request_install_now()
    bridge.setAutomaticUpdates(False)
    assert session.pending_install and not session._download_cancel.is_set()
    if not ready:
        session.events.put(("ready", tmp_path / "verified.exe"))
        bridge._pump()
        assert installs == [True]


def test_dismiss_auto_download_offer_keeps_quit_install_intent(
    update_notice_scene, monkeypatch
):
    from tests.test_qt_scene_port import polish_scene

    _, bridge, window = update_notice_scene
    session = bridge._updates
    session.automatic_download = True
    session.stage = "download"
    session.busy = True
    session.available = True
    bridge.updateChanged.emit()
    window.findChild(QObject, "updateNoticeButton").activated.emit()
    polish_scene(window.contentItem())
    popup = window.findChild(QObject, "updatePopup")
    assert popup.property("visible")
    window.findChild(QObject, "updateDismiss").activated.emit()
    assert not popup.property("visible")
    assert session.automatic_download and not session.pending_install


@pytest.mark.parametrize("repair", [False, True])
def test_recovery_primary_retries_repair_even_with_retained_ready_payload(
    update_notice_scene, monkeypatch, tmp_path, repair
):
    from tests.test_qt_scene_port import polish_scene

    _, bridge, window = update_notice_scene
    session = bridge._updates
    session.ready = tmp_path / "retained-verified.exe"
    session.repair = repair
    session.recovery = True
    actions = []
    monkeypatch.setattr(bridge, "repairUpdate", lambda: actions.append("repair"))
    monkeypatch.setattr(bridge, "installUpdateNow", lambda: actions.append("install"))
    bridge.updateChanged.emit()
    window.findChild(QObject, "updateNoticeButton").activated.emit()
    polish_scene(window.contentItem())
    primary = window.findChild(QObject, "updatePrimary")
    assert primary.property("visible")
    primary.activated.emit()
    assert actions == ["repair"]
    assert primary.property("label") == "Repair VODForge"
    assert session.ready == tmp_path / "retained-verified.exe" and session.recovery
