from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import shlex
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import SCHEMA_VERSION
from .report import comparison, markdown_report, summarize
from .util import json_dump, machine_snapshot, utc_now


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="./engineering-quality/run",
        description="Adversarial, evidence-producing VODForge engineering-quality harness",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    fast = subparsers.add_parser(
        "fast", help="Run the pre-commit release gate without hiding known debt"
    )
    fast.add_argument("--output-dir", type=Path, help="Gate report output directory")
    fast.add_argument(
        "--no-fail", action="store_true", help="Write the receipt but always exit zero"
    )
    for profile in ("normal", "deep"):
        run = subparsers.add_parser(
            profile, help=f"Run the {profile} engineering-quality profile"
        )
        run.add_argument(
            "--include-public",
            action="store_true",
            help="Exercise default-download public corpus entries",
        )
        run.add_argument(
            "--scenario",
            action="append",
            default=[],
            help="Run only this exact scenario id (repeatable)",
        )
        run.add_argument(
            "--compare", type=Path, help="Compare metrics with a prior results.json"
        )
        run.add_argument(
            "--e2e-result",
            type=Path,
            help="Include a separately produced packaged-app E2E receipt",
        )
        run.add_argument("--output-dir", type=Path, help="Report output directory")
        run.add_argument(
            "--no-fail",
            action="store_true",
            help="Always exit zero after writing reports",
        )
        if profile == "deep":
            run.add_argument(
                "--soak-jobs",
                type=int,
                choices=(50, 100),
                default=50,
                help="Run the controlled lifecycle soak for 50 jobs, or 100 after a persistent 50-job signal",
            )
    e2e = subparsers.add_parser(
        "packaged-e2e", help="Prepare/run a full packaged-app E2E evidence session"
    )
    artifact_source = e2e.add_mutually_exclusive_group()
    artifact_source.add_argument(
        "--artifact",
        type=Path,
        help="Direct app bundle (journey evidence only; not immutable-candidate proof)",
    )
    artifact_source.add_argument(
        "--candidate",
        type=Path,
        help="Candidate-artifact.json whose frozen ZIP will be freshly extracted",
    )
    e2e.add_argument(
        "--artifact-policy",
        choices=("development", "release"),
        default="release",
        help="Require either an ad-hoc development contract or the full signed release contract",
    )
    e2e.add_argument(
        "--profile",
        choices=("smoke", "deep"),
        default="smoke",
        help="Smoke proves one full journey and restart; deep also requires queue and cancellation evidence",
    )
    e2e.add_argument("--output-dir", type=Path)
    e2e.add_argument("--timeout", type=int, default=600)
    candidate = subparsers.add_parser(
        "candidate", help="Freeze and attest one immutable candidate ZIP"
    )
    candidate.add_argument("--archive", type=Path, required=True)
    candidate.add_argument("--version", required=True)
    candidate.add_argument(
        "--artifact-policy",
        choices=("development", "release"),
        required=True,
    )
    candidate.add_argument(
        "--build-command",
        required=True,
        help="Exact shell-style build argv to record; it is not executed",
    )
    candidate.add_argument(
        "--build-env",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="Reviewed build environment value to record (repeatable)",
    )
    candidate.add_argument(
        "--candidate-root",
        type=Path,
        default=Path("engineering-quality/candidates"),
    )
    release_receipt = subparsers.add_parser(
        "release-receipt",
        help="Bind candidate, FAST, NORMAL, DEEP, and packaged E2E evidence",
    )
    release_receipt.add_argument("--candidate", type=Path, required=True)
    release_receipt.add_argument("--fast-result", type=Path, required=True)
    release_receipt.add_argument("--normal-result", type=Path, required=True)
    release_receipt.add_argument("--deep-result", type=Path, required=True)
    release_receipt.add_argument("--e2e-result", type=Path, required=True)
    release_receipt.add_argument("--output-dir", type=Path, required=True)
    release_receipt.add_argument(
        "--command",
        dest="commands_used",
        action="append",
        default=[],
        required=True,
        help="Exact shell-style command used to produce evidence (repeatable)",
    )
    release_receipt.add_argument(
        "--no-fail", action="store_true", help="Write the receipt but always exit zero"
    )
    doctor = subparsers.add_parser(
        "doctor",
        help="Verify harness runtimes and dependencies without running media jobs",
    )
    doctor.add_argument("--artifact", type=Path, default=Path("dist/VODForge.app"))
    record = subparsers.add_parser(
        "record-e2e-event",
        help="Append one ordered screenshot-backed event to an active packaged E2E session",
    )
    record.add_argument("--session", type=Path, required=True)
    record.add_argument("--event", required=True)
    record.add_argument("--screenshot", type=Path)
    record.add_argument("--note")
    record.add_argument("--window-pid", type=int, required=True)
    record.add_argument("--window-owner-pid", type=int, required=True)
    record.add_argument("--window-id", type=int, required=True)
    record.add_argument("--window-title-token", required=True)
    record.add_argument(
        "--allow-gap",
        action="store_true",
        help="Record a later event while preserving earlier missing events as explicit evidence gaps",
    )
    record.add_argument("--control-action", choices=("running", "relaunch", "finish"))
    return parser


