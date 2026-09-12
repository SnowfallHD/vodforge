import json
import uuid

import pytest

from tests.test_product_telemetry import _permitted_installation
from yt_downloader.product_telemetry import ProductTelemetryOwner, _load_outbox
from yt_downloader.telemetry_features import (
    FEATURE_ACTIONS,
    attempt_identifier,
    validate_dimensions,
)

pytestmark = pytest.mark.usefixtures("production_telemetry_contract")


@pytest.mark.parametrize(
    "field,value,action",
    [
        ("note", "Private note sentinel", "notes_saved"),
        ("tags", ("private-tag",), "tags_saved"),
        ("category", "Private category", "category_saved"),
    ],
)
@pytest.mark.parametrize("operation", ["create", "clear", "unchanged", "failed"])
def test_annotation_save_producer_tracks_only_successful_changes(
    tmp_path, monkeypatch, field, value, action, operation
):
    from types import SimpleNamespace

    import yt_downloader.app as app_module
    from yt_downloader.library_annotations import (
        LibraryAnnotation,
        LibraryAnnotationsError,
        LibraryAnnotationsOwner,
    )

    owner = LibraryAnnotationsOwner(tmp_path / "annotations.json")
    populated = LibraryAnnotation(**{field: value})
    previous = populated if operation in {"clear", "unchanged"} else LibraryAnnotation()
    proposed = LibraryAnnotation() if operation == "clear" else populated
    owner.replace("run:test", previous)
    events = []
    outcomes = []
    info = {app_module.ANNOTATION_OWNER_KEY: "run:test", "title": "Private title"}
    app = SimpleNamespace(
        metadata_items=[info],
        library_annotations=owner,
        _reconcile_library_projection=lambda **kwargs: None,
        _record_feature=lambda *args: events.append(args),
        status_var=SimpleNamespace(set=lambda text: None),
    )

    def dialog(*args, **kwargs):
        return SimpleNamespace(
            show=lambda: outcomes.append(kwargs["on_save"](proposed))
        )

    monkeypatch.setattr(app_module, "LibraryAnnotationDialog", dialog)
    monkeypatch.setattr(
        app_module.messagebox, "showerror", lambda *args, **kwargs: None
    )
    if operation == "failed":

        def fail_save(*args):
            raise LibraryAnnotationsError("Cannot save private path")

        monkeypatch.setattr(owner, "replace", fail_save)
    app_module.DownloaderApp._show_library_annotation_editor(app, info)
    assert outcomes == [operation != "failed"]
    assert events == (
        [("organization", action)] if operation in {"create", "clear"} else []
    )
    assert owner.annotation_for("run:test") == (
        previous if operation == "failed" else proposed
    )
    assert "Private" not in repr(events)


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
            heycatch_recorder=lambda *_args, **_kwargs: False,
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
        heycatch_recorder=lambda *_args, **_kwargs: False,
    )
    for feature, actions in FEATURE_ACTIONS.items():
        for action in actions:
            assert owner.record_feature(feature, action)
            if feature != "updater":
                assert owner.record_feature(feature, action)
    owner.shutdown(2)
    events = _load_outbox(path)
    assert len(events) == sum(map(len, FEATURE_ACTIONS.values()))
    assert {(e.feature, e.action) for e in events} == {
        (f, a) for f, actions in FEATURE_ACTIONS.items() for a in actions
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
        heycatch_recorder=lambda *_args, **_kwargs: True,
    )
    assert owner.record_feature("library", "searched")
    owner.shutdown(2)
    AnalyticsConsentOwner(tmp_path).choose(False)
    assert not owner.record_feature("library", "searched")


@pytest.mark.parametrize("kind", ["error", "cancelled"])
def test_local_failure_callback_never_receives_exception_text(kind):
    import queue
    from types import SimpleNamespace

    from yt_downloader.local_audio_video_ui import LocalAudioVideoDialog

    calls = []
    events = queue.Queue()
    events.put((kind, "PRIVATE PATH AND TITLE"))
    control = SimpleNamespace(configure=lambda **kwargs: None)
    dialog = SimpleNamespace(
        _closed=False,
        _events=events,
        _worker=object(),
        _telemetry_run_id="random-local-run",
        on_telemetry=lambda *args: calls.append(args),
        cancel_button=control,
        audio_button=control,
        image_button=control,
        destination_button=control,
        profile_combo=control,
        choose_output=None,
        _sync_ready_state=lambda **kwargs: None,
        _close_when_idle=False,
    )
    LocalAudioVideoDialog._pump_events(dialog)
    assert calls == [
        (
            "local_conversion_failed"
            if kind == "error"
            else "local_conversion_stopped",
            "random-local-run",
        )
    ]
    assert "PRIVATE" not in repr(calls)


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


def test_update_observation_is_discarded_on_refusal_not_backfilled(
    tmp_path, monkeypatch
):
    import sys
    from types import SimpleNamespace

    import yt_downloader.app as app_module

    folder = tmp_path / "updates" / "v1"
    folder.mkdir(parents=True)
    receipt = folder / ("handoff-" + uuid.uuid4().hex + ".json")
    receipt.write_text(
        json.dumps(
            {
                "status": "failed",
                "executable": sys.executable,
                "telemetry_permitted": True,
            }
        )
    )
    monkeypatch.setattr(app_module, "application_data_dir", lambda: tmp_path)
    monkeypatch.delenv("VODFORGE_UPDATE_RECEIPT", raising=False)
    owner = SimpleNamespace(
        permitted=lambda: False,
        record=lambda *args, **kwargs: pytest.fail("refused update was recorded"),
    )
    app = SimpleNamespace(product_telemetry=owner, _closing=False)
    app_module.DownloaderApp._record_update_telemetry_receipt(app)
    assert receipt.with_suffix(".failed.telemetry-discarded").exists()
    owner.permitted = lambda: True
    app_module.DownloaderApp._record_update_telemetry_receipt(app)
