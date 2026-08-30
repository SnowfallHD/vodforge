from __future__ import annotations

import ast
import os
import stat
from pathlib import Path
from typing import Any


def _finding(
    finding_id: str,
    title: str,
    classification: str,
    severity: str,
    area: str,
    reproduction: list[str],
    evidence: list[str],
    suggested_fix: str,
    scenario_id: str,
) -> dict[str, Any]:
    return {
        "id": finding_id,
        "title": title,
        "classification": classification,
        "severity": severity,
        "area": area,
        "reproduction": reproduction,
        "evidence": evidence,
        "suggested_fix": suggested_fix,
        "scenario_id": scenario_id,
    }


def path_and_subprocess_probe(
    case_dir: Path, repo_root: Path
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    from yt_downloader.app import (
        build_vod_ffmpeg_command,
        resolved_video_output_target,
    )

    case_dir.mkdir(parents=True, exist_ok=True)
    output_root = case_dir / "chosen-output"
    malicious = {
        "id": "../../id/../escape",
        "title": "../../outside;$(touch SHOULD_NOT_EXIST)|CON:<script>\x00",
        "uploader": "../../../creator",
        "playlist_title": "../../playlist",
        "playlist_id": "../playlist-id",
    }
    target_dir, target_name = resolved_video_output_target(
        output_root, malicious, ".mp4"
    )
    lexical_contained = os.path.commonpath(
        [str(output_root), str(target_dir / target_name)]
    ) == str(output_root)
    injection_marker = case_dir / "SHOULD_NOT_EXIST"
    payload_path = case_dir / "source;$(touch SHOULD_NOT_EXIST).mp4"
    command = build_vod_ffmpeg_command("ffmpeg", payload_path, case_dir / "output.mp4")
    source_arg_count = sum(argument == str(payload_path) for argument in command)

    source = (repo_root / "yt_downloader" / "app.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    shell_true: list[int] = []
    string_subprocess: list[int] = []
    subprocess_names = {"run", "Popen", "call", "check_call", "check_output"}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr not in subprocess_names:
            continue
        if isinstance(node.func.value, ast.Name) and node.func.value.id == "subprocess":
            if any(
                keyword.arg == "shell"
                and isinstance(keyword.value, ast.Constant)
                and keyword.value.value is True
                for keyword in node.keywords
            ):
                shell_true.append(node.lineno)
            if node.args and isinstance(node.args[0], (ast.Constant, ast.JoinedStr)):
                string_subprocess.append(node.lineno)

    passed = (
        lexical_contained
        and source_arg_count == 1
        and not injection_marker.exists()
        and not shell_true
    )
    evidence = [
        f"Malicious metadata target: {target_dir / target_name}",
        f"Lexical containment under chosen root: {lexical_contained}",
        f"Injection-bearing source path remained one argv element: {source_arg_count == 1}",
        f"AST subprocess shell=True calls: {shell_true}",
        f"AST subprocess calls with literal/string command argument (review signal): {string_subprocess}",
    ]
    scenario = {
        "id": "security.path_and_subprocess_arguments",
        "evidence_tier": "unit_static",
        "category": "security",
        "status": "passed" if passed else "failed",
        "duration_seconds": 0.0,
        "metrics": {
            "shell_true_call_count": len(shell_true),
            "string_command_call_count": len(string_subprocess),
        },
        "evidence": evidence,
        "artifacts": [],
        "error": None,
    }
    findings = []
    if not passed:
        findings.append(
            _finding(
                "SEC-ARGV-PATH-001",
                "Untrusted path or metadata construction failed containment or subprocess argument safety",
                "security defect",
                "high",
                "yt_downloader/app.py output path and FFmpeg argv construction",
                [
                    "Run ./engineering-quality/run normal --scenario security.path_and_subprocess_arguments.",
                    "Inspect the resolved malicious-metadata target, argv element count, and AST shell invocation evidence.",
                ],
                evidence,
                "Keep untrusted metadata inside one sanitized path component, enforce resolved-root containment, and pass every subprocess argument as a distinct argv element with shell disabled.",
                "security.path_and_subprocess_arguments",
            )
        )
    return scenario, findings


def symlink_and_temp_probe(
    case_dir: Path,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    from yt_downloader.app import (
        create_staging_dir,
        package_downloaded_media_from_staging,
    )

    case_dir.mkdir(parents=True, exist_ok=True)
    output_root = case_dir / "chosen-output"
    outside = case_dir / "outside"
    staging_source = case_dir / "staged" / "id123.mp4"
    output_root.mkdir()
    outside.mkdir()
    staging_source.parent.mkdir()
    staging_source.write_bytes(b"synthetic staged media")
    (output_root / "Creator").symlink_to(outside, target_is_directory=True)
    info = {
        "id": "id123",
        "title": "Title",
        "uploader": "Creator",
        "webpage_url": "https://example.invalid/watch?v=id123",
    }
    packaged = package_downloaded_media_from_staging(
        case_dir / "staged",
        output_root,
        info,
        expected_extension=".mp4",
        staged_media=[(info, staging_source)],
    )
    resolved_targets = [path.resolve(strict=False) for path in packaged]
    escaped = any(
        os.path.commonpath([str(output_root.resolve()), str(path)])
        != str(output_root.resolve())
        for path in resolved_targets
    )

    mode_root = case_dir / "mode-output"
    mode_root.mkdir()
    staging = create_staging_dir(mode_root)
    mode = stat.S_IMODE(staging.stat().st_mode)
    private = mode & 0o077 == 0
    findings: list[dict[str, Any]] = []
    scenario_id = "security.symlink_containment_and_staging_permissions"
    if escaped:
        findings.append(
            _finding(
                "SEC-SYMLINK-OUTPUT-001",
                "Pre-existing output-directory symlink escapes the selected destination",
                "security defect",
                "medium",
                "yt_downloader/app.py package_downloaded_media_from_staging",
                [
                    "Create chosen-output/Creator as a symlink to a sibling outside directory.",
                    "Package staged media whose untrusted uploader metadata is Creator.",
                    "Resolve the committed target and compare it with the chosen output root.",
                ],
                [
                    f"Committed targets: {[str(path) for path in packaged]}",
                    f"Resolved targets: {[str(path) for path in resolved_targets]}",
                    "Containment check: escaped=True",
                ],
                "Reject symlink components beneath the output root and commit through directory handles/no-follow semantics after rechecking containment.",
                scenario_id,
            )
        )
    if not private:
        findings.append(
            _finding(
                "SEC-STAGING-MODE-001",
                "Per-run staging directory is not private under the effective umask",
                "security defect",
                "low",
                "yt_downloader/app.py create_staging_dir",
                [
                    "Create a production staging directory under a harness-owned destination.",
                    "Inspect its permission bits.",
                ],
                [
                    f"Observed staging mode: {oct(mode)}",
                    "Expected group/other permission bits: 0",
                ],
                "Create the staging root and run directory with mode 0700 and verify the effective mode before writing media.",
                scenario_id,
            )
        )
    scenario = {
        "id": scenario_id,
        "evidence_tier": "unit_static",
        "category": "security",
        "status": "failed" if escaped or not private else "passed",
        "duration_seconds": 0.0,
        "metrics": {"escaped_output_root": escaped, "staging_mode_octal": oct(mode)},
        "evidence": [
            f"Selected output root: {output_root}",
            f"Resolved committed target(s): {[str(path) for path in resolved_targets]}",
            f"Symlink escape reproduced: {escaped}",
            f"Per-run staging permissions: {oct(mode)}",
        ],
        "artifacts": [str(path) for path in packaged],
        "error": None,
    }
    return scenario, findings


def fresh_output_contract_probe(
    case_dir: Path,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    from yt_downloader.app import OutputType, validate_output_artifact

    case_dir.mkdir(parents=True, exist_ok=True)
    weak_mp3 = case_dir / "wrong-64k.mp3"
    weak_mp4 = case_dir / "wrong-profile.mp4"
    weak_mp3.write_bytes(b"not actually decoded because probe data is injected")
    weak_mp4.write_bytes(b"not actually decoded because probe data is injected")
    mp3_probe = {
        "format": {
            "format_name": "mp3",
            "duration": "6.0",
            "size": str(weak_mp3.stat().st_size),
        },
        "streams": [
            {
                "codec_type": "audio",
                "codec_name": "mp3",
                "bit_rate": "64000",
                "sample_rate": "22050",
                "channels": 1,
            }
        ],
    }
    mp4_probe = {
        "format": {
            "format_name": "mov,mp4",
            "duration": "6.0",
            "size": str(weak_mp4.stat().st_size),
        },
        "streams": [
            {
                "codec_type": "video",
                "codec_name": "h264",
                "width": 320,
                "height": 240,
                "profile": "Baseline",
                "pix_fmt": "yuv444p",
                "bit_rate": "100000",
            },
            {
                "codec_type": "audio",
                "codec_name": "aac",
                "sample_rate": "22050",
                "channels": 1,
                "bit_rate": "32000",
            },
        ],
    }
    accepted: list[str] = []
    try:
        validate_output_artifact(
            weak_mp3,
            OutputType.MP3,
            "unused",
            expected_duration_seconds=6,
            ffprobe_data=mp3_probe,
        )
        accepted.append(
            "64 kbps/22.05 kHz mono MP3 accepted despite a representative 320 kbps request"
        )
    except (OSError, RuntimeError, ValueError):
        pass
    try:
        validate_output_artifact(
            weak_mp4,
            OutputType.MP4,
            "unused",
            expected_duration_seconds=6,
            ffprobe_data=mp4_probe,
        )
        accepted.append(
            "100 kbps Baseline/yuv444p 320x240 MP4 accepted without matching a representative export plan"
        )
    except (OSError, RuntimeError, ValueError):
        pass
    finding = _finding(
        "CORR-FRESH-OUTPUT-PLAN-001",
        "Fresh-output validation does not enforce the requested export plan",
        "correctness defect",
        "medium",
        "yt_downloader/app.py validate_output_artifact and _download_worker_single",
        [
            "Provide nonempty ffprobe data with the correct container/codec/duration but materially wrong bitrate, resolution, pixel format, profile, sample rate, or channel count.",
            "Call the same validate_output_artifact function used before a fresh atomic commit.",
            "Observe that the artifact is accepted because no plan expectations are passed.",
        ],
        accepted,
        "Validate fresh outputs against the ExportPlan/AudioExportPlan before commit, reusing one canonical plan-matching contract for both new and existing artifacts.",
        "correctness.fresh_output_plan_validation",
    )
    failed = bool(accepted)
    scenario = {
        "id": "correctness.fresh_output_plan_validation",
        "evidence_tier": "unit_static",
        "category": "correctness",
        "status": "failed" if failed else "passed",
        "duration_seconds": 0.0,
        "metrics": {
            "validator_contract_weaknesses": len(accepted),
            "corrupted_final_outputs": 0,
        },
        "evidence": accepted or ["Both wrong-contract artifacts were rejected."],
        "artifacts": [str(weak_mp3), str(weak_mp4)],
        "error": None,
    }
    return scenario, [finding] if failed else []


def url_secret_persistence_probe(
    case_dir: Path,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    import yt_downloader.app as app_module
    from yt_downloader.history import sanitize_history_record

    case_dir.mkdir(parents=True, exist_ok=True)
    secret = "TOPSECRET-HARNESS-CANARY"
    url = f"https://user:pass@example.invalid/media?id=1&token={secret}#fragment"
    record = sanitize_history_record(
        {
            "id": "secret-case",
            "title": "Secret case",
            "webpage_url": url,
            "vodforge_run_activity": [f"Normalized URL: {url}"],
        },
        case_dir / "output",
    )
    report = case_dir / "batch-url-failures.txt"
    app_module.append_batch_failure_report(report, url, "injected failure")
    diagnostic = case_dir / "diagnostics.log"
    prior = app_module.DIAGNOSTICS_LOG_PATH
    try:
        app_module.DIAGNOSTICS_LOG_PATH = diagnostic
        app_module.write_diagnostic(f"URL received: {url}")
    finally:
        app_module.DIAGNOSTICS_LOG_PATH = prior
    persisted = {
        "history_activity": secret in str(record.get("vodforge_run_activity")),
        "history_url": secret in str(record.get("webpage_url")),
        "batch_failure": secret in report.read_text(encoding="utf-8"),
        "diagnostic": secret in diagnostic.read_text(encoding="utf-8"),
    }
    diagnostic_mode = stat.S_IMODE(diagnostic.stat().st_mode)
    leaked_areas = [name for name, leaked in persisted.items() if leaked]
    failed = bool(leaked_areas) or diagnostic_mode & 0o077 != 0
    findings: list[dict[str, Any]] = []
    if leaked_areas:
        findings.append(
            _finding(
                "SEC-URL-SECRET-PERSISTENCE-001",
                "Raw URL secrets persist in diagnostics, run activity, or failure reports",
                "security defect",
                "medium",
                "yt_downloader/app.py URL logging and yt_downloader/history.py run activity",
                [
                    "Use a credential/query-secret URL with a unique canary.",
                    "Pass it through production diagnostic, batch-failure, and history sanitation paths.",
                    "Search durable outputs for the canary.",
                ],
                [
                    f"Canary persisted in: {leaked_areas}",
                    f"History canonical webpage URL retained canary: {persisted['history_url']}",
                ],
                "Use one canonical log-safe URL formatter that removes userinfo, sensitive query fields, and fragments; sanitize run activity before persistence.",
                "security.url_secret_persistence",
            )
        )
    if diagnostic_mode & 0o077:
        findings.append(
            _finding(
                "SEC-DIAGNOSTIC-MODE-001",
                "Diagnostics file is readable beyond the current user",
                "security defect",
                "low",
                "yt_downloader/app.py write_diagnostic/reset_diagnostics_log",
                [
                    "Write a diagnostic file under the effective harness umask.",
                    "Inspect permission bits.",
                ],
                [f"Observed mode: {oct(diagnostic_mode)}"],
                "Create and chmod diagnostics to 0600 before writing, including existing files.",
                "security.url_secret_persistence",
            )
        )
    scenario = {
        "id": "security.url_secret_persistence",
        "evidence_tier": "unit_static",
        "category": "security",
        "status": "failed" if failed else "passed",
        "duration_seconds": 0.0,
        "metrics": {
            "leaked_area_count": len(leaked_areas),
            "diagnostic_mode_octal": oct(diagnostic_mode),
        },
        "evidence": [
            f"Unique canary persisted in: {leaked_areas}",
            f"Diagnostics mode: {oct(diagnostic_mode)}",
        ],
        "artifacts": [str(report), str(diagnostic)],
        "error": None,
    }
    return scenario, findings
