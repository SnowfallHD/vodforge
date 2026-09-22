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

from .diagnostic_fixtures import diagnostic_context
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
        launch_status, launch_body = post(
            "launch", {"credential_id": credential_id, "app_version": "0.1.8"}
        )
        if launch_status != 200:
            raise AssertionError(
                f"Legitimate launch failed: {launch_status} {launch_body}"
            )
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


def assert_feature_vocabulary(site: Path) -> None:
    """Fail the maintained backend gate if either language's contract drifts."""
    import re

    from yt_downloader.product_telemetry import PRODUCT_EVENT_NAMES
    from yt_downloader.telemetry_features import (
        DIMENSION_CHOICES,
        DIMENSION_PATTERNS,
        DIMENSION_RANGES,
        FEATURE_ACTIONS,
        OPERATION_FEATURES,
    )

    source = (site / "src/lib/product-telemetry.ts").read_text()
    for name, expected in (
        ("FEATURE_ACTIONS", FEATURE_ACTIONS),
        ("DIMENSION_CHOICES", DIMENSION_CHOICES),
    ):
        match = re.search(
            r"export const " + name + r": Record<string, readonly string\[\]> = (.*?);",
            source,
        )
        if (
            match is None
            or {
                key: frozenset(values)
                for key, values in json.loads(match.group(1)).items()
            }
            != expected
        ):
            raise AssertionError("Desktop/backend vocabulary drift: " + name)
    for name, expected in (
        ("DIMENSION_PATTERNS", DIMENSION_PATTERNS),
        (
            "DIMENSION_RANGES",
            {key: list(value) for key, value in DIMENSION_RANGES.items()},
        ),
    ):
        match = re.search(r"export const " + name + r": [^=]+ = (.*?);", source)
        if match is None or json.loads(match.group(1)) != expected:
            raise AssertionError("Desktop/backend vocabulary drift: " + name)
    operation_match = re.search(r"const OPERATION_FEATURES = new Set\((.*?)\);", source)
    if operation_match is None or set(json.loads(operation_match.group(1))) != set(
        OPERATION_FEATURES
    ):
        raise AssertionError("Desktop/backend operation-correlation vocabulary drift")
    from ast import literal_eval

    from yt_downloader.failure_diagnostics import (
        ERROR_TYPES,
        FAILURE_CODES,
        FAILURE_REASONS,
        FAILURE_STAGES,
        FIRST_PARTY_MODULES,
    )

    for key, expected in (
        ("FAILURE_REASONS", FAILURE_REASONS),
        ("failure_code", FAILURE_CODES),
        ("source_module", FIRST_PARTY_MODULES),
        ("source_scope", {"first_party_frame"}),
        ("stage", FAILURE_STAGES),
        ("error_type", ERROR_TYPES),
    ):
        pattern = (
            r"const " + key + r" = new Set\(\[(.*?)\]\)"
            if key == "FAILURE_REASONS"
            else r"\b" + key + r": new Set\(\[(.*?)\]\)"
        )
        match = re.search(pattern, source, re.DOTALL)
        if match is None or set(literal_eval("[" + match.group(1) + "]")) != expected:
            raise AssertionError("Desktop/backend diagnostic vocabulary drift: " + key)
    names = re.search(r"PRODUCT_EVENT_NAMES = \[(.*?)\] as const", source, re.DOTALL)
    if (
        names is None
        or set(re.findall(r'"([^"\n]+)"', names.group(1))) != PRODUCT_EVENT_NAMES
    ):
        raise AssertionError("Desktop/backend product event vocabulary drift")


