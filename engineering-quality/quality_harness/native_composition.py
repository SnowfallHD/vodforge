"""Compose candidate-bound native coverage, retaining every original outcome.

No process, fixture, telemetry request or original receipt is changed here.
Independent presentation actions may compose; recovery, queue and privacy chains
must be proved within one original session, never assembled across identities.
"""

from __future__ import annotations

import json
from pathlib import Path

from .packaged_e2e import (
    TELEMETRY_UI_EVENT_ORDER,
    _parse_observed_at,
    _validate_driver_trace,
)
from .receipt_composition import read_bound
from .source_identity import validate_manifest
from .util import sha256_file

FORMAT = "vodforge-native-composition-v1"
CHAINS = (
    (
        "app_visible",
        "url_entered",
        "settings_observed",
        "forge_started",
        "progress_observed",
        "completion_observed",
        "library_observed",
        "library_description_observed",
    ),
    (
        "slow_run_started",
        "second_run_queued",
        "cancellation_requested",
        "cancellation_observed",
        "queued_run_started",
        "queued_run_completion_observed",
    ),
    ("shutdown_requested", "restart_requested", "restart_observed"),
)


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _identity(binding):
    return {
        key: binding.get(key)
        for key in (
            "candidate_id",
            "source_commit",
            "source_manifest_sha256",
            "archive_sha256",
            "bundle_tree_sha256",
        )
    }


def _snapshot(ref, binding, launches, platform):
    from .telemetry_target import PREVIEW_DATABASE_ID, PREVIEW_WORKER

    value = read_bound(ref)
    _require(
        value.get("database_id") == PREVIEW_DATABASE_ID
        and value.get("worker") == PREVIEW_WORKER
        and value.get("rows_written") == 0,
        "Invalid read-only preview checkpoint",
    )
    _require(
        _identity(value.get("candidate_binding", {})) == _identity(binding),
        "Checkpoint belongs to another candidate",
    )
    import uuid

    install_id = str(uuid.UUID(value["install_id"]))
    _require(install_id == value["install_id"], "Noncanonical installation identity")
    _require(
        _parse_observed_at(value.get("read_at")) is not None
        and isinstance(value.get("events"), list),
        "Missing readback timestamp or events",
    )
    attestation = value.get("launch", {}).get("attestation", {})
    _require(
        any(
            value.get("launch", {}).get("launch_id") == item.get("launch_id")
            and value.get("launch", {}).get("session_nonce")
            == item.get("session_nonce")
            for item in launches
        ),
        "Checkpoint launch belongs to another session",
    )
    _require(
        attestation.get("telemetry_production") is False,
        "Production telemetry checkpoint rejected",
    )
    for row in value.get("installations", []):
        _require(
            row.get("install_id") == install_id and row.get("platform") == platform,
            "Checkpoint installation/platform mismatch",
        )
    events = value["events"]
    _require(
        len({e.get("event_id") for e in events}) == len(events)
        and all(e.get("event_id") for e in events),
        "Duplicate/missing checkpoint event identity",
    )
    for event in events:
        _require(event.get("platform") == platform, "Cross-platform checkpoint event")
        if event.get("event_name") == "app_opened":
            _require(
                json.loads(event.get("dimensions") or "{}").get("build_revision")
                == binding["source_commit"],
                "Checkpoint app-open belongs to another source",
            )
    return value