def _tool_versions() -> dict[str, str | None]:
    names = [
        "yt-dlp",
        "Pillow",
        "imageio-ffmpeg",
        "pytest",
        "psutil",
        "hypothesis",
        "jsonschema",
        "ruff",
        "mypy",
        "bandit",
        "pip-audit",
        "radon",
        "vulture",
        "mutmut",
        "pyobjc-framework-Quartz",
    ]
    versions: dict[str, str | None] = {}
    for name in names:
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = None
    return versions


def _run_id(profile: str, commit: str | None) -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return f"{timestamp}-{(commit or 'unknown')[:8]}-{profile}"


def _validate_result_shape(
    result: dict[str, Any], schema_path: Path | None = None
) -> None:
    required = {
        "schema_version",
        "run_id",
        "profile",
        "started_at",
        "completed_at",
        "machine",
        "summary",
        "scenarios",
        "findings",
    }
    missing = sorted(required - result.keys())
    if missing:
        raise RuntimeError(f"result is missing required fields: {missing}")
    allowed_statuses = {"passed", "failed", "error", "skipped"}
    for scenario in result["scenarios"]:
        if scenario.get("status") not in allowed_statuses:
            raise RuntimeError(
                f"invalid scenario status for {scenario.get('id')}: {scenario.get('status')}"
            )
    if schema_path is not None:
        try:
            from jsonschema import Draft202012Validator, FormatChecker
        except ImportError as exc:
            raise RuntimeError(
                "jsonschema is required to validate benchmark receipts; install engineering-quality/requirements.txt"
            ) from exc
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        errors = sorted(
            Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(
                result
            ),
            key=lambda item: list(item.absolute_path),
        )
        if errors:
            rendered = []
            for error in errors[:12]:
                location = (
                    "/".join(str(part) for part in error.absolute_path) or "<root>"
                )
                rendered.append(f"{location}: {error.message}")
            raise RuntimeError(
                "result failed JSON Schema validation: " + "; ".join(rendered)
            )


