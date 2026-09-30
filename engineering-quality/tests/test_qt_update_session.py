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
    assert calls == [
        (
            (plan,),
            {
                "repair": False,
                "telemetry_permitted": False,
                "telemetry_token": uuid.UUID(session._attempt).hex,
            },
        )
    ]
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
                "repair": True,
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
                "dimensions": {
                    "update_stage": "handoff",
                    "update_attempt": str(uuid.UUID(token)),
                },
            },
        )
    ]
    assert receipt.with_suffix(".failed.telemetry-queued").exists()


def _stored(owner, root):
    from yt_downloader.product_telemetry import _load_outbox

    assert owner.shutdown(2)
    events = [row.public_payload() for row in _load_outbox(root / "events.json")]
    assert "PRIVATE" not in json.dumps(events)
    assert str(root) not in json.dumps(events)
    return events


def _instrumented(tmp_path, monkeypatch, *, permitted=True):
    from tests.test_presentation_diagnostics import real_owner
    from yt_downloader import analytics_consent, product_telemetry

    monkeypatch.setattr(product_telemetry, "telemetry_collection_allowed", lambda: True)
    monkeypatch.setattr(analytics_consent, "telemetry_collection_allowed", lambda: True)

    owner = real_owner(tmp_path / "telemetry", permitted=permitted)
    session = qt_updates.QtUpdateSession("0.2.2")
    session.telemetry = owner
    # Drive provider completions explicitly, including delayed consent changes.
    monkeypatch.setattr(session, "_start", lambda *_args: True)
    monkeypatch.setattr(
        qt_updates, "release_asset_for_platform", lambda _release: object()
    )
    return session, owner


def test_update_funnel_distinguishes_explicit_choice_from_dismissal(
    tmp_path, monkeypatch
):
    session, owner = _instrumented(tmp_path, monkeypatch)
    assert session.check(automatic=True)
    session.events.put(("checked", _release("0.2.3")))
    assert session.poll() and session.available
    session.observe("shown")
    session.observe("shown")  # UI property refresh is not a second impression.
    session.observe("dismissed")
    session.observe("deferred")
    assert session.download()
    plan = MacUpdatePlan(
        tmp_path / "archive", tmp_path / "target", tmp_path / "staging"
    )
    session.events.put(("ready", plan))
    assert session.poll() and session.ready == plan
    assert not session.install(downloads_busy=True, telemetry_permitted=True)
    handoffs = []
    monkeypatch.setattr(
        qt_updates, "launch_macos_update", lambda *a, **kw: handoffs.append(kw)
    )
    assert session.install(downloads_busy=False, telemetry_permitted=True)
    events = _stored(owner, tmp_path / "telemetry")
    assert [e["action"] for e in events] == [
        "check_started",
        "available",
        "shown",
        "dismissed",
        "deferred",
        "download_started",
        "download_completed",
        "install_requested",
        "blocked",
        "install_requested",
        "handoff",
    ]
    assert len({e["dimensions"]["operation_id"] for e in events}) == 1
    assert events[1]["dimensions"]["update_target"] == "0.2.3"
    assert events[8]["dimensions"]["update_blocker"] == "active_work"
    assert all(e["dimensions"]["update_trigger"] == "automatic" for e in events)
    assert handoffs[0]["telemetry_permitted"] is True
    assert (
        str(uuid.UUID(handoffs[0]["telemetry_token"]))
        == events[-1]["dimensions"]["update_attempt"]
    )


def test_update_worker_preserves_machine_cause_before_friendly_copy(
    tmp_path, monkeypatch
):
    import urllib.error

    session, owner = _instrumented(tmp_path, monkeypatch)
    assert session.check()
    monkeypatch.setattr(
        qt_updates,
        "fetch_latest_release",
        lambda: (_ for _ in ()).throw(
            urllib.error.HTTPError("https://PRIVATE", 503, "PRIVATE account", {}, None)
        ),
    )
    session._check_worker()
    assert session.poll() and session.recovery
    assert "PRIVATE" not in session.status
    events = _stored(owner, tmp_path / "telemetry")
    assert [e["action"] for e in events] == ["check_started", "failed"]
    assert events[-1]["failure_detail"]["http_status"] == 503
    assert events[-1]["failure_detail"]["stage"] == "analysis"


