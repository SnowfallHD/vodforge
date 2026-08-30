from __future__ import annotations

import argparse
import json
import os
import plistlib
import signal
import subprocess
import sys
import time
from datetime import datetime
from itertools import pairwise
from pathlib import Path
from typing import Any

from .fault_server import FixtureHTTPServer
from .fixtures import generate_fixtures
from .metrics import ResourceSampler
from .util import json_dump, run_command, sha256_file, utc_now

EXPECTED_BUNDLE_IDENTIFIER = "com.snowfallhd.vodforge"
EXPECTED_TEAM_IDENTIFIER = "76G5W4954G"

SMOKE_UI_EVENT_ORDER = (
    "app_visible",
    "url_entered",
    "settings_observed",
    "forge_started",
    "progress_observed",
    "completion_observed",
    "library_observed",
    "shutdown_requested",
    "restart_requested",
    "restart_observed",
)

DEEP_UI_EVENT_ORDER = (
    *SMOKE_UI_EVENT_ORDER[:7],
    "slow_run_started",
    "second_run_queued",
    "cancellation_requested",
    "cancellation_observed",
    "queued_run_started",
    "queued_run_completion_observed",
    *SMOKE_UI_EVENT_ORDER[7:],
)

SMOKE_REQUIRED_UI_EVENTS = set(SMOKE_UI_EVENT_ORDER)
DEEP_REQUIRED_UI_EVENTS = set(DEEP_UI_EVENT_ORDER)

# Relaunch is a harness control transition rather than a visible application state.
# Every actual UI observation/action still requires its own screenshot.
SCREENSHOT_OPTIONAL_EVENTS = {"restart_requested"}


def _required_ui_events(profile: str) -> set[str]:
    return DEEP_REQUIRED_UI_EVENTS if profile == "deep" else SMOKE_REQUIRED_UI_EVENTS


def _required_ui_event_order(profile: str) -> tuple[str, ...]:
    return DEEP_UI_EVENT_ORDER if profile == "deep" else SMOKE_UI_EVENT_ORDER


def _codesign_value(output: str, key: str) -> str | None:
    prefix = f"{key}="
    for line in output.splitlines():
        if line.startswith(prefix):
            return line[len(prefix) :].strip() or None
    return None


def _artifact_receipt(artifact: Path, repo_root: Path) -> dict[str, Any]:
    artifact = artifact.resolve()
    executable = artifact / "Contents" / "MacOS" / "VODForge"
    ffprobe = artifact / "Contents" / "Frameworks" / "ffprobe"
    plist_path = artifact / "Contents" / "Info.plist"
    if (
        not artifact.is_dir()
        or not executable.is_file()
        or not ffprobe.is_file()
        or not plist_path.is_file()
    ):
        raise RuntimeError(f"packaged VODForge artifact is incomplete: {artifact}")
    with plist_path.open("rb") as handle:
        plist = plistlib.load(handle)
    checks = {
        "codesign_strict": run_command(
            [
                "codesign",
                "--verify",
                "--deep",
                "--strict",
                "--verbose=2",
                str(artifact),
            ],
            cwd=repo_root,
            timeout=60,
        ).as_dict(),
        "gatekeeper": run_command(
            ["spctl", "-a", "-t", "exec", "-vv", str(artifact)],
            cwd=repo_root,
            timeout=60,
        ).as_dict(),
        "staple": run_command(
            ["xcrun", "stapler", "validate", str(artifact)], cwd=repo_root, timeout=60
        ).as_dict(),
    }
    codesign_identity = run_command(
        ["codesign", "-dv", "--verbose=4", str(artifact)], cwd=repo_root, timeout=60
    )
    identity_output = f"{codesign_identity.stdout}\n{codesign_identity.stderr}"
    signed_identifier = _codesign_value(identity_output, "Identifier")
    team_identifier = _codesign_value(identity_output, "TeamIdentifier")
    ffprobe_version = run_command([str(ffprobe), "-version"], cwd=repo_root, timeout=30)
    identity_verified = (
        plist.get("CFBundleIdentifier") == EXPECTED_BUNDLE_IDENTIFIER
        and signed_identifier == EXPECTED_BUNDLE_IDENTIFIER
        and team_identifier == EXPECTED_TEAM_IDENTIFIER
    )
    return {
        "artifact": str(artifact),
        "executable": str(executable),
        "executable_sha256": sha256_file(executable),
        "bundle_identifier": plist.get("CFBundleIdentifier"),
        "bundle_version": plist.get("CFBundleShortVersionString"),
        "architecture": run_command(
            ["file", str(executable)], cwd=repo_root, timeout=30
        ).stdout.strip(),
        "signed_identifier": signed_identifier,
        "team_identifier": team_identifier,
        "expected_bundle_identifier": EXPECTED_BUNDLE_IDENTIFIER,
        "expected_team_identifier": EXPECTED_TEAM_IDENTIFIER,
        "identity_verified": identity_verified,
        "codesign_identity": codesign_identity.as_dict(),
        "bundled_ffprobe": {
            "path": str(ffprobe),
            "sha256": sha256_file(ffprobe),
            "version": ffprobe_version.as_dict(),
            "runnable": ffprobe_version.returncode == 0,
        },
        "checks": checks,
        "verified": (
            identity_verified
            and ffprobe_version.returncode == 0
            and all(check.get("returncode") == 0 for check in checks.values())
        ),
    }


