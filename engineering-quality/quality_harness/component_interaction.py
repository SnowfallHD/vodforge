"""Bounded source/component observations, distinct from media/native acceptance."""

from __future__ import annotations

from itertools import pairwise
from pathlib import Path

from .pipeline_interaction import _contained, _number, load_observation
from .transaction_interaction import _file, _trace

COMPONENT_CONTRACTS = {
    "correctness.fresh_output_plan_validation": "resolved-plan-validator-calls-v1",
    "security.path_and_subprocess_arguments": "static-path-argv-construction-v1",
    "security.symlink_containment_and_staging_permissions": "symlink-refusal-private-stage-v1",
}


def _argv(raw, root, check):
    rows = _trace(
        raw,
        "trace",
        ["before_construction", "construction_returned", "source_review_returned"],
        check,
    )
    if rows is None:
        return
    before, during, after = rows
    output = before.get("output_root", "")
    check(
        "before",
        "fresh_static_construction",
        all(k in before for k in ("output_root", "root_exists", "marker_exists")),
        _contained(output, str(root))
        and before.get("root_exists") is False
        and before.get("marker_exists") is False,
        "Controlled root and injection marker are absent before pure path/argv construction",
    )
    metadata = during.get("metadata")
    check(
        "during",
        "adversarial_metadata_contained",
        isinstance(metadata, dict) and isinstance(during.get("target_name"), str),
        isinstance(metadata, dict)
        and metadata.get("title")
        == "../../outside;$(touch SHOULD_NOT_EXIST)|CON:<script>\x00"
        and _contained(
            str(Path(during.get("target_dir", "")) / during.get("target_name", "")),
            output,
        )
        and Path(during.get("target_name", "")).name == during.get("target_name")
        and "\x00"
        not in str(during.get("target_dir", "")) + during.get("target_name", ""),
        "Traversal/shell-looking metadata is contained in sanitized path components",
    )
    cmd, source = during.get("command"), during.get("source_path")
    typed = isinstance(cmd, list) and all(isinstance(x, str) for x in cmd)
    check(
        "during",
        "single_argument_transport",
        typed and isinstance(source, str),
        typed
        and cmd[0] == "ffmpeg"
        and source == str(root / "source;$(touch SHOULD_NOT_EXIST).mp4")
        and cmd.count(source) == 1
        and "-i" in cmd
        and cmd[cmd.index("-i") + 1] == source
        and str(root / "output.mp4") == cmd[-1],
        "FFmpeg builder returns a list and keeps the literal input path as exactly one input argument; no process executes in this probe",
    )
    check(
        "after",
        "reviewed_static_subprocess_calls",
        isinstance(after.get("shell_true"), list)
        and isinstance(after.get("string_subprocess"), list)
        and isinstance(after.get("source"), dict),
        after.get("marker_exists") is False
        and after.get("shell_true") == []
        and _file(after.get("source"))
        and Path(after["source"]["path"]).as_posix().endswith("/yt_downloader/app.py"),
        "Recorded AST source hash has no shell=True calls; string argv calls remain visible review signals",
    )


def _symlink(raw, root, check):
    rows = _trace(
        raw,
        "trace",
        ["before_packaging", "packaging_returned", "private_staging_created"],
        check,
    )
    if rows is None:
        return
    before, during, after = rows
    source = before.get("source")
    check(
        "before",
        "owned_escape_fixture",
        isinstance(source, dict),
        _file(source)
        and _contained(source["path"], str(root))
        and before.get("output_root") == str(root / "chosen-output")
        and before.get("outside") == str(root / "outside")
        and before.get("link") == str(root / "chosen-output/Creator")
        and before.get("link_is_symlink") is True
        and before.get("link_target") == before.get("outside")
        and before.get("outside_entries") == [],
        "Observed selected descendant actually links to the empty owned outside fixture before production packaging",
    )
    check(
        "during",
        "production_symlink_refusal",
        all(
            k in during
            for k in ("exception_type", "packaged", "source", "outside_entries")
        ),
        during.get("exception_type") == "UnsafeOutputPathError"
        and during.get("packaged") == []
        and during.get("source") == source
        and during.get("outside_entries") == [],
        "Production packaging rejects the descendant symlink without moving the source or writing outside",
    )
    stage, stage_root = after.get("stage"), after.get("root")
    typed = isinstance(stage, dict) and isinstance(stage_root, dict)
    check(
        "after",
        "observed_private_stage",
        typed and isinstance(after.get("os_name"), str),
        typed
        and after.get("os_name") == "posix"
        and stage.get("exists") is True
        and stage.get("symlink") is False
        and stage.get("mode") == 0o700
        and stage_root.get("exists") is True
        and stage_root.get("symlink") is False
        and stage_root.get("mode") == 0o700
        and stage_root.get("path") == str(root / "mode-output/.vfstage")
        and _contained(stage.get("path", ""), str(root / "mode-output"), staged=True)
        and Path(stage.get("path", "")).parent == Path(stage_root.get("path", "")),
        "Actual POSIX staging root and per-run directory are private 0700; Windows ACL qualification remains separate",
    )
    check(
        "after",
        "escape_source_preserved",
        all(k in after for k in ("source", "outside_entries")),
        after.get("source") == source and after.get("outside_entries") == [],
        "Exact original staged source survives and controlled outside remains empty after subsequent staging creation",
    )


