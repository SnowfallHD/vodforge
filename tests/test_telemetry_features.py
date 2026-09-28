import json
import uuid

import pytest

from tests.test_product_telemetry import _permitted_installation
from yt_downloader.product_telemetry import ProductTelemetryOwner, _load_outbox
from yt_downloader.telemetry_features import (
    FEATURE_ACTIONS,
    OPERATION_FEATURES,
    attempt_identifier,
    validate_dimensions,
)

pytestmark = pytest.mark.usefixtures("production_telemetry_contract")


def test_playlist_preflight_failure_has_an_operation_before_any_item(
    tmp_path, monkeypatch
):
    from tests.test_metadata_helpers import _worker_test_app, _worker_test_job
    from yt_downloader import download_service as app_module

    installation = tmp_path / "installation.json"
    _permitted_installation(installation)
    state = tmp_path / "events.json"
    telemetry = ProductTelemetryOwner(
        state_path=state,
        installation_state_path=installation,
        app_version="0.2.3",
        d1_recorder=lambda _event: False,
    )
    app = _worker_test_app()
    app.product_telemetry = telemetry
    monkeypatch.setattr(app_module, "load_yt_dlp", lambda: object())
    monkeypatch.setattr(app_module, "write_diagnostic", lambda _message: None)
    ExtractorError = type("ExtractorError", (RuntimeError,), {})
    app._expand_download_source = lambda *_a, **_kw: (_ for _ in ()).throw(
        ExtractorError("private playlist title https://private.invalid")
    )
    job = _worker_test_job(tmp_path)
    app._download_worker_single(job)
    assert telemetry.shutdown(2)
    observations = [
        row for row in _load_outbox(state) if row.feature == "download_operation"
    ]
    assert [row.action for row in observations] == ["started", "failed"]
    assert (
        observations[0].dimensions["operation_id"]
        == observations[1].dimensions["operation_id"]
    )
    assert observations[1].failure_detail.stage == "preparation"
    assert observations[1].failure_detail.reason == "provider_extraction"
    assert "private" not in str(observations[1].failure_detail.payload())


def test_playlist_preflight_user_stop_closes_its_operation(tmp_path, monkeypatch):
    from tests.test_metadata_helpers import _worker_test_app, _worker_test_job
    from yt_downloader import download_service as app_module

    installation = tmp_path / "installation.json"
    _permitted_installation(installation)
    state = tmp_path / "events.json"
    telemetry = ProductTelemetryOwner(
        state_path=state,
        installation_state_path=installation,
        app_version="0.2.3",
        d1_recorder=lambda _event: False,
    )
    app = _worker_test_app()
    app.product_telemetry = telemetry
    monkeypatch.setattr(app_module, "load_yt_dlp", lambda: object())
    monkeypatch.setattr(app_module, "write_diagnostic", lambda _message: None)
    app._expand_download_source = lambda *_a, **_kw: (_ for _ in ()).throw(
        app_module._DownloadControlRequestError(
            app_module._DownloadControlKind.CANCEL_RUN
        )
    )
    job = _worker_test_job(tmp_path)
    app._download_worker_single(job)
    assert telemetry.shutdown(2)
    observations = [
        row for row in _load_outbox(state) if row.feature == "download_operation"
    ]
    assert [row.action for row in observations] == ["started", "cancelled"]
    assert (
        observations[0].dimensions["operation_id"]
        == observations[1].dimensions["operation_id"]
    )


@pytest.mark.parametrize("phase", ["check", "downloading_repair"])
def test_qt_updater_failures_are_not_classified_as_media_extraction(monkeypatch, phase):
    """A 403 from GitHub or the installer host is not a provider extraction."""
    from urllib.error import HTTPError

    from yt_downloader import failure_diagnostics
    from yt_downloader.qt_quick import update_session

    captured = []
    real = failure_diagnostics.capture_failure

    def recording(error, **kwargs):
        detail = real(error, **kwargs)
        captured.append((kwargs, detail))
        return detail

    monkeypatch.setattr(update_session, "capture_failure", recording)
    error = HTTPError("https://private.invalid/installer", 403, "secret", None, None)
    monkeypatch.setattr(
        update_session, "fetch_latest_release", lambda: (_ for _ in ()).throw(error)
    )
    session = update_session.QtUpdateSession("0.2.3")
    if phase == "check":
        session._check_worker()
    else:
        session.stage = phase
        session._download_worker(None)
    session.poll()
    assert captured
    for kwargs, detail in captured:
        assert kwargs.get("context") == "updater"
        assert detail.http_status == 403
        assert detail.reason != "provider_extraction"
        assert "private" not in str(detail.payload())

