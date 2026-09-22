"""Native relink cancellation retains the request's consent boundary."""

from __future__ import annotations

import json
import os
from pathlib import Path
from types import MethodType
from unittest.mock import Mock

import pytest

from tests.test_archive_native import application as _application
from tests.test_archive_native import pump, seed
from tests.test_product_telemetry import _permitted_installation
from yt_downloader.platform_services import capture_own_widget
from yt_downloader.product_telemetry import ProductTelemetryOwner, _load_outbox

_REAL_RECORD = ProductTelemetryOwner.record
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
def test_relink_cancel_retains_request_consent(
    application, tmp_path, monkeypatch, permission
):
    app = application
    seed(app, tmp_path, count=1)
    app._select_focus_view("library")
    app.geometry("1100x700")
    pump(app)
    before = json.dumps(app.download_history, sort_keys=True)
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
    # Preview isolation suppresses the class recorder. Restore it only on this
    # temporary owner, whose two injected transports are controlled and offline.
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
    # Keep verification pending to exercise cancellation through the actual UI.
    # No worker or filesystem effects are claimed by this input-lifecycle test.
    monkeypatch.setattr(app._archive_worker, "submit", lambda *args: 1)
    output = (
        Path(os.environ.get("VODFORGE_NATIVE_EVIDENCE_DIR", str(tmp_path))) / permission
    )
    output.mkdir(parents=True, exist_ok=True)

    def capture(name):
        image = capture_own_widget(app)
        assert image is not None
        image.save(output / f"{name}.png")

    try:
        app._archive_begin_relink(
            None, (0,), exact=str(tmp_path / "PRIVATE replacement.mp4")
        )
        pump(app)
        assert app._archive_overlay is not None
        if permission == "late_grant":
            telemetry.set_enabled(True)
        elif permission == "regrant":
            telemetry.set_enabled(False)
            telemetry.set_enabled(True)

        def walk(widget):
            for child in widget.winfo_children():
                yield child
                yield from walk(child)

        cancel = next(
            w
            for w in walk(app._archive_overlay)
            if w.winfo_class() == "TButton" and str(w.cget("text")) == "Back to Library"
        )
        capture("before-cancel")
        cancel.event_generate("<Enter>")
        cancel.event_generate(
            "<ButtonPress-1>", x=cancel.winfo_width() // 2, y=cancel.winfo_height() // 2
        )
        pump(app, 0.08)
        assert app._archive_overlay is not None
        assert "pressed" in cancel.state()
        capture("during-cancel")
        cancel.event_generate(
            "<ButtonRelease-1>",
            x=cancel.winfo_width() // 2,
            y=cancel.winfo_height() // 2,
        )
        pump(app)
        assert app._archive_overlay is None
        assert app._archive_work_deadline == 0
        assert app._archive_callback is None
        assert json.dumps(app.download_history, sort_keys=True) == before
        capture("after-cancel")
        telemetry.shutdown(2)
        events = _load_outbox(tmp_path / "events.json")
        # Other application presentation events are outside this operation receipt.
        events = [
            event for event in events if event.feature == "archive_relink_operation"
        ]
        assert [event.action for event in events] == (
            ["requested", "cancelled"] if permission == "allowed" else []
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
                    "input": "Tk-generated button press/release, not physical or OS-injected input",
                    "phases": ["before-cancel", "during-cancel", "after-cancel"],
                    "history_unchanged": True,
                    "verification": "submission held pending",
                    "limits": "Cancellation only; no verified-file, commit, native picker, whole-family usability or package claim",
                },
                indent=2,
            )
        )
    finally:
        telemetry.shutdown(2)
