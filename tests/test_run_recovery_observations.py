"""Actual recovery refusals must retain a useful private-safe cause."""

import json
import os
from pathlib import Path

import pytest

from tests.test_product_telemetry import _permitted_installation
from tests.test_run_state import _job
from yt_downloader import run_state as state
from yt_downloader.analytics_consent import AnalyticsConsentOwner
from yt_downloader.product_telemetry import ProductTelemetryOwner, _load_outbox

pytestmark = pytest.mark.usefixtures("production_telemetry_contract")


def telemetry(tmp_path, *, enabled=True, sink=lambda event: False):
    install = tmp_path / "installation.json"
    _permitted_installation(install)
    return ProductTelemetryOwner(
        state_path=tmp_path / "events.json",
        installation_state_path=install,
        app_version="0.2.3",
        enabled=enabled,
        d1_recorder=sink,
        heycatch_recorder=lambda *_a, **_k: True,
    )


@pytest.mark.parametrize(
    "case,cause,stage",
    [
        ("parse", "malformed_json", "journal_read"),
        ("schema", "unsupported_schema", "journal_validation"),
        ("live", "live_owner", "owner_check"),
        ("staging", "invalid_staging", "staging_validation"),
        ("read", "read_failed", "journal_read"),
        ("write", "write_failed", "journal_write"),
        ("cleanup", "cleanup_failed", "staging_cleanup"),
        ("queue", "invalid_record", "queue_loading"),
    ],
)
def test_real_failure_retains_exact_cause_and_blocks_start(
    tmp_path, monkeypatch, case, cause, stage
):
    monkeypatch = pytest.MonkeyPatch()
    path = tmp_path / "active-run.json"
    job = _job(tmp_path)
    store = state.ActiveRunStore(path)
    store.begin(job)
    payload = json.loads(path.read_text())
    payload["owner_pid"] = os.getpid()
    if case == "parse":
        path.write_text("{PRIVATE")
    elif case == "schema":
        payload["schema_version"] = 999
        path.write_text(json.dumps(payload))
    elif case == "live":
        payload["owner_pid"] = os.getppid()
        path.write_text(json.dumps(payload))
    elif case == "staging":
        payload["staging_dirs"] = ["/PRIVATE/outside"]
        path.write_text(json.dumps(payload))
    elif case == "queue":
        payload.update(state="idle", queued_jobs="PRIVATE")
        path.write_text(json.dumps(payload))
    else:
        path.write_text(json.dumps(payload))
    original = path.read_bytes()
    if case == "read":
        read = Path.read_text

        def denied(p, *a, **k):
            if p == path:
                raise PermissionError(13, "PRIVATE /path")
            return read(p, *a, **k)

        monkeypatch.setattr(Path, "read_text", denied)
    if case == "write":
        monkeypatch.setattr(
            state,
            "write_private_bytes",
            lambda *_: (_ for _ in ()).throw(PermissionError(13, "PRIVATE /path")),
        )
    if case == "cleanup":
        recover = state.recover_interrupted_run
        monkeypatch.setattr(
            state,
            "recover_interrupted_run",
            lambda store: recover(
                store,
                cleanup_staging=lambda _: (_ for _ in ()).throw(
                    OSError(5, "PRIVATE /path")
                ),
            ),
        )
    owner = state.RunRecoveryOwner(path)
    owner.recover_at_startup()
    owner.queued_at_startup()
    # Unpatch filesystem injection before exercising independent telemetry storage.
    monkeypatch.undo()
    out = telemetry(tmp_path)
    owner.bind_observer(out.record_operation, report_startup=True)
    with pytest.raises(state.RunStateError):
        owner.begin(job)
    assert out.shutdown(2)
    events = _load_outbox(tmp_path / "events.json")
    assert [e.action for e in events] == ["failed", "start_blocked"]
    for event in events:
        assert event.dimensions["recovery_cause"] == cause
        assert event.dimensions["recovery_stage"] == stage
        assert event.dimensions["recovery_disposition"] == "blocked_preserved"
    assert events[0].dimensions["operation_id"] == events[1].dimensions["operation_id"]
    assert events[1].attempt_id and events[1].attempt_id != job.run_id
    destination = os.environ.get("VODFORGE_RECOVERY_FIXTURES_DIR")
    if destination:
        target = Path(destination)
        target.mkdir(parents=True, exist_ok=True)
        (target / (case + ".json")).write_text(
            json.dumps(
                {
                    "case": case,
                    "cause": cause,
                    "stage": stage,
                    "events": [e.public_payload() for e in events],
                },
                indent=2,
            )
        )
    assert path.read_bytes() == original
    assert "PRIVATE" not in (tmp_path / "events.json").read_text()