def test_attempts_link_across_restart_without_exposing_local_identity(tmp_path):
    installation = tmp_path / "installation.json"
    install_id = _permitted_installation(installation)
    path = tmp_path / "events.json"

    def owner():
        return ProductTelemetryOwner(
            state_path=path,
            installation_state_path=installation,
            app_version="0.2.1",
            d1_recorder=lambda _event: False,
        )

    first = owner()
    first.record(
        "run_started",
        attempt_key="private-local-key",
        dedupe_key="start",
        run_kind="youtube",
        output_type="original",
    )
    first.shutdown(2)
    second = owner()
    second.record(
        "run_failed",
        attempt_key="private-local-key",
        dedupe_key="failed",
        run_kind="youtube",
        output_type="original",
    )
    second.shutdown(2)
    second.record(
        "run_started",
        attempt_key="retry-key",
        retry_key="private-local-key",
        dedupe_key="retry",
        run_kind="youtube",
        output_type="original",
    )
    second.shutdown(2)
    events = [e.public_payload() for e in _load_outbox(path)]
    assert events[0]["attempt_id"] == events[1]["attempt_id"] == events[2]["retry_of"]
    assert events[2]["attempt_id"] != events[0]["attempt_id"]
    assert "private-local-key" not in json.dumps(events)
    assert (
        attempt_identifier(str(uuid.uuid4()), "private-local-key")
        != events[0]["attempt_id"]
    )
    assert events[0]["attempt_id"] == attempt_identifier(
        install_id, "private-local-key"
    )


@pytest.mark.parametrize(
    "dimensions",
    [
        {"url": "https://private.invalid"},
        {"preset": "secret title"},
        {"notes": "secret"},
        {"theme": "#abcdff"},
        {"size_bucket": 100},
        {"__proto__": "x"},
    ],
)
def test_private_or_unbounded_dimensions_rejected(dimensions):
    with pytest.raises((ValueError, TypeError)):
        validate_dimensions(dimensions)


def test_all_feature_actions_persist_and_are_deduplicated_in_session(tmp_path):
    installation = tmp_path / "installation.json"
    _permitted_installation(installation)
    path = tmp_path / "events.json"
    owner = ProductTelemetryOwner(
        state_path=path,
        installation_state_path=installation,
        app_version="0.2.1",
        d1_recorder=lambda _event: False,
    )
    legacy_features = {
        key: actions
        for key, actions in FEATURE_ACTIONS.items()
        if key not in OPERATION_FEATURES
    }
    for feature, actions in legacy_features.items():
        for action in actions:
            dimensions = (
                {"exception_kind": "other", "exception_origin": "main_thread"}
                if feature == "application_lifecycle"
                and action == "unhandled_exception"
                else {}
            )
            if feature == "application_lifecycle" and action == "screen_viewed":
                dimensions = {"view": "forge"}
            assert owner.record_feature(feature, action, dimensions=dimensions)
            if feature != "updater":
                assert owner.record_feature(feature, action, dimensions=dimensions)
    owner.shutdown(2)
    events = _load_outbox(path)
    assert len(events) == sum(map(len, legacy_features.values()))
    assert {(e.feature, e.action) for e in events} == {
        (f, a) for f, actions in legacy_features.items() for a in actions
    }


