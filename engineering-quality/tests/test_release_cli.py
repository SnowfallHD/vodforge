from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pytest
from quality_harness import candidate_artifact, cli
from quality_harness.release_gate import FAST_REQUIRED_COMMANDS
from quality_harness.util import json_dump


def _fast_source_result() -> dict[str, Any]:
    commands = {
        name: {
            "returncode": 0,
            "timed_out": False,
            "unavailable": False,
            "duration_seconds": 0.01,
        }
        for name in FAST_REQUIRED_COMMANDS
    }
    return {
        "scenarios": [
            {
                "id": "unit_static.repository_suite",
                "status": "failed",
                "metrics": {
                    "commands": commands,
                    "ruff_complexity_finding_count": 74,
                    "command_failures": ["ruff_complexity"],
                },
                "evidence": ["complexity remains visible"],
            },
            {
                "id": "unit_static.bounded_mutation_history",
                "status": "passed",
                "metrics": {},
                "evidence": ["bounded mutation was caught"],
            },
        ]
    }


def test_fast_command_passes_required_checks_without_hiding_complexity(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repo = tmp_path / "repo"
    harness = repo / "engineering-quality"
    harness.mkdir(parents=True)

    def fake_run_profile(
        args: argparse.Namespace, *, repo_root: Path, harness_root: Path
    ) -> int:
        assert args.no_fail is True
        assert args.scenario == [
            "unit_static.repository_suite",
            "unit_static.bounded_mutation_history",
        ]
        args.output_dir.mkdir(parents=True)
        json_dump(args.output_dir / "results.json", _fast_source_result())
        return 0

    monkeypatch.setattr(cli, "run_profile", fake_run_profile)
    monkeypatch.setattr(
        cli,
        "machine_snapshot",
        lambda _root: ({}, {"commit": "a" * 40, "branch": "test"}),
    )
    output = tmp_path / "fast"
    status = cli.run_fast_gate(
        argparse.Namespace(output_dir=output, no_fail=False),
        repo_root=repo,
        harness_root=harness,
    )

    receipt = json.loads((output / "fast-gate.json").read_text(encoding="utf-8"))
    assert status == 0
    assert receipt["status"] == "passed"
    assert receipt["blocking_check_ids"] == []
    assert receipt["visible_nonblocking_debt"][0]["status"] == "failed"


def test_candidate_command_records_reviewed_argv_and_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repo = tmp_path / "repo"
    harness = repo / "engineering-quality"
    harness.mkdir(parents=True)
    observed: dict[str, Any] = {}

    def fake_create(archive: Path, **kwargs: Any) -> tuple[Path, dict[str, Any]]:
        observed.update({"archive": archive, **kwargs})
        receipt_path = harness / "candidate-artifact.json"
        return receipt_path, {
            "immutable_archive": {"sha256": "f" * 64},
            "packaged_e2e_eligible": True,
            "publish_eligible": False,
        }

    monkeypatch.setattr(candidate_artifact, "create_candidate_receipt", fake_create)
    args = argparse.Namespace(
        archive=Path("dist/candidate.zip"),
        version="1.2.3-dev",
        artifact_policy="development",
        build_command="./build_and_package_macos.sh 1.2.3-dev",
        build_env=["VODFORGE_UNSIGNED_REVIEW=1"],
        candidate_root=Path("engineering-quality/candidates"),
    )

    assert cli.run_candidate_gate(args, repo_root=repo, harness_root=harness) == 0
    assert observed["archive"] == (repo / "dist/candidate.zip").resolve()
    assert observed["build_command"] == [
        "./build_and_package_macos.sh",
        "1.2.3-dev",
    ]
    assert observed["build_environment"] == {"VODFORGE_UNSIGNED_REVIEW": "1"}


def test_build_environment_rejects_duplicates_and_malformed_values() -> None:
    with pytest.raises(ValueError, match="KEY=VALUE"):
        cli._build_environment(["missing-separator"])
    with pytest.raises(ValueError, match="duplicate"):
        cli._build_environment(["VODFORGE_PYTHON=a", "VODFORGE_PYTHON=b"])


def test_packaged_parser_separates_direct_bundle_from_candidate() -> None:
    candidate = cli._parser().parse_args(
        ["packaged-e2e", "--candidate", "candidate-artifact.json"]
    )
    direct = cli._parser().parse_args(
        ["packaged-e2e", "--artifact", "dist/VODForge.app"]
    )

    assert candidate.candidate == Path("candidate-artifact.json")
    assert candidate.artifact is None
    assert direct.artifact == Path("dist/VODForge.app")
    assert direct.candidate is None
