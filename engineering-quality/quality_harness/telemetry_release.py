"""Read-only preview-D1 evidence, bound to a packaged journey and source.

No fixture insertion, production target option, credential export, or provider
success simulation lives here. Snapshots are taken alongside the real UI driver.
"""

from __future__ import annotations

import json
import subprocess
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PREVIEW_DATABASE_ID = "924640fb-3be3-47ca-992c-1c7745bd8469"
PREVIEW_WORKER = "vodforge-preview"
CHECKPOINTS = (
    "first_launch",
    "same_version_reopen",
    "events_complete",
    "denied",
    "disabled",
    "unknown",
)
from yt_downloader.product_telemetry import PRODUCT_EVENT_NAMES
from yt_downloader.telemetry_features import FEATURE_ACTIONS, validate_dimensions
from yt_downloader.whats_new import SHOWCASE_MODE

EVENTS = PRODUCT_EVENT_NAMES


def read_preview_snapshot(site: Path, install_id: str) -> dict[str, Any]:
    install_id = str(uuid.UUID(install_id))
    config = json.loads((site / "wrangler.preview.jsonc").read_text())
    databases = config.get("d1_databases", [])
    if (
        config.get("name") != PREVIEW_WORKER
        or config.get("routes") != []
        or len(databases) != 1
        or databases[0].get("database_id") != PREVIEW_DATABASE_ID
        or databases[0].get("database_name") != "vodforge_preview"
    ):
        raise ValueError("Preview Worker/database isolation configuration mismatch")
    # The only interpolated value is a parsed UUID. Never select bearer secrets,
    # email, feedback text, browser capabilities, or another installation's rows.
    statements = [
        f"SELECT install_id,platform,first_app_version,current_app_version,created_at,first_launched_at,last_seen_at,first_seen_at,cloud_clicked_at,source FROM installations WHERE install_id='{install_id}'",
        f"SELECT COUNT(*) AS count FROM telemetry_clients WHERE install_id='{install_id}'",
        f"SELECT event_id,event_name,occurred_at,received_at,app_version,platform,release_channel,run_kind,output_type,failure_reason,from_version,to_version,schema_version,attempt_id,retry_of,feature,action,dimensions FROM product_events WHERE install_id='{install_id}' ORDER BY occurred_at,event_id",
    ]
    command = [
        "node",
        str(site / "node_modules/wrangler/bin/wrangler.js"),
        "d1",
        "execute",
        "vodforge_preview",
        "--remote",
        "--config",
        "wrangler.preview.jsonc",
        "--command",
        ";".join(statements),
        "--json",
    ]
    completed = subprocess.run(
        command, cwd=site, capture_output=True, text=True, timeout=90, check=True
    )
    data = json.loads(completed.stdout)
    if len(data) != 3 or any(
        row.get("success") is not True or row.get("meta", {}).get("rows_written") != 0
        for row in data
    ):
        raise ValueError("Preview D1 readback failed or wrote rows")
    return {
        "database_id": PREVIEW_DATABASE_ID,
        "worker": PREVIEW_WORKER,
        "read_at": datetime.now(timezone.utc).isoformat(),
        "install_id": install_id,
        "installations": data[0]["results"],
        "clients": data[1]["results"][0]["count"],
        "events": data[2]["results"],
        "rows_written": 0,
    }


