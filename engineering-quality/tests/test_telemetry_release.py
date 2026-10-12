from copy import deepcopy

import pytest
from quality_harness.diagnostic_fixtures import diagnostic_context
from quality_harness.telemetry_release import (
    CHECKPOINTS,
    PREVIEW_DATABASE_ID,
    PREVIEW_WORKER,
    release_checks,
)
from quality_harness.telemetry_release import (
    validate_journey as validate_unbound_journey,
)


def validate_journey(data):
    return validate_unbound_journey(data, candidate=candidate())


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
    binding = {
        "verified": True,
        "archive_sha256": archive,
        "artifact_policy": "release",
    }
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
        for output in ("mp4", "mp3", "original")
    ]
    events += [
        {"event_name": name}
        for name in ("run_failed", "run_stopped", "local_conversion_completed")
    ]
    import json
    import uuid

    from quality_harness import telemetry_release

    from yt_downloader.product_telemetry import PRODUCT_EVENT_NAMES
    from yt_downloader.telemetry_features import FEATURE_ACTIONS

    for name in PRODUCT_EVENT_NAMES - {e["event_name"] for e in events}:
        if name != "feature_used":
            events.append({"event_name": name})
    events += [
        {"event_name": "feature_used", "feature": feature, "action": action}
        for feature, actions in FEATURE_ACTIONS.items()
        if feature != "announcement" or telemetry_release.SHOWCASE_MODE != "none"
        for action in actions
        if not (
            feature == "announcement"
            and action == "try_it"
            and telemetry_release.SHOWCASE_MODE == "whats-new"
        )
    ]
    first_attempt = str(uuid.uuid4())
    retry_attempt = str(uuid.uuid4())
    for event in events:
        event["schema_version"] = 2
        event["dimensions"] = "{}"
        if str(event.get("feature", "")).endswith("_operation"):
            event["dimensions"] = json.dumps(
                {
                    **diagnostic_context(event["feature"], event["action"]),
                    "instrumentation": "diagnostics_v1",
                    "build_revision": candidate["source"]["commit"],
                    "operation_id": str(uuid.uuid4()),
                    "operation_step": "1",
                }
            )
        if event["event_name"].startswith(("run_", "local_conversion_")):
            event["attempt_id"] = first_attempt
    extra_starts = []
    for event in events:
        name = event["event_name"]
        if name in {
            "run_completed",
            "run_failed",
            "run_stopped",
            "local_conversion_completed",
            "local_conversion_failed",
            "local_conversion_stopped",
        }:
            event["attempt_id"] = str(uuid.uuid4())
            if name == "run_failed":
                first_attempt = event["attempt_id"]
            extra_starts.append(
                {
                    "event_name": "local_conversion_started"
                    if name.startswith("local_")
                    else "run_started",
                    "attempt_id": event["attempt_id"],
                    "schema_version": 2,
                    "dimensions": "{}",
                }
            )
    events.extend(extra_starts)
    events += [
        {
            "event_name": "run_started",
            "attempt_id": retry_attempt,
            "retry_of": first_attempt,
            "schema_version": 2,
            "dimensions": "{}",
        },
        {
            "event_name": "run_completed",
            "attempt_id": retry_attempt,
            "retry_of": first_attempt,
            "schema_version": 2,
            "dimensions": "{}",
        },
    ]
    for preset in ("everyday", "streaming", "editing", "sharing", "ctv", "custom"):
        events.append(
            {
                "event_name": "media_exported",
                "schema_version": 2,
                "attempt_id": first_attempt,
                "dimensions": json.dumps(
                    {
                        "preset": preset,
                        "encoder": "nvidia"
                        if preset == "ctv" and platform == "windows"
                        else "cpu",
                    }
                ),
            }
        )
    for index, event in enumerate(events):
        event["event_id"] = str(index)
    first["events"] = deepcopy(events[:1])
    reopened["events"] = deepcopy(events[:2])
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
                        "renderer": "qt",
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
    import hashlib
    import json

    from quality_harness import telemetry_release

    files = {
        name: {
            "kind": "file",
            "sha256": hashlib.sha256(
                (telemetry_release.ANNOUNCEMENT_SOURCE_ROOT / name).read_bytes()
            ).hexdigest(),
        }
        for name in telemetry_release.ANNOUNCEMENT_SOURCE_FILES
    }
    manifest = {"format": "vodforge-source-files-v1", "files": files}
    digest = hashlib.sha256(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    manifest["sha256"] = digest
    return {
        "source": {"commit": "a" * 40, "manifest": manifest, "manifest_sha256": digest},
        "verification": {"verified": True},
        "immutable_archive": {"sha256": "b" * 64},
    }


def test_valid_preview_readbacks():
    assert validate_journey(telemetry_fixture(candidate())) == []


@pytest.mark.parametrize(
    "checkpoint, count",
    [
        ("first_launch", 0),
        ("first_launch", 2),
        ("same_version_reopen", 1),
        ("same_version_reopen", 3),
    ],
)
def test_app_open_must_arrive_at_each_launch_not_only_after_later_features(
    checkpoint, count
):
    data = telemetry_fixture(candidate())
    data["snapshots"][checkpoint]["events"] = [
        {"event_name": "app_opened", "event_id": str(index)} for index in range(count)
    ]
    assert validate_journey(data)


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


def test_private_development_artifact_cannot_satisfy_release_telemetry():
    c = candidate()
    data = telemetry_fixture(c, "windows")
    data["packaged_e2e"]["candidate_binding"]["artifact_policy"] = "development"
    assert release_checks([data], c)[1]["status"] == "failed"


def test_silent_release_rejects_announcement_event(monkeypatch):
    monkeypatch.setattr("quality_harness.telemetry_release.SHOWCASE_MODE", "none")
    data = telemetry_fixture(candidate())
    data["snapshots"]["events_complete"]["events"].append(
        {
            "event_id": "unexpected-announcement",
            "event_name": "feature_used",
            "feature": "announcement",
            "action": "shown",
            "schema_version": 2,
            "dimensions": "{}",
        }
    )
    assert "Disabled release announcement emitted telemetry" in validate_journey(data)


def test_operation_release_observations_require_correlation_and_exact_source():
    import json

    candidate = {
        "source": {"commit": "a" * 40},
        "immutable_archive": {"sha256": "b" * 64},
    }
    data = telemetry_fixture(candidate)
    events = data["snapshots"]["events_complete"]["events"]
    event = next(
        event
        for event in events
        if str(event.get("feature", "")).endswith("_operation")
    )
    event["dimensions"] = "{}"
    assert "Operation observation missing correlation" in validate_journey(data)
    event["dimensions"] = json.dumps(
        {
            "instrumentation": "diagnostics_v1",
            "operation_id": "fd2f4067-e5b4-46b2-b9c0-c8707a0523e1",
            "operation_step": "1",
            "build_revision": "unknown",
        }
    )
    assert (
        "Operation build revision does not match packaged source"
        in validate_journey(data)
    )


def test_release_readback_rejects_contradictory_presentation_action():
    import json

    data = telemetry_fixture(candidate())
    event = next(
        e
        for e in data["snapshots"]["events_complete"]["events"]
        if e.get("feature") == "presentation_operation" and e.get("action") == "fault"
    )
    dimensions = json.loads(event["dimensions"])
    dimensions.update(missing_image_bucket="0", missing_image_role="none")
    event["dimensions"] = json.dumps(dimensions)
    assert validate_journey(data)


def test_enabled_release_requires_announcement_observations(tmp_path, monkeypatch):
    c = editorial_candidate(tmp_path, monkeypatch, "whats-new", ["design"])
    data = telemetry_fixture(c)
    assert validate_journey(data) == []
    events = data["snapshots"]["events_complete"]["events"]
    events[:] = [event for event in events if event.get("feature") != "announcement"]
    assert any("Missing feature/action" in error for error in validate_journey(data))


def without_action(data, feature, action):
    for name in ("events_complete", "denied", "disabled"):
        data["snapshots"][name]["events"] = [
            event
            for event in data["snapshots"][name]["events"]
            if (event.get("feature"), event.get("action")) != (feature, action)
        ]
    data["expected_event_counts"]["feature_used"] -= 1


@pytest.mark.parametrize(
    "platform,renderers,required",
    [
        ("windows", ["qt", "qt"], False),
        ("windows", ["tk", "tk"], False),
        ("macos", ["qt", "qt"], False),
        ("macos", ["tk", "tk"], True),
        ("macos", ["qt", "tk"], True),
        ("macos", [None, None], True),
        ("macos", ["unknown", "unknown"], True),
    ],
)
def test_native_fallback_requirement_matches_platform_and_attested_renderer(
    platform, renderers, required
):
    data = telemetry_fixture(candidate(), platform)
    for launch, renderer in zip(data["packaged_e2e"]["launches"], renderers):
        if renderer is not None:
            launch["attestation"]["renderer"] = renderer
        else:
            launch["attestation"].pop("renderer", None)
    without_action(data, "player", "controls_fallback")
    errors = validate_journey(data)
    assert bool(errors) is required
    if required:
        assert any("('player', 'controls_fallback')" in error for error in errors)


def test_unverified_renderer_cannot_remove_macos_fallback_requirement():
    data = telemetry_fixture(candidate())
    for launch in data["packaged_e2e"]["launches"]:
        launch["attestation"]["renderer"] = "qt"
    data["packaged_e2e"]["launches"][0]["verified"] = False
    without_action(data, "player", "controls_fallback")
    assert any(
        "('player', 'controls_fallback')" in error for error in validate_journey(data)
    )


@pytest.mark.parametrize("platform", ["macos", "windows"])
def test_applicable_player_action_still_blocks_release(platform):
    data = telemetry_fixture(candidate(), platform)
    for launch in data["packaged_e2e"]["launches"]:
        launch["attestation"]["renderer"] = "qt"
    without_action(data, "player", "controls_fallback")
    without_action(data, "player", "fit")
    assert any("('player', 'fit')" in error for error in validate_journey(data))


QT_LEGACY_ACTIONS = (
    ("help_operation", "popup_returned"),
    ("library", "source_tags_copied"),
    ("library", "thumbnail_url_copied"),
    ("playback_operation", "focused"),
    ("player", "description_opened"),
    ("player", "description_closed"),
    ("watch", "singleton_shown"),
)


@pytest.mark.parametrize("platform", ["macos", "windows"])
@pytest.mark.parametrize("pair", QT_LEGACY_ACTIONS)
@pytest.mark.parametrize("renderer", ["qt", "tk", "mixed", "unknown", "unverified"])
def test_reviewed_legacy_semantics_require_verified_qt_applicability(
    platform, pair, renderer
):
    data = telemetry_fixture(candidate(), platform)
    for launch in data["packaged_e2e"]["launches"]:
        launch["attestation"]["renderer"] = (
            "qt" if renderer in {"qt", "mixed", "unverified"} else renderer
        )
    if renderer == "mixed":
        data["packaged_e2e"]["launches"][0]["attestation"]["renderer"] = "tk"
    if renderer == "unverified":
        data["packaged_e2e"]["launches"][0]["verified"] = False
    without_action(data, *pair)
    errors = validate_journey(data)
    missing = any(repr(pair) in error for error in errors)
    assert missing is (renderer != "qt")
    if renderer == "qt":
        assert not errors


@pytest.mark.parametrize("platform", ["macos", "windows"])
@pytest.mark.parametrize(
    "pair",
    [
        ("download_operation", "reused"),
        ("help_operation", "replaced"),
        ("player", "hover_preview_shown"),
        ("watch", "rail_scrolled"),
    ],
)
def test_qt_shared_and_supported_actions_remain_required(platform, pair):
    data = telemetry_fixture(candidate(), platform)
    for launch in data["packaged_e2e"]["launches"]:
        launch["attestation"]["renderer"] = "qt"
    for legacy in QT_LEGACY_ACTIONS:
        without_action(data, *legacy)
    without_action(data, "player", "controls_fallback")
    without_action(data, *pair)
    assert any(repr(pair) in error for error in validate_journey(data))


def editorial_candidate(tmp_path, monkeypatch, mode, keys):
    """Synthetic candidate source, never a packaged/native evidence fixture."""
    import shutil

    from quality_harness import telemetry_release as module

    for name in module.ANNOUNCEMENT_SOURCE_FILES:
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(module.ANNOUNCEMENT_SOURCE_ROOT / name, target)
    catalog = ",".join(f"FeatureHighlight({key!r})" for key in keys)
    if catalog:
        catalog += ","
    (tmp_path / module.ANNOUNCEMENT_SOURCE_FILES[0]).write_text(
        f"SHOWCASE_MODE={mode!r}\nSHOWCASE_ID='synthetic'\n"
        f"HIGHLIGHTS=({catalog})\nDID_YOU_KNOW_HIGHLIGHTS=({catalog})\n"
    )
    monkeypatch.setattr(module, "ANNOUNCEMENT_SOURCE_ROOT", tmp_path)
    monkeypatch.setattr(module, "SHOWCASE_MODE", mode)
    return candidate()


@pytest.mark.parametrize(
    "mode,keys,actions",
    [
        ("whats-new", ["design", "custom-output"], {"shown"}),
        ("whats-new", ["output-settings", "design"], {"shown"}),
        ("whats-new", ["output-settings"], {"shown", "try_it"}),
        ("did-you-know", ["youtube-access-tip"], {"shown", "try_it"}),
        ("none", [], set()),
    ],
)
def test_bound_editorial_action_semantics_and_rejections(
    tmp_path, monkeypatch, mode, keys, actions
):
    from collections import Counter

    from quality_harness.telemetry_release import candidate_announcement_actions

    c = editorial_candidate(tmp_path, monkeypatch, mode, keys)
    data = telemetry_fixture(c)
    assert candidate_announcement_actions(c, data) == actions

    def observed(pairs):
        changed = deepcopy(data)
        events = changed["snapshots"]["events_complete"]["events"]
        events[:] = [e for e in events if e.get("feature") != "announcement"]
        events.extend(
            {
                "event_id": "editorial-" + action,
                "event_name": "feature_used",
                "feature": "announcement",
                "action": action,
                "schema_version": 2,
                "dimensions": "{}",
            }
            for action in pairs
        )
        for name in ("denied", "disabled"):
            changed["snapshots"][name]["events"] = deepcopy(events)
        changed["expected_event_counts"] = dict(
            Counter(e["event_name"] for e in events)
        )
        return validate_unbound_journey(changed, candidate=c)

    assert observed(actions) == []
    for action in actions:
        assert any(
            repr(("announcement", action)) in e for e in observed(actions - {action})
        )
    for action in {"shown", "try_it", "done"} - actions:
        assert (
            "Announcement event is unreachable in the bound candidate configuration"
            in observed(actions | {action})
        )


@pytest.mark.parametrize(
    "mutation",
    [
        "source_bytes",
        "manifest_digest",
        "missing_producer",
        "candidate_unverified",
        "different_commit",
        "unverified_launch",
        "unknown_renderer",
        "mixed_renderer",
        "missing_candidate",
    ],
)
def test_announcement_exclusion_cannot_be_supplied_without_source_binding(
    mutation, tmp_path, monkeypatch
):
    from quality_harness import telemetry_release as module

    monkeypatch.setattr(module, "SHOWCASE_MODE", "whats-new")
    c = editorial_candidate(tmp_path, monkeypatch, "whats-new", ["design"])
    data = telemetry_fixture(c)  # Explicit enabled catalog: shown, no Try it.
    if mutation == "source_bytes":
        c["source"]["manifest"]["files"][module.ANNOUNCEMENT_SOURCE_FILES[0]][
            "sha256"
        ] = "0" * 64
    elif mutation == "manifest_digest":
        c["source"]["manifest_sha256"] = "0" * 64
    elif mutation == "missing_producer":
        del c["source"]["manifest"]["files"][module.ANNOUNCEMENT_SOURCE_FILES[1]]
    if mutation in {"source_bytes", "missing_producer"}:
        import hashlib
        import json

        manifest = c["source"]["manifest"]
        payload = {k: v for k, v in manifest.items() if k != "sha256"}
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        manifest["sha256"] = digest
        c["source"]["manifest_sha256"] = digest
    if mutation == "candidate_unverified":
        c["verification"]["verified"] = False
    elif mutation == "different_commit":
        c["source"]["commit"] = "c" * 40
    elif mutation == "unverified_launch":
        data["packaged_e2e"]["launches"][0]["verified"] = False
    elif mutation in {"unknown_renderer", "mixed_renderer"}:
        data["packaged_e2e"]["launches"][0]["attestation"]["renderer"] = (
            "future" if mutation == "unknown_renderer" else "tk"
        )
    elif mutation == "missing_candidate":
        c = None
    # A receipt cannot opt itself out or relabel Done as a separate action.
    data["announcement_actions"] = ["shown"]
    errors = validate_unbound_journey(data, candidate=c)
    assert any("('announcement', 'try_it')" in e for e in errors)
    if c is not None:
        assert any("Announcement" in e for e in errors)


@pytest.mark.parametrize(
    "mode,keys", [("future", ["design"]), ("whats-new", []), ("did-you-know", [])]
)
def test_unknown_or_empty_editorial_configuration_fails_closed(
    tmp_path, monkeypatch, mode, keys
):
    c = editorial_candidate(tmp_path, monkeypatch, mode, keys)
    assert validate_unbound_journey(telemetry_fixture(c), candidate=c)


@pytest.mark.parametrize(
    "mode,keys,try_it",
    [
        ("whats-new", ["design", "custom-output"], False),
        ("whats-new", ["output-settings"], True),
        ("did-you-know", ["tip"], True),
    ],
)
def test_actual_qt_editorial_owner_distinguishes_done_and_try_it(
    monkeypatch, mode, keys, try_it
):
    from types import SimpleNamespace

    from yt_downloader.qt_quick.main import Bridge
    from yt_downloader.whats_new import FeatureHighlight, NativePreview

    observed = []
    owner = SimpleNamespace(
        _editorial_kind=mode,
        _editorial_slides=tuple(
            FeatureHighlight(key, key, key, NativePreview.OUTPUT_SETTINGS)
            for key in keys
        ),
        _settings={},
        _schedule_preferences_save=lambda: None,
        _record_update_feature=lambda feature, action: observed.append(
            (feature, action)
        ),
        _help_observations=SimpleNamespace(panel_closed=lambda: None),
        editorialChanged=SimpleNamespace(emit=lambda: None),
    )
    label = Bridge.editorialFinishLabel.fget(owner)
    assert (label == "Try it") is try_it
    Bridge.dismissEditorial(owner, label == "Try it")
    Bridge.dismissEditorial(owner, True)
    assert observed == ([("announcement", "try_it")] if try_it else [])
    assert not owner._editorial_kind and not owner._editorial_slides