def run_doctor(args: argparse.Namespace, *, repo_root: Path, harness_root: Path) -> int:
    from .fixtures import find_ffmpeg, find_ffprobe

    problems: list[str] = []
    try:
        ffmpeg = find_ffmpeg()
        print(f"[doctor] ffmpeg={ffmpeg}")
    except RuntimeError as exc:
        ffmpeg = None
        problems.append(str(exc))
    try:
        ffprobe = find_ffprobe(ffmpeg)
        print(f"[doctor] ffprobe={ffprobe}")
    except RuntimeError as exc:
        problems.append(str(exc))
    versions = _tool_versions()
    required = ["yt-dlp", "Pillow", "pytest", "psutil", "hypothesis", "jsonschema"]
    if sys.platform == "darwin":
        required.append("pyobjc-framework-Quartz")
    missing = [name for name in required if versions.get(name) is None]
    if missing:
        problems.append(f"missing Python packages: {missing}")
    artifact = (
        (repo_root / args.artifact).resolve()
        if not args.artifact.is_absolute()
        else args.artifact.resolve()
    )
    packaged_ffprobe = artifact / "Contents" / "Frameworks" / "ffprobe"
    print(f"[doctor] packaged_artifact={artifact} present={artifact.is_dir()}")
    print(
        f"[doctor] packaged_ffprobe={packaged_ffprobe} present={packaged_ffprobe.is_file()}"
    )
    if problems:
        for problem in problems:
            print(f"[doctor] ERROR: {problem}", file=sys.stderr)
        print(
            "[doctor] Install the production and engineering-quality requirements plus a system FFmpeg distribution that includes ffprobe.",
            file=sys.stderr,
        )
        return 2
    print(f"[doctor] schema={harness_root / 'schemas' / 'run-result.schema.json'}")
    print("[doctor] normal/deep headless prerequisites are ready")
    return 0


def _read_json_object(path: Path, *, label: str) -> dict[str, Any]:
    resolved = path.expanduser().resolve()
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise RuntimeError(f"{label} is not readable JSON: {resolved}") from exc
    if not isinstance(payload, dict):
        raise TypeError(f"{label} must contain one JSON object")
    return payload


def run_fast_gate(
    args: argparse.Namespace, *, repo_root: Path, harness_root: Path
) -> int:
    from .release_gate import evaluate_fast_result, gate_outcome

    _machine, repository = machine_snapshot(repo_root)
    gate_id = _run_id("fast", repository.get("commit"))
    gate_dir = (args.output_dir or (harness_root / "reports" / gate_id)).resolve()
    raw_dir = gate_dir / "engineering-quality"
    profile_args = argparse.Namespace(
        command="normal",
        include_public=False,
        scenario=[
            "unit_static.repository_suite",
            "unit_static.bounded_mutation_history",
        ],
        compare=None,
        e2e_result=None,
        output_dir=raw_dir,
        no_fail=True,
    )
    run_profile(profile_args, repo_root=repo_root, harness_root=harness_root)
    result_path = raw_dir / "results.json"
    result = _read_json_object(result_path, label="FAST source receipt")
    checks = evaluate_fast_result(result)
    status = gate_outcome(checks)
    receipt = {
        "schema_version": "1.0.0",
        "receipt_type": "vodforge_fast_gate",
        "generated_at": utc_now(),
        "status": status,
        "passed": status == "passed",
        "source_result": str(result_path),
        "source_commit": repository.get("commit"),
        "checks": checks,
        "blocking_check_ids": [
            item["id"]
            for item in checks
            if item.get("required") is True and item.get("status") != "passed"
        ],
        "visible_nonblocking_debt": [
            item
            for item in checks
            if item.get("required") is False and item.get("status") != "passed"
        ],
    }
    gate_dir.mkdir(parents=True, exist_ok=True)
    json_dump(gate_dir / "fast-gate.json", receipt)
    (gate_dir / "fast-gate.md").write_text(
        "# VODForge FAST release gate\n\n"
        f"Status: **{status.upper()}**\n\n"
        + "\n".join(f"- {str(item['status']).upper()}: {item['id']}" for item in checks)
        + "\n",
        encoding="utf-8",
    )
    print(f"[release-gate] fast_result={result_path}", flush=True)
    print(
        f"[release-gate] fast_receipt={gate_dir / 'fast-gate.json'} status={status}",
        flush=True,
    )
    return 0 if args.no_fail or status == "passed" else 1


def _build_environment(values: list[str]) -> dict[str, str]:
    environment: dict[str, str] = {}
    for item in values:
        key, separator, value = item.partition("=")
        if not separator or not key:
            raise ValueError("--build-env values must use KEY=VALUE")
        if key in environment:
            raise ValueError(f"duplicate --build-env key: {key}")
        environment[key] = value
    return environment


