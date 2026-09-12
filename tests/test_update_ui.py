from __future__ import annotations

from pathlib import Path

import pytest

import yt_downloader.app as app_module
from yt_downloader.app import DownloaderApp
from yt_downloader.updates import MacUpdatePlan, ReleaseAsset, ReleaseInfo


class FakeButton:
    def __init__(self) -> None:
        self.values = {}

    def config(self, **kwargs) -> None:
        self.values.update(kwargs)


class FakeVar:
    def __init__(self, value: str = "") -> None:
        self.value = value

    def set(self, value: str) -> None:
        self.value = value


def _release(version: str) -> ReleaseInfo:
    tag = f"v{version}"
    return ReleaseInfo(
        version=version,
        tag_name=tag,
        name=f"VODForge {version}",
        html_url=f"https://github.com/SnowfallHD/vodforge/releases/tag/{tag}",
        notes="",
        assets=(
            ReleaseAsset(
                f"VODForge-Windows-Setup-v{version}.exe",
                "https://github.com/example/windows",
                10,
            ),
            ReleaseAsset(
                f"VODForge-macOS-arm64-v{version}.zip",
                "https://github.com/example/mac-arm",
                10,
            ),
            ReleaseAsset(
                f"VODForge-macOS-x64-v{version}.zip",
                "https://github.com/example/mac-x64",
                10,
            ),
        ),
    )


def _app_stub() -> DownloaderApp:
    app = DownloaderApp.__new__(DownloaderApp)
    app.update_button = FakeButton()
    app.status_var = FakeVar("Ready")
    app.update_check_silent = False
    app._schedule_auto_update_check = lambda *_args, **_kwargs: None
    return app


def test_silent_current_version_check_does_not_interrupt_user(monkeypatch):
    app = _app_stub()
    app.update_check_silent = True
    monkeypatch.setattr(app_module, "__version__", "1.2.3")
    shown = []
    monkeypatch.setattr(
        app_module.messagebox, "showinfo", lambda *args: shown.append(args)
    )

    app._show_update_result(_release("1.2.3"))

    assert shown == []
    assert app.status_var.value == "Ready"
    assert app.update_button.values["text"] == "Up to date"


def test_automatic_check_prompts_for_new_signed_platform_asset(monkeypatch):
    app = _app_stub()
    app.update_check_silent = True
    monkeypatch.setattr(app_module, "__version__", "1.2.3")
    monkeypatch.setattr(app_module.messagebox, "askyesno", lambda *_args: True)
    monkeypatch.setattr(
        app_module, "release_asset_for_platform", lambda release: release.assets[0]
    )
    started = []
    app._start_update_download = lambda release: started.append(release.tag_name)

    app._show_update_result(_release("1.2.4"))

    assert started == ["v1.2.4"]
    assert app.update_button.values["text"] == "Update v1.2.4"


def test_verified_macos_plan_launches_handoff_and_exits_ui(monkeypatch, tmp_path: Path):
    app = _app_stub()
    destroyed = []
    scheduled = []
    app._request_application_close = lambda: destroyed.append(True)
    app.after = lambda delay, callback: scheduled.append((delay, callback))
    launched = []
    monkeypatch.setattr(
        app_module, "launch_macos_update", lambda plan, **kwargs: launched.append(plan)
    )
    plan = MacUpdatePlan(
        source_app=tmp_path / "staged-test" / "VODForge.app",
        target_app=tmp_path / "Applications" / "VODForge.app",
        staging_root=tmp_path / "staged-test",
    )

    app._install_downloaded_update(plan)

    assert launched == [plan]
    assert app.update_button.values == {
        "state": "disabled",
        "text": "Installing update…",
    }
    assert scheduled[0][0] == 250
    scheduled[0][1]()
    assert destroyed == [True]


@pytest.mark.parametrize("platform", ["macos", "windows"])
@pytest.mark.parametrize("permitted", [True, False, None])
@pytest.mark.parametrize("repair", [False, True])
def test_update_handoff_preserves_current_telemetry_permission(
    monkeypatch, tmp_path, platform, permitted, repair
):
    from types import SimpleNamespace

    app = _app_stub()
    app._update_repair_requested = repair
    app._request_application_close = lambda: None
    app.after = lambda *_args: None
    app._record_feature = lambda *_args, **_kwargs: None
    if permitted is not None:
        app.product_telemetry = SimpleNamespace(permitted=lambda: permitted)
    launched = []

    def capture_handoff(update, **kwargs):
        launched.append(kwargs)
        return tmp_path / "handoff.json"

    monkeypatch.setattr(app_module, "is_windows", lambda: platform == "windows")
    monkeypatch.setattr(app_module, "launch_macos_update", capture_handoff)
    monkeypatch.setattr(app_module, "launch_windows_update", capture_handoff)
    update = (
        MacUpdatePlan(
            source_app=tmp_path / "staged" / "VODForge.app",
            target_app=tmp_path / "installed" / "VODForge.app",
            staging_root=tmp_path / "staged",
        )
        if platform == "macos"
        else tmp_path / "setup.exe"
    )

    app._install_downloaded_update(update)

    assert len(launched) == 1
    assert launched[0]["repair"] is repair
    assert launched[0].get("telemetry_permitted") is (permitted is True)


