"""Local-only cross-repository telemetry checks; no production authority."""

from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from .util import machine_snapshot, run_command

_BLOCKED_ATTEMPTS: list[str] = []
_GUARD_INSTALLED = False
_OWNERSHIP_ORIGINS = (
    "fresh",
    "claim",
    "cloud_seen",
    "cloud_click",
    "legacy_launch",
    "waitlist",
)


def _validate_ownership_cases(cases):
    """Missing coverage is failure, not a vacuously green delivery receipt."""
    if [case["origin"] for case in cases] != list(_OWNERSHIP_ORIGINS):
        raise AssertionError("Incomplete ownership entry-point matrix")
    for case in cases:
        if case["statuses"] != [200, 200, 409, 401]:
            raise AssertionError(f"Credential isolation failed: {case['origin']}")
        if case["client_count"] != 1 or case["legacy"] != {
            "unchanged": True,
            "accepted": 0,
        }:
            raise AssertionError(f"Durable ownership failed: {case['origin']}")


def _ownership_probe(url, process):
    if urlsplit(url).hostname != "127.0.0.1":
        raise AssertionError("Ownership probe is not loopback-only")

    def post(action, body):
        request = Request(
            url + action,
            data=json.dumps(body).encode(),
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer " + "a" * 43,
            },
        )
        try:
            with urlopen(request, timeout=10) as response:
                return response.status, json.load(response)
        except HTTPError as error:
            with error:
                return error.code, json.load(error)

    cases = []
    for origin in _OWNERSHIP_ORIGINS:
        install_id, credential_id = str(uuid.uuid4()), str(uuid.uuid4())
        status, _ = post("ownership-seed", {"kind": origin, "installId": install_id})
        if status != 200:
            raise AssertionError(f"Ownership seed failed: {origin}")
        body = {
            "credential_id": credential_id,
            "install_id": install_id,
            "platform": "macos",
            "app_version": "0.1.8",
            "schema_version": 1,
        }
        statuses = [post("enroll", body)[0], post("enroll", body)[0]]
        other = str(uuid.uuid4())
        statuses.append(post("enroll", {**body, "credential_id": other})[0])
        statuses.append(
            post("launch", {"credential_id": other, "app_version": "0.1.8"})[0]
        )
        if (
            post("launch", {"credential_id": credential_id, "app_version": "0.1.8"})[0]
            != 200
        ):
            raise AssertionError("Legitimate launch failed")
        _, legacy = post("ownership-legacy", {"installId": install_id})
        process.stdin.write('{"op":"snapshot"}\n')
        process.stdin.flush()
        saved = _read_line(process)
        cases.append(
            {
                "origin": origin,
                "statuses": statuses,
                "legacy": legacy,
                "client_count": sum(
                    c["install_id"] == install_id for c in saved["clients"]
                ),
            }
        )
    _validate_ownership_cases(cases)
    return cases


def install_telemetry_guard() -> None:
    """Observe before network I/O and fail the final receipt even if swallowed."""
    global _GUARD_INSTALLED
    os.environ["VODFORGE_DISABLE_TELEMETRY"] = "1"
    if _GUARD_INSTALLED:
        return

    def guard(event, args):
        host = None
        if event == "urllib.Request":
            host = urlsplit(args[0]).hostname
        elif event == "socket.getaddrinfo":
            host = args[0]
        if isinstance(host, str) and any(
            host.lower() == domain or host.lower().endswith("." + domain)
            for domain in ("getvodforge.com", "heycatch.ai")
        ):
            _BLOCKED_ATTEMPTS.append("production_telemetry_attempt")
            raise RuntimeError("Production telemetry forbidden in engineering harness")

    sys.addaudithook(guard)
    _GUARD_INSTALLED = True


def receipt(identifier, passed, evidence, artifacts=()):
    return (
        {
            "id": identifier,
            "evidence_tier": "unit_static",
            "category": "reliability",
            "status": "passed" if passed else "failed",
            "duration_seconds": 0,
            "metrics": {},
            "evidence": evidence,
            "artifacts": list(map(str, artifacts)),
            "error": None,
        },
        [],
    )


def isolation_receipt():
    return receipt(
        "unit_static.telemetry_isolation",
        not _BLOCKED_ATTEMPTS,
        [
            f"Blocked production attempts: {len(_BLOCKED_ATTEMPTS)}",
            "Harness process guard covers urllib requests and hostname resolution; Worker outbound fetch is disabled.",
        ],
    )


def backend_suite(repo_root: Path, case_dir: Path):
    site = Path(
        os.environ.get("VODFORGE_SITE_REPO", str(repo_root.parent / "vodforge-site"))
    ).resolve()
    case_dir.mkdir(parents=True, exist_ok=True)
    _, before = machine_snapshot(site)
    result = run_command(["npm", "test"], cwd=site, timeout=180)
    _, after = machine_snapshot(site)
    passed = (
        result.returncode == 0 and before == after and not before["status_porcelain"]
    )
    artifact = case_dir / "backend-receipt.json"
    artifact.write_text(
        json.dumps(
            {
                "repository": before,
                "unchanged": before == after,
                "returncode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
            },
            indent=2,
        )
    )
    return receipt(
        "unit_static.telemetry_backend_suite",
        passed,
        [
            f"Site commit: {before.get('commit')}; dirty: {bool(before.get('status_porcelain'))}",
            f"Site npm test exit: {result.returncode}; source unchanged: {before == after}",
        ],
        [artifact],
    )


