from __future__ import annotations

import json
import uuid
from types import SimpleNamespace

import pytest

from tests.test_archive_relink import record
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


@pytest.mark.parametrize("legacy_mismatch", [False, True])
def test_preview_observations_contain_only_counts_and_time(tmp_path, legacy_mismatch):
    new = tmp_path / "Secret Channel" / "Private Playlist"
    new.mkdir(parents=True)
    chosen = new / ("Private title.mp3" if legacy_mismatch else "Private title.mp4")
    chosen.write_bytes(b"synthetic")
    rows = [record(tmp_path / "old" / "Private title.mp4")]
    if legacy_mismatch:
        rows[0].pop("vodforge_output_path")
        rows[0]["vodforge_encoding_summary"]["output"].pop("Output file path")
    preview = verify_relink(preview_relink(rows, exact_files={0: str(chosen)}), rows)
    dimensions = relink_dimensions(preview)
    assert dimensions["identity_mismatch_count"] == ("1" if legacy_mismatch else "0")
    assert dimensions["verified_count"] == ("0" if legacy_mismatch else "1")
    assert dimensions["unresolved_count"] == ("1" if legacy_mismatch else "0")
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
    )
    assert operation(
        owner, "archive_relink_operation", "verified", str(uuid.uuid4()), dimensions
    )
    owner.shutdown(2)
    persisted = _load_outbox(tmp_path / "events.json")[0].dimensions
    assert persisted["identity_mismatch_count"] == dimensions["identity_mismatch_count"]
    assert persisted["verified_count"] == dimensions["verified_count"]
    assert persisted["unresolved_count"] == dimensions["unresolved_count"]


def test_optional_observation_failure_cannot_replace_operation_outcome():
    def broken(*args, **kwargs):
        raise OSError("private unavailable telemetry destination")

    owner = SimpleNamespace(record_feature=broken, record_operation=broken)
    assert not usage(owner, "watch", "opened")
    assert not operation(
        owner, "archive_relink_operation", "committed", str(uuid.uuid4())
    )