def test_offline_retry_and_restart_keep_event_identity(tmp_path):
    path = tmp_path / "active-run.json"
    path.write_text("{")
    owner = state.RunRecoveryOwner(path)
    owner.recover_at_startup()
    out = telemetry(tmp_path)
    owner.bind_observer(out.record_operation, report_startup=True)
    assert out.shutdown(2)
    ids = [e.event_id for e in _load_outbox(tmp_path / "events.json")]
    assert len(ids) == 1
    # Binding twice cannot create a second startup event.
    owner.bind_observer(out.record_operation, report_startup=True)
    assert out.shutdown(2)
    assert [e.event_id for e in _load_outbox(tmp_path / "events.json")] == ids
    received = []
    again = telemetry(
        tmp_path, sink=lambda event: received.append(event.event_id) is None
    )
    again.flush_async()
    assert again.shutdown(2)
    assert received == ids and not (tmp_path / "events.json").exists()


def test_no_consent_backfill_and_withdrawal_discards_queue(tmp_path):
    path = tmp_path / "active-run.json"
    path.write_text("{")
    owner = state.RunRecoveryOwner(path)
    owner.recover_at_startup()
    out = telemetry(tmp_path, enabled=False)
    owner.bind_observer(out.record_operation, report_startup=False)
    out.set_enabled(True)
    owner.bind_observer(out.record_operation, report_startup=True)
    assert out.shutdown(2)
    assert not (tmp_path / "events.json").exists()
    with pytest.raises(state.RunStateError):
        owner.begin(_job(tmp_path))
    assert out.shutdown(2)
    assert len(_load_outbox(tmp_path / "events.json")) == 1
    AnalyticsConsentOwner(tmp_path).choose(False)
    out.set_enabled(False)
    assert not (tmp_path / "events.json").exists()


def test_restored_missing_source_reports_outcome_not_generic_failure(tmp_path):
    job = _job(tmp_path)
    job.url = ""
    job.urls = []
    path = tmp_path / "active-run.json"
    state.ActiveRunStore(path).record_terminal_attempt(job, "Failed", "old attempt")
    owner = state.RunRecoveryOwner(path)
    terminal, queued = owner.startup_recovery()
    assert len(terminal) == 1 and queued == [] and owner.recovery_notice is None
    out = telemetry(tmp_path)
    owner.bind_observer(out.record_operation, report_startup=True)
    assert out.shutdown(2)
    events = _load_outbox(tmp_path / "events.json")
    assert len(events) == 1
    event = events[0]
    assert event.action == "restored_without_retry"
    assert event.dimensions["recovery_cause"] == "missing_retry_url"
    assert event.dimensions["recovery_disposition"] == "restored_without_retry"
    assert event.dimensions["item_count_bucket"] == "1"
    assert event.failure_detail is None

    destination = os.environ.get("VODFORGE_RECOVERY_FIXTURES_DIR")
    if destination:
        target = Path(destination)
        target.mkdir(parents=True, exist_ok=True)
        (target / "restored.json").write_text(
            json.dumps(
                {
                    "case": "restored",
                    "cause": "missing_retry_url",
                    "stage": "terminal_restore",
                    "events": [event.public_payload()],
                },
                indent=2,
            )
        )


