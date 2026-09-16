from __future__ import annotations

import json
import uuid
from types import SimpleNamespace

import pytest

from tests.test_archive_relink import mapping, record
from tests.test_product_telemetry import _permitted_installation
from yt_downloader.archive_observations import operation, relink_dimensions, usage
from yt_downloader.archive_relink import preview_relink, verify_relink
from yt_downloader.cloud_funnel import load_or_create_installation_state
from yt_downloader.product_telemetry import ProductTelemetryOwner, _load_outbox
from yt_downloader.telemetry_features import FEATURE_ACTIONS, OPERATION_FEATURES

pytestmark = pytest.mark.usefixtures("production_telemetry_contract")


@pytest.mark.parametrize("permission", ["denied", "allowed", "withdrawn"])
def test_all_archive_actions_obey_consent_and_exclude_private_content(
    tmp_path, permission
):
    installation = tmp_path / "installation.json"
    if permission == "denied":
        load_or_create_installation_state(installation)
    else:
        _permitted_installation(installation)
    owner = ProductTelemetryOwner(
        state_path=tmp_path / "events.json",
        installation_state_path=installation,
        app_version="0.2.3",
        d1_recorder=lambda _: False,
        heycatch_recorder=lambda *a, **k: False,
    )
    if permission == "withdrawn":
        owner.set_enabled(False)
    key = str(uuid.uuid4())
    for feature in ("archive", "watch"):
        for action in sorted(FEATURE_ACTIONS[feature]):
            assert usage(owner, feature, action) == (permission == "allowed")
            assert usage(owner, feature, action) == (permission == "allowed")
    for feature in (
        "archive_relink_operation",
        "archive_location_operation",
        "archive_history_operation",
    ):
        for action in sorted(OPERATION_FEATURES[feature]):
            assert operation(owner, feature, action, key) == (permission == "allowed")
    owner.shutdown(2)
    events = _load_outbox(tmp_path / "events.json")
    assert bool(events) == (permission == "allowed")
    for feature in ("archive", "watch"):
        relevant = [event for event in events if event.feature == feature]
        assert len(relevant) == (
            len(FEATURE_ACTIONS[feature]) if permission == "allowed" else 0
        )
    # Session dedupe may acknowledge a previously observed action without using
    # the replacement fields; no new event or private value may be persisted.
    usage(owner, "watch", "searched", {"query": "private title token"})
    assert not operation(owner, "archive_relink_operation", "requested", "private-path")
    owner.shutdown(2)
    assert "private" not in json.dumps(
        [event.public_payload() for event in _load_outbox(tmp_path / "events.json")]
    )


def test_preview_observations_contain_only_counts_and_time(tmp_path):
    new = tmp_path / "Secret Channel" / "Private Playlist"
    new.mkdir(parents=True)
    (new / "Private title.mp4").write_bytes(b"synthetic")
    rows = [record(tmp_path / "old" / "Private title.mp4")]
    preview = verify_relink(
        preview_relink(rows, [mapping(tmp_path / "old", new)]), rows
    )
    dimensions = relink_dimensions(preview)
    assert dimensions["verified_count"] == "1"
    assert dimensions["unresolved_count"] == "0"
    assert not any(
        value in json.dumps(dimensions)
        for value in ("Private", "Secret", str(tmp_path))
    )
    _permitted_installation(tmp_path / "installation.json")
    owner = ProductTelemetryOwner(
        state_path=tmp_path / "events.json",
        installation_state_path=tmp_path / "installation.json",
        app_version="0.2.3",
        d1_recorder=lambda _: False,
        heycatch_recorder=lambda *a, **k: False,
    )
    assert operation(
        owner, "archive_relink_operation", "verified", str(uuid.uuid4()), dimensions
    )
    owner.shutdown(2)
    assert _load_outbox(tmp_path / "events.json")[0].dimensions["verified_count"] == "1"


def test_optional_observation_failure_cannot_replace_operation_outcome():
    def broken(*args, **kwargs):
        raise OSError("private unavailable telemetry destination")

    owner = SimpleNamespace(record_feature=broken, record_operation=broken)
    assert not usage(owner, "watch", "opened")
    assert not operation(
        owner, "archive_relink_operation", "committed", str(uuid.uuid4())
    )


@pytest.mark.parametrize("boundary", ["defer", "startup", "settlement"])
def test_history_failure_producers_observe_bounded_outcome_without_private_data(
    tmp_path, monkeypatch, boundary
):
    from types import MethodType

    from tests.test_archive_ui_owners import Variable
    from yt_downloader import history
    from yt_downloader.app import DownloaderApp
    from yt_downloader.archive_library_ui import ArchiveLibraryMixin

    events = []
    app = SimpleNamespace(
        history_path=tmp_path / "private-history.json",
        product_telemetry=SimpleNamespace(
            record_operation=lambda *a, **k: events.append((a, k))
        ),
        status_var=Variable(),
        _event_write_diagnostic=lambda *a: None,
        _append_log=lambda *a: None,
    )
    app._archive_usage = MethodType(ArchiveLibraryMixin._archive_usage, app)
    if boundary == "defer":

        def failed_stage(*a, **k):
            raise history.HistoryError("private-path and private-note")

        monkeypatch.setattr(
            "yt_downloader.archive_library_ui.stage_history_mutation", failed_stage
        )
        with pytest.raises(history.HistoryError):
            ArchiveLibraryMixin._archive_defer_history(
                app, "key", lambda: None, mutation={}
            )
        assert not app.__dict__.get("_archive_deferred_history")
    else:
        history.pending_history_path(app.history_path).write_text("{invalid")
        if boundary == "startup":
            DownloaderApp._load_download_history(app)
        else:
            assert not ArchiveLibraryMixin._archive_flush_history(app)
        assert app._history_recovery_blocked
    assert [args[1] for args, kwargs in events] == ["started", "failed"]
    assert events[-1][1]["failure_detail"].stage == "history"
    assert "private" not in json.dumps(events, default=lambda value: value.payload())