def test_update_current_and_no_platform_asset_are_distinct(tmp_path, monkeypatch):
    session, owner = _instrumented(tmp_path, monkeypatch)
    assert session.check()
    session.events.put(("checked", _release("0.2.2")))
    session.poll()
    assert not session.available and not session.manual
    assert session.check()
    monkeypatch.setattr(qt_updates, "release_asset_for_platform", lambda _release: None)
    session.events.put(("checked", _release("0.2.3")))
    session.poll()
    assert session.manual
    events = _stored(owner, tmp_path / "telemetry")
    assert [e["action"] for e in events] == [
        "check_started",
        "current",
        "check_started",
        "unsupported",
    ]
    assert events[0]["dimensions"]["update_target"] == "unknown"
    assert events[2]["dimensions"]["update_target"] == "unknown"
    assert (
        events[0]["dimensions"]["operation_id"]
        != events[2]["dimensions"]["operation_id"]
    )


def test_update_helper_failure_is_not_success_and_keeps_installer(
    tmp_path, monkeypatch
):
    session, owner = _instrumented(tmp_path, monkeypatch)
    session._begin_observation("repair")
    session.ready = MacUpdatePlan(
        tmp_path / "archive", tmp_path / "target", tmp_path / "staging"
    )
    monkeypatch.setattr(
        qt_updates,
        "launch_macos_update",
        lambda *_a, **_kw: (_ for _ in ()).throw(PermissionError("PRIVATE path")),
    )
    assert not session.install(downloads_busy=False, telemetry_permitted=True)
    assert session.ready is not None and session.recovery
    events = _stored(owner, tmp_path / "telemetry")
    assert [e["action"] for e in events] == ["install_requested", "failed"]
    assert events[-1]["failure_detail"]["reason"] == "permission_denied"
    assert events[-1]["dimensions"]["update_stage"] == "handoff"


def test_delayed_update_never_adopts_later_grant(tmp_path, monkeypatch):
    from yt_downloader.analytics_consent import AnalyticsConsentOwner

    session, owner = _instrumented(tmp_path, monkeypatch, permitted=False)
    assert session.check()
    AnalyticsConsentOwner(tmp_path / "telemetry").choose(True)
    owner.set_enabled(True)
    session.events.put(("checked", _release("0.2.3")))
    session.poll()
    session.ready = MacUpdatePlan(
        tmp_path / "archive", tmp_path / "target", tmp_path / "staging"
    )
    handoffs = []
    monkeypatch.setattr(
        qt_updates, "launch_macos_update", lambda *a, **kw: handoffs.append(kw)
    )
    assert session.install(downloads_busy=False, telemetry_permitted=True)
    assert handoffs[0]["telemetry_permitted"] is False
    assert _stored(owner, tmp_path / "telemetry") == []


def test_update_revocation_then_regrant_does_not_resume_old_observation(
    tmp_path, monkeypatch
):
    from yt_downloader.analytics_consent import AnalyticsConsentOwner

    session, owner = _instrumented(tmp_path, monkeypatch)
    assert session.check()
    consent = AnalyticsConsentOwner(tmp_path / "telemetry")
    consent.choose(False)
    owner.set_enabled(False)
    consent.choose(True)
    owner.set_enabled(True)
    session.events.put(("checked", _release("0.2.3")))
    session.poll()
    session.observe("shown")
    session.ready = MacUpdatePlan(
        tmp_path / "archive", tmp_path / "target", tmp_path / "staging"
    )
    handoffs = []
    monkeypatch.setattr(
        qt_updates, "launch_macos_update", lambda *a, **kw: handoffs.append(kw)
    )
    assert session.install(downloads_busy=False, telemetry_permitted=True)
    assert handoffs[0]["telemetry_permitted"] is False
    assert not [
        e
        for e in _stored(owner, tmp_path / "telemetry")
        if e["action"] != "check_started"
    ]