@pytest.mark.parametrize("operation", ["begin", "queue"])
@pytest.mark.parametrize("fault", ["invalid_source", "write_denied"])
def test_runtime_journal_refusal_is_observed_without_poisoning_recovery(
    tmp_path, monkeypatch, operation, fault
):
    """A refused write preserves data, emits its cause, and permits a later valid intent."""
    path = tmp_path / "active-run.json"
    owner = state.RunRecoveryOwner(path)
    original_job = _job(tmp_path)
    owner.store.begin(original_job)
    original = path.read_bytes()
    out = telemetry(tmp_path)
    owner.bind_observer(out.record_operation, report_startup=False)
    job = _job(tmp_path)
    job.run_id = "next-runtime-attempt"
    cause = "missing_retry_url" if fault == "invalid_source" else "write_failed"
    stage = "journal_validation" if fault == "invalid_source" else "journal_write"

    def submit(candidate):
        if operation == "begin":
            owner.begin(candidate)
        else:
            owner.queue_changed([candidate])

    with monkeypatch.context() as context:
        if fault == "invalid_source":
            job.url = "file:///PRIVATE/source"
            job.urls = [job.url]
        else:

            def denied(*_args, **_kwargs):
                raise PermissionError(13, "PRIVATE /path")

            context.setattr(state, "write_private_bytes", denied)
        with pytest.raises(state.RunStateError) as raised:
            submit(job)
        assert raised.value.cause == cause
        assert path.read_bytes() == original
    assert owner.recovery_notice is None
    assert out.shutdown(2)
    events = _load_outbox(tmp_path / "events.json")
    assert len(events) == 1
    event = events[0]
    assert event.feature == "run_recovery_operation" and event.action == "failed"
    assert event.dimensions["recovery_cause"] == cause
    assert event.dimensions["recovery_stage"] == stage
    assert event.dimensions["recovery_entry"] == (
        "run_admission" if operation == "begin" else "queue_update"
    )
    assert event.dimensions["recovery_disposition"] == "blocked_preserved"
    assert event.attempt_id and event.attempt_id != job.run_id
    assert "PRIVATE" not in (tmp_path / "events.json").read_text()
    healthy = _job(tmp_path)
    healthy.run_id = "healthy-successor"
    submit(healthy)
    assert owner.recovery_notice is None
    assert out.shutdown(2)
    assert len(_load_outbox(tmp_path / "events.json")) == 1
    destination = os.environ.get("VODFORGE_RECOVERY_FIXTURES_DIR")
    if destination:
        target = Path(destination)
        target.mkdir(parents=True, exist_ok=True)
        case = "runtime-" + operation + "-" + fault
        (target / (case + ".json")).write_text(
            json.dumps(
                {
                    "case": case,
                    "cause": cause,
                    "stage": stage,
                    "events": [event.public_payload()],
                },
                indent=2,
            )
        )


@pytest.mark.parametrize(
    "mode", ["disabled_consent", "observer_fault", "diagnostic_fault"]
)
def test_runtime_journal_observation_cannot_change_refusal_or_consent(tmp_path, mode):
    path = tmp_path / "active-run.json"

    def broken(*_args, **_kwargs):
        raise RuntimeError("PRIVATE observer")

    owner = state.RunRecoveryOwner(
        path, diagnostic=broken if mode == "diagnostic_fault" else None
    )
    out = telemetry(tmp_path, enabled=False)
    owner.bind_observer(
        out.record_operation if mode == "disabled_consent" else broken,
        report_startup=False,
    )
    bad = _job(tmp_path)
    bad.url, bad.urls = "", []
    with pytest.raises(state.RunStateError) as raised:
        owner.begin(bad)
    assert raised.value.cause == "missing_retry_url"
    assert not path.exists() and owner.recovery_notice is None
    owner.begin(_job(tmp_path))
    assert path.exists() and owner.recovery_notice is None
    assert out.shutdown(2)
    assert not (tmp_path / "events.json").exists()


def test_repeated_runtime_refusals_have_distinct_operations_and_stable_attempt(
    tmp_path,
):
    path = tmp_path / "active-run.json"
    owner = state.RunRecoveryOwner(path)
    out = telemetry(tmp_path)
    owner.bind_observer(out.record_operation, report_startup=False)
    job = _job(tmp_path)
    job.url, job.urls = "", []
    for _ in range(2):
        with pytest.raises(state.RunStateError):
            owner.begin(job)
    assert out.shutdown(2)
    events = _load_outbox(tmp_path / "events.json")
    assert len(events) == 2
    assert events[0].attempt_id == events[1].attempt_id
    assert events[0].attempt_id and events[0].attempt_id != job.run_id
    assert events[0].dimensions["operation_id"] != events[1].dimensions["operation_id"]
    assert all(e.dimensions["operation_step"] == "1" for e in events)
    assert not path.exists() and owner.recovery_notice is None
    destination = os.environ.get("VODFORGE_RECOVERY_FIXTURES_DIR")
    if destination:
        target = Path(destination)
        target.mkdir(parents=True, exist_ok=True)
        (target / "runtime-repeated.json").write_text(
            json.dumps(
                {
                    "case": "runtime-repeated",
                    "cause": "missing_retry_url",
                    "stage": "journal_validation",
                    "events": [e.public_payload() for e in events],
                },
                indent=2,
            )
        )
