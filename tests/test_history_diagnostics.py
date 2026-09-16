"""Actual history producers, durable product outbox, and bounded privacy facts."""

from __future__ import annotations

import errno
import json
import os
from pathlib import Path
from types import MethodType, SimpleNamespace

import pytest

from tests.test_archive_ui_owners import Variable
from tests.test_product_telemetry import _permitted_installation
from yt_downloader.app import DownloaderApp
from yt_downloader.archive_library_ui import ArchiveLibraryMixin
from yt_downloader.history import (
    HistoryError,
    load_history,
    pending_history_path,
    stage_history_mutation,
)
from yt_downloader.product_telemetry import ProductTelemetryOwner, _load_outbox

pytestmark = pytest.mark.usefixtures("production_telemetry_contract")


def make_app(tmp_path, monkeypatch, *, consent=True, release=True):
    installation = tmp_path / "installation.json"
    if consent:
        _permitted_installation(installation)
    monkeypatch.setattr(
        "yt_downloader.product_telemetry.telemetry_collection_allowed", lambda: release
    )
    owner = ProductTelemetryOwner(
        state_path=tmp_path / "events.json",
        installation_state_path=installation,
        app_version="0.2.3",
        d1_recorder=lambda _: False,
        heycatch_recorder=lambda *a, **k: False,
    )
    app = SimpleNamespace(
        history_path=tmp_path / "PRIVATE history.json",
        product_telemetry=owner,
        status_var=Variable(),
        _event_write_diagnostic=lambda *a: None,
        _append_log=lambda *a: None,
        _reconcile_library_projection=lambda: None,
        library_output_type_var=SimpleNamespace(
            get=lambda: "MP4", set=lambda value: None
        ),
    )
    for name in ("_archive_usage", "_archive_observe"):
        setattr(app, name, MethodType(getattr(ArchiveLibraryMixin, name), app))
    return app


def payloads(app):
    app.product_telemetry.shutdown(2)
    return [
        event.public_payload()
        for event in _load_outbox(app.history_path.parent / "events.json")
    ]


@pytest.mark.parametrize("boundary", ["startup", "settlement"])
@pytest.mark.parametrize(
    "document,cause",
    [
        ("main", "malformed_json"),
        ("main", "unsupported_schema"),
        ("pending", "malformed_json"),
    ],
)
def test_real_document_failures_have_distinct_durable_diagnostics(
    tmp_path, monkeypatch, boundary, document, cause
):
    app = make_app(tmp_path, monkeypatch)
    path = (
        app.history_path
        if document == "main"
        else pending_history_path(app.history_path)
    )
    raw = (
        '{"PRIVATE":'
        if cause == "malformed_json"
        else '{"schema_version": 999, "items": []}'
    )
    path.write_text(raw)
    for _ in range(2):
        if boundary == "startup":
            DownloaderApp._load_download_history(app)
        else:
            assert not ArchiveLibraryMixin._archive_flush_history(app)
    events = payloads(app)
    failures = [event for event in events if event.get("action") == "failed"]
    assert len(failures) == 2
    assert len({event["dimensions"]["operation_id"] for event in failures}) == 2
    for event in failures:
        assert event["feature"] == "archive_history_operation"
        dimensions = event["dimensions"]
        assert dimensions["history_boundary"] == boundary
        assert dimensions["history_document"] == document
        assert dimensions["history_phase"] == (
            "parse" if cause == "malformed_json" else "validate"
        )
        assert dimensions["build_revision"] == "unknown"
        assert dimensions["operation_step"] == "2"
        detail = event["failure_detail"]
        assert detail["failure_code"] == "history_" + cause
        assert detail["reason"] == "validation"
        assert detail["stage"] == "history"
        assert detail["source_module"] == "history"
        assert detail["source_scope"] == "first_party_frame"
        assert 1 <= detail["source_line"] <= 100000
        assert "os_error" not in detail
    assert app._history_recovery_blocked
    assert path.read_text() == raw
    assert "PRIVATE" not in json.dumps(events)
    assert str(tmp_path) not in json.dumps(events)


