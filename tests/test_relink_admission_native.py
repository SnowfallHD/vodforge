"""Relink admission and queued cancellation preserve terminal observations."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from threading import Event
from types import MethodType
from unittest.mock import Mock

import pytest

from tests.test_archive_native import application as _application
from tests.test_archive_native import pump, seed
from tests.test_product_telemetry import _permitted_installation
from tests.test_relink_consent_native import _REAL_RECORD
from tests.test_relink_navigation_native import descendants, wait_for
from yt_downloader.archive_work import ArchiveWorkOwner
from yt_downloader.history import load_history, save_history
from yt_downloader.platform_services import capture_own_widget
from yt_downloader.product_telemetry import ProductTelemetryOwner, _load_outbox

application = _application
pytestmark = pytest.mark.skipif(
    os.environ.get("VODFORGE_NATIVE_UI_TESTS") != "1", reason="native display required"
)


@pytest.mark.usefixtures("production_telemetry_contract")
@pytest.mark.parametrize(
    "permission",
    [
        "allowed",
        "denied",
        "late_grant",
        "regrant",
        "observer_unavailable",
        "observer_failure",
    ],
)
@pytest.mark.parametrize("admission", ["refused", "queued_cancel", "queued_timeout"])
def test_relink_admission_has_real_terminal_observation(
    application, tmp_path, monkeypatch, permission, admission
):
    app = application
    seed(app, tmp_path, 1)
    app.history_path = tmp_path / "history.json"
    save_history(app.history_path, app.download_history)
    app.download_history = load_history(app.history_path)
    save_history(app.history_path, app.download_history)
    app._reconcile_library_projection()
    pump(app)
    before_history = json.loads(json.dumps(app.download_history))
    before_disk = app.history_path.read_bytes()
    replacement = tmp_path / "PRIVATE replacement.mp4"
    replacement.write_bytes(b"nonempty existence fixture; no playback claim")
    installation = tmp_path / "installation.json"
    _permitted_installation(installation)
    telemetry = ProductTelemetryOwner(
        state_path=tmp_path / "events.json",
        installation_state_path=installation,
        app_version="0.2.3",
        enabled=permission not in {"denied", "late_grant"},
        d1_recorder=lambda _: False,
        heycatch_recorder=lambda *args, **kwargs: False,
    )
    monkeypatch.setattr(telemetry, "record", MethodType(_REAL_RECORD, telemetry))
    monkeypatch.setattr(app, "product_telemetry", telemetry)
    if permission in {"observer_unavailable", "observer_failure"}:
        monkeypatch.setattr(
            telemetry,
            "bind_operation"
            if permission == "observer_unavailable"
            else "record_operation",
            Mock(side_effect=OSError("PRIVATE observation failure")),
        )
    release, entered = Event(), Event()
    output = (
        Path(os.environ.get("VODFORGE_NATIVE_EVIDENCE_DIR", str(tmp_path)))
        / f"{admission}-{permission}"
    )
    output.mkdir(parents=True, exist_ok=True)

    def capture(phase):
        # Widget state can settle before AppKit presents the new review frame.
        pump(app, 0.15)
        bitmap = capture_own_widget(app)
        assert bitmap is not None
        bitmap.save(output / f"{phase}.png")

    try:
        app._archive_begin_relink(None, (0,), exact=str(replacement))
        panel = app._archive_overlay

        def ready():
            return next(
                (
                    w
                    for w in descendants(panel)
                    if w.winfo_class() == "TButton"
                    and str(w.cget("text")) == "Update location"
                    and "disabled" not in w.state()
                ),
                None,
            )

        wait_for(app, ready)
        # Verification is complete. Exercise the real worker's admission/lifecycle,
        # not a fake return value or manually injected completion callback.
        app._archive_worker.close()
        if admission.startswith("queued_"):
            original_run = ArchiveWorkOwner._run

            def held_run(owner):
                entered.set()
                assert release.wait(6)
                original_run(owner)

            monkeypatch.setattr(ArchiveWorkOwner, "_run", held_run)
            app._archive_worker = ArchiveWorkOwner()
            assert entered.wait(1)
        if permission == "late_grant":
            telemetry.set_enabled(True)
        elif permission == "regrant":
            telemetry.set_enabled(False)
            telemetry.set_enabled(True)
        capture("before")
        ready().invoke()
        if admission.startswith("queued_"):
            assert app._archive_commit_active
            if admission == "queued_timeout":
                app._archive_work_deadline = time.monotonic() - 1
                wait_for(app, lambda: app._archive_commit_cancel_reason == "timeout")
            else:
                app._focus_nav_buttons["watch"].invoke()
            assert app._archive_commit_active and app._archive_callback is not None
            capture("during")
            release.set()
            wait_for(app, lambda: not app._archive_commit_active)
        else:
            capture("during")
        assert not app._archive_commit_active
        assert app._archive_callback is None
        assert app._archive_overlay is panel
        assert app.download_history == before_history
        assert app.history_path.read_bytes() == before_disk
        status = panel._archive_relink_status.get()
        assert "Saving" not in status
        if admission == "refused":
            assert "could not start" in status
        elif admission == "queued_timeout":
            assert "took too long" in status.lower()
        else:
            assert "cancelled" in status.lower()
        capture("after")
        back = next(
            w
            for w in descendants(panel)
            if w.winfo_class() == "TButton" and str(w.cget("text")) == "Back to Library"
        )
        back.invoke()
        pump(app)
        assert app._archive_overlay is None
        assert (
            app.download_history == before_history
            and app.history_path.read_bytes() == before_disk
        )
        capture("returned")
        telemetry.shutdown(2)
        events = [
            event
            for event in _load_outbox(tmp_path / "events.json")
            if event.feature == "archive_relink_operation"
        ]
        expected = ["requested", "verified", "commit_requested"]
        expected += (
            ["failed"]
            if admission == "refused"
            else [
                "cancel_requested",
                "timed_out" if admission == "queued_timeout" else "cancelled",
            ]
        )
        assert [event.action for event in events] == (
            expected if permission == "allowed" else []
        )
        if events:
            assert len({event.dimensions["operation_id"] for event in events}) == 1
            payloads = [event.public_payload() for event in events]
            assert "PRIVATE" not in json.dumps(payloads) and str(
                tmp_path
            ) not in json.dumps(payloads)
            (output / "producer-events.json").write_text(json.dumps(payloads, indent=2))
        (output / "scope.json").write_text(
            json.dumps(
                {
                    "input": "Direct real button invocation, not physical input",
                    "admission": admission,
                    "permission": permission,
                    "phases": ["before", "during", "after", "returned"],
                    "history_unchanged": True,
                    "worker": "Real closed owner or real owner held before its run loop",
                    "capture_intervention": "pump(app, .15) before native view-cache capture; settled-state evidence only",
                    "limits": "No unassisted temporal, media decode, native picker, physical-input, Windows or exact-package claim",
                },
                indent=2,
            )
        )
    finally:
        release.set()
        telemetry.shutdown(2)


@pytest.mark.usefixtures("production_telemetry_contract")
@pytest.mark.parametrize(
    "permission",
    [
        "allowed",
        "denied",
        "late_grant",
        "regrant",
        "observer_unavailable",
        "observer_failure",
    ],
)
@pytest.mark.parametrize(
    "outcome", ["verification_failed", "verification_timeout", "verification_refused"]
)
def test_verification_settlement_and_return_are_truthful(
    application, tmp_path, monkeypatch, permission, outcome
):
    from yt_downloader import archive_library_ui

    app = application
    seed(app, tmp_path, 1)
    before_history = json.loads(json.dumps(app.download_history))
    replacement = tmp_path / "PRIVATE replacement.mp4"
    replacement.write_bytes(b"existence only")
    installation = tmp_path / "installation.json"
    _permitted_installation(installation)
    telemetry = ProductTelemetryOwner(
        state_path=tmp_path / "events.json",
        installation_state_path=installation,
        app_version="0.2.3",
        enabled=permission not in {"denied", "late_grant"},
        d1_recorder=lambda _: False,
        heycatch_recorder=lambda *args, **kwargs: False,
    )
    monkeypatch.setattr(telemetry, "record", MethodType(_REAL_RECORD, telemetry))
    monkeypatch.setattr(app, "product_telemetry", telemetry)
    if permission in {"observer_unavailable", "observer_failure"}:
        monkeypatch.setattr(
            telemetry,
            "bind_operation"
            if permission == "observer_unavailable"
            else "record_operation",
            Mock(side_effect=OSError("PRIVATE observation failure")),
        )
    release, entered = Event(), Event()
    verify = archive_library_ui.verify_relink

    def held_verify(*args, **kwargs):
        entered.set()
        assert release.wait(6)
        if outcome == "verification_failed":
            raise OSError("PRIVATE unavailable file")
        return verify(*args, **kwargs)

    monkeypatch.setattr(archive_library_ui, "verify_relink", held_verify)
    output = (
        Path(os.environ.get("VODFORGE_NATIVE_EVIDENCE_DIR", str(tmp_path)))
        / f"{outcome}-{permission}"
    )
    output.mkdir(parents=True, exist_ok=True)

    def capture(phase):
        # Widget state can settle before AppKit presents the new review frame.
        pump(app, 0.15)
        bitmap = capture_own_widget(app)
        assert bitmap is not None
        bitmap.save(output / f"{phase}.png")

    try:
        if outcome == "verification_refused":
            app._archive_worker.close()
        capture("before")
        app._archive_begin_relink(None, (0,), exact=str(replacement))
        panel = app._archive_overlay
        if outcome != "verification_refused":
            wait_for(app, entered.is_set)
        if permission == "late_grant":
            telemetry.set_enabled(True)
        elif permission == "regrant":
            telemetry.set_enabled(False)
            telemetry.set_enabled(True)
        capture("during")
        if outcome == "verification_timeout":
            app._archive_work_deadline = time.monotonic() - 1
            wait_for(app, lambda: app._archive_callback is None)
            settled_status = panel._archive_relink_status.get()
            release.set()
            wait_for(app, lambda: not app._archive_worker.busy)
            pump(app, 0.1)
            assert panel._archive_relink_status.get() == settled_status, (
                "Retired verification changed the review"
            )
        elif outcome != "verification_refused":
            release.set()
            wait_for(app, lambda: app._archive_callback is None)
        status = panel._archive_relink_status.get()
        document = next(w for w in descendants(panel) if w.winfo_class() == "Text")
        contents = document.get("1.0", "end")
        buttons = [w for w in descendants(panel) if w.winfo_class() == "TButton"]
        checks = {
            "history_unchanged": app.download_history == before_history,
            "verification_stopped": app._archive_callback is None
            and app._archive_work_deadline == 0,
            "status_settled": status != "Checking selected files…",
            "rows_settled": "Checking file" not in contents,
            "update_disabled": all(
                "disabled" in w.state()
                for w in buttons
                if str(w.cget("text")).startswith("Update")
            ),
        }
        capture("after")
        next(w for w in buttons if str(w.cget("text")) == "Back to Library").invoke()
        pump(app)
        checks["returned"] = app._archive_overlay is None
        capture("returned")
        telemetry.shutdown(2)
        events = [
            event
            for event in _load_outbox(tmp_path / "events.json")
            if event.feature == "archive_relink_operation"
        ]
        expected = [
            "requested",
            "timed_out" if outcome == "verification_timeout" else "failed",
        ]
        checks["exact_terminal_observations"] = [event.action for event in events] == (
            expected if permission == "allowed" else []
        )
        (output / "scope.json").write_text(
            json.dumps(
                {
                    "input": "Direct return-button invocation; real closed worker for refusal, gated real worker otherwise",
                    "phases": ["before", "during", "after", "returned"],
                    "checks": checks,
                    "timeout": "Expired real poller deadline only in timeout cases; not genuinely slow storage",
                    "admission": outcome,
                    "during": "Immediate refusal has no pending-work phase; capture shows the synchronous outcome"
                    if outcome == "verification_refused"
                    else "Verification held pending",
                    "capture_intervention": "pump(app, .15) before native view-cache capture; settled-state evidence only",
                    "limits": "No unassisted temporal, native picker, physical input, Windows, package or whole-screen qualification",
                },
                indent=2,
            )
        )
        assert all(checks.values()), {k: v for k, v in checks.items() if not v}
        if events:
            assert len({event.dimensions["operation_id"] for event in events}) == 1
            payloads = [event.public_payload() for event in events]
            assert "PRIVATE" not in json.dumps(payloads) and str(
                tmp_path
            ) not in json.dumps(payloads)
            (output / "producer-events.json").write_text(json.dumps(payloads, indent=2))
    finally:
        release.set()
        telemetry.shutdown(2)
