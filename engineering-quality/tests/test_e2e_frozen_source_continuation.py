"""An unchanged frozen app can run with a newer QA harness, never changed product inputs."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from quality_harness import windows_e2e_platform as windows
from quality_harness.util import CommandResult, run_command


def git(repo, *args):
    result = run_command(["git", *args], cwd=repo, timeout=15)
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


@pytest.fixture
def frozen_source(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.name", "QA fixture")
    git(repo, "config", "user.email", "qa@example.invalid")
    (repo / "product.py").write_text("original product\n")
    (repo / "build-script.py").write_text("original build input\n")
    (repo / "engineering-quality").mkdir()
    harness = repo / "engineering-quality" / "fixture.py"
    harness.write_text("original harness\n")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "frozen product")
    frozen = git(repo, "rev-parse", "HEAD")
    harness.write_text("continued harness\n")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "harness continuation only")
    artifact = tmp_path / "VODForge"
    internal = artifact / "_internal"
    internal.mkdir(parents=True)
    for name in (
        "VODForge.exe",
        "_internal/ffmpeg.exe",
        "_internal/ffprobe.exe",
        "_internal/deno.exe",
    ):
        (artifact / name).write_bytes(b"packaged fixture")
    (internal / "VODFORGE_VERSION").write_text("1.2.3")
    (internal / "VODFORGE_BUILD_REVISION").write_text(frozen)
    monkeypatch.setattr(windows, "sys", SimpleNamespace(platform="win32"))
    monkeypatch.setenv("SystemRoot", str(tmp_path))
    facts = {
        "status": "Valid",
        "timestamp": True,
        "subject": 'CN="Kryden Ventures, LLC", O="Kryden Ventures, LLC"',
        "version": "1.2.3",
    }

    def inspect(argv, **kwargs):
        if argv[0] == "git":
            return run_command(argv, **kwargs)
        output = (
            json.dumps(facts)
            if "-EncodedCommand" in argv
            else "ffprobe version fixture"
        )
        return CommandResult(argv, 0, 0.01, output, "", False)

    monkeypatch.setattr(windows, "run_command", inspect)
    return repo, artifact, frozen, facts


def test_direct_inspection_still_requires_current_source(frozen_source):
    repo, artifact, _, _ = frozen_source
    receipt = windows.windows_artifact_receipt(artifact, repo, "release")
    assert receipt["verified"] is False
    assert receipt["build_revision_verified"] is False


def test_verified_frozen_revision_allows_only_harness_changes(frozen_source):
    repo, artifact, frozen, _ = frozen_source
    receipt = windows.windows_artifact_receipt(
        artifact, repo, "release", expected_source_commit=frozen
    )
    assert receipt["verified"] is True
    assert receipt["build_revision"] == frozen
    assert receipt["build_source_verification"]["harness_commit"] == git(
        repo, "rev-parse", "HEAD"
    )
    assert receipt["build_source_verification"]["unchanged_product_inputs"] is True


@pytest.mark.parametrize(
    "defect",
    [
        "product",
        "build",
        "dirty_product",
        "untracked_product",
        "unknown_revision",
        "wrong_expected_revision",
        "not_ancestor",
        "signature",
        "publisher",
        "timestamp",
        "version",
        "probe",
    ],
)
def test_frozen_revision_continuation_fails_closed(frozen_source, monkeypatch, defect):
    repo, artifact, frozen, facts = frozen_source
    expected = frozen
    if defect in {"product", "build", "dirty_product"}:
        (repo / ("build-script.py" if defect == "build" else "product.py")).write_text(
            "changed product or build input\n"
        )
        if defect != "dirty_product":
            git(repo, "add", ".")
            git(repo, "commit", "-qm", "changed input")
    elif defect == "untracked_product":
        (repo / "new-product.py").write_text("untracked input\n")
    elif defect == "unknown_revision":
        (artifact / "_internal/VODFORGE_BUILD_REVISION").write_text("unknown")
    elif defect == "wrong_expected_revision":
        expected = git(repo, "rev-parse", "HEAD")
    elif defect == "not_ancestor":
        git(repo, "checkout", "--orphan", "unrelated")
        git(repo, "add", ".")
        git(repo, "commit", "-qm", "unrelated history")
    elif defect == "signature":
        facts["status"] = "Invalid"
    elif defect == "publisher":
        facts["subject"] = 'O="Other"'
    elif defect == "timestamp":
        facts["timestamp"] = False
    elif defect == "version":
        facts["version"] = "9.9.9"
    elif defect == "probe":
        original = windows.run_command

        def failed_probe(argv, **kwargs):
            if Path(argv[0]).name == "ffprobe.exe":
                return CommandResult(argv, 1, 0.01, "", "probe failed", False)
            return original(argv, **kwargs)

        monkeypatch.setattr(windows, "run_command", failed_probe)
    receipt = windows.windows_artifact_receipt(
        artifact, repo, "release", expected_source_commit=expected
    )
    assert receipt["verified"] is False
    assert receipt["release_eligible"] is False