def test_update_confirmation_requires_actual_running_bytes(tmp_path, monkeypatch):
    import hashlib
    import os

    from yt_downloader.updates import confirmed_update_telemetry_receipt

    executable = tmp_path / "VODForge"
    executable.write_bytes(b"candidate bytes")
    receipt = tmp_path / ("handoff-" + uuid.uuid4().hex + ".json")
    value = {
        "status": "relaunched",
        "telemetry_permitted": True,
        "pid": os.getpid(),
        "repair": True,
        "executable_sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
    }
    receipt.write_text(json.dumps(value))
    assert confirmed_update_telemetry_receipt(receipt, executable) == (
        receipt.stem[8:],
        True,
        "relaunched",
        "unknown",
    )
    executable.write_bytes(b"other bytes")
    assert confirmed_update_telemetry_receipt(receipt, executable) is None
    value["status"] = "failed"
    receipt.write_text(json.dumps(value))
    assert confirmed_update_telemetry_receipt(receipt, executable) is None


def test_audio_cover_does_not_become_video_resolution():
    from yt_downloader.telemetry_features import measured_dimensions

    assert measured_dimensions(
        {
            "streams": [
                {
                    "codec_type": "video",
                    "height": 1080,
                    "disposition": {"attached_pic": 1},
                },
                {"codec_type": "audio"},
            ],
            "format": {"duration": "61", "size": "2000000", "filename": "secret"},
        }
    ) == {
        "resolution": "audio",
        "duration_bucket": "under_5m",
        "size_bucket": "under_10mb",
    }


def test_denial_cannot_reuse_cached_engagement_success(tmp_path):
    from yt_downloader.analytics_consent import AnalyticsConsentOwner

    installation = tmp_path / "installation.json"
    _permitted_installation(installation)
    owner = ProductTelemetryOwner(
        state_path=tmp_path / "events.json",
        installation_state_path=installation,
        app_version="0.2.1",
        d1_recorder=lambda _event: True,
    )
    assert owner.record_feature("library", "searched")
    owner.shutdown(2)
    AnalyticsConsentOwner(tmp_path).choose(False)
    assert not owner.record_feature("library", "searched")


def test_failed_update_receipt_survives_later_but_never_backfills_denied(tmp_path):
    from yt_downloader.updates import pending_update_telemetry_receipts

    folder = tmp_path / "updates" / "v1"
    folder.mkdir(parents=True)
    executable = tmp_path / "VODForge.exe"
    executable.write_bytes(b"current")
    path = folder / ("handoff-" + uuid.uuid4().hex + ".json")
    body = {
        "status": "failed",
        "executable": str(executable),
        "telemetry_permitted": False,
    }
    path.write_text(json.dumps(body))
    assert list(pending_update_telemetry_receipts(folder.parent, executable)) == []
    body["telemetry_permitted"] = True
    path.write_text(json.dumps(body))
    result = list(pending_update_telemetry_receipts(folder.parent, executable))
    assert result == [(path, (path.stem[8:], False, "failed", "unknown"))]
    path.with_suffix(".failed.telemetry-queued").write_text("queued")
    assert list(pending_update_telemetry_receipts(folder.parent, executable)) == []


def test_operation_journeys_repeat_order_and_revoke_without_presence_dedup(tmp_path):
    installation = tmp_path / "installation.json"
    _permitted_installation(installation)
    path = tmp_path / "events.json"
    owner = ProductTelemetryOwner(
        state_path=path,
        installation_state_path=installation,
        app_version="0.2.3-dev",
        d1_recorder=lambda _event: False,
    )
    keys = [str(uuid.uuid4()), str(uuid.uuid4())]
    for key in keys:
        for action in ("requested", "shown", "closed"):
            assert owner.record_operation(
                "help_operation",
                action,
                operation_key=key,
                dimensions={"help_target": "feedback"},
            )
    assert owner.shutdown(2)
    events = [e.public_payload() for e in _load_outbox(path)]
    assert len(events) == 6
    assert [e["action"] for e in events] == ["requested", "shown", "closed"] * 2
    assert [e["dimensions"]["operation_step"] for e in events] == ["1", "2", "3"] * 2
    identities = [e["dimensions"]["operation_id"] for e in events]
    assert len(set(identities[:3])) == len(set(identities[3:])) == 1
    assert identities[0] != identities[3]
    assert all(e["dimensions"]["instrumentation"] == "diagnostics_v1" for e in events)
    owner.set_enabled(False)
    assert not owner.record_operation("help_operation", "closed", operation_key=keys[0])
    assert not path.exists()
    owner.set_enabled(True)
    assert owner.record_operation("help_operation", "requested", operation_key=keys[0])
    assert owner.shutdown(2)
    fresh = _load_outbox(path)[0].dimensions
    assert fresh["operation_step"] == "1"
    assert fresh["operation_id"] not in identities


