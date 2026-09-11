from copy import deepcopy

import pytest
from quality_harness.telemetry_release import (
    CHECKPOINTS,
    PREVIEW_DATABASE_ID,
    PREVIEW_WORKER,
    release_checks,
    validate_journey,
)


def telemetry_fixture(candidate, platform="macos"):
    from quality_harness.packaged_e2e import TELEMETRY_UI_EVENT_ORDER

    archive = candidate["immutable_archive"]["sha256"]
    installation = {
        "install_id": "qa",
        "created_at": "2026-09-10 12:00:00",
        "first_launched_at": "2026-09-10 12:00:00",
        "last_seen_at": "2026-09-10 12:00:00",
        "current_app_version": "0.2.2",
    }
    binding = {"verified": True, "archive_sha256": archive}
    first = {
        "install_id": "qa",
        "database_id": PREVIEW_DATABASE_ID,
        "worker": PREVIEW_WORKER,
        "rows_written": 0,
        "installations": [installation],
        "clients": 1,
        "events": [],
        "candidate_binding": binding,
    }
    reopened = deepcopy(first)
    reopened["installations"][0]["last_seen_at"] = "2026-09-10 12:01:00"
    complete = deepcopy(reopened)
    complete["installations"][0].update(
        first_seen_at="2026-09-10 12:01:00", cloud_clicked_at="2026-09-10 12:01:00"
    )
    events = [{"event_name": "app_opened"}, {"event_name": "app_opened"}]
    events += [
        {"event_name": name, "output_type": output}
        for name in ("run_started", "run_completed", "playback_started")
        for output in ("mp4", "mp3", None)
    ]
    events += [
        {"event_name": name}
        for name in ("run_failed", "run_stopped", "local_conversion_completed")
    ]
    for index, event in enumerate(events):
        event["event_id"] = str(index)
    complete["events"] = events
    from collections import Counter

    baseline = deepcopy(first)
    baseline["installations"][0]["current_app_version"] = "0.2.1"
    updated = deepcopy(first)
    updated["events"] = [
        {"event_name": "client_update", "from_version": "0.2.1", "to_version": "0.2.2"}
    ]
    unknown = deepcopy(first)
    unknown.update(installations=[], clients=0, events=[])
    denied = deepcopy(complete)
    denied["consent_choice"] = "denied"
    disabled = deepcopy(complete)
    disabled["launch"] = {"attestation": {"telemetry_preview": False}}
    return {
        "platform": platform,
        "source_commit": candidate["source"]["commit"],
        "telemetry_mode": "preview",
        "packaged_e2e": {
            "scenario": {"status": "passed"},
            "driver_trace": {
                "events": [{"event": name} for name in TELEMETRY_UI_EVENT_ORDER]
            },
            "driver_trace_validation": {"valid": True},
            "telemetry_mode": "preview",
            "process_provenance": {"verified": True},
            "artifact_integrity": {"verified": True},
            "launches": [
                {
                    "verified": True,
                    "attestation": {
                        "telemetry_preview": True,
                        "telemetry_production": False,
                    },
                }
                for _ in range(2)
            ],
            "candidate_binding": binding,
        },
        "expected_event_counts": dict(Counter(e["event_name"] for e in events)),
        "snapshots": {
            "first_launch": first,
            "same_version_reopen": reopened,
            "events_complete": complete,
            "denied": denied,
            "disabled": disabled,
            "unknown": unknown,
        },
        "update": {"before": baseline, "after": updated},
    }


def candidate():
    return {"source": {"commit": "a" * 40}, "immutable_archive": {"sha256": "b" * 64}}


def test_valid_preview_readbacks():
    assert validate_journey(telemetry_fixture(candidate())) == []


@pytest.mark.parametrize("checkpoint", CHECKPOINTS)
def test_missing_checkpoint_blocks(checkpoint):
    data = telemetry_fixture(candidate())
    del data["snapshots"][checkpoint]
    assert validate_journey(data)