def validator_inputs():
    """Independent exact injected probe matrix; no decoder or worker claim."""
    audio3 = {
        "codec_type": "audio",
        "codec_name": "mp3",
        "bit_rate": "320000",
        "sample_rate": "48000",
        "channels": 2,
    }
    video = {
        "codec_type": "video",
        "codec_name": "h264",
        "width": 640,
        "height": 360,
        "profile": "High",
        "pix_fmt": "yuv420p",
        "bit_rate": "1580000",
    }
    audio4 = {
        "codec_type": "audio",
        "codec_name": "aac",
        "sample_rate": "48000",
        "channels": 2,
        "bit_rate": "160000",
    }
    art = {
        "codec_type": "video",
        "codec_name": "mjpeg",
        "width": 640,
        "height": 360,
        "disposition": {"attached_pic": 1},
    }
    import copy

    rows = {}

    def add(label, kind, streams, *, tags=None, flags=None, accepted=False):
        fmt = {
            "format_name": "mp3" if kind == "MP3" else "mov,mp4",
            "duration": "6.0",
            "size": "51",
        }
        if tags is not None:
            fmt["tags"] = tags
        rows[label] = {
            "kind": kind,
            "probe": {"format": fmt, "streams": copy.deepcopy(streams)},
            "expectations": {"expected_duration_seconds": 6, **(flags or {})},
            "accepted": accepted,
        }

    for label, field, value in [
        ("MP3 bitrate", "bit_rate", "64000"),
        ("MP3 sample rate", "sample_rate", "22050"),
        ("MP3 channels", "channels", 1),
        ("MP3 codec", "codec_name", "aac"),
    ]:
        add(label, "MP3", [{**audio3, field: value}])
    for label, field, value in [
        ("MP4 width", "width", 320),
        ("MP4 height", "height", 240),
        ("MP4 video codec", "codec_name", "vp9"),
        ("MP4 pixel format", "pix_fmt", "yuv444p"),
        ("MP4 H.264 profile", "profile", "Baseline"),
        ("MP4 video bitrate", "bit_rate", "100000"),
    ]:
        add(label, "MP4", [{**video, field: value}, audio4])
    for label, field, value in [
        ("MP4 audio codec", "codec_name", "opus"),
        ("MP4 excessive audio bitrate", "bit_rate", "500000"),
        ("MP4 zero audio bitrate", "bit_rate", "0"),
        ("MP4 unavailable audio bitrate", "bit_rate", "N/A"),
        ("MP4 audio sample rate", "sample_rate", "22050"),
        ("MP4 audio channels", "channels", 1),
    ]:
        add(label, "MP4", [video, {**audio4, field: value}])
    tags = {"title": "Synthetic fixture", "keywords": "alpha,unicode-Δ"}
    expected_tags = ["alpha", "unicode-Δ"]
    for kind, streams in [("MP3", [audio3]), ("MP4", [video, audio4])]:
        flags = {"expected_tags": expected_tags}
        if kind == "MP4":
            flags.update(embed_metadata=True, embed_cover_art=True)
        add(kind + " requested metadata", kind, [*streams, art], tags={}, flags=flags)
        add(
            kind + " requested artwork",
            kind,
            streams,
            tags=tags if kind == "MP3" else None,
            flags=flags
            if kind == "MP3"
            else {
                "embed_metadata": False,
                "embed_cover_art": True,
                "expected_tags": [],
            },
        )
        add(
            kind + " requested keyword tag",
            kind,
            [*streams, art],
            tags={"title": "Synthetic fixture", "keywords": "alpha"},
            flags=flags,
        )
    add(
        "matching MP3 plan",
        "MP3",
        [audio3],
        flags={"expected_tags": ["ignored-when-metadata-disabled"]},
        accepted=True,
    )
    flags = {"embed_metadata": False, "embed_cover_art": False}
    add(
        "matching source-limited MP4 plan",
        "MP4",
        [video, audio4],
        flags={**flags, "expected_tags": ["ignored-when-metadata-disabled"]},
        accepted=True,
    )
    add(
        "matching quiet AAC plan",
        "MP4",
        [video, {**audio4, "bit_rate": "2000"}],
        flags=flags,
        accepted=True,
    )
    add(
        "matching embedded MP3 plan",
        "MP3",
        [audio3, art],
        tags=tags,
        flags={"expected_tags": expected_tags},
        accepted=True,
    )
    add(
        "matching embedded MP4 plan",
        "MP4",
        [video, audio4, art],
        tags=tags,
        flags={
            "embed_metadata": True,
            "embed_cover_art": True,
            "expected_tags": expected_tags,
        },
        accepted=True,
    )
    return rows