def _probe_media(
    paths: list[Path], artifact_receipt: dict[str, Any], *, repo_root: Path
) -> list[dict[str, Any]]:
    ffprobe = Path(str(artifact_receipt["bundled_ffprobe"]["path"])).resolve()
    output: list[dict[str, Any]] = []
    for path in paths:
        entry: dict[str, Any] = {
            "path": str(path),
            "size_bytes": path.stat().st_size,
            "sha256": sha256_file(path),
            "ffprobe_executable": str(ffprobe),
            "ffprobe_sha256": artifact_receipt["bundled_ffprobe"]["sha256"],
        }
        result = run_command(
            [
                str(ffprobe),
                "-v",
                "error",
                "-print_format",
                "json",
                "-show_entries",
                "format=format_name,size,duration:format_tags:stream=codec_type,codec_name,width,height,avg_frame_rate,r_frame_rate,bit_rate,pix_fmt,profile,sample_rate,channels:stream_disposition",
                str(path),
            ],
            cwd=repo_root,
            timeout=30,
        )
        entry["ffprobe_command"] = result.as_dict()
        try:
            probe = json.loads(result.stdout) if result.returncode == 0 else None
            if (
                not isinstance(probe, dict)
                or not isinstance(probe.get("format"), dict)
                or not probe.get("streams")
            ):
                raise ValueError("ffprobe returned no format/stream evidence")
            entry["ffprobe"] = probe
            entry["readable"] = True
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            entry["readable"] = False
            entry["error"] = f"{type(exc).__name__}: {exc}"
        output.append(entry)
    return output