def validate_journey(data: dict[str, Any]) -> list[str]:
    """Recompute assertions from readbacks; never trust a supplied passed flag."""
    errors: list[str] = []
    snapshots = data.get("snapshots", {})
    if set(snapshots) != set(CHECKPOINTS):
        return ["Every launch/events/privacy checkpoint is required"]
    for name, snapshot in snapshots.items():
        if (
            snapshot.get("database_id") != PREVIEW_DATABASE_ID
            or snapshot.get("worker") != PREVIEW_WORKER
            or snapshot.get("rows_written") != 0
        ):
            errors.append(f"{name}: invalid preview readback")
    identities = {s.get("install_id") for s in snapshots.values()}
    if len(identities) != 1 or None in identities:
        errors.append("Checkpoints must use the same isolated installation")
    first, reopened, complete = (snapshots[n] for n in CHECKPOINTS[:3])
    unknown = snapshots["unknown"]
    if (
        unknown.get("installations") != []
        or unknown.get("clients") != 0
        or unknown.get("events") != []
    ):
        errors.append("Unknown-consent launch must not create optional telemetry rows")
    if any(
        len(s.get("installations", [])) != 1 or s.get("clients") != 1
        for name, s in snapshots.items()
        if name != "unknown"
    ):
        return errors + ["Expected one installation and one credential throughout"]
    initial, second, last = (s["installations"][0] for s in (first, reopened, complete))
    if (
        not initial.get("last_seen_at")
        or not second.get("last_seen_at")
        or second["last_seen_at"] <= initial["last_seen_at"]
    ):
        errors.append("Same-version reopen did not advance last seen")
    for field in ("first_launched_at", "current_app_version", "created_at"):
        if not initial.get(field) or second.get(field) != initial[field]:
            errors.append(f"Reopen changed or omitted {field}")
    if any(e["event_name"] == "client_update" for e in reopened.get("events", [])):
        errors.append("Same-version reopen created an update event")
    actual = Counter(e["event_name"] for e in complete.get("events", []))
    expected = data.get("expected_event_counts", {})
    if not EVENTS <= set(expected) or any(
        type(n) is not int or n < 1 for n in expected.values()
    ):
        errors.append(
            "Explicit positive expected counts for every product event required"
        )
    if actual != Counter(expected):
        errors.append("D1 event counts disagree with observed journey actions")
    if actual["app_opened"] < 2:
        errors.append("Two app-open events are required")
    events = complete.get("events", [])
    if len({e["event_id"] for e in events}) != len(events):
        errors.append("Duplicate event IDs")
    for output in ("mp4", "mp3", "original"):
        for name in ("run_started", "run_completed", "playback_started"):
            if not any(
                e["event_name"] == name and e.get("output_type") == output
                for e in events
            ):
                errors.append(f"Missing {name}/{output or 'Original audio'} journey")
    observed_actions = {
        (event.get("feature"), event.get("action"))
        for event in [
            *events,
            *data.get("update", {}).get("after", {}).get("events", []),
        ]
        if event.get("event_name") == "feature_used"
    }
    required_actions = {
        (feature, action)
        for feature, actions in FEATURE_ACTIONS.items()
        if feature != "announcement" or SHOWCASE_MODE != "none"
        for action in actions
    }
    if SHOWCASE_MODE == "none" and any(
        feature == "announcement" for feature, _ in observed_actions
    ):
        errors.append("Disabled release announcement emitted telemetry")
    if not required_actions <= observed_actions:
        errors.append(
            "Missing feature/action preview-D1 observations: "
            + str(sorted(required_actions - observed_actions))
        )
    attempts: dict[str, set[str]] = {}
    presets: set[str] = set()
    encoders: set[str] = set()
    for event in events:
        if event.get("schema_version") != 2:
            errors.append("Current candidate must emit schema v2")
        try:
            dimensions = validate_dimensions(
                json.loads(event.get("dimensions") or "{}")
            )
        except (ValueError, TypeError):
            errors.append("Invalid or private telemetry dimensions")
            continue
        if dimensions.get("preset"):
            presets.add(dimensions["preset"])
        if dimensions.get("encoder"):
            encoders.add(dimensions["encoder"])
        attempt = event.get("attempt_id")
        if event["event_name"].startswith(("run_", "local_conversion_")):
            try:
                uuid.UUID(attempt)
            except (ValueError, TypeError, AttributeError):
                errors.append("Lifecycle event missing opaque attempt identifier")
            else:
                attempts.setdefault(attempt, set()).add(event["event_name"])
    for attempt, names in attempts.items():
        if (
            len(names & {"run_completed", "run_failed", "run_stopped"}) > 1
            or len(
                names
                & {
                    "local_conversion_completed",
                    "local_conversion_failed",
                    "local_conversion_stopped",
                }
            )
            > 1
        ):
            errors.append("An attempt has conflicting terminal outcomes")
        if (
            names & {"run_completed", "run_failed", "run_stopped"}
            and "run_started" not in names
        ):
            errors.append("Run outcome has no matching start")
        if (
            names
            & {
                "local_conversion_completed",
                "local_conversion_failed",
                "local_conversion_stopped",
            }
            and "local_conversion_started" not in names
        ):
            errors.append("Local conversion outcome has no matching start")
    if not any(
        event.get("retry_of") in attempts
        and event.get("retry_of") != event.get("attempt_id")
        and event["event_name"] == "run_completed"
        for event in events
    ):
        errors.append("A successful retry must link to its earlier attempt")
    if not {"everyday", "streaming", "editing", "sharing", "ctv", "custom"} <= presets:
        errors.append("All six export presets require observed telemetry")
    if "cpu" not in encoders or (
        data.get("platform") == "windows" and "nvidia" not in encoders
    ):
        errors.append("Actual CPU and Windows NVIDIA export observations required")
    if not last.get("first_seen_at") or not last.get("cloud_clicked_at"):
        errors.append("Settings impression and Cloud-interest observations required")
    for name in ("denied", "disabled"):
        for field in ("installations", "clients", "events"):
            if snapshots[name].get(field) != complete.get(field):
                errors.append(f"{name}: telemetry changed D1 {field}")
    if snapshots["denied"].get("consent_choice") != "denied":
        errors.append("Denied checkpoint must retain the actual saved refusal")
    if (
        snapshots["disabled"]
        .get("launch", {})
        .get("attestation", {})
        .get("telemetry_preview")
        is not False
    ):
        errors.append("Disabled checkpoint requires an attested disabled launch")
    update = data.get("update", {})
    before, after = update.get("before", {}), update.get("after", {})
    if not before or not after:
        errors.append("Real old-to-candidate version update readbacks required")
    else:
        for snapshot in (before, after):
            if (
                snapshot.get("database_id") != PREVIEW_DATABASE_ID
                or snapshot.get("rows_written") != 0
            ):
                errors.append("Update evidence must be read-only preview D1")
        old_rows, new_rows = (
            before.get("installations", []),
            after.get("installations", []),
        )
        if len(old_rows) != 1 or len(new_rows) != 1:
            errors.append("Update installation missing")
        else:
            old, new = old_rows[0], new_rows[0]
            updates = [
                e
                for e in after.get("events", [])
                if e["event_name"] == "client_update"
                and e.get("to_version") == new.get("current_app_version")
            ]
            if (
                old.get("install_id") != new.get("install_id")
                or old.get("current_app_version") == new.get("current_app_version")
                or new.get("current_app_version") != last.get("current_app_version")
                or len(updates) != 1
                or updates[0].get("from_version") != old.get("current_app_version")
            ):
                errors.append(
                    "Update must preserve installation and emit exactly one correct transition"
                )
    return errors


