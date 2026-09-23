"""Qt update intent must keep verified helper and active-work gates intact."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from yt_downloader.qt_quick import update_session as qt_updates
from yt_downloader.updates import (
    MacUpdatePlan,
    ReleaseInfo,
    record_update_telemetry_receipts,
)


def _release(version: str) -> ReleaseInfo:
    return ReleaseInfo(
        version=version,
        tag_name=f"v{version}",
        name="VODForge",
        html_url="https://github.com/SnowfallHD/vodforge/releases/latest",
        notes="",
        assets=(),
    )


def test_new_release_without_platform_asset_offers_manual_page(
    monkeypatch: Any,
) -> None:
    session = qt_updates.QtUpdateSession("0.2.2")
    monkeypatch.setattr(qt_updates, "release_asset_for_platform", lambda _release: None)
    session.events.put(("checked", _release("0.2.3")))
    assert session.poll()
    assert session.manual and not session.available
    assert not session.download()
    assert "download page" in session.status


def test_verified_mac_update_handoff_waits_for_idle_work(
    tmp_path: Path, monkeypatch: Any
) -> None:
    session = qt_updates.QtUpdateSession("0.2.2")
    release = _release("0.2.3")
    archive = tmp_path / "verified.zip"
    target = tmp_path / "VODForge.app"
    plan = MacUpdatePlan(archive, target, tmp_path / "staging")
    calls: list[tuple[Any, ...]] = []
    monkeypatch.setattr(qt_updates, "is_macos", lambda: True)
    monkeypatch.setattr(qt_updates, "running_macos_app", lambda: target)
    monkeypatch.setattr(qt_updates, "download_verified_update", lambda *_args: archive)
    monkeypatch.setattr(qt_updates, "cleanup_stale_macos_updates", lambda *_args: None)
    monkeypatch.setattr(qt_updates, "prepare_macos_update", lambda *_args: plan)
    monkeypatch.setattr(
        qt_updates,
        "launch_macos_update",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )
    session._download_worker(release)
    assert session.poll() and session.ready == plan
    assert not session.install(downloads_busy=True, telemetry_permitted=False)
    assert not calls and session.ready == plan
    assert session.install(downloads_busy=False, telemetry_permitted=False)
    assert calls == [((plan,), {"repair": False, "telemetry_permitted": False})]
    assert session.ready is None


def test_repair_refuses_downgrade_and_failed_helper_keeps_recovery(
    tmp_path: Path, monkeypatch: Any
) -> None:
    session = qt_updates.QtUpdateSession("0.2.3")
    monkeypatch.setattr(qt_updates, "fetch_latest_release", lambda: _release("0.2.2"))
    monkeypatch.setattr(
        qt_updates,
        "download_verified_update",
        lambda *_args: (_ for _ in ()).throw(AssertionError("downgrade downloaded")),
    )
    session._download_worker(None)
    assert session.poll() and session.recovery and session.ready is None

    installer = tmp_path / "verified.exe"
    session.ready = installer
    monkeypatch.setattr(qt_updates, "is_windows", lambda: True)
    monkeypatch.setattr(
        qt_updates,
        "launch_windows_update",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("helper refused")),
    )
    assert not session.install(downloads_busy=False, telemetry_permitted=False)
    assert session.recovery and session.ready == installer


def test_check_again_retires_previous_ready_installer(
    monkeypatch: Any, tmp_path: Path
) -> None:
    session = qt_updates.QtUpdateSession("0.2.2")
    session.ready = tmp_path / "old.exe"
    session.release = _release("0.2.3")
    session.available = True
    monkeypatch.setattr(session, "_start", lambda *_args: True)
    assert session.check()
    assert session.ready is None
    assert session.release is None and not session.available


def test_update_outcomes_are_bounded_and_consumed_once() -> None:
    session = qt_updates.QtUpdateSession("0.2.2")
    session.stage = "download"
    session.events.put(("error", "private installer path and provider detail"))
    assert session.poll() and session.recovery
    assert "private installer path" not in session.status
    assert session.take_observations() == [("failed", {"update_stage": "download"})]
    assert session.take_observations() == []


def test_shared_update_receipt_queues_only_bounded_action_once(tmp_path: Path) -> None:
    executable = tmp_path / "VODForge.exe"
    executable.write_bytes(b"installed")
    folder = tmp_path / "updates" / "v0.2.3"
    folder.mkdir(parents=True)
    token = uuid.uuid4().hex
    receipt = folder / f"handoff-{token}.json"
    receipt.write_text(
        json.dumps(
            {
                "status": "failed",
                "executable": str(executable),
                "telemetry_permitted": True,
                "stage": "handoff",
            }
        )
    )

    class Telemetry:
        def __init__(self) -> None:
            self.calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

        def permitted(self) -> bool:
            return True

        def record(self, *args: Any, **kwargs: Any) -> bool:
            self.calls.append((args, kwargs))
            return True

    owner = Telemetry()
    record_update_telemetry_receipts(owner, folder.parent, executable)
    record_update_telemetry_receipts(owner, folder.parent, executable)
    assert owner.calls == [
        (
            ("feature_used",),
            {
                "dedupe_key": token + ":failed",
                "feature": "updater",
                "action": "failed",
                "dimensions": {"update_stage": "handoff"},
            },
        )
    ]
    assert receipt.with_suffix(".failed.telemetry-queued").exists()
