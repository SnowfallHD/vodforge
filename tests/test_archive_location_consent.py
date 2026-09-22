"""Storage-location producers retain the consent decision at request time."""

import json
import os
from pathlib import Path
from threading import Event
from types import MethodType, SimpleNamespace
from unittest.mock import Mock

import pytest

from tests.test_product_telemetry import _permitted_installation
from yt_downloader.archive_library_ui import ArchiveLibraryMixin
from yt_downloader.archive_paths import ArchivePath
from yt_downloader.archive_work import ArchiveWorkResult
from yt_downloader.product_telemetry import ProductTelemetryOwner, _load_outbox


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
@pytest.mark.parametrize("outcome", ["completed", "failed", "timed_out", "cancelled"])
def test_location_observations_keep_request_consent(
    tmp_path, monkeypatch, permission, outcome
):
    installation = tmp_path / "installation.json"
    _permitted_installation(installation)
    telemetry = ProductTelemetryOwner(
        state_path=tmp_path / "outbox.json",
        installation_state_path=installation,
        app_version="0.2.3",
        enabled=permission not in {"denied", "late_grant"},
        d1_recorder=lambda _: False,
        heycatch_recorder=lambda *args, **kwargs: False,
    )
    if permission in {"observer_unavailable", "observer_failure"}:
        monkeypatch.setattr(
            telemetry,
            "bind_operation"
            if permission == "observer_unavailable"
            else "record_operation",
            Mock(side_effect=OSError("PRIVATE observer error")),
        )
    folder = tmp_path / "PRIVATE folder"
    if outcome != "failed":
        folder.mkdir()
    path = ArchivePath.parse(str(folder))
    pending = {}

    def submit(kind, work, done, **callbacks):
        pending.update(work=work, done=done, **callbacks)
        return True

    app = SimpleNamespace(
        product_telemetry=telemetry,
        _archive_context_path=path,
        _archive_status=Mock(),
        status_var=Mock(),
        _archive_submit=submit,
        video_tree=SimpleNamespace(set_location_state=Mock()),
    )
    app._archive_observe = MethodType(ArchiveLibraryMixin._archive_observe, app)
    try:
        ArchiveLibraryMixin._archive_location_request(app, path, "check")
        if permission == "late_grant":
            telemetry.set_enabled(True)
        elif permission == "regrant":
            telemetry.set_enabled(False)
            telemetry.set_enabled(True)
        if outcome in {"completed", "failed"}:
            value = pending["work"](Event())
            assert value == ("available" if outcome == "completed" else "missing")
            pending["done"](
                ArchiveWorkResult(1, "availability", value=value, elapsed_ms=5)
            )
            app.video_tree.set_location_state.assert_called_once_with(path, value)
        else:
            pending["on_timeout" if outcome == "timed_out" else "on_cancel"]()
            app.video_tree.set_location_state.assert_not_called()
        telemetry.shutdown(2)
        events = _load_outbox(tmp_path / "outbox.json")
        assert [event.action for event in events] == (
            ["requested", outcome] if permission == "allowed" else []
        )
        assert folder.exists() == (outcome != "failed")
        if events:
            assert len({event.dimensions["operation_id"] for event in events}) == 1
            assert [event.dimensions["operation_step"] for event in events] == [
                "1",
                "2",
            ]
            payloads = [event.public_payload() for event in events]
            assert "PRIVATE" not in json.dumps(payloads) and str(
                tmp_path
            ) not in json.dumps(payloads)
            output = os.environ.get("VODFORGE_LOCATION_FIXTURE_DIR")
            if output:
                target = Path(output)
                target.mkdir(parents=True, exist_ok=True)
                (target / f"{outcome}.json").write_text(json.dumps(payloads, indent=2))
    finally:
        telemetry.shutdown(2)