def compose_native_coverage(candidate, platform, constituents, *, updater_refs=()):
    """Recompute bounded scope; a failed wrapper is never rewritten as passed."""
    _require(platform in {"macos", "windows"}, "Unknown native platform")
    _require(
        candidate.get("artifact_policy") == "release", "Release candidate required"
    )
    _require(
        candidate.get("verification", {}).get("verified") is True
        or candidate.get("readback_verification", {}).get("verified") is True,
        "Unverified candidate",
    )
    _require(
        candidate.get("machine", {}).get("system")
        == {"macos": "Darwin", "windows": "Windows"}[platform],
        "Candidate platform mismatch",
    )
    source = candidate.get("source", {})
    _require(
        validate_manifest(source.get("manifest"), source.get("manifest_sha256")),
        "Invalid candidate source manifest",
    )
    expected = {
        "candidate_id": candidate.get("candidate_id"),
        "source_commit": source.get("commit"),
        "source_manifest_sha256": source.get("manifest_sha256"),
        "archive_sha256": candidate.get("immutable_archive", {}).get("sha256"),
        "bundle_tree_sha256": candidate.get("artifact", {})
        .get("bundle_tree", {})
        .get("sha256"),
    }
    _require(all(expected.values()), "Missing candidate/archive/tree identity")
    _require(
        isinstance(constituents, list) and bool(constituents), "No native constituents"
    )
    covered, cohorts, original_paths = set(), [], set()
    incomplete_chains = []
    for row in constituents:
        ref = row["receipt"]
        _require(ref["path"] not in original_paths, "Duplicate original native receipt")
        original_paths.add(ref["path"])
        original = read_bound(ref)
        session = read_bound(row["session"])
        binding = original.get("candidate_binding", {})
        _require(
            _identity(binding) == expected
            and _identity(session.get("candidate_binding", {})) == expected
            and binding.get("verified") is True
            and binding.get("artifact_policy") == "release"
            and session.get("candidate_binding", {}).get("artifact_policy")
            == "release",
            "Native constituent candidate/hash mismatch",
        )
        _require(
            original.get("telemetry_mode")
            == session.get("telemetry_mode")
            == "preview",
            "Native constituent consent mode mismatch",
        )
        _require(
            original.get("artifact_integrity", {}).get("verified") is True
            and original.get("process_provenance", {}).get("verified") is True,
            "Native integrity/process provenance failed",
        )
        metrics = original.get("scenario", {}).get("metrics", {})
        _require(
            metrics.get("clean_exit") is True
            and metrics.get("harness_forced_termination") is False
            and metrics.get("unexpected_process_exit") is False
            and metrics.get("staging_residue_count") == 0
            and metrics.get("surviving_owned_process_count") == 0,
            "Native owner/cleanup failure cannot be composed",
        )
        launches = original.get("launches", [])
        _require(
            launches and launches == session.get("launches"),
            "Original launch receipts changed",
        )
        for launch in launches:
            attestation = launch.get("attestation", {})
            _require(
                launch.get("verified") is True
                and launch.get("returncode") == 0
                and not launch.get("group_survivors_after_exit"),
                "Unverified or unclean native launch",
            )
            _require(
                attestation.get("renderer") == "qt"
                and attestation.get("telemetry_production") is False
                and attestation.get("pid") == launch.get("pid")
                and attestation.get("session_nonce") == session.get("session_nonce"),
                "Native attestation/consent identity mismatch",
            )
            _require(
                launch.get("bundle_tree_sha256") == expected["bundle_tree_sha256"]
                and launch.get("executable_sha256")
                == candidate.get("artifact", {}).get("executable_sha256")
                and launch.get("observed_executable")
                == launch.get("expected_executable"),
                "Native executable/tree identity mismatch",
            )
        directory = Path(session["session_dir"])
        trace_ref = row["trace"]
        trace = read_bound(trace_ref)
        _require(trace == original.get("driver_trace"), "Original driver trace changed")
        validation = _validate_driver_trace(
            trace,
            profile=session["e2e_profile"],
            session_dir=directory,
            session_nonce=session["session_nonce"],
            launches=launches,
            continuations=session.get("continuations"),
        )
        _require(
            validation["structural_valid"],
            "Native trace provenance, sequence or screenshot failure",
        )
        completed = _parse_observed_at(original.get("completed_at"))
        _require(completed is not None, "Missing native completion timestamp")
        for event in trace["events"]:
            launch = next(
                item
                for item in launches
                if item["launch_sequence"] == event["launch_sequence"]
            )
            observed = _parse_observed_at(event["observed_at"])
            _require(
                launch["create_time"] <= observed.timestamp() <= completed.timestamp(),
                "Native observation is outside its owned process interval",
            )
            if event.get("screenshot"):
                _require(
                    event.get("screenshot_sha256")
                    == sha256_file(Path(event["screenshot"])),
                    "Original native frame bytes changed",
                )
        actions = set(validation["observed_required_order"])
        selected = row.get("actions", list(actions))
        _require(
            isinstance(selected, list)
            and len(selected) == len(set(selected))
            and set(selected) <= actions,
            "Selected native action absent or duplicate",
        )
        selected = set(selected)
        for chain in CHAINS:
            present = selected.intersection(chain)
            if present and present != set(chain):
                # Keep original bounded coverage visible, but never stitch a
                # causally incomplete chain out of different installations.
                selected.difference_update(chain)
                incomplete_chains.append(
                    {
                        "receipt": ref,
                        "present": sorted(present),
                        "missing": sorted(set(chain) - present),
                    }
                )
        if "restart_observed" in selected:
            _require(
                original.get("history_persistence", {}).get("verified") is True,
                "Restart has no independent persistence proof",
            )
        snapshots = {
            name: _snapshot(value, binding, launches, platform)
            for name, value in row.get("snapshots", {}).items()
        }
        checkpoint_order = (
            "unknown",
            "first_launch",
            "same_version_reopen",
            "events_complete",
            "denied",
            "disabled",
        )
        times = [
            _parse_observed_at(snapshots[name]["read_at"])
            for name in checkpoint_order
            if name in snapshots
        ]
        _require(times == sorted(times), "Consent checkpoint chronology reversed")
        identities = {s["install_id"] for s in snapshots.values()}
        _require(
            len(identities) <= 1, "Consent checkpoints mix installation identities"
        )
        if "unknown" in snapshots:
            _require(
                snapshots["unknown"].get("installations") == []
                and snapshots["unknown"].get("clients") == 0
                and snapshots["unknown"].get("events") == [],
                "Unknown consent created optional preview rows",
            )
        if (
            "consent_denied_observed" in selected
            or "telemetry_disabled_observed" in selected
        ):
            _require(
                {"events_complete", "denied", "disabled"} <= set(snapshots),
                "Privacy action missing same-cohort readbacks",
            )
            baseline = snapshots["events_complete"]
            for name in ("denied", "disabled"):
                _require(
                    all(
                        snapshots[name].get(k) == baseline.get(k)
                        for k in ("installations", "clients", "events")
                    ),
                    "Consent withdrawal changed preview data",
                )
            _require(
                snapshots["denied"].get("consent_choice") == "denied"
                and snapshots["disabled"]
                .get("launch", {})
                .get("attestation", {})
                .get("telemetry_preview")
                is False,
                "Missing actual denied/disabled consent",
            )
        covered.update(selected)
        cohorts.append(
            {
                "receipt": ref,
                "session": row["session"],
                "trace": trace_ref,
                "original_status": original.get("scenario", {}).get("status"),
                "session_nonce": session["session_nonce"],
                "installation_id": next(iter(identities), None),
                "covered_actions": sorted(selected),
                "snapshots": row.get("snapshots", {}),
                "missing_original_actions": validation["missing_events"],
            }
        )
        if row.get("page_refs"):
            _require(
                "first_launch" in row.get("snapshots", {}),
                "Pages require their original enrollment checkpoint",
            )
            cohorts[-1]["page_inventory"] = compose_page_inventory(
                row["snapshots"]["first_launch"],
                row["page_refs"],
                binding,
                launches,
                platform,
            )
    updater_scopes = [_update_transactions(candidate, ref) for ref in updater_refs]
    remaining = [a for a in TELEMETRY_UI_EVENT_ORDER if a not in covered]
    return {
        "format": FORMAT,
        "candidate_binding": expected,
        "platform": platform,
        "constituents": constituents,
        "cohorts": cohorts,
        "updater_refs": list(updater_refs),
        "bounded_update_transactions": updater_scopes,
        "covered_actions": sorted(covered),
        "remaining_actions": remaining,
        "incomplete_chains": incomplete_chains,
        "native_coverage_complete": not remaining,
        "release_acceptance": False,
        "limits": "Native scope only. D1 counts/privacy/update identities remain per cohort; complete telemetry and independent media/pipeline release checks are still required.",
    }