@pytest.mark.parametrize("document", ["main", "pending"])
@pytest.mark.parametrize(
    "raw,cause",
    [
        ("null", "invalid_structure"),
        ("[]", "invalid_structure"),
        ('{"schema_version":999}', "unsupported_schema"),
        ('{"schema_version":1,"items":0,"operations":0}', "invalid_structure"),
        (bytes([255]) + b"PRIVATE", "invalid_encoding"),
    ],
)
def test_document_validation_is_explicit_and_non_destructive(
    tmp_path, monkeypatch, document, raw, cause
):
    app = make_app(tmp_path, monkeypatch)
    path = (
        app.history_path
        if document == "main"
        else pending_history_path(app.history_path)
    )
    data = raw if isinstance(raw, bytes) else raw.encode()
    path.write_bytes(data)
    DownloaderApp._load_download_history(app)
    events = payloads(app)
    detail = events[-1]["failure_detail"]
    assert detail["failure_code"] == "history_" + cause
    assert detail["reason"] == "validation"
    assert path.read_bytes() == data


@pytest.mark.parametrize(
    "boundary,document,phase",
    [
        ("startup", "main", "read"),
        ("startup", "pending", "read"),
        ("settlement", "main", "write"),
        ("settlement", "pending", "retire"),
        ("defer", "pending", "write"),
    ],
)
@pytest.mark.parametrize(
    "number,reason",
    [
        (errno.EACCES, "permission_denied"),
        (errno.ENOSPC, "disk_full"),
        (errno.EIO, "filesystem"),
    ],
)
def test_typed_io_failures_reach_durable_outbox_without_losing_history(
    tmp_path, monkeypatch, boundary, document, phase, number, reason
):
    app = make_app(tmp_path, monkeypatch)
    mutation = {"kind": "activity", "owners": [], "activity": []}
    journal = pending_history_path(app.history_path)
    if boundary == "settlement":
        stage_history_mutation(app.history_path, mutation)
    target = app.history_path if document == "main" else journal
    if phase == "read":
        method = "stat"
    elif phase == "write":
        target = (
            target.with_name("." + target.name + ".tmp")
            if document == "main"
            else target.with_name(target.name + ".tmp")
        )
        method = "write_text"
    else:
        method = "unlink"
    original = getattr(Path, method)

    def fault(path, *args, **kwargs):
        if path == target:
            raise OSError(number, "PRIVATE sign in no space left /title")
        return original(path, *args, **kwargs)

    with monkeypatch.context() as scoped:
        scoped.setattr(Path, method, fault)
        if boundary == "startup":
            DownloaderApp._load_download_history(app)
        elif boundary == "settlement":
            assert not ArchiveLibraryMixin._archive_flush_history(app)
        else:
            with pytest.raises(HistoryError):
                ArchiveLibraryMixin._archive_defer_history(
                    app, "test", lambda: None, mutation=mutation
                )
            assert not app.__dict__.get("_archive_deferred_history")
    events = payloads(app)
    event = events[-1]
    assert event["action"] == "failed"
    assert event["dimensions"]["history_boundary"] == boundary
    assert event["dimensions"]["history_document"] == document
    assert event["dimensions"]["history_phase"] == phase
    detail = event["failure_detail"]
    assert detail["os_error"] == number
    assert detail["reason"] == reason
    assert detail.get("failure_code") == (
        "disk_full" if number == errno.ENOSPC else None
    )
    assert detail["source_module"] == "history"
    assert "PRIVATE" not in json.dumps(events)
    if boundary == "settlement":
        assert journal.exists()
        assert load_history(app.history_path) == []
        assert not journal.exists()


@pytest.mark.parametrize(
    "consent,release,withdrawn",
    [
        (False, True, False),
        (True, False, False),
        (True, True, True),
    ],
)
def test_real_failures_obey_consent_and_production_gate(
    tmp_path, monkeypatch, consent, release, withdrawn
):
    app = make_app(tmp_path, monkeypatch, consent=consent, release=release)
    if withdrawn:
        app.product_telemetry.set_enabled(False)
    app.history_path.write_text("PRIVATE invalid")
    DownloaderApp._load_download_history(app)
    assert app._history_recovery_blocked
    assert payloads(app) == []


