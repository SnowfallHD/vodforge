"""Local-only cross-repository telemetry checks; no production authority."""

from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlsplit

from .util import machine_snapshot, run_command

_BLOCKED_ATTEMPTS: list[str] = []
_GUARD_INSTALLED = False


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
                    transport, "production_telemetry_allowed", return_value=True
                ),
                patch.object(transport, "__version__", "0.1.8"),
                patch.object(
                    product_telemetry, "production_telemetry_allowed", return_value=True
                ),
                patch.object(
                    analytics_consent, "production_telemetry_allowed", return_value=True
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
                assert owner.first_launch("0.1.8", "macos"), "Repeat launch rejected"
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
                for diagnostic in failures:
                    assert usage.record(
                        "run_failed",
                        run_kind="youtube",
                        output_type="mp4",
                        failure_reason=diagnostic.reason,
                        failure_detail=diagnostic.payload(),
                    )
                    assert usage.shutdown(10), "Usage outbox did not drain"
                assert len(delivered) == 2, (
                    f"Expected two emitted failures, got {len(delivered)}"
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
        ],
        [artifact],
    )