def _update_transactions(candidate, ref):
    """Retain helper transaction proof separately from UI/D1/privacy coverage."""
    proof = read_bound(ref)
    _require(
        proof.get("candidate") == candidate["source"]["commit"],
        "Updater source mismatch",
    )
    import uuid

    uuid.UUID(proof["installation_id"])
    originals = [read_bound(item) for item in proof["evidence"]]
    states = [item for item in originals if "helpers" in item and "attestation" in item]
    _require(len(states) >= 2, "Missing original updater states")
    helpers = {}
    data_hashes = None
    for state in states:
        _require(
            state.get("candidate_archive_sha256")
            == candidate["immutable_archive"]["sha256"]
            and state.get("executable_sha256")
            == candidate["artifact"]["executable_sha256"],
            "Updater target archive/executable mismatch",
        )
        att = read_bound(
            {"path": state["attestation_path"], "sha256": state["attestation_sha256"]}
        )
        _require(
            att == state["attestation"]
            and att.get("pid") == state["pid"]
            and att.get("executable") == state["executable"]
            and att.get("telemetry_preview") is True
            and att.get("telemetry_production") is False,
            "Updater attestation/consent mismatch",
        )
        _require(
            Path(state["screenshot"]).is_file()
            and sha256_file(Path(state["screenshot"])) == state["screenshot_sha256"],
            "Updater original frame changed",
        )
        hashes = {item["path"]: item["sha256"] for item in state["data_preservation"]}
        _require(
            hashes
            and all(
                item["sha256"] == item.get("observed_sha256")
                for item in state["data_preservation"]
            ),
            "Updater durable-data mismatch",
        )
        _require(
            data_hashes is None or data_hashes == hashes,
            "Updater transaction data owners changed",
        )
        data_hashes = hashes
        for item in state["helpers"]:
            helper = read_bound({"path": item["copied_path"], "sha256": item["sha256"]})
            _require(
                helper == item["receipt"]
                and helper.get("status") == "relaunched"
                and helper.get("executable_sha256")
                == candidate["artifact"]["executable_sha256"]
                and helper.get("telemetry_permitted") is True
                and type(helper.get("repair")) is bool,
                "Original updater helper failed or changed",
            )
            key = helper["repair"]
            _require(
                key not in helpers or helpers[key] == item["sha256"],
                "Conflicting updater helper identity",
            )
            helpers[key] = item["sha256"]
    _require(
        set(helpers) == {False, True} and len(set(helpers.values())) == 2,
        "Distinct Update and Repair original helpers required",
    )
    return {
        "scope": "actual_update_repair_transactions",
        "original_proof": ref,
        "installation_id": proof["installation_id"],
        "helper_hashes": helpers,
        "retained": True,
        "telemetry_checkpoint_complete": False,
        "clean_exit_proved": False,
        "limits": "Separate installation. Does not supply main journey counts/privacy, complete UI action or historical public compatibility; original final cleanup limit remains open.",
    }