def _read_line(process):
    # Windows cannot select() anonymous pipes. Bound the read on every platform.
    result = queue.Queue()
    threading.Thread(
        target=lambda: result.put(process.stdout.readline()), daemon=True
    ).start()
    try:
        line = result.get(timeout=30)
    except queue.Empty as exc:
        raise TimeoutError("Local telemetry Worker response timed out") from exc
    if not line:
        raise RuntimeError("Local telemetry Worker exited")
    return json.loads(line)


def integration_probe(repo_root: Path, case_dir: Path, runner, server):
    from yt_downloader import analytics_consent, product_telemetry
    from yt_downloader import telemetry_credentials as transport
    from yt_downloader.cloud_funnel import (
        load_or_create_installation_state,
        mark_attribution_claim_confirmed,
    )
    from yt_downloader.failure_diagnostics import FailureDiagnostic

    site = Path(
        os.environ.get("VODFORGE_SITE_REPO", str(repo_root.parent / "vodforge-site"))
    ).resolve()
    case_dir.mkdir(parents=True, exist_ok=True)
    failures = []
    _, source_before = machine_snapshot(site)
    if source_before["status_porcelain"]:
        raise AssertionError("Telemetry integration requires a clean site commit")
    for suffix in ("404", "500"):
        result = runner.run_job(
            case_id="telemetry-failure-" + suffix,
            url=server.url("/status/" + suffix),
            output_type="MP4",
        )
        detail = result.get("failure_diagnostic")
        if not result.get("error") or not detail:
            raise AssertionError(
                "Real worker failure did not provide machine diagnostics"
            )
        failures.append(FailureDiagnostic(**detail))
    script = Path(__file__).with_name("telemetry_worker.mjs")
    with (case_dir / "worker.stderr.txt").open("w") as errors:
        process = subprocess.Popen(
            ["node", str(script), str(site)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=errors,
            text=True,
            cwd=case_dir,
        )
        try:
            url = _read_line(process)["url"]
            if urlsplit(url).hostname != "127.0.0.1":
                raise AssertionError("Worker is not loopback-only")
            # Test-scoped permission override ONLY after endpoint is pinned to
            # loopback. The production transport and HTTP serialization are real.
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
                consent = analytics_consent.AnalyticsConsentOwner(case_dir / "client")
                owner = transport.TelemetryCredentialOwner(case_dir / "client")
                assert not owner.first_launch("0.1.7", "macos"), (
                    "Unknown permission leaked"
                )
                consent.choose(False)
                assert not owner.first_launch("0.1.7", "macos"), "Refusal leaked"
                consent.choose(True)
                assert owner.first_launch("0.1.7", "macos"), "Initial launch rejected"
                assert owner.first_launch("0.1.8", "macos"), "Update launch rejected"
                assert owner.observe_session("0.1.8", "macos"), (
                    "Session launch rejected"
                )
                process.stdin.write('{"op":"snapshot"}\n')
                process.stdin.flush()
                before_reopen = _read_line(process)
                time.sleep(1.1)  # D1 CURRENT_TIMESTAMP has second precision.
                reopened = transport.TelemetryCredentialOwner(case_dir / "client")
                assert reopened.observe_session("0.1.8", "macos")
                process.stdin.write('{"op":"snapshot"}\n')
                process.stdin.flush()
                after_reopen = _read_line(process)
                assert (
                    after_reopen["installations"][0]["last_seen_at"]
                    > before_reopen["installations"][0]["last_seen_at"]
                )
                assert (
                    after_reopen["installations"][0]["first_launched_at"]
                    == before_reopen["installations"][0]["first_launched_at"]
                )
                assert len(after_reopen["clients"]) == 1
                assert owner.cloud_event(
                    "cloud_seen",
                    after_reopen["installations"][0]["install_id"],
                    "0.1.8",
                    "macos",
                )
                assert owner.cloud_event(
                    "cloud_click",
                    after_reopen["installations"][0]["install_id"],
                    "0.1.8",
                    "macos",
                )
                state_path = case_dir / "client" / "installation.json"
                state = load_or_create_installation_state(state_path)
                mark_attribution_claim_confirmed(state_path, state.install_id)
                delivered = []

                def deliver(event):
                    payload = event.public_payload()
                    delivered.append(payload)
                    return owner.event(payload)

                usage = product_telemetry.ProductTelemetryOwner(
                    state_path=case_dir / "client" / "outbox.json",
                    installation_state_path=state_path,
                    app_version="0.1.8",
                    platform_name="darwin",
                    d1_recorder=deliver,
                    heycatch_recorder=lambda *_args, **_kwargs: True,
                )
                # Exercise the real outbox and serializer for every supported
                # product event, not only two hand-selected failure payloads.
                dimensions = [
                    ("app_opened", {}),
                    *[
                        (name, {"run_kind": "youtube", "output_type": output})
                        for output in ("mp4", "mp3", None)
                        for name in ("run_started", "run_completed", "run_stopped")
                    ],
                    ("playback_started", {"output_type": "mp4"}),
                    ("playback_started", {"output_type": "mp3"}),
                    (
                        "local_conversion_completed",
                        {"run_kind": "local_audio_video", "output_type": "mp4"},
                    ),
                ]
                for index, (name, fields) in enumerate(dimensions):
                    assert usage.record(name, dedupe_key=f"metric-{index}", **fields)
                    assert usage.record(name, dedupe_key=f"metric-{index}", **fields)
                assert usage.shutdown(10)
                for diagnostic in failures:
                    assert usage.record(
                        "run_failed",
                        run_kind="youtube",
                        output_type="mp4",
                        failure_reason=diagnostic.reason,
                        failure_detail=diagnostic.payload(),
                    )
                    assert usage.shutdown(10), "Usage outbox did not drain"
                assert len(delivered) == len(dimensions) + 2, (
                    f"Missing or duplicated emitted metrics: {len(delivered)}"
                )
                for payload in delivered:
                    assert owner.event(payload)
                process.stdin.write('{"op":"snapshot"}\n')
                process.stdin.flush()
                snapshot = _read_line(process)
                _, source_after = machine_snapshot(site)
                assert source_before == source_after
                snapshot["site_commit"] = source_before["commit"]
                artifact = case_dir / "local-d1-receipt.json"
                artifact.write_text(json.dumps(snapshot, indent=2))
                assert len(snapshot["installations"]) == 1
                assert snapshot["installations"][0]["first_seen_at"]
                assert snapshot["installations"][0]["cloud_clicked_at"]
                expected_names = {name for name, _fields in dimensions} | {
                    "run_failed",
                    "client_update",
                }
                assert {
                    event["event_name"] for event in snapshot["events"]
                } == expected_names
                assert len(snapshot["events"]) == len(delivered) + 1
                for payload in delivered:
                    stored_event = next(
                        event
                        for event in snapshot["events"]
                        if event["event_id"] == payload["event_id"]
                    )
                    for field in (
                        "event_name",
                        "run_kind",
                        "output_type",
                    ):
                        assert stored_event[field] == payload.get(field), field
                    actual_time = datetime.fromisoformat(
                        stored_event["occurred_at"].replace("Z", "+00:00")
                    )
                    emitted_time = datetime.fromisoformat(
                        payload["occurred_at"].replace("Z", "+00:00")
                    )
                    assert abs((actual_time - emitted_time).total_seconds()) < 0.001
                consent.choose(False)
                denied_owner = transport.TelemetryCredentialOwner(case_dir / "client")
                assert not denied_owner.observe_session("0.1.8", "macos")
                assert not denied_owner.event(delivered[0])
                process.stdin.write('{"op":"snapshot"}\n')
                process.stdin.flush()
                assert _read_line(process) == {
                    key: value
                    for key, value in snapshot.items()
                    if key != "site_commit"
                }
                assert snapshot["installations"][0]["current_app_version"] == "0.1.8"
                updates = [
                    e for e in snapshot["events"] if e["event_name"] == "client_update"
                ]
                assert (
                    len(updates) == 1
                    and updates[0]["from_version"] == "0.1.7"
                    and updates[0]["to_version"] == "0.1.8"
                ), f"Unexpected update records: {updates}"
                stored = [
                    e for e in snapshot["events"] if e["event_name"] == "run_failed"
                ]
                assert len(stored) == 2, f"Unexpected failure records: {stored}"
                assert all(
                    "http_status" in json.loads(e["failure_detail"]) for e in stored
                )
                # HTTP 500 is deliberately not guessed into a narrower reason;
                # its real status/type/stage must survive even with 'unknown'.
                assert sorted(
                    (
                        e["failure_reason"],
                        json.loads(e["failure_detail"])["http_status"],
                    )
                    for e in stored
                ) == [("source_unavailable", 404), ("unknown", 500)]
                assert all(
                    json.loads(e["failure_detail"])["error_type"] == "HTTPError"
                    and json.loads(e["failure_detail"])["stage"] == "preparation"
                    for e in stored
                )
                encoded = json.dumps(stored)
                assert (
                    str(case_dir) not in encoded
                    and "http://" not in encoded
                    and "127.0.0.1" not in encoded
                )
                snapshot["ownership_matrix"] = _ownership_probe(url, process)
                artifact.write_text(json.dumps(snapshot, indent=2))
        except Exception:
            import traceback

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
    return receipt(
        "unit_static.telemetry_local_contract",
        True,
        [
            "Real Python HTTP → real Worker owner → local D1 migrations.",
            "One installation, one observed update, exact failure retries deduplicated.",
            "Real 404/500 worker failures stored only bounded machine facts.",
            "Six real installation entry points: retry, second actor, durable credential count, legacy write exclusion.",
        ],
        [artifact],
    )