def test_operation_observation_limits_preserve_missing_evidence(tmp_path, monkeypatch):
    installation = tmp_path / "installation.json"
    _permitted_installation(installation)
    path = tmp_path / "events.json"
    owner = ProductTelemetryOwner(
        state_path=path,
        installation_state_path=installation,
        app_version="0.2.3-dev",
        d1_recorder=lambda _event: False,
    )
    monkeypatch.setattr(owner, "flush_async", lambda: None)
    key = str(uuid.uuid4())
    for _ in range(64):
        assert owner.record_operation("help_operation", "requested", operation_key=key)
    assert not owner.record_operation("help_operation", "requested", operation_key=key)
    assert len(_load_outbox(path)) == 64
    other = str(uuid.uuid4())
    assert owner.record_operation("help_operation", "requested", operation_key=other)
    assert _load_outbox(path)[-1].dimensions["observation_drop_count"] == "1"
    assert owner.record_operation("help_operation", "closed", operation_key=other)
    assert _load_outbox(path)[-1].dimensions["observation_drop_count"] == "0"


@pytest.mark.parametrize(
    "dimensions",
    [
        {"operation_id": "private URL"},
        {"build_revision": "/Users/private"},
        {"operation_step": "65"},
        {"operation_step": "01"},
        {"item_count": "10001"},
        {"item_count": True},
        {"item_count": "-1"},
        {"title": "private"},
    ],
)
def test_operation_dimension_contract_rejects_unbounded_values(dimensions):
    from yt_downloader.telemetry_features import validate_dimensions

    with pytest.raises((TypeError, ValueError)):
        validate_dimensions(dimensions)


def test_build_revision_requires_build_marker(tmp_path):
    from yt_downloader.version import read_build_revision

    marker = tmp_path / "VODFORGE_BUILD_REVISION"
    assert read_build_revision(marker) == "unknown"
    marker.write_text("private arbitrary content")
    assert read_build_revision(marker) == "unknown"
    marker.write_text("a" * 40 + "\n")
    assert read_build_revision(marker) == "a" * 40


@pytest.mark.parametrize(
    "feature,action",
    [
        ("download_operation", "stage"),
        ("local_conversion_operation", "started"),
        ("help_operation", "requested"),
        ("playback_operation", "requested"),
        ("resize_operation", "settled"),
    ],
)
def test_rejected_observation_increments_drop_count_for_next_valid_fact(
    tmp_path, feature, action
):
    installation = tmp_path / "installation.json"
    _permitted_installation(installation)
    state = tmp_path / "events.json"
    telemetry = ProductTelemetryOwner(
        state_path=state,
        installation_state_path=installation,
        app_version="0.2.1",
        d1_recorder=lambda _event: False,
    )
    operation = str(uuid.uuid4())
    with pytest.raises(ValueError):
        telemetry.record_operation(
            feature,
            action,
            operation_key=operation,
            dimensions={"private_note": "PRIVATE"},
        )
    assert telemetry.record_operation(
        feature, action, operation_key=operation, dimensions={"stage": "analysis"}
    )
    assert telemetry.record_operation(
        feature, action, operation_key=operation, dimensions={"stage": "analysis"}
    )
    assert telemetry.shutdown(2)
    events = _load_outbox(state)
    assert len(events) == 2
    assert events[0].dimensions["operation_step"] == "2"
    assert events[0].dimensions["observation_drop_count"] == "1"
    assert events[1].dimensions["operation_step"] == "3"
    assert events[1].dimensions["observation_drop_count"] == "0"