def compose_page_inventory(context_ref, page_refs, binding, launches, platform):
    """Reassemble retained pages per installation; never invent a final snapshot.

    Older pages omitted rowid/query bounds. Their action inventory is reusable,
    but their watermark cannot supply a completed/privacy release checkpoint.
    """
    context = _snapshot(context_ref, binding, launches, platform)
    grouped = {}
    for ref in page_refs:
        page = read_bound(ref)
        _require(
            page.get("install_id") == context["install_id"],
            "Page installation identity mismatch",
        )
        low, high, total, offset = (
            page.get("lower_exclusive", 0),
            page.get("watermark"),
            page.get("total"),
            page.get("offset"),
        )
        _require(
            all(type(n) is int and n >= 0 for n in (low, high, total, offset))
            and high > low,
            "Invalid page watermark/offset",
        )
        raw = page.get("raw", {})
        _require(raw.get("isError") is not True, "Page connector failed")
        blocks = [
            json.loads(c["text"])
            for c in raw.get("content", [])
            if c.get("type") == "text"
        ]
        _require(len(blocks) == 1, "Ambiguous original page payload")
        result = blocks[0]
        _require(
            result.get("success") is True
            and result.get("meta", {}).get("rows_written") == 0,
            "Page read failed or wrote rows",
        )
        columns, rows = result.get("columns"), result.get("rows")
        _require(
            isinstance(columns, list)
            and len(columns) == len(set(columns))
            and isinstance(rows, list)
            and all(len(row) == len(columns) for row in rows),
            "Truncated/malformed original page",
        )
        _require(
            {"event_id", "event_name", "platform", "dimensions"} <= set(columns),
            "Page lacks event identity/source",
        )
        key = (low, high, total)
        grouped.setdefault(key, []).append(
            (offset, [dict(zip(columns, row, strict=True)) for row in rows], ref)
        )
    previous, seen, identities, refs = 0, {}, [], []
    rowid_bound = True
    for (low, high, total), pages in sorted(grouped.items()):
        _require(low == previous, "Page watermark gap or overlapping ranges")
        cursor = 0
        for offset, rows, ref in sorted(pages):
            _require(
                offset == cursor and (rows or total == 0),
                "Page offset gap, overlap or unexpected empty page",
            )
            for event in rows:
                eid = event.get("event_id")
                _require(
                    eid and eid not in seen,
                    "Duplicate/overlapping event ID across pages",
                )
                _require(
                    event.get("platform") == platform, "Cross-platform paged event"
                )
                if "rowid" in event:
                    _require(
                        type(event["rowid"]) is int and low < event["rowid"] <= high,
                        "Event exceeds original watermark",
                    )
                else:
                    rowid_bound = False
                if event.get("event_name") == "app_opened":
                    _require(
                        json.loads(event.get("dimensions") or "{}").get(
                            "build_revision"
                        )
                        == binding["source_commit"],
                        "Paged source mismatch",
                    )
                seen[eid] = event
            refs.append(ref)
            cursor += len(rows)
        _require(cursor == total, "Page total disagrees with actual rows")
        identities.append({"lower_exclusive": low, "watermark": high, "total": total})
        previous = high
    return {
        "context": context_ref,
        "pages": refs,
        "install_id": context["install_id"],
        "watermark": previous,
        "ranges": identities,
        "row_count": len(seen),
        "feature_actions": sorted(
            {
                (e.get("feature"), e.get("action"))
                for e in seen.values()
                if e.get("event_name") == "feature_used"
            }
        ),
        "watermark_row_binding_verified": rowid_bound,
        "complete_privacy_checkpoint": False,
        "limits": "Original installation kept separate. Missing original rowid/query boundary leaves watermark unproven; no synthesized installations/clients/privacy snapshot.",
    }