def release_checks(receipts, candidate):
    """Require both shipping platforms; a telemetry-off E2E cannot satisfy this."""
    from .release_gate import _check

    checks = []
    for platform in ("macos", "windows"):
        matching = [r for r in receipts if r.get("platform") == platform]
        errors = []
        if len(matching) != 1:
            errors.append("Exactly one preview journey receipt required")
        else:
            data = matching[0]
            errors.extend(validate_journey(data))
            if data.get("source_commit") != candidate.get("source", {}).get("commit"):
                errors.append("Telemetry source does not match release candidate")
            journey = data.get("packaged_e2e", {})
            binding = journey.get("candidate_binding", {})
            if (
                journey.get("scenario", {}).get("status") != "passed"
                or binding.get("verified") is not True
                or binding.get("artifact_policy") != "release"
                or not binding.get("archive_sha256")
                or data.get("telemetry_mode") != "preview"
                or journey.get("telemetry_mode") != "preview"
                or journey.get("process_provenance", {}).get("verified") is not True
                or journey.get("artifact_integrity", {}).get("verified") is not True
            ):
                errors.append("Passed exact-artifact packaged preview journey required")
            from .packaged_e2e import TELEMETRY_UI_EVENT_ORDER

            trace = journey.get("driver_trace", {}).get("events", [])
            if (
                not set(TELEMETRY_UI_EVENT_ORDER)
                <= {event.get("event") for event in trace}
                or journey.get("driver_trace_validation", {}).get("valid") is not True
            ):
                errors.append(
                    "All telemetry UI actions require verified native driver evidence"
                )
            launches = journey.get("launches", [])
            if sum(
                launch.get("attestation", {}).get("telemetry_preview") is True
                for launch in launches
            ) < 2 or any(
                launch.get("verified") is not True
                or launch.get("attestation", {}).get("telemetry_production")
                is not False
                for launch in launches
            ):
                errors.append("Two attested preview-only launches required")
            for snapshot in data.get("snapshots", {}).values():
                if snapshot.get("candidate_binding", {}).get(
                    "archive_sha256"
                ) != binding.get("archive_sha256"):
                    errors.append("Snapshot belongs to a different artifact")
            if platform == "macos" and binding.get("archive_sha256") != candidate.get(
                "immutable_archive", {}
            ).get("sha256"):
                errors.append(
                    "Mac telemetry artifact does not match publication artifact"
                )
        checks.append(
            _check(
                "telemetry.preview_d1." + platform,
                label=platform + " packaged preview D1 telemetry",
                status="failed" if errors else "passed",
                required=True,
                evidence=errors
                or [
                    "All product events, same-version reopen, update, funnel and privacy readbacks agree"
                ],
            )
        )
    return checks


