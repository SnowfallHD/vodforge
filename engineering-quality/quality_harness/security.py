from __future__ import annotations

import ast
import os
import stat
import urllib.parse
from pathlib import Path
from typing import Any

from .fault_server import FixtureHTTPServer


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
    from yt_downloader.safe_output import UnsafeOutputPathError

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
    rejected = False
    rejection_evidence = ""
    packaged: list[Path] = []
    try:
        packaged = package_downloaded_media_from_staging(
            case_dir / "staged",
            output_root,
            info,
            expected_extension=".mp4",
            staged_media=[(info, staging_source)],
        )
    except UnsafeOutputPathError as exc:
        rejected = True
        rejection_evidence = f"{type(exc).__name__}: {exc}"
    resolved_targets = [path.resolve(strict=False) for path in packaged]
    escaped = any(
        os.path.commonpath([str(output_root.resolve()), str(path)])
        != str(output_root.resolve())
        for path in resolved_targets
    )
    outside_entries = list(outside.rglob("*"))
    staged_preserved = staging_source.is_file()
    safely_rejected = rejected and staged_preserved and not outside_entries

    mode_root = case_dir / "mode-output"
    mode_root.mkdir()
    staging = create_staging_dir(mode_root)
    staging_root_mode = stat.S_IMODE(staging.parent.stat().st_mode)
    staging_mode = stat.S_IMODE(staging.stat().st_mode)
    posix_mode_contract = os.name != "nt"
    private = not posix_mode_contract or (
        staging_root_mode == 0o700 and staging_mode == 0o700
    )
    findings: list[dict[str, Any]] = []
    scenario_id = "security.symlink_containment_and_staging_permissions"
    if not safely_rejected:
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
                    f"Unsafe path rejected with exact production error: {rejected}",
                    f"Staged file preserved: {staged_preserved}",
                    f"Outside entries: {[str(path) for path in outside_entries]}",
                    f"Containment check: escaped={escaped}",
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
                    f"Observed staging root mode: {oct(staging_root_mode)}",
                    f"Observed per-run staging mode: {oct(staging_mode)}",
                    "Expected POSIX modes: 0700 for both directories",
                ],
                "Create the staging root and run directory with mode 0700 and verify the effective mode before writing media.",
                scenario_id,
            )
        )
    scenario = {
        "id": scenario_id,
        "evidence_tier": "unit_static",
        "category": "security",
        "status": "failed" if not safely_rejected or not private else "passed",
        "duration_seconds": 0.0,
        "metrics": {
            "escaped_output_root": escaped,
            "unsafe_symlink_rejected": rejected,
            "staged_file_preserved": staged_preserved,
            "outside_entry_count": len(outside_entries),
            "staging_root_mode_octal": oct(staging_root_mode),
            "staging_mode_octal": oct(staging_mode),
            "posix_mode_contract_applicable": posix_mode_contract,
        },
        "evidence": [
            f"Selected output root: {output_root}",
            f"Resolved committed target(s): {[str(path) for path in resolved_targets]}",
            f"Symlink escape reproduced: {escaped}",
            f"Unsafe descendant symlink rejection: {rejection_evidence or 'missing'}",
            f"Staged file preserved after rejection: {staged_preserved}",
            f"Entries written outside selected root: {[str(path) for path in outside_entries]}",
            f"Staging root permissions: {oct(staging_root_mode)}",
            f"Per-run staging permissions: {oct(staging_mode)}",
        ],
        "artifacts": [str(path) for path in packaged],
        "error": None,
    }
    return scenario, findings