def compose_command(args):
    from .candidate_artifact import load_and_verify_candidate

    _require(not args.output.exists(), "Preserve existing composition output")
    candidate = load_and_verify_candidate(args.candidate)
    selection = read_bound(
        {"path": str(args.selection.resolve()), "sha256": sha256_file(args.selection)}
    )
    result = compose_native_coverage(
        candidate,
        args.platform,
        selection["constituents"],
        updater_refs=selection.get("updater_refs", []),
    )
    result["candidate_ref"] = {
        "path": str(args.candidate.resolve()),
        "sha256": sha256_file(args.candidate),
    }
    result["selection_ref"] = {
        "path": str(args.selection.resolve()),
        "sha256": sha256_file(args.selection),
    }
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "covered": len(result["covered_actions"]),
                "remaining": result["remaining_actions"],
                "release_acceptance": False,
            }
        )
    )
    return 0


def verify_native_composition(result, candidate):
    """Recompute every selected scope; edited summaries never confer coverage."""
    try:
        _require(result.get("format") == FORMAT, "Unknown native composition")
        expected = compose_native_coverage(
            candidate,
            result["platform"],
            result["constituents"],
            updater_refs=result.get("updater_refs", []),
        )
        return all(
            json.dumps(result.get(key), sort_keys=True)
            == json.dumps(value, sort_keys=True)
            for key, value in expected.items()
        )
    except (KeyError, TypeError, ValueError, OSError, json.JSONDecodeError):
        return False


def release_checks(result):
    """Evaluate a linked native aggregate without promoting any original wrapper.

    Existing independent pipeline/media/persistence requirements apply to a
    designated core receipt. Only its UI coverage predicate comes from the
    recomputed aggregate; no worker, restart or cleanup predicate is supplied.
    """
    from .candidate_artifact import load_and_verify_candidate
    from .release_gate import _check, evaluate_packaged_e2e_receipt

    errors, core_checks = [], []
    try:
        _require(
            result["native_coverage_complete"],
            "Native action coverage remains incomplete: "
            + str(result["remaining_actions"]),
        )
        ref = result["candidate_ref"]
        read_bound(ref)
        candidate = load_and_verify_candidate(Path(ref["path"]))
        _require(
            verify_native_composition(result, candidate),
            "Native composition changed or failed revalidation",
        )
        cores = [row for row in result["constituents"] if row.get("core") is True]
        _require(
            len(cores) == 1,
            "Exactly one independently qualified core pipeline/restart receipt required",
        )
        import copy

        original = read_bound(cores[0]["receipt"])
        derived = copy.deepcopy(original)
        derived["scenario"]["metrics"]["ui_interaction_observed"] = True
        # Do not reuse the original full-journey status. Its other independent
        # predicates remain unchanged and are evaluated by the existing gate.
        core_checks = evaluate_packaged_e2e_receipt(derived)[1:]
        _require(
            all(check["status"] == "passed" for check in core_checks),
            "Core media/pipeline/restart/cleanup scope remains incomplete",
        )
    except (KeyError, TypeError, ValueError, RuntimeError, OSError) as error:
        errors.append(str(error))
    return [
        _check(
            "packaged_e2e.full_journey",
            label="Composed native coverage and independent core journey",
            status="failed" if errors else "passed",
            required=True,
            evidence=[
                *errors,
                "Original wrapper statuses retained; only complete aggregate coverage can satisfy this check.",
            ],
            metrics={
                "remaining_actions": result.get("remaining_actions"),
                "original_statuses": [
                    c.get("original_status") for c in result.get("cohorts", [])
                ],
            },
        ),
        *core_checks,
    ]