def _validator(raw, root, check):
    calls = raw.get("calls")
    typed = isinstance(calls, list) and all(isinstance(x, dict) for x in calls)
    specs = validator_inputs()
    check(
        "before",
        "exact_probe_matrix",
        typed,
        typed
        and len(calls) == len(specs)
        and {x.get("label") for x in calls} == specs.keys()
        and raw.get("scope")
        == "injected ffprobe data; no real media decoding or worker commit",
        "Every fixed invalid and matching injected probe is represented exactly once; bounded component scope is explicit",
    )
    if not typed:
        return
    timed = all(
        _number(x.get(k))
        for x in calls
        for k in ("entered_seconds", "returned_seconds")
    )
    check(
        "during",
        "ordered_actual_calls",
        timed and _number(raw.get("clock_origin_monotonic")),
        timed
        and all(0 <= x["entered_seconds"] < x["returned_seconds"] for x in calls)
        and all(
            a["returned_seconds"] <= b["entered_seconds"] for a, b in pairwise(calls)
        ),
        "Each actual validator invocation has ordered entry/return observations on one monotonic clock",
    )
    for call in calls:
        label = call.get("label")
        spec = specs.get(label)
        if spec is None:
            continue
        plan = call.get("plan")
        before = call.get("source_before")
        is3 = spec["kind"] == "MP3"
        embedded3 = is3 and ("requested" in label or "embedded" in label)
        required = {
            "audio_bitrate_kbps": 320,
            "source_audio_kbps": 192,
            "effective_audio_kbps": 192,
        }
        required.update(
            {
                "output_type": "MP3",
                "output_sample_rate": "48000",
                "output_channels": "2",
                "embed_metadata": embedded3,
                "embed_cover_art": embedded3,
            }
            if is3
            else {
                "mode": "Auto CBR",
                "output_width": 640,
                "output_height": 360,
                "video_bitrate_kbps": 1500,
                "audio_sample_rate": "48000",
                "audio_channels": "2",
            }
        )
        check(
            "before",
            label + "_bound_inputs",
            isinstance(plan, dict) and isinstance(before, dict),
            isinstance(plan, dict)
            and all(plan.get(k) == v for k, v in required.items())
            and _file(before)
            and before.get("path")
            == str(root / ("wrong-64k.mp3" if is3 else "wrong-profile.mp4"))
            and before.get("size_bytes") == 51
            and call.get("output_type") == spec["kind"]
            and call.get("probe") == spec["probe"]
            and call.get("expectations") == spec["expectations"]
            and call.get("binary") == "unused",
            "Observed plan, synthetic file and exact injected mismatch/matching probe belong to this invocation",
        )
        check(
            "after",
            label + "_actual_outcome",
            "exception_type" in call and "source_after" in call,
            call.get("exception_type") == (None if spec["accepted"] else "RuntimeError")
            and call.get("source_after") == before,
            "Production validator accepts matching data and rejects the targeted mismatch without changing the source bytes",
        )
    files = raw.get("files_after")
    check(
        "after",
        "all_synthetic_sources_preserved",
        isinstance(files, list),
        isinstance(files, list)
        and len(files) == 2
        and {x.get("path") for x in files}
        == {str(root / "wrong-64k.mp3"), str(root / "wrong-profile.mp4")}
        and all(
            _file(x) and any(x == c.get("source_before") for c in calls) for x in files
        ),
        "Both synthetic sources retain their original hashes after all controlled calls",
    )


def evaluate_component(scenario):
    raw, reason = load_observation(scenario)
    rows = []

    def check(phase, name, present, valid, detail):
        rows.append(
            {
                "phase": phase,
                "assertion": name,
                "status": "unproven"
                if not present
                else "passed"
                if valid
                else "failed",
                "evidence": detail,
            }
        )

    if raw is None:
        for phase in ("before", "during", "after"):
            check(phase, "raw_receipt_binding", False, False, reason)
    else:
        try:
            check(
                "before",
                "component_identity",
                "scenario_id" in raw and "contract" in raw,
                raw.get("scenario_id") == scenario["id"]
                and raw.get("contract") == COMPONENT_CONTRACTS[scenario["id"]],
                "Actual component identity matches its explicit source-only contract",
            )
            evaluator = (
                _validator
                if scenario["id"].startswith("correctness")
                else _argv
                if "subprocess" in scenario["id"]
                else _symlink
            )
            evaluator(raw, Path(scenario["raw_result"]).parent, check)
        except (KeyError, TypeError, ValueError, AttributeError, IndexError):
            check(
                "during",
                "observation_schema",
                False,
                False,
                "Missing/malformed component observations",
            )
    phases = {}
    for phase in ("before", "during", "after"):
        states = [r["status"] for r in rows if r["phase"] == phase]
        phases[phase] = (
            "failed"
            if "failed" in states
            else "unproven"
            if not states or "unproven" in states
            else "passed"
        )
    return {
        "status": "failed"
        if "failed" in phases.values()
        else "unproven"
        if "unproven" in phases.values()
        else "passed",
        "scenario_id": scenario["id"],
        "required_phases": list(phases),
        "phase_review": phases,
        "assertion_mapping": rows,
        "domain_contract": COMPONENT_CONTRACTS[scenario["id"]],
        "reason": "Controlled construction, packaging or injected validation; no native, decoder or fresh commit acceptance.",
    }