@pytest.mark.parametrize(
    "mutation",
    ["stale", "duplicate", "missing_event", "privacy", "production", "update"],
)
def test_real_metric_mismatches_cannot_be_overridden_by_passed(mutation):
    data = telemetry_fixture(candidate())
    data["status"] = "passed"
    snapshots = data["snapshots"]
    if mutation == "stale":
        snapshots["same_version_reopen"]["installations"][0]["last_seen_at"] = (
            snapshots["first_launch"]["installations"][0]["last_seen_at"]
        )
    elif mutation == "duplicate":
        snapshots["events_complete"]["events"].append(
            snapshots["events_complete"]["events"][0]
        )
    elif mutation == "missing_event":
        snapshots["events_complete"]["events"].pop()
    elif mutation == "privacy":
        snapshots["denied"]["installations"][0]["last_seen_at"] = "2026-09-10 12:30:00"
    elif mutation == "production":
        snapshots["first_launch"]["database_id"] = (
            "a254402e-4130-4a53-ba33-bcada9ab602b"
        )
    else:
        data["update"]["after"]["events"] *= 2
    assert validate_journey(data)


def test_both_platforms_and_exact_candidate_are_required():
    c = candidate()
    receipts = [telemetry_fixture(c, p) for p in ("macos", "windows")]
    assert all(check["status"] == "passed" for check in release_checks(receipts, c))
    assert any(check["status"] == "failed" for check in release_checks(receipts[:1], c))
    receipts[0]["source_commit"] = "c" * 40
    assert any(check["status"] == "failed" for check in release_checks(receipts, c))


def test_snapshot_refuses_production_binding_before_running_wranger(
    tmp_path, monkeypatch
):
    import json

    from quality_harness.telemetry_release import read_preview_snapshot

    (tmp_path / "wrangler.preview.jsonc").write_text(
        json.dumps(
            {
                "name": "vodforge-site",
                "routes": [],
                "d1_databases": [
                    {
                        "database_id": "a254402e-4130-4a53-ba33-bcada9ab602b",
                        "database_name": "vodforge",
                    }
                ],
            }
        )
    )
    monkeypatch.setattr(
        "quality_harness.telemetry_release.subprocess.run",
        lambda *a, **kw: pytest.fail("must not contact production"),
    )
    with pytest.raises(ValueError, match="isolation"):
        read_preview_snapshot(tmp_path, "ca40ed92-c8bb-41d9-a453-b9089a069a56")


@pytest.mark.parametrize(
    "field,value",
    [
        ("telemetry_mode", "off"),
        ("process_provenance", {"verified": False}),
        ("artifact_integrity", {"verified": False}),
        ("launches", []),
    ],
)
def test_telemetry_off_or_unattested_journey_blocks_release(field, value):
    c = candidate()
    data = telemetry_fixture(c)
    data["packaged_e2e"][field] = value
    assert release_checks([data], c)[0]["status"] == "failed"


def test_counts_without_the_actual_ui_actions_cannot_pass():
    c = candidate()
    data = telemetry_fixture(c)
    data["packaged_e2e"]["driver_trace"]["events"] = [{"event": "completion_observed"}]
    assert release_checks([data], c)[0]["status"] == "failed"


def test_telemetry_profile_exposes_every_required_producer_action():
    from quality_harness.cli import _parser
    from quality_harness.packaged_e2e import _required_ui_event_order

    args = _parser().parse_args(
        ["packaged-e2e", "--profile", "telemetry", "--telemetry", "preview"]
    )
    events = _required_ui_event_order(args.profile)
    assert len(events) == len(set(events))
    assert {
        "mp4_playback_observed",
        "mp3_completion_observed",
        "mp3_playback_observed",
        "original_completion_observed",
        "original_playback_observed",
        "local_conversion_observed",
        "failure_observed",
        "retry_completion_observed",
        "cloud_interest_observed",
        "consent_denied_observed",
        "telemetry_disabled_observed",
        "restart_observed",
    } <= set(events)
