"""Source-hash-bound local HTTP/Worker/D1 diagnostic producer matrix.

Runs actual native presentation producers and actual source admission owners.
Fault fixtures are synthetic. It has no production or release authority.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import subprocess
import uuid
from collections import defaultdict
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlsplit

from .diagnostic_expectations import verify_scenario_events
from .diagnostic_probes import (
    LIBRARY_CASES,
    OPENING_CASES,
    PRESENTATION_CASES,
    RELINK_CASES,
    library_case,
    opening_case,
    presentation_case,
    relink_case,
)
from .library_disclosure_probe import DISCLOSURE_CASES, disclosure_case
from .qt_diagnostic_probes import QT_PRESENTATION_CASES, qt_presentation_case
from .telemetry_checks import (
    _read_line,
    assert_feature_vocabulary,
    install_telemetry_guard,
)
from .watch_queue_probe import QUEUE_CASES, queue_case


def source_snapshot(repo: Path):
    repo = repo.resolve()
    root = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    direct_git = root.returncode == 0 and Path(root.stdout.strip()).resolve() == repo
    if direct_git:
        paths = (
            subprocess.check_output(
                ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
                cwd=repo,
            )
            .decode()
            .split("\0")
        )
        base_commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=repo, text=True
        ).strip()
        status = subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=repo, text=True
        )
        inventory = "git"
    else:
        # Frozen snapshots may sit inside a different repository. Git paths from
        # that ancestor do not describe this source and can yield an empty map.
        ignored = {
            ".git",
            "node_modules",
            "__pycache__",
            ".pytest_cache",
            ".mypy_cache",
            ".ruff_cache",
            ".hypothesis",
            ".wrangler",
            ".astro",
            "dist",
        }
        paths = [
            str(path.relative_to(repo))
            for path in repo.rglob("*")
            if path.is_file()
            and not path.is_symlink()
            and not any(part in ignored for part in path.relative_to(repo).parts)
            and path.suffix not in {".pyc", ".pyo"}
        ]
        base_commit, status, inventory = None, "frozen directory", "directory"
    hashes = {
        name: hashlib.sha256((repo / name).read_bytes()).hexdigest()
        for name in sorted(set(paths))
        if name and (repo / name).is_file()
    }
    if not hashes:
        raise AssertionError(f"Source inventory is empty: {repo}")
    return {
        "root": str(repo),
        "inventory": inventory,
        "base_commit": base_commit,
        "status": status,
        "files": hashes,
        "manifest_sha256": hashlib.sha256(
            json.dumps(hashes, sort_keys=True).encode()
        ).hexdigest(),
    }


def save(path: Path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")


def pipeline(repo: Path, site: Path, destination: Path, *, cases=None):
    from yt_downloader import analytics_consent, product_telemetry
    from yt_downloader import telemetry_credentials as transport
    from yt_downloader.cloud_funnel import (
        load_or_create_installation_state,
        mark_attribution_claim_confirmed,
    )
    from yt_downloader.library_diagnostics import begin_library_action

    runtime_repo = Path(__file__).resolve().parents[2]
    if runtime_repo != repo.resolve():
        raise AssertionError(
            "Diagnostic runtime does not match requested desktop source"
        )
    if Path(product_telemetry.__file__).resolve().parent.parent != repo.resolve():
        raise AssertionError("Imported desktop does not match requested source")
    install_telemetry_guard()
    destination.mkdir(parents=True, exist_ok=True)
    assert_feature_vocabulary(site)
    before = {"desktop": source_snapshot(repo), "backend": source_snapshot(site)}
    save(destination / "source-before.json", before)
    script = Path(__file__).with_name("telemetry_worker.mjs")
    mapping, delivered, diagnostics = [], [], []
    chosen = set(
        cases
        or (
            *PRESENTATION_CASES,
            *LIBRARY_CASES,
            *OPENING_CASES,
            *RELINK_CASES,
            *QUEUE_CASES,
            *DISCLOSURE_CASES,
        )
    )
    assert chosen <= set(
        PRESENTATION_CASES
        + LIBRARY_CASES
        + OPENING_CASES
        + RELINK_CASES
        + QUEUE_CASES
        + DISCLOSURE_CASES
        + QT_PRESENTATION_CASES
    )
    with (destination / "worker.stderr.txt").open("w") as errors:
        process = subprocess.Popen(
            ["node", str(script), str(site)],
            cwd=destination,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=errors,
            text=True,
        )
        try:
            url = _read_line(process)["url"]
            assert urlsplit(url).hostname == "127.0.0.1"

            def snapshot():
                process.stdin.write('{"op":"snapshot"}\n')
                process.stdin.flush()
                return _read_line(process)

            with (
                patch.object(transport, "ENDPOINT", url + "api/telemetry/v2/"),
                patch.object(
                    transport, "telemetry_collection_allowed", return_value=True
                ),
                patch.object(transport, "__version__", "0.1.8"),
                patch.object(
                    product_telemetry, "telemetry_collection_allowed", return_value=True
                ),
                patch.object(
                    analytics_consent, "telemetry_collection_allowed", return_value=True
                ),
            ):
                client = destination / "client"
                consent = analytics_consent.AnalyticsConsentOwner(client)
                consent.choose(True)
                credential = transport.TelemetryCredentialOwner(client)
                assert credential.first_launch("0.1.8", "macos")
                installation = client / "installation.json"
                state = load_or_create_installation_state(installation)
                mark_attribution_claim_confirmed(installation, state.install_id)

                def create_usage(key):
                    def deliver(event):
                        payload = event.public_payload()
                        success = credential.event(payload)
                        if success:
                            delivered.append(payload)
                        return success

                    return product_telemetry.ProductTelemetryOwner(
                        state_path=client / (key + "-outbox.json"),
                        installation_state_path=installation,
                        app_version="0.1.8",
                        platform_name="darwin",
                        d1_recorder=deliver,
                        heycatch_recorder=lambda *_a, **_k: True,
                        diagnostic=diagnostics.append,
                    )

                for case in (
                    *PRESENTATION_CASES,
                    *QT_PRESENTATION_CASES,
                    *LIBRARY_CASES,
                    *OPENING_CASES,
                    *RELINK_CASES,
                    *QUEUE_CASES,
                    *DISCLOSURE_CASES,
                ):
                    if case not in chosen:
                        continue
                    offset = len(delivered)
                    usage = create_usage(case)
                    try:
                        result = (
                            disclosure_case
                            if case in DISCLOSURE_CASES
                            else queue_case
                            if case in QUEUE_CASES
                            else qt_presentation_case
                            if case in QT_PRESENTATION_CASES
                            else presentation_case
                            if case in PRESENTATION_CASES
                            else opening_case
                            if case in OPENING_CASES
                            else relink_case
                            if case in RELINK_CASES
                            else library_case
                        )(destination / "fixtures" / case, usage, case)
                    finally:
                        usage.flush_async()
                        assert usage.shutdown(10), "Outbox worker did not stop"
                    assert not product_telemetry._load_outbox(
                        client / (case + "-outbox.json")
                    ), (case, "Undelivered producer events")
                    events = delivered[offset:]
                    feature = (
                        ("player" if case == "player_description" else "library")
                        if case in DISCLOSURE_CASES
                        else "watch_queue_operation"
                        if case in QUEUE_CASES
                        else "presentation_operation"
                        if case in (*PRESENTATION_CASES, *QT_PRESENTATION_CASES)
                        else "playback_operation"
                        if case in OPENING_CASES
                        else "archive_relink_operation"
                        if case in RELINK_CASES
                        else "library_action_operation"
                    )
                    diagnostic_events = [
                        e for e in events if e.get("feature") == feature
                    ]
                    assert diagnostic_events, (case, "No diagnostic producer events")
                    if case == "hidden_control_fault":
                        assert any(
                            e["action"] == "fault"
                            and e["dimensions"]["missing_image_role"] == "control"
                            and e["dimensions"]["presentation_visibility"] == "hidden"
                            for e in diagnostic_events
                        )
                    if case == "missing_artwork":
                        assert any(
                            e["action"] == "fault"
                            and e["dimensions"]["missing_image_role"] == "artwork"
                            for e in diagnostic_events
                        )
                    verify_scenario_events(case, events)
                    mapping.append(
                        {**result, "event_ids": [e["event_id"] for e in events]}
                    )
                    print(json.dumps({"case": case, "events": len(events)}), flush=True)
                original = snapshot()
                save(destination / "initial-d1-snapshot.json", original)
                assert len(original["events"]) == len(delivered)
                by_id = {e["event_id"]: e for e in original["events"]}
                assert len(by_id) == len(delivered)
                for scenario in mapping:
                    actual = []
                    for event_id in scenario["event_ids"]:
                        stored = dict(by_id[event_id])
                        stored["dimensions"] = json.loads(stored["dimensions"])
                        if stored["failure_detail"] is not None:
                            stored["failure_detail"] = json.loads(
                                stored["failure_detail"]
                            )
                        actual.append(stored)
                    verify_scenario_events(scenario["case"], actual)
                for event in delivered:
                    stored = by_id[event["event_id"]]
                    for field in (
                        "event_name",
                        "run_kind",
                        "output_type",
                        "attempt_id",
                        "retry_of",
                        "feature",
                        "action",
                        "schema_version",
                    ):
                        assert stored[field] == event.get(field), (
                            event["event_id"],
                            field,
                        )
                    assert json.loads(stored["dimensions"]) == event["dimensions"]
                    if "failure_detail" in event:
                        assert (
                            json.loads(stored["failure_detail"])
                            == event["failure_detail"]
                        )
                        assert stored["failure_reason"] == event["failure_reason"]
                    assert credential.event(event)
                assert snapshot()["events"] == original["events"], (
                    "Replay inserted duplicates"
                )
                example = next(
                    (
                        e
                        for e in delivered
                        if e.get("feature") == "presentation_operation"
                    ),
                    next(
                        e
                        for e in delivered
                        if e.get("feature")
                        in {
                            "presentation_operation",
                            "library_action_operation",
                            "playback_operation",
                            "archive_relink_operation",
                            "watch_queue_operation",
                        }
                    ),
                )
                is_queue = example["feature"] == "watch_queue_operation"
                is_presentation = example["feature"] == "presentation_operation"
                is_playback = example["feature"] == "playback_operation"
                is_relink = example["feature"] == "archive_relink_operation"
                malformed = []
                for kind in (
                    "missing_core",
                    "private_content",
                    "unknown_enum",
                    "contradictory_fault",
                ):
                    event = copy.deepcopy(example)
                    event["event_id"] = str(uuid.uuid4())
                    if kind == "missing_core":
                        event["dimensions"].pop(
                            "mode_eligible_bucket"
                            if is_presentation
                            else "operation_id"
                            if is_playback or is_relink or is_queue
                            else "library_subject"
                        )
                    elif kind == "private_content":
                        event["dimensions"][
                            "presentation_mode"
                            if is_presentation
                            else "playback_origin"
                            if is_playback
                            else "relink_mode"
                            if is_relink
                            else "queue_kind"
                            if is_queue
                            else "library_boundary"
                        ] = "PRIVATE path /Users/private.mp4"
                    elif kind == "unknown_enum":
                        event["dimensions"][
                            "presentation_trigger"
                            if is_presentation
                            else "playback_failure_boundary"
                            if is_playback
                            else "relink_mode"
                            if is_relink
                            else "queue_order"
                            if is_queue
                            else "library_intent"
                        ] = "invalid_enum"
                    elif is_presentation:
                        event["action"] = "fault"
                        event["dimensions"]["missing_image_role"] = "none"
                        event["dimensions"]["missing_image_bucket"] = "0"
                    elif is_queue:
                        event["dimensions"]["item_count_bucket"] = "12345"
                    elif is_relink:
                        event["dimensions"]["identity_mismatch_count"] = "5001"
                    elif is_playback:
                        event["action"] = "ready"
                        event["failure_reason"] = "unknown"
                        # A healthy ready event cannot carry a failure reason.
                    else:
                        event["action"] = "completed"
                        event["dimensions"]["library_boundary"] = "annotation"
                    try:
                        accepted = credential.event(event)
                    except transport.RejectedTelemetryEvent:
                        accepted = False
                    assert not accepted, kind
                    malformed.append({"case": kind, "accepted": False})
                assert snapshot()["events"] == original["events"], (
                    "Malformed event persisted"
                )
                # Original consent context cannot adopt a later grant.
                usage = create_usage("consent")
                granted = begin_library_action(usage, "preview_start", "preview")
                consent.choose(False)
                granted.emit("admitted", "queue")
                denied = begin_library_action(usage, "preview_start", "preview")
                consent.choose(True)
                granted.emit("completed", "queue")
                denied.emit("completed", "queue")
                assert usage.shutdown(10)
                # Its initial requested event may race transport. Drain before
                # taking the final denied control below; only existing IDs allowed.
                consent_before = snapshot()
                consent.choose(False)
                denied_usage = create_usage("denied")
                observation = begin_library_action(
                    denied_usage, "preview_start", "preview"
                )
                observation.emit("admitted", "queue")
                observation.emit("completed", "queue")
                denied_usage.flush_async()
                assert denied_usage.shutdown(10)
                assert not credential.event(example)
                assert snapshot() == consent_before
                extra = [
                    e for e in consent_before["events"] if e["event_id"] not in by_id
                ]
                assert all(e["action"] == "requested" for e in extra), (
                    "Revoked operation resumed"
                )
                # Packet contains D1 rows only, without scenario labels or outcome assertions.
                rows = original["events"]
                encoded = json.dumps(rows)
                assert all(
                    token not in encoded
                    for token in (
                        "PRIVATE",
                        "Private",
                        "preview-0",
                        "youtube.com",
                        "/Users/",
                        "thumbnail.jpeg",
                    )
                )
                groups = defaultdict(list)
                for event in rows:
                    dims = json.loads(event["dimensions"])
                    if event.get("feature") in {
                        "presentation_operation",
                        "library_action_operation",
                        "playback_operation",
                        "archive_relink_operation",
                        "watch_queue_operation",
                    }:
                        groups[(event["feature"], dims["operation_id"])].append(
                            int(dims["operation_step"])
                        )
                assert all(
                    steps == list(range(1, len(steps) + 1)) for steps in groups.values()
                ), groups
                save(destination / "persisted-diagnostic-rows.json", rows)
                save(destination / "scenario-mapping.json", mapping)
                save(destination / "delivered-events.json", delivered[: len(rows)])
                after = {
                    "desktop": source_snapshot(repo),
                    "backend": source_snapshot(site),
                }
                assert before == after, "Source changed during diagnostic pipeline"
                save(destination / "source-after.json", after)
                save(
                    destination / "receipt.json",
                    {
                        "passed": True,
                        "scope": "local source Python HTTP to real Worker owner and migrated local D1; synthetic fixtures; no release/deployment authority",
                        "case_count": len(mapping),
                        "stored_events": len(rows),
                        "operation_count": len(groups),
                        "operation_count_scope": sorted(
                            {feature for feature, _key in groups}
                        ),
                        "all_operation_count": len(
                            {
                                (
                                    event["feature"],
                                    json.loads(event["dimensions"])["operation_id"],
                                )
                                for event in rows
                                if "operation_id" in json.loads(event["dimensions"])
                            }
                        ),
                        "source_unchanged": True,
                        "packet_sha256": hashlib.sha256(
                            (
                                destination / "persisted-diagnostic-rows.json"
                            ).read_bytes()
                        ).hexdigest(),
                        "malformed_controls": malformed,
                        "consent_contexts_do_not_resume": True,
                        "denied_transport_and_outbox_silent": True,
                        "replay_idempotent": True,
                        "all_scenario_outcomes_asserted_after_d1_readback": True,
                        "source": before,
                        "diagnostic_messages": diagnostics,
                    },
                )
                print(
                    json.dumps(
                        {"passed": True, "events": len(rows), "cases": len(mapping)}
                    ),
                    flush=True,
                )
        except Exception:
            import traceback

            traceback.print_exc(file=errors)
            save(destination / "partial-delivered-events.json", delivered)
            try:
                save(destination / "failed-readback.json", snapshot())
            except Exception:  # noqa: BLE001 - preserve the original failed assertion
                traceback.print_exc(file=errors)
            raise
        finally:
            if process.poll() is None:
                process.stdin.write('{"op":"stop"}\n')
                process.stdin.flush()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
            process.stdin.close()
            process.stdout.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--site", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--case", action="append")
    args = parser.parse_args()
    pipeline(args.repo, args.site, args.destination, cases=args.case)


if __name__ == "__main__":
    main()


def diagnostic_surface_contract(repo_root: Path, output_dir: Path, *, ui: str = "tk"):
    """Enroll the actual producer/transport matrix in the engineering harness."""
    import sys

    from .telemetry_checks import receipt
    from .util import run_command

    site = Path(
        os.environ.get("VODFORGE_SITE_REPO", str(repo_root.parent / "vodforge-site"))
    ).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    if ui not in {"tk", "qt"}:
        raise ValueError(f"Unsupported presentation renderer: {ui}")
    command = [
        sys.executable,
        "-m",
        "quality_harness.diagnostic_pipeline",
        "--repo",
        str(repo_root),
        "--site",
        str(site),
        "--destination",
        str(output_dir),
    ]
    if ui == "qt":
        for case in QT_PRESENTATION_CASES:
            command.extend(("--case", case))
    result = run_command(
        command,
        cwd=repo_root,
        timeout=240,
        env={
            **os.environ,
            "VODFORGE_NATIVE_UI_TESTS": "1",
            "VODFORGE_DISABLE_TELEMETRY": "1",
        },
    )
    log = output_dir / "runner.log"
    log.write_text(result.stdout + "\n" + result.stderr)
    report = output_dir / "receipt.json"
    data = json.loads(report.read_text()) if report.exists() else {}
    expected_cases = (
        len(QT_PRESENTATION_CASES)
        if ui == "qt"
        else len(PRESENTATION_CASES)
        + len(LIBRARY_CASES)
        + len(OPENING_CASES)
        + len(RELINK_CASES)
        + len(QUEUE_CASES)
        + len(DISCLOSURE_CASES)
    )
    passed = (
        result.returncode == 0
        and data.get("passed") is True
        and data.get("case_count") == expected_cases
    )
    return receipt(
        "unit_static.telemetry_presentation_contract",
        passed,
        [
            (
                "Actual Qt Quick image-status producers through loopback HTTP, real Worker, migrated local D1."
                if ui == "qt"
                else "Actual Tk presentation and source admission producers through loopback HTTP, real Worker, migrated local D1."
            ),
            "Hash-bound source only; synthetic fixtures; no packaged, preview or deployment authority.",
            f"Producer cases: {data.get('case_count', 0)}; stored events: {data.get('stored_events', 0)}",
        ],
        [report, log, output_dir / "persisted-diagnostic-rows.json"],
    )