def test_recovery_sequence_and_real_build_artifact(tmp_path, monkeypatch):
    import sys

    app = make_app(tmp_path, monkeypatch)
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    revision = "b" * 40
    (bundle / "VODFORGE_BUILD_REVISION").write_text(revision)
    monkeypatch.setattr(sys, "_MEIPASS", str(bundle), raising=False)
    called = []
    ArchiveLibraryMixin._archive_defer_history(
        app,
        "key",
        lambda: called.append(True),
        mutation={"kind": "activity", "owners": [], "activity": []},
    )
    assert pending_history_path(app.history_path).exists()
    assert ArchiveLibraryMixin._archive_flush_history(app)
    assert called == [True]
    assert not pending_history_path(app.history_path).exists()
    assert load_history(app.history_path) == []
    events = payloads(app)
    assert [event["action"] for event in events] == [
        "started",
        "deferred",
        "started",
        "recovered",
        "completed",
    ]
    assert [event["dimensions"]["operation_step"] for event in events] == [
        "1",
        "2",
        "1",
        "2",
        "3",
    ]
    assert len({event["dimensions"]["operation_id"] for event in events}) == 2
    assert all(event["dimensions"]["build_revision"] == revision for event in events)
    assert events[3]["dimensions"]["item_count"] == "1"
    assert all("failure_detail" not in event for event in events)


def test_unknown_failure_does_not_classify_private_message(tmp_path, monkeypatch):
    app = make_app(tmp_path, monkeypatch)

    def unknown(*args, **kwargs):
        raise HistoryError("PRIVATE login required no space left timeout")

    monkeypatch.setattr(
        "yt_downloader.archive_library_ui.stage_history_mutation", unknown
    )
    with pytest.raises(HistoryError):
        ArchiveLibraryMixin._archive_defer_history(
            app, "key", lambda: None, mutation={}
        )
    event = payloads(app)[-1]
    assert event["failure_detail"]["reason"] == "unknown"
    assert "failure_code" not in event["failure_detail"]
    assert event["dimensions"]["history_document"] == "unknown"
    assert event["dimensions"]["history_phase"] == "unknown"
    assert "PRIVATE" not in json.dumps(event)


def test_export_real_producer_outbox_for_backend(tmp_path, monkeypatch):
    """Optional harness bridge exports exact public events, never fabricated rows."""
    cases = []
    for document, raw in [
        ("main", '{"PRIVATE":'),
        ("main", '{"schema_version":999}'),
        ("pending", '{"PRIVATE":'),
    ]:
        case = tmp_path / str(len(cases))
        case.mkdir()
        app = make_app(case, monkeypatch)
        path = (
            app.history_path
            if document == "main"
            else pending_history_path(app.history_path)
        )
        path.write_text(raw)
        DownloaderApp._load_download_history(app)
        events = payloads(app)
        assert [event["action"] for event in events] == ["started", "failed"]
        cases.append({"document": document, "events": events})
    serialized = json.dumps(cases, indent=2)
    assert "PRIVATE" not in serialized
    assert str(tmp_path) not in serialized
    if destination := os.environ.get("VODFORGE_HISTORY_PRODUCER_EVENTS"):
        Path(destination).write_text(serialized + "\n")


def test_unlocated_os_error_keeps_phase_unknown_and_typed_cause(tmp_path, monkeypatch):
    app = make_app(tmp_path, monkeypatch)

    def fault(*args, **kwargs):
        raise OSError(errno.EACCES, "PRIVATE no space left")

    monkeypatch.setattr("yt_downloader.history._stage_history_mutation", fault)
    with pytest.raises(HistoryError):
        ArchiveLibraryMixin._archive_defer_history(
            app, "key", lambda: None, mutation={}
        )
    event = payloads(app)[-1]
    assert event["dimensions"]["history_phase"] == "unknown"
    assert event["dimensions"]["history_document"] == "pending"
    assert event["failure_detail"]["reason"] == "permission_denied"
    assert "failure_code" not in event["failure_detail"]
    assert "PRIVATE" not in json.dumps(event)