def fresh_output_contract_probe(
    case_dir: Path,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    from dataclasses import replace

    from yt_downloader.app import (
        AudioExportPlan,
        ExportMode,
        ExportPlan,
        OutputType,
        validate_output_artifact,
    )

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
    mp3_plan = AudioExportPlan(
        output_type=OutputType.MP3,
        audio_format_id="fixture-audio",
        format_selector="fixture-audio",
        source_audio_kbps=192,
        effective_audio_kbps=192,
        audio_bitrate_kbps=320,
        source_sample_rate="48000",
        output_sample_rate="48000",
        source_channels="2",
        output_channels="2",
        audio_codec="opus",
        embed_metadata=False,
        embed_cover_art=False,
        cover_art_source="No Art",
    )
    mp4_plan = ExportPlan(
        mode=ExportMode.AUTO_CBR,
        video_format_id="fixture-video",
        audio_format_id="fixture-audio",
        format_selector="fixture-video+fixture-audio",
        # This is deliberately below a typical 1080p UI ceiling: the resolved
        # plan records what the selected source can actually produce.
        output_width=640,
        output_height=360,
        source_video_kbps=1500,
        effective_video_kbps=1500,
        video_bitrate_kbps=1500,
        source_audio_kbps=192,
        effective_audio_kbps=192,
        audio_bitrate_kbps=320,
    )
    accepted: list[str] = []
    valid_rejections: list[str] = []
    valid_mp3_probe = {
        **mp3_probe,
        "streams": [
            {
                **mp3_probe["streams"][0],
                "bit_rate": "320000",
                "sample_rate": "48000",
                "channels": 2,
            }
        ],
    }
    valid_mp4_probe = {
        **mp4_probe,
        "streams": [
            {
                **mp4_probe["streams"][0],
                "width": 640,
                "height": 360,
                "profile": "High",
                "pix_fmt": "yuv420p",
                "bit_rate": "1580000",
            },
            {
                **mp4_probe["streams"][1],
                "sample_rate": "48000",
                "channels": 2,
                # A real low-complexity AAC fixture can measure near half its
                # requested encoder target even though FFmpeg received -b:a.
                "bit_rate": "160000",
            },
        ],
    }
    expected_tags = ["alpha", "unicode-Δ"]
    attached_art = {
        "codec_type": "video",
        "codec_name": "mjpeg",
        "width": 640,
        "height": 360,
        "disposition": {"attached_pic": 1},
    }
    embedded_format_tags = {
        "title": "Synthetic fixture",
        "keywords": ",".join(expected_tags),
    }
    embedded_mp3_plan = replace(
        mp3_plan,
        embed_metadata=True,
        embed_cover_art=True,
        cover_art_source="Synthetic fixture artwork",
    )
    valid_embedded_mp3_probe = {
        **valid_mp3_probe,
        "format": {
            **valid_mp3_probe["format"],
            "tags": embedded_format_tags,
        },
        "streams": [valid_mp3_probe["streams"][0], attached_art],
    }
    valid_embedded_mp4_probe = {
        **valid_mp4_probe,
        "format": {
            **valid_mp4_probe["format"],
            "tags": embedded_format_tags,
        },
        "streams": [*valid_mp4_probe["streams"], attached_art],
    }
    mp3_stream = valid_mp3_probe["streams"][0]
    mp4_video = valid_mp4_probe["streams"][0]
    mp4_audio = valid_mp4_probe["streams"][1]
    invalid_probes = [
        (
            "MP3 bitrate",
            weak_mp3,
            OutputType.MP3,
            mp3_plan,
            {**valid_mp3_probe, "streams": [{**mp3_stream, "bit_rate": "64000"}]},
        ),
        (
            "MP3 sample rate",
            weak_mp3,
            OutputType.MP3,
            mp3_plan,
            {**valid_mp3_probe, "streams": [{**mp3_stream, "sample_rate": "22050"}]},
        ),
        (
            "MP3 channels",
            weak_mp3,
            OutputType.MP3,
            mp3_plan,
            {**valid_mp3_probe, "streams": [{**mp3_stream, "channels": 1}]},
        ),
        (
            "MP3 codec",
            weak_mp3,
            OutputType.MP3,
            mp3_plan,
            {**valid_mp3_probe, "streams": [{**mp3_stream, "codec_name": "aac"}]},
        ),
    ]
    for label, field, value in (
        ("MP4 width", "width", 320),
        ("MP4 height", "height", 240),
        ("MP4 video codec", "codec_name", "vp9"),
        ("MP4 pixel format", "pix_fmt", "yuv444p"),
        ("MP4 H.264 profile", "profile", "Baseline"),
        ("MP4 video bitrate", "bit_rate", "100000"),
    ):
        invalid_probes.append(
            (
                label,
                weak_mp4,
                OutputType.MP4,
                mp4_plan,
                {**valid_mp4_probe, "streams": [{**mp4_video, field: value}, mp4_audio]},
            )
        )
    for label, field, value in (
        ("MP4 audio codec", "codec_name", "opus"),
        ("MP4 audio bitrate", "bit_rate", "32000"),
        ("MP4 audio sample rate", "sample_rate", "22050"),
        ("MP4 audio channels", "channels", 1),
    ):
        invalid_probes.append(
            (
                label,
                weak_mp4,
                OutputType.MP4,
                mp4_plan,
                {**valid_mp4_probe, "streams": [mp4_video, {**mp4_audio, field: value}]},
            )
        )
    for label, path, output_type, plan, probe in invalid_probes:
        try:
            validate_output_artifact(
                path,
                output_type,
                "unused",
                expected_duration_seconds=6,
                plan=plan,
                ffprobe_data=probe,
            )
            accepted.append(f"{label} mismatch was accepted despite the resolved export plan")
        except (OSError, RuntimeError, ValueError):
            pass
    embedding_invalid_probes = [
        (
            "MP3 requested metadata",
            weak_mp3,
            OutputType.MP3,
            embedded_mp3_plan,
            {
                **valid_embedded_mp3_probe,
                "format": {**valid_embedded_mp3_probe["format"], "tags": {}},
            },
            {"expected_tags": expected_tags},
        ),
        (
            "MP3 requested artwork",
            weak_mp3,
            OutputType.MP3,
            embedded_mp3_plan,
            {**valid_embedded_mp3_probe, "streams": [valid_mp3_probe["streams"][0]]},
            {"expected_tags": expected_tags},
        ),
        (
            "MP3 requested keyword tag",
            weak_mp3,
            OutputType.MP3,
            embedded_mp3_plan,
            {
                **valid_embedded_mp3_probe,
                "format": {
                    **valid_embedded_mp3_probe["format"],
                    "tags": {"title": "Synthetic fixture", "keywords": "alpha"},
                },
            },
            {"expected_tags": expected_tags},
        ),
        (
            "MP4 requested metadata",
            weak_mp4,
            OutputType.MP4,
            mp4_plan,
            {
                **valid_embedded_mp4_probe,
                "format": {**valid_embedded_mp4_probe["format"], "tags": {}},
            },
            {
                "embed_metadata": True,
                "embed_cover_art": True,
                "expected_tags": expected_tags,
            },
        ),
        (
            "MP4 requested artwork",
            weak_mp4,
            OutputType.MP4,
            mp4_plan,
            valid_mp4_probe,
            {
                "embed_metadata": False,
                "embed_cover_art": True,
                "expected_tags": [],
            },
        ),
        (
            "MP4 requested keyword tag",
            weak_mp4,
            OutputType.MP4,
            mp4_plan,
            {
                **valid_embedded_mp4_probe,
                "format": {
                    **valid_embedded_mp4_probe["format"],
                    "tags": {"title": "Synthetic fixture", "keywords": "alpha"},
                },
            },
            {
                "embed_metadata": True,
                "embed_cover_art": True,
                "expected_tags": expected_tags,
            },
        ),
    ]
    for label, path, output_type, plan, probe, expectations in embedding_invalid_probes:
        try:
            validate_output_artifact(
                path,
                output_type,
                "unused",
                expected_duration_seconds=6,
                plan=plan,
                ffprobe_data=probe,
                **expectations,
            )
            accepted.append(
                f"{label} mismatch was accepted despite the requested output contract"
            )
        except (OSError, RuntimeError, ValueError):
            pass
    for label, path, output_type, plan, probe, expectations in (
        (
            "matching MP3 plan",
            weak_mp3,
            OutputType.MP3,
            mp3_plan,
            valid_mp3_probe,
            {"expected_tags": ["ignored-when-metadata-disabled"]},
        ),
        (
            "matching source-limited MP4 plan",
            weak_mp4,
            OutputType.MP4,
            mp4_plan,
            valid_mp4_probe,
            {
                "embed_metadata": False,
                "embed_cover_art": False,
                "expected_tags": ["ignored-when-metadata-disabled"],
            },
        ),
        (
            "matching embedded MP3 plan",
            weak_mp3,
            OutputType.MP3,
            embedded_mp3_plan,
            valid_embedded_mp3_probe,
            {"expected_tags": expected_tags},
        ),
        (
            "matching embedded MP4 plan",
            weak_mp4,
            OutputType.MP4,
            mp4_plan,
            valid_embedded_mp4_probe,
            {
                "embed_metadata": True,
                "embed_cover_art": True,
                "expected_tags": expected_tags,
            },
        ),
    ):
        try:
            validate_output_artifact(
                path,
                output_type,
                "unused",
                expected_duration_seconds=6,
                plan=plan,
                ffprobe_data=probe,
                **expectations,
            )
        except (OSError, RuntimeError, ValueError) as exc:
            valid_rejections.append(f"{label} was rejected: {type(exc).__name__}: {exc}")
    finding = _finding(
        "CORR-FRESH-OUTPUT-PLAN-001",
        "Fresh-output validation does not enforce the requested export plan",
        "correctness defect",
        "medium",
        "yt_downloader/app.py validate_output_artifact and _download_worker_single",
        [
            "Provide nonempty ffprobe data with the correct container/codec/duration but materially wrong bitrate, resolution, pixel format, profile, sample rate, channel count, metadata, artwork, or keyword tags.",
            "Call the same validate_output_artifact function used before a fresh atomic commit.",
            "Observe whether any single plan invariant is accepted despite the resolved plan being passed.",
        ],
        accepted + valid_rejections,
        "Validate fresh outputs against the ExportPlan/AudioExportPlan before commit, reusing one canonical plan-matching contract for both new and existing artifacts.",
        "correctness.fresh_output_plan_validation",
    )
    failed = bool(accepted or valid_rejections)
    scenario = {
        "id": "correctness.fresh_output_plan_validation",
        "evidence_tier": "unit_static",
        "category": "correctness",
        "status": "failed" if failed else "passed",
        "duration_seconds": 0.0,
        "metrics": {
            "validator_contract_weaknesses": len(accepted) + len(valid_rejections),
            "corrupted_final_outputs": 0,
        },
        "evidence": accepted
        + valid_rejections
        or [
            "Every injected plan/metadata/artwork/tag mismatch was rejected.",
            "Matching MP3, embedded MP3, source-limited MP4, and embedded MP4 artifacts were accepted.",
        ],
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
    app_module.append_batch_failure_report(report, url, f"injected failure while requesting {url}")
    activity = case_dir / "activity.log"
    app_module.append_activity_log(f"Normalized URL: {url}", activity)
    with app_module._ACTIVITY_LOG_LOCK:
        app_module._close_activity_log_locked()
    metadata = app_module.write_compact_video_metadata(
        case_dir / "metadata",
        {
            "id": "secret-case",
            "title": "Secret case",
            "webpage_url": url,
            "thumbnail": url,
        },
        [],
    )
    diagnostic = case_dir / "diagnostics.log"
    prior = app_module.DIAGNOSTICS_LOG_PATH
    try:
        app_module.DIAGNOSTICS_LOG_PATH = diagnostic
        app_module.write_diagnostic(f"URL received: {url}")
    finally:
        with app_module._DIAGNOSTICS_LOG_LOCK:
            if app_module._DIAGNOSTICS_LOG_HANDLE is not None:
                app_module._DIAGNOSTICS_LOG_HANDLE.close()
            app_module._DIAGNOSTICS_LOG_HANDLE = None
            app_module._DIAGNOSTICS_LOG_HANDLE_PATH = None
        app_module.DIAGNOSTICS_LOG_PATH = prior
    durable_text = {
        "history_activity": str(record.get("vodforge_run_activity")),
        "history_url": str(record.get("webpage_url")),
        "persistent_activity": activity.read_text(encoding="utf-8"),
        "batch_failure": report.read_text(encoding="utf-8"),
        "diagnostic": diagnostic.read_text(encoding="utf-8"),
        "compact_metadata": metadata.read_text(encoding="utf-8"),
    }
    safe_identity = "https://example.invalid/media"
    persisted = {name: secret in text or "user:pass" in text for name, text in durable_text.items()}
    diagnostic_mode = stat.S_IMODE(diagnostic.stat().st_mode)
    activity_mode = stat.S_IMODE(activity.stat().st_mode)
    failure_report_mode = stat.S_IMODE(report.stat().st_mode)
    posix_mode_contract = os.name != "nt"
    private_log_modes = not posix_mode_contract or all(
        mode == 0o600
        for mode in (diagnostic_mode, activity_mode, failure_report_mode)
    )
    leaked_areas = [name for name, leaked in persisted.items() if leaked]
    missing_identity_areas = [name for name, text in durable_text.items() if safe_identity not in text]
    failed = bool(leaked_areas or missing_identity_areas) or not private_log_modes
    findings: list[dict[str, Any]] = []
    if leaked_areas or missing_identity_areas:
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
                    "Search durable outputs for the canary and require useful safe URL identity to remain.",
                ],
                [
                    f"Canary persisted in: {leaked_areas}",
                    f"Safe URL identity missing from: {missing_identity_areas}",
                    f"History canonical webpage URL retained canary: {persisted['history_url']}",
                ],
                "Use one canonical log-safe URL formatter that removes userinfo, sensitive query fields, and fragments; sanitize run activity before persistence.",
                "security.url_secret_persistence",
            )
        )
    if not private_log_modes:
        findings.append(
            _finding(
                "SEC-DIAGNOSTIC-MODE-001",
                "Durable local logs are readable beyond the current user",
                "security defect",
                "low",
                "yt_downloader/app.py diagnostics, activity, and batch-failure sinks",
                [
                    "Write a diagnostic file under the effective harness umask.",
                    "Inspect permission bits.",
                ],
                [
                    f"Observed diagnostics mode: {oct(diagnostic_mode)}",
                    f"Observed activity mode: {oct(activity_mode)}",
                    f"Observed batch-failure mode: {oct(failure_report_mode)}",
                ],
                "Open durable private logs without following redirects and restrict new or existing files to 0600 before writing.",
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
            "safe_identity_missing_area_count": len(missing_identity_areas),
            "diagnostic_mode_octal": oct(diagnostic_mode),
            "activity_mode_octal": oct(activity_mode),
            "failure_report_mode_octal": oct(failure_report_mode),
            "posix_mode_contract_applicable": posix_mode_contract,
        },
        "evidence": [
            f"Unique canary persisted in: {leaked_areas}",
            f"Safe URL identity missing from: {missing_identity_areas}",
            f"Diagnostics mode: {oct(diagnostic_mode)}",
            f"Activity mode: {oct(activity_mode)}",
            f"Batch-failure mode: {oct(failure_report_mode)}",
        ],
        "artifacts": [str(report), str(activity), str(diagnostic), str(metadata)],
        "error": None,
    }
    return scenario, findings