def run_candidate_gate(
    args: argparse.Namespace, *, repo_root: Path, harness_root: Path
) -> int:
    from .candidate_artifact import create_candidate_receipt

    archive = (
        (repo_root / args.archive).resolve()
        if not args.archive.is_absolute()
        else args.archive.resolve()
    )
    candidate_root = (
        (repo_root / args.candidate_root).resolve()
        if not args.candidate_root.is_absolute()
        else args.candidate_root.resolve()
    )
    command = shlex.split(args.build_command)
    if not command:
        raise ValueError("--build-command must contain at least one argv value")
    receipt_path, receipt = create_candidate_receipt(
        archive,
        repo_root=repo_root,
        candidate_root=candidate_root,
        candidate_version=args.version,
        artifact_policy=args.artifact_policy,
        build_command=command,
        build_environment=_build_environment(args.build_env),
    )
    print(f"[candidate] receipt={receipt_path}", flush=True)
    print(
        f"[candidate] archive_sha256={receipt['immutable_archive']['sha256']}",
        flush=True,
    )
    print(
        f"[candidate] packaged_e2e_eligible={receipt['packaged_e2e_eligible']} "
        f"publish_eligible={receipt['publish_eligible']}",
        flush=True,
    )
    return 0


def run_release_receipt_gate(args: argparse.Namespace) -> int:
    from .candidate_artifact import load_and_verify_candidate
    from .release_gate import build_release_receipt, write_release_receipt

    candidate = load_and_verify_candidate(args.candidate)
    receipt = build_release_receipt(
        candidate=candidate,
        fast_result=_read_json_object(args.fast_result, label="FAST result"),
        normal_result=_read_json_object(args.normal_result, label="NORMAL result"),
        deep_result=_read_json_object(args.deep_result, label="DEEP result"),
        packaged_e2e=_read_json_object(args.e2e_result, label="packaged E2E result"),
        commands_used=[shlex.split(command) for command in args.commands_used],
    )
    paths = write_release_receipt(args.output_dir.resolve(), receipt)
    print(
        f"[release-gate] receipt={paths['json']} status={receipt['status']} "
        f"release_eligible={receipt['release_eligible']}",
        flush=True,
    )
    return 0 if args.no_fail or receipt["release_eligible"] else 1