def backend_suite(repo_root: Path, case_dir: Path):
    site = Path(
        os.environ.get("VODFORGE_SITE_REPO", str(repo_root.parent / "vodforge-site"))
    ).resolve()
    case_dir.mkdir(parents=True, exist_ok=True)
    assert_feature_vocabulary(site)
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
                        for output in ("mp4", "mp3", "original")
                        for name in ("run_started", "run_completed", "run_stopped")
                    ],
                    ("playback_started", {"output_type": "mp4"}),
                    ("playback_started", {"output_type": "mp3"}),
                    (
                        "local_conversion_completed",
                        {"run_kind": "local_audio_video", "output_type": "mp4"},
                    ),
                ]
                from yt_downloader.telemetry_features import FEATURE_ACTIONS

                for name in (
                    product_telemetry.PRODUCT_EVENT_NAMES
                    - {name for name, _ in dimensions}
                    - {"run_failed", "feature_used"}
                ):
                    dimensions.append(
                        (
                            name,
                            {
                                "run_kind": "local_audio_video"
                                if name.startswith("local_conversion_")
                                else "youtube",
                                "output_type": "mp4",
                            },
                        )
                    )
                dimensions.extend(
                    ("feature_used", {"feature": feature, "action": action})
                    for feature, actions in FEATURE_ACTIONS.items()
                    for action in sorted(actions)
                )
                for index, (name, fields) in enumerate(dimensions):
                    if str(fields.get("feature", "")).endswith("_operation"):
                        fields["dimensions"] = {
                            **diagnostic_context(fields["feature"], fields["action"]),
                            "instrumentation": "diagnostics_v1",
                            "build_revision": "unknown",
                            "operation_id": str(uuid.uuid4()),
                            "operation_step": "1",
                        }
                    if (
                        name.startswith(("run_", "local_conversion_"))
                        or name == "media_exported"
                    ):
                        fields["attempt_key"] = f"attempt-{index}"
                    if name == "app_opened":
                        assert usage.record_app_opened()
                    else:
                        assert usage.record(
                            name, dedupe_key=f"metric-{index}", **fields
                        )
                    assert usage.shutdown(10), "First delivery did not finish"
                    assert not (case_dir / "client" / "outbox.json").exists()
                    if name == "app_opened":
                        assert usage.record_app_opened()
                    else:
                        assert usage.record(
                            name, dedupe_key=f"metric-{index}", **fields
                        )
                    assert usage.shutdown(10), "Repeated callback did not finish"
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
                # Reproduce failures through the actual app/archive producer;
                # hand-built vocabulary events alone cannot detect cause loss.
                from types import SimpleNamespace

                from yt_downloader.app import DownloaderApp
                from yt_downloader.history import pending_history_path

                producer_events = []
                for document, raw, cause in (
                    ("main", '{"PRIVATE":', "malformed_json"),
                    ("main", '{"schema_version":999}', "unsupported_schema"),
                    ("pending", '{"PRIVATE":', "malformed_json"),
                ):
                    fixture = case_dir / ("history-" + str(len(producer_events)))
                    fixture.mkdir()
                    history_path = fixture / "PRIVATE-history.json"
                    damaged = (
                        history_path
                        if document == "main"
                        else pending_history_path(history_path)
                    )
                    damaged.write_text(raw)
                    app = SimpleNamespace(
                        history_path=history_path,
                        product_telemetry=usage,
                        status_var=SimpleNamespace(set=lambda value: None),
                        _append_log=lambda value: None,
                    )
                    previous = len(delivered)
                    DownloaderApp._load_download_history(app)
                    assert usage.shutdown(10), "History producer did not drain"
                    observed = delivered[previous:]
                    assert [event["action"] for event in observed] == [
                        "started",
                        "failed",
                    ]
                    failure = observed[-1]
                    assert failure["dimensions"]["history_document"] == document
                    assert (
                        failure["failure_detail"]["failure_code"] == "history_" + cause
                    )
                    assert failure["failure_detail"]["source_module"] == "history"
                    assert failure["dimensions"]["operation_step"] == "2"
                    assert damaged.read_text() == raw and app._history_recovery_blocked
                    assert "PRIVATE" not in json.dumps(observed)
                    producer_events.extend(observed)
                (case_dir / "history-producer-events.json").write_text(
                    json.dumps(producer_events, indent=2)
                )
                # Exercise actual canonical metadata copy producers as well. The
                # clipboard is controlled; the consent/outbox/HTTP/D1 owners are real.
                copy_app = object.__new__(DownloaderApp)
                copy_app.product_telemetry = usage
                copy_app.metadata_items = [
                    {
                        "tags": ["PRIVATE source"],
                        "description": "PRIVATE description",
                        "vodforge_user_tags": ["PRIVATE personal"],
                        "vodforge_user_note": "PRIVATE note",
                        "thumbnail": "https://example.invalid/PRIVATE.jpg",
                        "webpage_url": "https://www.youtube.com/watch?v=abcdefghijk",
                    }
                ]
                copy_app.video_tree = SimpleNamespace(selection=lambda: ("0",))
                copy_app.status_var = SimpleNamespace(set=lambda value: None)
                copied = []
                copy_app.clipboard_clear = copied.clear
                copy_app.clipboard_append = copied.append
                copy_events = []
                for method, action, expected in (
                    ("_copy_tags", "source_tags_copied", "PRIVATE source"),
                    (
                        "_copy_description",
                        "source_description_copied",
                        "PRIVATE description",
                    ),
                    ("_copy_personal_tags", "personal_tags_copied", "PRIVATE personal"),
                    ("_copy_personal_note", "personal_note_copied", "PRIVATE note"),
                    (
                        "_copy_thumbnail_url",
                        "thumbnail_url_copied",
                        "https://example.invalid/PRIVATE.jpg",
                    ),
                    (
                        "_copy_youtube_url",
                        "youtube_url_copied",
                        "https://www.youtube.com/watch?v=abcdefghijk",
                    ),
                ):
                    previous = len(delivered)
                    assert getattr(copy_app, method)() and copied == [expected]
                    assert usage.shutdown(10), "Copy producer did not drain"
                    observed = delivered[previous:]
                    assert len(observed) == 1 and observed[0]["action"] == action
                    assert observed[0]["dimensions"] == {}
                    assert "PRIVATE" not in json.dumps(observed)
                    copy_events.extend(observed)
                (case_dir / "copy-producer-events.json").write_text(
                    json.dumps(copy_events, indent=2)
                )
                from yt_downloader.watch_ui import WatchView

                watch = object.__new__(WatchView)
                watch._hero_seen_key = ""
                watch._mode = "playlists"
                watch._on_usage = copy_app._archive_usage
                played = []
                watch._on_play = played.append
                previous = len(delivered)
                watch._observe_hero("PRIVATE source identity")
                watch._observe_hero("PRIVATE source identity")
                watch._play_hero(7)
                assert usage.shutdown(10), "Hero producer did not drain"
                hero_events = delivered[previous:]
                assert played == [7]
                assert [event["action"] for event in hero_events] == [
                    "hero_shown",
                    "hero_played",
                ]
                assert all(
                    event["dimensions"] == {"watch_mode": "playlists"}
                    for event in hero_events
                )
                assert "PRIVATE" not in json.dumps(hero_events)
                (case_dir / "hero-producer-events.json").write_text(
                    json.dumps(hero_events, indent=2)
                )
                from yt_downloader.media_player_ui import MediaPlayerWindow

                player = object.__new__(MediaPlayerWindow)
                player._details_visible = False
                player._apply_details_visibility = lambda: None
                player._on_feature = lambda action, **fields: copy_app._record_feature(
                    "player", action, **fields
                )
                selected_panels = []
                player._info_notebook = SimpleNamespace(select=selected_panels.append)
                previous = len(delivered)
                targets = ("chapters", "info", "source", "output", "notes", "moments")
                player._detail_targets = {
                    f"PRIVATE owned panel {i}": target
                    for i, target in enumerate(targets)
                }
                for panel in player._detail_targets:
                    player._select_information_panel(panel)
                    player._select_information_panel(panel)
                player._select_information_panel(
                    "PRIVATE unregistered source path title note"
                )
                player._toggle_details()
                assert usage.shutdown(10), "Player disclosure producers did not drain"
                player_events = delivered[previous:]
                assert selected_panels == [
                    panel for panel in player._detail_targets for _ in range(2)
                ]
                assert [event["action"] for event in player_events] == [
                    "details_opened",
                    *(["detail_viewed"] * 6),
                    "details_closed",
                ]
                assert [
                    event["dimensions"]["detail_target"]
                    for event in player_events
                    if event["action"] == "detail_viewed"
                ] == list(targets)
                assert all(event["feature"] == "player" for event in player_events)
                assert "PRIVATE" not in json.dumps(player_events)
                (case_dir / "player-disclosure-producer-events.json").write_text(
                    json.dumps(player_events, indent=2)
                )
                # Controlled providers exercise real backend, player, app,
                # consent/outbox and HTTP Worker/D1 producers. This is diagnostic
                # provenance evidence, not a native or audible-output test.
                from quality_harness.playback_probe import CASES, run_case

                control_events = []
                control_results = []
                for case in CASES:
                    previous = len(delivered)
                    result = run_case(case_dir / "playback" / case, usage, case)
                    assert usage.shutdown(10), "Playback producer did not drain"
                    observed = delivered[previous:]
                    assert observed and observed[-1]["action"] == "closed"
                    assert "PRIVATE" not in json.dumps(observed)
                    result["event_ids"] = [event["event_id"] for event in observed]
                    result["outcomes"] = [
                        event["dimensions"]["volume_outcome"]
                        for event in observed
                        if event["action"].startswith("volume_")
                    ]
                    control_results.append(result)
                    control_events.extend(observed)
                results = {value["case"]: value for value in control_results}
                assert results["immediate_mute"]["outcomes"] == ["applied"]
                assert results["delayed_mute"]["outcomes"] == ["pending", "applied"]
                assert results["pending_at_close"]["outcomes"] == [
                    "pending",
                    "pending_at_close",
                ]
                assert results["setter_exception"]["outcomes"] == ["failed"]
                assert results["command_flood"]["outcomes"][-1] == "pending_at_close"
                assert len(results["command_flood"]["outcomes"]) == 33
                (case_dir / "playback-control-producer-events.json").write_text(
                    json.dumps(control_events, indent=2)
                )
                (case_dir / "playback-control-results.json").write_text(
                    json.dumps(control_results, indent=2)
                )
                assert len(delivered) == len(dimensions) + 2 + len(
                    producer_events
                ) + len(copy_events) + len(hero_events) + len(player_events) + len(
                    control_events
                ), f"Missing or duplicated emitted metrics: {len(delivered)}"
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
                        "attempt_id",
                        "retry_of",
                        "feature",
                        "action",
                        "schema_version",
                    ):
                        assert stored_event[field] == payload.get(field), field
                    assert (
                        json.loads(stored_event["dimensions"]) == payload["dimensions"]
                    )
                    if "failure_detail" in payload:
                        assert (
                            json.loads(stored_event["failure_detail"])
                            == payload["failure_detail"]
                        )
                        assert (
                            stored_event["failure_reason"] == payload["failure_reason"]
                        )
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
                    and json.loads(e["failure_detail"])["stage"] == "analysis"
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
            "Actual app history failures preserve main/pending, parse/schema cause, source frame, revision and ordered operation steps in D1.",
            "Six actual canonical Library copy producers store only bounded action names; source/personal content is absent.",
            "Actual Watch hero and player disclosure producers store bounded actions without media titles, paths, notes or panel identities.",
            "Controlled backend/player/app volume transitions and original failure boundaries survive actual HTTP and D1; repeated polls are silent, command flood is capped, final pending-at-close is retained. This does not prove native or audible output.",
            "Six real installation entry points: retry, second actor, durable credential count, legacy write exclusion.",
        ],
        [artifact],
    )