def snapshot_command(args) -> int:
    session = json.loads(args.session.read_text())
    if session.get("candidate_binding", {}).get(
        "verified"
    ) is not True or not session.get("launches"):
        raise ValueError("Snapshot requires an attested immutable-candidate session")
    profile = Path(session["state_paths"]["application_data"])
    state = json.loads((profile / "installation.json").read_text())
    snapshot = read_preview_snapshot(args.site.resolve(), state["install_id"])
    from yt_downloader.settings_store import load_settings

    snapshot["consent_choice"] = (
        load_settings(profile / "settings.json")
        .get("analytics_consent", {})
        .get("choice")
    )
    snapshot["launch"] = session.get("current_launch") or session["launches"][-1]
    snapshot["session_nonce"] = session["session_nonce"]
    snapshot["candidate_binding"] = session["candidate_binding"]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(snapshot, indent=2) + "\n")
    print(f"Preview D1 checkpoint saved: {args.output}")
    return 0


def verify_command(args) -> int:
    candidate = json.loads(args.candidate.read_text())
    journey = json.loads(args.e2e_result.read_text())
    data = {
        "platform": args.platform,
        "source_commit": candidate["source"]["commit"],
        "telemetry_mode": "preview",
        "packaged_e2e": journey,
        "expected_event_counts": json.loads(args.expected_counts.read_text()),
        "snapshots": {
            name: json.loads((args.snapshots / (name + ".json")).read_text())
            for name in CHECKPOINTS
        },
        "update": {
            name: json.loads(
                (args.snapshots / ("update_" + name + ".json")).read_text()
            )
            for name in ("before", "after")
        },
    }
    checks = release_checks([data], candidate)
    check = next(check for check in checks if check["id"].endswith(args.platform))
    data["status"] = check["status"]
    data["errors"] = check["evidence"] if check["status"] != "passed" else []
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(data, indent=2) + "\n")
    print(f"Preview telemetry {data['status']}: {args.output}")
    return 0 if data["status"] == "passed" else 1