def run_profile(
    args: argparse.Namespace, *, repo_root: Path, harness_root: Path
) -> int:
    profile = args.command
    machine, repository = machine_snapshot(repo_root)
    run_id = _run_id(profile, repository.get("commit"))
    report_dir = (args.output_dir or (harness_root / "reports" / run_id)).resolve()
    run_root = (harness_root / ".runs" / run_id).resolve()
    run_root.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    # Import production only after private process-local homes exist. This keeps
    # history, thumbnails, diagnostics, yt-dlp state, and temp files away from
    # the developer's real VODForge data.
    original_environment = {
        key: os.environ.get(key)
        for key in ("HOME", "XDG_DATA_HOME", "LOCALAPPDATA", "TMPDIR", "TMP", "TEMP")
    }
    os.environ["VODFORGE_QUALITY_ORIGINAL_ENV"] = json.dumps(original_environment)
    isolated_home = run_root / "home"
    isolated_tmp = run_root / "tmp"
    isolated_home.mkdir()
    isolated_tmp.mkdir()
    os.environ["HOME"] = str(isolated_home)
    os.environ["XDG_DATA_HOME"] = str(isolated_home / ".local" / "share")
    os.environ["LOCALAPPDATA"] = str(isolated_home / "AppData" / "Local")
    os.environ["TMPDIR"] = str(isolated_tmp)

    from .fault_server import FixtureHTTPServer
    from .fixtures import generate_fixtures
    from .pipeline import configure_production_sandbox
    from .scenarios import run_scenarios

    started_at = utc_now()
    started = time.monotonic()
    print(
        f"[quality] run={run_id} profile={profile} commit={repository.get('commit')}",
        flush=True,
    )
    print("[quality] generating legal local fixtures", flush=True)
    fixture_manifest = generate_fixtures(run_root / "fixtures", deep=profile == "deep")
    production_state = configure_production_sandbox(run_root)
    selected = set(args.scenario) if args.scenario else None
    with FixtureHTTPServer(run_root / "fixtures") as server:
        print(f"[quality] loopback fault origin={server.base_url}", flush=True)
        scenarios, findings = run_scenarios(
            repo_root=repo_root,
            harness_root=harness_root,
            run_root=run_root,
            server=server,
            profile=profile,
            soak_jobs=getattr(args, "soak_jobs", None),
            include_public=bool(args.include_public),
            selected=selected,
            e2e_result=args.e2e_result.resolve() if args.e2e_result else None,
            progress=lambda scenario_id: print(
                f"[quality] scenario={scenario_id}", flush=True
            ),
        )
        server_receipt = server.state.snapshot()
    summary, aggregate = summarize(scenarios)
    result: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "profile": profile,
        "started_at": started_at,
        "completed_at": utc_now(),
        "duration_seconds": round(time.monotonic() - started, 4),
        "machine": machine,
        "repository": repository,
        "tool_versions": _tool_versions(),
        "isolation": {
            "home": str(isolated_home),
            "tmp": str(isolated_tmp),
            "production_state": production_state,
            "cookies_or_browser_profiles_used": False,
        },
        "corpus": {
            "manifest": str(harness_root / "corpus" / "manifest.json"),
            "generated": fixture_manifest,
            "fault_server_receipt": server_receipt,
            "public_media_enabled": bool(args.include_public or profile == "deep"),
        },
        "summary": summary,
        "aggregate_metrics": aggregate,
        "scenarios": scenarios,
        "findings": findings,
    }
    baseline = (
        json.loads(args.compare.read_text(encoding="utf-8")) if args.compare else None
    )
    result["comparison"] = comparison(result, baseline)
    _validate_result_shape(result, harness_root / "schemas" / "run-result.schema.json")
    result_path = report_dir / "results.json"
    summary_path = report_dir / "summary.md"
    json_dump(result_path, result)
    summary_path.write_text(markdown_report(result), encoding="utf-8")
    latest = harness_root / "reports" / "latest"
    try:
        if latest.is_symlink() or latest.exists():
            latest.unlink()
        latest.symlink_to(report_dir, target_is_directory=True)
    except OSError:
        pass
    print(f"[quality] results={result_path}", flush=True)
    print(f"[quality] summary={summary_path}", flush=True)
    print(
        f"[quality] passed={summary['passed']} failed={summary['failed']} errors={summary['errors']} skipped={summary['skipped']}",
        flush=True,
    )
    return (
        0 if args.no_fail or (summary["failed"] == 0 and summary["errors"] == 0) else 1
    )


def main(argv: list[str] | None = None) -> None:
    args = _parser().parse_args(argv)
    harness_root = Path(__file__).resolve().parents[1]
    repo_root = harness_root.parent
    if args.command == "fast":
        raise SystemExit(
            run_fast_gate(args, repo_root=repo_root, harness_root=harness_root)
        )
    if args.command == "candidate":
        raise SystemExit(
            run_candidate_gate(args, repo_root=repo_root, harness_root=harness_root)
        )
    if args.command == "release-receipt":
        raise SystemExit(run_release_receipt_gate(args))
    if args.command == "packaged-e2e":
        from .packaged_e2e import run_packaged_e2e_session

        raise SystemExit(
            run_packaged_e2e_session(
                args, repo_root=repo_root, harness_root=harness_root
            )
        )
    if args.command == "doctor":
        raise SystemExit(
            run_doctor(args, repo_root=repo_root, harness_root=harness_root)
        )
    if args.command == "record-e2e-event":
        from .e2e_record import record_e2e_event

        raise SystemExit(record_e2e_event(args))
    raise SystemExit(run_profile(args, repo_root=repo_root, harness_root=harness_root))


if __name__ == "__main__":
    main()
