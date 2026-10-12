"""Worker/UI settlement preserves actual history on uncertain completion."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from tests.test_archive_file_operations import item, move_context
from tests.test_presentation_diagnostics import real_owner
from yt_downloader.archive_observations import operation
from yt_downloader.product_telemetry import _load_outbox
from yt_downloader.telemetry_features import FEATURE_ACTIONS, validate_dimensions

# Imported fixtures intentionally exercise the same real, isolated file owner.
__all__ = ["item", "move_context"]
pytestmark = pytest.mark.usefixtures("production_telemetry_contract")


def dialog():
    return SimpleNamespace(
        primary=Mock(),
        secondary=Mock(),
        note=Mock(),
        message=Mock(),
        heading=Mock(),
        exists=lambda: True,
    )


@pytest.mark.parametrize("permission", ["allowed", "denied", "withdrawn"])
def test_file_observations_obey_consent_and_exclude_file_content(tmp_path, permission):
    telemetry = real_owner(tmp_path, permitted=permission != "denied")
    if permission == "withdrawn":
        telemetry.set_enabled(False)
    import uuid

    key = str(uuid.uuid4())
    for action, dimensions in [
        ("requested", {"file_action": "move", "item_count": "2"}),
        ("started", {"file_action": "move"}),
        ("needs_attention", {"file_action": "move"}),
    ]:
        assert action in FEATURE_ACTIONS["library_file_operation"]
        validate_dimensions(dimensions)
        operation(telemetry, "library_file_operation", action, key, dimensions)
    assert telemetry.shutdown(2)
    events = [
        e
        for e in _load_outbox(tmp_path / "events.json")
        if e.feature == "library_file_operation"
    ]
    assert [event.action for event in events] == (
        ["requested", "started", "needs_attention"] if permission == "allowed" else []
    )
    payload = json.dumps([event.public_payload() for event in events])
    assert str(tmp_path) not in payload
    with pytest.raises(ValueError):
        validate_dimensions({"file_action": "/private/filename.mp4"})


def test_unexpected_observation_failure_cannot_own_file_outcomes():
    observer = SimpleNamespace(
        record_operation=Mock(side_effect=RuntimeError("offline"))
    )
    assert not operation(
        observer,
        "library_file_operation",
        "completed",
        "key",
        {"file_action": "delete", "committed_count": "2"},
    )