def test_windows_update_worker_verifies_installer_before_ready_event(
    monkeypatch,
    tmp_path: Path,
):
    app = _app_stub()
    sequence: list[object] = []

    class EventSink:
        def put(self, event) -> None:
            sequence.append(("event", event))

    installer = tmp_path / "verified update.exe"
    installer.write_bytes(b"signed installer fixture")
    app.events = EventSink()

    def fake_download(_release_info, _destination):
        sequence.append(("download", installer))
        return installer

    monkeypatch.setattr(app_module.sys, "platform", "win32")
    monkeypatch.setattr(app_module, "application_data_dir", lambda: tmp_path)
    monkeypatch.setattr(
        app_module,
        "download_verified_update",
        fake_download,
    )
    monkeypatch.setattr(
        app_module,
        "verify_windows_authenticode",
        lambda path: sequence.append(("verify", path)),
    )

    app._update_download_worker(_release("1.2.4"))

    assert sequence == [
        ("download", installer),
        ("verify", installer),
        ("event", ("update_ready", installer)),
    ]


def test_windows_handoff_changes_status_and_schedules_safe_close(monkeypatch, tmp_path):
    app = _app_stub()
    scheduled = []
    app._request_application_close = lambda: None
    app.after = lambda delay, callback: scheduled.append(callback)
    monkeypatch.setattr(app_module, "is_windows", lambda: True)
    monkeypatch.setattr(
        app_module,
        "launch_windows_update",
        lambda path, **kwargs: tmp_path / "receipt.json",
    )
    app._set_focus_update_state("Downloading update…", "")
    app._install_downloaded_update(tmp_path / "setup.exe")
    assert app.update_button.values == {
        "state": "disabled",
        "text": "Installing update…",
    }
    assert scheduled == [app._request_application_close]


def test_failed_handoff_leaves_app_open_and_exposes_recovery(monkeypatch, tmp_path):
    app = _app_stub()
    monkeypatch.setattr(app_module, "is_windows", lambda: True)

    def fail(path, **kwargs):
        raise RuntimeError("helper denied")

    monkeypatch.setattr(app_module, "launch_windows_update", fail)
    shown = []
    monkeypatch.setattr(
        app_module, "show_update_recovery", lambda *args: shown.append(args)
    )
    app._install_downloaded_update(tmp_path / "setup.exe")
    assert app.update_button.values == {
        "state": "normal",
        "text": "Update needs attention",
    }
    assert "helper denied" in shown[0][1]
    assert "Repair VODForge" in app.status_var.value
    assert shown[0][2] == app._repair_update


def test_update_does_not_interrupt_active_or_queued_media(monkeypatch, tmp_path):
    from types import SimpleNamespace

    monkeypatch.setattr(
        app_module, "launch_windows_update", lambda _: pytest.fail("must not install")
    )
    for state in (
        {"worker": SimpleNamespace(is_alive=lambda: True)},
        {"local_audio_video": SimpleNamespace(active=True)},
        {"pending_jobs": [object()]},
    ):
        app = _app_stub()
        app.__dict__.update(state)
        app._install_downloaded_update(tmp_path / "setup.exe")
        assert app.update_button.values["text"] == "Update ready"


def test_repair_fetches_latest_even_when_current_version_is_installed(
    monkeypatch, tmp_path
):
    app = _app_stub()
    events = []
    from types import SimpleNamespace

    app.events = SimpleNamespace(put=events.append)
    release = _release("1.2.4")
    installer = tmp_path / "VODForge-Windows-Setup-v1.2.4.exe"
    monkeypatch.setattr(app_module, "fetch_latest_release", lambda: release)
    monkeypatch.setattr(app_module, "application_data_dir", lambda: tmp_path)
    monkeypatch.setattr(app_module, "is_macos", lambda: False)
    monkeypatch.setattr(app_module, "is_windows", lambda: True)
    verified = []
    monkeypatch.setattr(
        app_module, "download_verified_update", lambda info, dest: installer
    )
    monkeypatch.setattr(app_module, "verify_windows_authenticode", verified.append)
    app._update_download_worker(None)
    assert verified == [installer]
    assert events == [("update_ready", installer)]


def test_failed_repair_download_routes_to_actionable_recovery(monkeypatch):
    app = _app_stub()
    events = []
    from types import SimpleNamespace

    app.events = SimpleNamespace(put=events.append)

    def offline():
        raise OSError("network unavailable")

    monkeypatch.setattr(app_module, "fetch_latest_release", offline)
    app._update_download_worker(None)
    assert events == [("update_install_error", "network unavailable")]


@pytest.mark.parametrize("silent", [True, False])
def test_update_check_failure_is_actionable_only_when_user_requested(
    monkeypatch, silent
):
    from yt_downloader.ui_events import UiEventHandlersMixin

    app = _app_stub()
    app.update_check_silent = silent
    shown = []
    logged = []
    app._show_update_recovery = shown.append
    app._event_write_diagnostic = logged.append
    UiEventHandlersMixin._handle_update_check_error(app, "network unavailable")
    assert shown == ([] if silent else ["network unavailable"])
    assert bool(logged) is silent
