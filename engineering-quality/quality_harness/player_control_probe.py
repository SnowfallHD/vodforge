"""Verify real player-control producers through isolated loopback HTTP and D1.

The injected provider failures exercise production backend/player/app/outbox
code. This is source/transport evidence, not physical-input or package evidence.
Dirty source is explicitly hash-bound; no commit, deployment or external service.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlsplit

from .playback_probe import CONTROL_CASES, CONTROL_EXPECTATIONS, run_case
from .telemetry_checks import _read_line, assert_feature_vocabulary


def source_hashes(repo: Path, site: Path) -> dict[str, str]:
    paths = [
        *sorted((repo / "yt_downloader").glob("*.py")),
        *sorted((repo / "engineering-quality/quality_harness").glob("*.py")),
        repo / "engineering-quality/quality_harness/telemetry_worker.mjs",
        repo / "tests/test_libvlc_backend.py",
        *sorted((site / "src/lib").glob("*.ts")),
        *sorted((site / "migrations").glob("*.sql")),
    ]
    return {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}


def run(site: Path, output: Path) -> dict:
    from yt_downloader import analytics_consent, product_telemetry
    from yt_downloader import telemetry_credentials as transport
    from yt_downloader.cloud_funnel import (
        load_or_create_installation_state,
        mark_attribution_claim_confirmed,
    )

    repo = Path(__file__).resolve().parents[2]
    output.mkdir(parents=True, exist_ok=False)
    before = source_hashes(repo, site)
    receipt = {"source_before": before, "passed": False}
    assert_feature_vocabulary(site)
    script = Path(__file__).with_name("telemetry_worker.mjs")
    with (output / "worker.stderr.txt").open("w") as errors:
        process = subprocess.Popen(
            ["node", str(script), str(site)],
            cwd=output,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=errors,
            text=True,
        )
        try:
            url = _read_line(process)["url"]
            assert urlsplit(url).hostname == "127.0.0.1"
            receipt["loopback_url"] = url
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
                client = output / "client"
                consent = analytics_consent.AnalyticsConsentOwner(client)
                credential = transport.TelemetryCredentialOwner(client)
                assert not credential.first_launch("0.1.8", "macos")
                consent.choose(False)
                assert not credential.first_launch("0.1.8", "macos")
                consent.choose(True)
                assert credential.first_launch("0.1.8", "macos")
                installation = client / "installation.json"
                state = load_or_create_installation_state(installation)
                mark_attribution_claim_confirmed(installation, state.install_id)
                delivered = []

                def deliver(event):
                    payload = event.public_payload()
                    accepted = credential.event(payload)
                    if accepted:
                        delivered.append(payload)
                    return accepted

                usage = product_telemetry.ProductTelemetryOwner(
                    state_path=client / "outbox.json",
                    installation_state_path=installation,
                    app_version="0.1.8",
                    platform_name="darwin",
                    d1_recorder=deliver,
                    heycatch_recorder=lambda *_args, **_kwargs: True,
                )
                results = []
                for case in CONTROL_CASES:
                    start = len(delivered)
                    result = run_case(output / "cases" / case, usage, case)
                    assert usage.shutdown(10)
                    events = delivered[start:]
                    receipt.update(
                        active_case=case, observed_events=events, producer_result=result
                    )
                    assert events[-1]["action"] == "closed"
                    failures = [
                        event for event in events if event["action"] == "control_failed"
                    ]
                    assert len(failures) == 1
                    failure = failures[0]
                    assert (
                        failure["dimensions"]["playback_control"]
                        == CONTROL_EXPECTATIONS[case][0]
                    )
                    assert (
                        failure["dimensions"]["playback_control_origin"]
                        == CONTROL_EXPECTATIONS[case][1]
                    )
                    assert failure["dimensions"]["playback_view"] == "embedded"
                    assert failure["failure_detail"]["os_error"] == 5
                    assert (
                        failure["failure_detail"]["source_scope"] == "first_party_frame"
                    )
                    assert (
                        len({event["dimensions"]["operation_id"] for event in events})
                        == 1
                    )
                    assert "PRIVATE" not in json.dumps(events)
                    result["event_ids"] = [event["event_id"] for event in events]
                    result["failure_event_id"] = failure["event_id"]
                    results.append(result)
                assert not (client / "outbox.json").exists()
                for event in delivered:
                    assert credential.event(event)
                assert process.stdin is not None
                process.stdin.write('{"op":"snapshot"}\n')
                process.stdin.flush()
                snapshot = _read_line(process)
                assert len(snapshot["events"]) == len(delivered)
                for event in delivered:
                    stored = next(
                        row
                        for row in snapshot["events"]
                        if row["event_id"] == event["event_id"]
                    )
                    assert stored["action"] == event["action"]
                    assert json.loads(stored["dimensions"]) == event["dimensions"]
                    if "failure_detail" in event:
                        assert (
                            json.loads(stored["failure_detail"])
                            == event["failure_detail"]
                        )
                consent.choose(False)
                assert not credential.event(delivered[0])
                process.stdin.write('{"op":"snapshot"}\n')
                process.stdin.flush()
                assert _read_line(process) == snapshot
                receipt.update(
                    results=results,
                    delivered=delivered,
                    stored=snapshot,
                    consent_checks_passed=True,
                    duplicate_delivery_idempotent=True,
                    physical_input=False,
                    packaged_acceptance=False,
                )
            receipt["source_after"] = source_hashes(repo, site)
            assert receipt["source_before"] == receipt["source_after"]
            receipt["passed"] = True
        finally:
            if process.poll() is None:
                assert process.stdin is not None
                process.stdin.write('{"op":"stop"}\n')
                process.stdin.flush()
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
            (output / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.site.resolve(), args.output.resolve())
    print(
        json.dumps(
            {
                "passed": result["passed"],
                "cases": len(result["results"]),
                "stored_events": len(result["stored"]["events"]),
            }
        )
    )


if __name__ == "__main__":
    main()
