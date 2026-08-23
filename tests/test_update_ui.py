from __future__ import annotations

from pathlib import Path

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
            ReleaseAsset(f"VODForge-Windows-Setup-v{version}.exe", "https://github.com/example/windows", 10),
            ReleaseAsset(f"VODForge-macOS-arm64-v{version}.zip", "https://github.com/example/mac-arm", 10),
            ReleaseAsset(f"VODForge-macOS-x64-v{version}.zip", "https://github.com/example/mac-x64", 10),
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
    monkeypatch.setattr(app_module.messagebox, "showinfo", lambda *args: shown.append(args))

    app._show_update_result(_release("1.2.3"))

    assert shown == []
    assert app.status_var.value == "Ready"
    assert app.update_button.values["text"] == "Up to date"


def test_automatic_check_prompts_for_new_signed_platform_asset(monkeypatch):
    app = _app_stub()
    app.update_check_silent = True
    monkeypatch.setattr(app_module, "__version__", "1.2.3")
    monkeypatch.setattr(app_module.messagebox, "askyesno", lambda *_args: True)
    monkeypatch.setattr(app_module, "release_asset_for_platform", lambda release: release.assets[0])
    started = []
    app._start_update_download = lambda release: started.append(release.tag_name)

    app._show_update_result(_release("1.2.4"))

    assert started == ["v1.2.4"]
    assert app.update_button.values["text"] == "Update v1.2.4"


def test_verified_macos_plan_launches_handoff_and_exits_ui(monkeypatch, tmp_path: Path):
    app = _app_stub()
    destroyed = []
    scheduled = []
    app.destroy = lambda: destroyed.append(True)
    app.after = lambda delay, callback: scheduled.append((delay, callback))
    launched = []
    monkeypatch.setattr(app_module, "launch_macos_update", lambda plan: launched.append(plan))
    plan = MacUpdatePlan(
        source_app=tmp_path / "staged-test" / "VODForge.app",
        target_app=tmp_path / "Applications" / "VODForge.app",
        staging_root=tmp_path / "staged-test",
    )

    app._install_downloaded_update(plan)

    assert launched == [plan]
    assert app.update_button.values == {"state": "disabled", "text": "Installing update…"}
    assert scheduled[0][0] == 250
    scheduled[0][1]()
    assert destroyed == [True]