def thumbnail_network_authority_probe(
    case_dir: Path,
    source_server: FixtureHTTPServer,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    from yt_downloader.thumbnail_network import download_bounded_url_bytes

    case_dir.mkdir(parents=True, exist_ok=True)
    source_url = source_server.url("/page/normal")
    same_origin_url = source_server.url("/thumbnail.jpg")
    same_origin_payload = download_bounded_url_bytes(
        same_origin_url,
        source_url=source_url,
        timeout_seconds=5,
    )

    with FixtureHTTPServer(source_server.fixture_dir) as target_server:
        target_url = target_server.url("/thumbnail.jpg")
        direct_rejection = ""
        try:
            download_bounded_url_bytes(
                target_url,
                source_url=source_url,
                timeout_seconds=5,
            )
        except RuntimeError as exc:
            direct_rejection = f"{type(exc).__name__}: {exc}"

        redirect_url = source_server.url(
            "/redirect/thumbnail?to=" + urllib.parse.quote(target_url, safe="")
        )
        redirect_rejection = ""
        try:
            download_bounded_url_bytes(
                redirect_url,
                source_url=source_url,
                timeout_seconds=5,
            )
        except RuntimeError as exc:
            redirect_rejection = f"{type(exc).__name__}: {exc}"

        target_snapshot = target_server.state.snapshot()

    source_snapshot = source_server.state.snapshot()
    same_origin_succeeded = bool(same_origin_payload)
    direct_rejected = "not trusted" in direct_rejection
    redirect_rejected = "not trusted" in redirect_rejection
    target_requests = int(target_snapshot.get("total_requests") or 0)
    redirect_first_hop_requests = int(
        (source_snapshot.get("requests") or {}).get("/redirect/thumbnail", 0)
    )
    passed = (
        same_origin_succeeded
        and direct_rejected
        and redirect_rejected
        and target_requests == 0
        and redirect_first_hop_requests >= 1
    )
    evidence = [
        f"Explicit same-origin fixture thumbnail succeeded: {same_origin_succeeded}",
        f"Direct cross-origin metadata URL rejection: {direct_rejection or 'missing'}",
        f"Allowed first hop to cross-origin redirect rejection: {redirect_rejection or 'missing'}",
        f"Forbidden target-origin request count: {target_requests}",
        f"Source-origin redirect first-hop request count: {redirect_first_hop_requests}",
    ]
    scenario_id = "security.thumbnail_network_authority"
    scenario = {
        "id": scenario_id,
        "evidence_tier": "unit_static",
        "category": "security",
        "status": "passed" if passed else "failed",
        "duration_seconds": 0.0,
        "metrics": {
            "same_origin_fetch_succeeded": same_origin_succeeded,
            "direct_cross_origin_rejected": direct_rejected,
            "cross_origin_redirect_rejected": redirect_rejected,
            "forbidden_target_request_count": target_requests,
            "redirect_first_hop_request_count": redirect_first_hop_requests,
        },
        "evidence": evidence,
        "artifacts": [],
        "error": None,
    }
    if passed:
        return scenario, []
    return scenario, [
        _finding(
            "SEC-THUMBNAIL-SSRF-001",
            "Untrusted thumbnail metadata can escape its source network authority",
            "security defect",
            "high",
            "yt_downloader thumbnail fetch and redirect handling",
            [
                "Run ./engineering-quality/run normal --scenario security.thumbnail_network_authority.",
                "Use one explicit loopback source origin and point its thumbnail directly or by redirect at a second loopback origin.",
                "Require the second origin to receive zero requests while a same-origin thumbnail remains usable.",
            ],
            evidence,
            "Bind thumbnail fetches to reviewed YouTube HTTPS authorities or the exact explicitly submitted source origin, and validate every redirect before following it.",
            scenario_id,
        )
    ]