def _parse_observed_at(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _validate_driver_trace(
    events_payload: dict[str, Any],
    *,
    profile: str,
    session_dir: Path,
) -> dict[str, Any]:
    required_order = _required_ui_event_order(profile)
    required = set(required_order)
    raw_events = events_payload.get("events")
    events = raw_events if isinstance(raw_events, list) else []
    named_events = [
        event
        for event in events
        if isinstance(event, dict) and isinstance(event.get("event"), str)
    ]
    event_names = [str(event["event"]) for event in named_events]
    counts = {name: event_names.count(name) for name in required}
    duplicates = sorted(name for name, count in counts.items() if count > 1)
    missing_events = [name for name in required_order if counts.get(name, 0) == 0]
    observed_required_order = [name for name in event_names if name in required]
    expected_present_order = [
        name for name in required_order if name in observed_required_order
    ]
    order_valid = observed_required_order == expected_present_order and not duplicates

    timestamps: list[datetime] = []
    invalid_timestamp_events: list[str] = []
    for event in named_events:
        parsed = _parse_observed_at(event.get("observed_at"))
        if parsed is None:
            invalid_timestamp_events.append(str(event["event"]))
        else:
            timestamps.append(parsed)
    timestamps_monotonic = all(
        current >= previous for previous, current in pairwise(timestamps)
    )

    ui_root = (session_dir / "ui").resolve()
    raw_declared_screenshots = events_payload.get("screenshots")
    screenshot_items = (
        raw_declared_screenshots if isinstance(raw_declared_screenshots, list) else []
    )
    declared_screenshots = {
        str(Path(item).resolve())
        for item in screenshot_items
        if isinstance(item, str) and item
    }
    invalid_screenshot_events: list[str] = []
    screenshot_receipts: list[dict[str, Any]] = []
    for event in named_events:
        name = str(event["event"])
        if name not in required or name in SCREENSHOT_OPTIONAL_EVENTS:
            continue
        raw_path = event.get("screenshot")
        valid = False
        reason = None
        screenshot_path: Path | None = None
        if not isinstance(raw_path, str) or not raw_path:
            reason = "missing screenshot path"
        else:
            screenshot_path = Path(raw_path).resolve()
            try:
                screenshot_path.relative_to(ui_root)
            except ValueError:
                reason = "screenshot is outside the session UI directory"
            else:
                if str(screenshot_path) not in declared_screenshots:
                    reason = "screenshot is not declared in the trace"
                elif screenshot_path.suffix.lower() not in {".jpeg", ".jpg", ".png"}:
                    reason = "unsupported screenshot extension"
                elif (
                    not screenshot_path.is_file() or screenshot_path.stat().st_size <= 0
                ):
                    reason = "screenshot is missing or empty"
                else:
                    valid = True
        if not valid:
            invalid_screenshot_events.append(name)
        screenshot_receipts.append(
            {
                "event": name,
                "path": str(screenshot_path) if screenshot_path else None,
                "valid": valid,
                "reason": reason,
                "sha256": sha256_file(screenshot_path)
                if valid and screenshot_path
                else None,
            }
        )

    structural_valid = (
        isinstance(raw_events, list)
        and order_valid
        and not invalid_timestamp_events
        and timestamps_monotonic
        and not invalid_screenshot_events
    )
    return {
        "valid": structural_valid and not missing_events,
        "structural_valid": structural_valid,
        "event_names": event_names,
        "required_order": list(required_order),
        "observed_required_order": observed_required_order,
        "missing_events": missing_events,
        "duplicate_events": duplicates,
        "order_valid": order_valid,
        "invalid_timestamp_events": invalid_timestamp_events,
        "timestamps_monotonic": timestamps_monotonic,
        "invalid_screenshot_events": invalid_screenshot_events,
        "screenshot_receipts": screenshot_receipts,
    }


def _persisted_state_snapshot(home: Path) -> dict[str, Any]:
    downloads = home / "Downloads"
    history_path = (
        home / "Library" / "Application Support" / "VODForge" / "download-history.json"
    )
    media = []
    for path in sorted((*downloads.rglob("*.mp4"), *downloads.rglob("*.mp3"))):
        media.append(
            {
                "path": str(path.resolve()),
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    return {
        "captured_at": utc_now(),
        "history_path": str(history_path),
        "history_sha256": sha256_file(history_path) if history_path.is_file() else None,
        "media": media,
    }


def _history_persistence_receipt(
    home: Path,
    media_probes: list[dict[str, Any]],
    launches: list[dict[str, Any]],
    activity: str,
    restart_baseline: dict[str, Any] | None,
    *,
    expected_output_type: str,
) -> dict[str, Any]:
    history_path = (
        home / "Library" / "Application Support" / "VODForge" / "download-history.json"
    )
    history_error = None
    payload: dict[str, Any] = {}
    if history_path.is_file():
        try:
            candidate = json.loads(history_path.read_text(encoding="utf-8"))
            if not isinstance(candidate, dict):
                raise TypeError("history root is not an object")
            payload = candidate
        except (OSError, json.JSONDecodeError, TypeError) as exc:
            history_error = f"{type(exc).__name__}: {exc}"
    else:
        history_error = "history file is missing"
    items = payload.get("items") if isinstance(payload.get("items"), list) else []
    final_by_path = {
        str(Path(str(item["path"])).resolve()): item for item in media_probes
    }
    history_output_paths: list[str] = []
    matching_items: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        summary = item.get("vodforge_encoding_summary")
        output = summary.get("output") if isinstance(summary, dict) else None
        raw_path = output.get("Output file path") if isinstance(output, dict) else None
        if isinstance(raw_path, str) and raw_path:
            resolved = str(Path(raw_path).resolve())
            history_output_paths.append(resolved)
            if resolved in final_by_path:
                matching_items.append(item)
    baseline_media = {
        str(item.get("path")): item
        for item in (restart_baseline or {}).get("media", [])
        if isinstance(item, dict) and item.get("path")
    }
    media_stable = (
        bool(baseline_media)
        and set(baseline_media) == set(final_by_path)
        and all(
            baseline_media[path].get("sha256") == final_by_path[path].get("sha256")
            for path in baseline_media
        )
    )
    history_hash_stable = bool(
        restart_baseline and restart_baseline.get("history_sha256")
    ) and (
        restart_baseline.get("history_sha256")
        == (sha256_file(history_path) if history_path.is_file() else None)
    )
    loaded_after_restart = f"Loaded download history: {history_path}" in activity
    restart_launches = [
        item
        for item in launches[1:]
        if item.get("reason") == "driver_requested_restart"
    ]
    output_type_matches = bool(matching_items) and all(
        str(item.get("vodforge_output_type") or "").upper()
        == expected_output_type.upper()
        for item in matching_items
    )
    expected_suffix = ".mp4" if expected_output_type.upper() == "MP4" else ".mp3"
    media_extensions_match = bool(final_by_path) and all(
        Path(path).suffix.lower() == expected_suffix for path in final_by_path
    )
    verified = (
        len(launches) >= 2
        and bool(restart_launches)
        and history_error is None
        and bool(matching_items)
        and output_type_matches
        and media_extensions_match
        and media_stable
        and history_hash_stable
        and loaded_after_restart
    )
    return {
        "verified": verified,
        "history_path": str(history_path),
        "history_error": history_error,
        "history_item_count": len(items),
        "matching_history_item_count": len(matching_items),
        "history_output_paths": history_output_paths,
        "expected_output_type": expected_output_type,
        "output_type_matches": output_type_matches,
        "media_extensions_match": media_extensions_match,
        "launch_count_at_least_two": len(launches) >= 2,
        "driver_requested_restart_launch_count": len(restart_launches),
        "loaded_after_restart": loaded_after_restart,
        "media_hashes_stable_across_restart": media_stable,
        "history_hash_stable_across_restart": history_hash_stable,
        "pre_restart_snapshot": restart_baseline,
    }


def _finding(evidence: list[str], *, evidence_gap_only: bool) -> dict[str, Any]:
    if evidence_gap_only:
        return {
            "id": "E2E-PACKAGED-EVIDENCE-GAP-001",
            "title": "Packaged VODForge journey lacks complete automatable UI evidence",
            "classification": "maintainability risk",
            "severity": "medium",
            "area": "packaged UI accessibility and end-to-end testability",
            "reproduction": [
                "Run ./engineering-quality/run packaged-e2e --profile smoke --artifact dist/VODForge.app.",
                "Drive the listed journey through the visible packaged UI.",
                "Inspect the missing UI events and saved accessibility/screenshot receipts.",
            ],
            "evidence": evidence,
            "suggested_fix": "Expose stable semantic/accessibility identities and keyboard actions for the custom Tk navigation and run controls, then keep the screenshot-backed packaged journey as a release gate.",
            "scenario_id": "packaged_app_e2e.full_journey",
        }
    return {
        "id": "E2E-PACKAGED-JOURNEY-001",
        "title": "Packaged VODForge did not complete the required UI-to-committed-media journey",
        "classification": "reliability defect",
        "severity": "high",
        "area": "packaged VODForge application UI-to-media journey",
        "reproduction": [
            "Run ./engineering-quality/run packaged-e2e --artifact dist/VODForge.app.",
            "Drive the listed UI journey and write driver-events.json through the UI driver protocol.",
            "Inspect e2e-result.json and packaged diagnostics.",
        ],
        "evidence": evidence,
        "suggested_fix": "Repair the first missing artifact/UI/worker/output/cleanup receipt; do not substitute the headless layer for this full-app failure.",
        "scenario_id": "packaged_app_e2e.full_journey",
    }


def _launch(
    executable: Path,
    env: dict[str, str],
    stdout_path: Path,
    stderr_path: Path,
) -> tuple[subprocess.Popen[bytes], Any, Any]:
    stdout_handle = stdout_path.open("ab")
    stderr_handle = stderr_path.open("ab")
    process = subprocess.Popen(
        [str(executable)],
        env=env,
        cwd=executable.parents[3],
        stdin=subprocess.DEVNULL,
        stdout=stdout_handle,
        stderr=stderr_handle,
        start_new_session=True,
    )
    return process, stdout_handle, stderr_handle


def run_packaged_e2e_session(
    args: argparse.Namespace, *, repo_root: Path, harness_root: Path
) -> int:
    if sys.platform != "darwin":
        print(
            "[e2e] packaged macOS E2E requires macOS; no headless result is substituted",
            file=sys.stderr,
        )
        return 2
    artifact = (
        (repo_root / args.artifact).resolve()
        if not args.artifact.is_absolute()
        else args.artifact.resolve()
    )
    timestamp = (
        time.strftime("%Y%m%dT%H%M%S", time.gmtime())
        + f"{time.time_ns() % 1_000_000_000:09d}Z"
    )
    session_dir = (
        args.output_dir or (harness_root / "reports" / f"{timestamp}-packaged-e2e")
    ).resolve()
    session_dir.mkdir(parents=True, exist_ok=True)
    workspace = harness_root / ".runs" / f"{timestamp}-packaged-e2e"
    workspace.mkdir(parents=True, exist_ok=True)
    home = workspace / "home"
    tmp = workspace / "tmp"
    fixtures = workspace / "fixtures"
    for path in (home, tmp, fixtures, home / "Downloads", session_dir / "ui"):
        path.mkdir(parents=True, exist_ok=True)
    receipt = _artifact_receipt(artifact, repo_root)
    fixture_manifest = generate_fixtures(fixtures, deep=False)
    driver_events_path = session_dir / "driver-events.json"
    control_path = session_dir / "control.json"
    json_dump(driver_events_path, {"events": [], "screenshots": [], "notes": []})
    json_dump(control_path, {"action": "running"})
    env = os.environ.copy()
    env.update(
        {
            "HOME": str(home),
            "XDG_DATA_HOME": str(home / ".local" / "share"),
            "LOCALAPPDATA": str(home / "AppData" / "Local"),
            "TMPDIR": str(tmp),
            "VODFORGE_QUALITY_E2E": "1",
        }
    )
    started_at = utc_now()
    started = time.monotonic()
    sampler = ResourceSampler(workspace).start()
    launches: list[dict[str, Any]] = []
    restart_baseline: dict[str, Any] | None = None
    timed_out = False
    with FixtureHTTPServer(fixtures) as server:
        required_ui_events = _required_ui_events(args.profile)
        journey = [
            "Observe the packaged VODForge window and record app_visible.",
            "Paste input_url into the visible URL field and record url_entered.",
            "Open Settings, inspect/change a real setting, close it, and record settings_observed.",
            "Start Forge and record forge_started.",
            "Observe real progress/status from the worker and record progress_observed.",
            "Wait for a truthful completion state and record completion_observed.",
            "Open Library and observe the completed item, then record library_observed.",
            "Request normal app shutdown, set control action to relaunch, and record shutdown_requested plus restart_requested.",
            "Verify the same exact artifact restores history/output after restart and record restart_observed.",
            "Quit normally again and set control action to finish.",
        ]
        if args.profile == "deep":
            journey[7:7] = [
                "Start slow_input_url and record slow_run_started once transfer is active.",
                "Submit input_url while the slow run remains active; observe a real queued card and record second_run_queued.",
                "Cancel the active run through the visible UI and record cancellation_requested.",
                "Observe a clean stopped/cancelled state with no committed partial and record cancellation_observed.",
                "Observe the queued run advance into active work and record queued_run_started.",
                "Wait for the queued run to complete and record queued_run_completion_observed.",
            ]
        session = {
            "schema_version": "1.0.0",
            "e2e_profile": args.profile,
            "session_dir": str(session_dir),
            "artifact_receipt": receipt,
            "fixture_manifest": fixture_manifest,
            "input_url": server.url("/page/unicode"),
            "slow_input_url": server.url("/slow/page"),
            "expected_output_root": str(home / "Downloads"),
            "expected_output_type": "MP4",
            "driver_events_path": str(driver_events_path),
            "control_path": str(control_path),
            "required_ui_events": sorted(required_ui_events),
            "journey": journey,
        }
        json_dump(session_dir / "session.json", session)
        print(f"[e2e] session={session_dir / 'session.json'}", flush=True)
        print(f"[e2e] app=VODForge input_url={session['input_url']}", flush=True)
        print(f"[e2e] driver_events={driver_events_path}", flush=True)
        print(
            "[e2e] waiting for the UI driver; quit the app normally to finalize",
            flush=True,
        )
        executable = Path(receipt["executable"])
        process, stdout_handle, stderr_handle = _launch(
            executable,
            env,
            session_dir / "app.stdout.log",
            session_dir / "app.stderr.log",
        )
        launches.append({"pid": process.pid, "started_at": utc_now()})
        deadline = time.monotonic() + int(args.timeout)
        last_notice = 0.0
        while time.monotonic() < deadline:
            action = "running"
            try:
                action = str(
                    json.loads(control_path.read_text(encoding="utf-8")).get("action")
                    or "running"
                )
            except (AttributeError, json.JSONDecodeError, OSError, TypeError):
                pass
            returncode = process.poll()
            if returncode is not None:
                launches[-1].update(
                    {"completed_at": utc_now(), "returncode": returncode}
                )
                stdout_handle.close()
                stderr_handle.close()
                if action == "relaunch":
                    restart_baseline = _persisted_state_snapshot(home)
                    launches[-1]["pre_restart_state"] = restart_baseline
                    json_dump(control_path, {"action": "running"})
                    process, stdout_handle, stderr_handle = _launch(
                        executable,
                        env,
                        session_dir / "app.stdout.log",
                        session_dir / "app.stderr.log",
                    )
                    launches.append(
                        {
                            "pid": process.pid,
                            "started_at": utc_now(),
                            "reason": "driver_requested_restart",
                        }
                    )
                    continue
                break
            if time.monotonic() - last_notice >= 15:
                print(
                    f"[e2e] app pid={process.pid} elapsed={time.monotonic() - started:.0f}s action={action}",
                    flush=True,
                )
                last_notice = time.monotonic()
            time.sleep(0.25)
        else:
            timed_out = True
            try:
                os.killpg(process.pid, signal.SIGTERM)
                process.wait(timeout=10)
            except (OSError, subprocess.TimeoutExpired):
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except OSError:
                    pass
            launches[-1].update(
                {
                    "completed_at": utc_now(),
                    "returncode": process.poll(),
                    "timed_out": True,
                }
            )
            stdout_handle.close()
            stderr_handle.close()
        server_receipt = server.state.snapshot()
    resources = sampler.stop()
    try:
        loaded_events = json.loads(driver_events_path.read_text(encoding="utf-8"))
        events_payload = loaded_events if isinstance(loaded_events, dict) else {}
    except (json.JSONDecodeError, OSError) as exc:
        events_payload = {
            "events": [],
            "screenshots": [],
            "notes": [f"invalid driver trace: {type(exc).__name__}: {exc}"],
        }
    trace_validation = _validate_driver_trace(
        events_payload, profile=args.profile, session_dir=session_dir
    )
    required_ui_events = _required_ui_events(args.profile)
    missing_events = trace_validation["missing_events"]
    media_paths = sorted((home / "Downloads").rglob("*.mp4")) + sorted(
        (home / "Downloads").rglob("*.mp3")
    )
    media_probes = _probe_media(media_paths, receipt, repo_root=repo_root)
    diagnostic_path = home / "Library" / "Logs" / "VODForge" / "latest.log"
    activity_path = home / "Library" / "Logs" / "VODForge" / "activity.log"
    diagnostics = (
        diagnostic_path.read_text(encoding="utf-8", errors="replace")
        if diagnostic_path.is_file()
        else ""
    )
    activity = (
        activity_path.read_text(encoding="utf-8", errors="replace")
        if activity_path.is_file()
        else ""
    )
    history_persistence = _history_persistence_receipt(
        home,
        media_probes,
        launches,
        activity,
        restart_baseline,
        expected_output_type="MP4",
    )
    archived_diagnostics = []
    for path in sorted(session_dir.glob("diagnostics-*.log")):
        archived_diagnostics.append(path.read_text(encoding="utf-8", errors="replace"))
    all_diagnostics = "\n".join([*archived_diagnostics, diagnostics])
    stage_receipts = {
        "yt_dlp_or_download": (
            "download and yt-dlp post-processing elapsed_seconds=" in all_diagnostics
            or ("selected format " in activity and ": downloading" in activity)
        ),
        "ffmpeg_transcode": "transcode elapsed_seconds=" in all_diagnostics
        or "transcoded staged VODForge output" in activity,
        "ffprobe_validation": "artifact validation elapsed_seconds=" in all_diagnostics
        or ": validated " in activity,
        "atomic_commit": "atomic output commit elapsed_seconds=" in all_diagnostics
        or " before atomic commit" in activity,
    }
    staging_residue = [
        str(path)
        for path in (home / "Downloads").rglob("*")
        if ".vfstage" in path.parts
    ]
    clean_exit = bool(launches) and all(
        item.get("returncode") == 0 for item in launches
    )
    unexpected_process_exit = any(
        item.get("returncode") not in {0, None} and not item.get("timed_out")
        for item in launches
    )
    observed_event_names = set(trace_validation["event_names"])
    expected_jobs_attempted = 3 if args.profile == "deep" else 1
    jobs_completed = int(
        "completion_observed" in observed_event_names
        and bool(media_probes)
        and all(stage_receipts.values())
    )
    if args.profile == "deep":
        jobs_completed += int("queued_run_completion_observed" in observed_event_names)
    jobs_cancelled = int(
        args.profile == "deep" and "cancellation_observed" in observed_event_names
    )
    jobs_failed = max(0, expected_jobs_attempted - jobs_completed - jobs_cancelled)
    passed = (
        receipt["verified"]
        and not timed_out
        and trace_validation["valid"]
        and bool(media_probes)
        and all(item.get("readable") for item in media_probes)
        and all(stage_receipts.values())
        and not staging_residue
        and history_persistence["verified"]
        and clean_exit
        and resources.get("peak_zombie_processes", 0) == 0
    )
    evidence = [
        f"Artifact SHA-256: {receipt['executable_sha256']} version={receipt['bundle_version']} verified={receipt['verified']}",
        f"UI driver trace valid: {trace_validation['valid']}; ordered events: {trace_validation['observed_required_order']}; missing: {missing_events}; invalid screenshots: {trace_validation['invalid_screenshot_events']}",
        f"Packaged pipeline stage receipts: {stage_receipts}",
        f"Final media count: {len(media_probes)}; all independently readable using bundled ffprobe {receipt['bundled_ffprobe']['sha256']}: {bool(media_probes) and all(item.get('readable') for item in media_probes)}",
        f"Launch/exit receipts: {launches}; clean_exit={clean_exit}",
        f"Restart/history persistence: verified={history_persistence['verified']}; history_items={history_persistence['history_item_count']}; matching_items={history_persistence['matching_history_item_count']}; media_hashes_stable={history_persistence['media_hashes_stable_across_restart']}",
        f"Staging residue: {staging_residue}; peak zombies: {resources.get('peak_zombie_processes')}",
    ]
    scenario = {
        "id": "packaged_app_e2e.full_journey",
        "evidence_tier": "packaged_app_e2e",
        "category": "full application E2E",
        "status": "passed" if passed else "failed",
        "duration_seconds": round(time.monotonic() - started, 4),
        "metrics": {
            "jobs_attempted": expected_jobs_attempted,
            "jobs_completed": jobs_completed,
            "jobs_failed": jobs_failed,
            "jobs_cancelled": jobs_cancelled,
            "e2e_profile": args.profile,
            "required_ui_events": sorted(required_ui_events),
            "artifact_observed": True,
            "artifact_verified": receipt["verified"],
            "ui_interaction_observed": trace_validation["valid"],
            "missing_ui_events": missing_events,
            "driver_trace_structural_valid": trace_validation["structural_valid"],
            "driver_event_order_valid": trace_validation["order_valid"],
            "driver_event_timestamps_monotonic": trace_validation[
                "timestamps_monotonic"
            ],
            "invalid_screenshot_event_count": len(
                trace_validation["invalid_screenshot_events"]
            ),
            "final_output_probed": bool(media_probes),
            "media_output_count": len(media_probes),
            "pipeline_stage_receipts": stage_receipts,
            "launch_count": len(launches),
            "restart_history_persistence_verified": history_persistence["verified"],
            "clean_exit": clean_exit,
            "peak_rss_bytes": resources.get("peak_rss_bytes"),
            "peak_cpu_percent": resources.get("peak_cpu_percent"),
            "peak_zombie_processes": resources.get("peak_zombie_processes"),
            "staging_residue_count": len(staging_residue),
            "unexpected_process_exit": unexpected_process_exit,
            "harness_forced_termination": timed_out,
        },
        "evidence": evidence,
        "artifacts": [
            str(artifact),
            str(driver_events_path),
            str(diagnostic_path),
            str(activity_path),
            *[item["path"] for item in media_probes],
        ],
        "error": "session timed out" if timed_out else None,
    }
    evidence_gap_only = (
        receipt["verified"]
        and bool(media_probes)
        and all(item.get("readable") for item in media_probes)
        and all(stage_receipts.values())
        and not staging_residue
        and not unexpected_process_exit
        and clean_exit
        and history_persistence["verified"]
        and trace_validation["structural_valid"]
        and missing_events == ["library_observed"]
    )
    findings = (
        [] if passed else [_finding(evidence, evidence_gap_only=evidence_gap_only)]
    )
    payload = {
        "schema_version": "1.0.0",
        "started_at": started_at,
        "completed_at": utc_now(),
        "artifact_receipt": receipt,
        "fixture_server_receipt": server_receipt,
        "driver_trace": events_payload,
        "driver_trace_validation": trace_validation,
        "launches": launches,
        "media_probes": media_probes,
        "history_persistence": history_persistence,
        "diagnostics_path": str(diagnostic_path),
        "activity_path": str(activity_path),
        "resource_metrics": resources,
        "scenario": scenario,
        "findings": findings,
    }
    json_dump(session_dir / "e2e-result.json", payload)
    (session_dir / "summary.md").write_text(
        "# Packaged VODForge E2E\n\n"
        f"Status: **{scenario['status'].upper()}**\n\n"
        + "\n".join(f"- {item}" for item in evidence)
        + "\n",
        encoding="utf-8",
    )
    print(
        f"[e2e] result={session_dir / 'e2e-result.json'} status={scenario['status']}",
        flush=True,
    )
    return 0 if passed else 1
