from __future__ import annotations

import json
import os
import stat
import zipfile
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from quality_harness import candidate_artifact
from quality_harness.candidate_artifact import (
    create_candidate_receipt,
    load_and_verify_candidate,
    load_candidate_receipt,
    materialize_candidate_for_e2e,
    validate_candidate_archive,
    verify_candidate_receipt,
)
from quality_harness.e2e_provenance import bundle_tree_receipt
from quality_harness.util import sha256_file


def _write_archive(path: Path, *, traversal: bool = False) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("VODForge.app/Contents/MacOS/VODForge", b"executable")
        archive.writestr(
            "VODForge.app/Contents/Resources/VODFORGE_VERSION", b"1.2.3-dev"
        )
        if traversal:
            archive.writestr("VODForge.app/../../escape", b"unsafe")


def _extract_for_test(archive: Path, destination: Path) -> None:
    with zipfile.ZipFile(archive) as source:
        for member in source.infolist():
            path = destination.joinpath(*Path(member.filename).parts)
            if member.is_dir():
                path.mkdir(parents=True, exist_ok=True)
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(source.read(member))


def _artifact_inspector(
    artifact: Path, _repo_root: Path, policy: str
) -> dict[str, Any]:
    tree = bundle_tree_receipt(artifact)
    return {
        "artifact_policy": policy,
        "artifact": str(artifact),
        "bundle_tree": tree,
        "bundle_version": "1.2.3",
        "runtime_version": "1.2.3-dev",
        "policy_verified": True,
        "release_eligible": policy == "release",
        "signature_state": (
            "developer_id" if policy == "release" else "development_ad_hoc"
        ),
        "notarization_state": "stapled" if policy == "release" else "not_stapled",
        "gatekeeper_state": (
            "accepted" if policy == "release" else "not_release_accepted"
        ),
    }


@pytest.fixture
def clean_repository(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        candidate_artifact,
        "machine_snapshot",
        lambda _root: (
            {"system": "Darwin", "machine": "arm64", "python": "3.13.7"},
            {
                "commit": "a" * 40,
                "branch": "codex/release-gate",
                "status_porcelain": [],
            },
        ),
    )


def test_candidate_receipt_freezes_and_binds_development_archive(
    tmp_path: Path, clean_repository: None
) -> None:
    repo = tmp_path / "repo"
    harness = repo / "engineering-quality"
    harness.mkdir(parents=True)
    source = tmp_path / "built.zip"
    _write_archive(source)

    receipt_path, receipt = create_candidate_receipt(
        source,
        repo_root=repo,
        candidate_root=harness / "reports" / "candidates",
        candidate_version="1.2.3-dev",
        artifact_policy="development",
        build_command=["./build_and_package_macos.sh", "1.2.3-dev"],
        build_environment={"VODFORGE_UNSIGNED_REVIEW": "1"},
        artifact_inspector=_artifact_inspector,
        extractor=_extract_for_test,
    )

    frozen = Path(receipt["immutable_archive"]["path"])
    assert frozen != source
    assert sha256_file(frozen) == sha256_file(source)
    if os.name != "nt":
        assert stat.S_IMODE(frozen.stat().st_mode) == 0o444
    assert receipt["source"]["commit"] == "a" * 40
    assert receipt["artifact"]["signature_state"] == "development_ad_hoc"
    assert receipt["packaged_e2e_eligible"] is True
    assert receipt["publish_eligible"] is False
    assert verify_candidate_receipt(receipt)["verified"] is True
    assert (
        load_candidate_receipt(receipt_path)["candidate_id"] == receipt["candidate_id"]
    )
    assert (
        load_and_verify_candidate(receipt_path)["candidate_id"]
        == receipt["candidate_id"]
    )
    if os.name != "nt":
        assert stat.S_IMODE(receipt_path.stat().st_mode) == 0o400
    schema = json.loads(
        (
            Path(__file__).parents[1] / "schemas" / "candidate-artifact.schema.json"
        ).read_text(encoding="utf-8")
    )
    assert (
        list(
            Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(
                receipt
            )
        )
        == []
    )


def test_release_policy_remains_separate_from_development(
    tmp_path: Path, clean_repository: None
) -> None:
    repo = tmp_path / "repo"
    harness = repo / "engineering-quality"
    harness.mkdir(parents=True)
    source = tmp_path / "release.zip"
    _write_archive(source)

    _path, receipt = create_candidate_receipt(
        source,
        repo_root=repo,
        candidate_root=harness / "reports" / "candidates",
        candidate_version="1.2.3-dev",
        artifact_policy="release",
        build_command=["release-build", "1.2.3-dev"],
        artifact_inspector=_artifact_inspector,
        extractor=_extract_for_test,
    )

    assert receipt["artifact"]["signature_state"] == "developer_id"
    assert receipt["packaged_e2e_eligible"] is True
    assert receipt["publish_eligible"] is True


def test_candidate_reverification_detects_archive_and_bundle_mutation(
    tmp_path: Path, clean_repository: None
) -> None:
    repo = tmp_path / "repo"
    harness = repo / "engineering-quality"
    harness.mkdir(parents=True)
    source = tmp_path / "built.zip"
    _write_archive(source)
    _path, receipt = create_candidate_receipt(
        source,
        repo_root=repo,
        candidate_root=harness / "reports" / "candidates",
        candidate_version="1.2.3-dev",
        artifact_policy="development",
        build_command=["build"],
        artifact_inspector=_artifact_inspector,
        extractor=_extract_for_test,
    )

    frozen = Path(receipt["immutable_archive"]["path"])
    frozen.chmod(0o644)
    frozen.write_bytes(b"replaced")
    executable = Path(receipt["artifact"]["artifact"]) / "Contents/MacOS/VODForge"
    executable.write_bytes(b"mutated")

    verification = verify_candidate_receipt(receipt)
    assert verification["verified"] is False
    assert "frozen archive hash changed" in verification["failures"]
    assert "extracted artifact tree hash changed" in verification["failures"]
    assert verification["packaged_e2e_eligible"] is False
    assert verification["publish_eligible"] is False


def test_e2e_materialization_uses_frozen_zip_not_prior_extraction(
    tmp_path: Path, clean_repository: None
) -> None:
    repo = tmp_path / "repo"
    harness = repo / "engineering-quality"
    harness.mkdir(parents=True)
    source = tmp_path / "built.zip"
    _write_archive(source)
    receipt_path, receipt = create_candidate_receipt(
        source,
        repo_root=repo,
        candidate_root=harness / "reports" / "candidates",
        candidate_version="1.2.3-dev",
        artifact_policy="development",
        build_command=["build"],
        artifact_inspector=_artifact_inspector,
        extractor=_extract_for_test,
    )
    prior_executable = Path(receipt["artifact"]["artifact"]) / "Contents/MacOS/VODForge"
    prior_executable.write_bytes(b"tampered-prior-extraction")

    workspace = tmp_path / "e2e-workspace"
    workspace.mkdir()
    artifact, binding = materialize_candidate_for_e2e(
        receipt_path,
        workspace / "candidate",
        extractor=_extract_for_test,
    )

    assert (artifact / "Contents/MacOS/VODForge").read_bytes() == b"executable"
    assert binding == {
        "candidate_id": receipt["candidate_id"],
        "candidate_version": "1.2.3-dev",
        "artifact_policy": "development",
        "source_commit": "a" * 40,
        "archive_sha256": receipt["immutable_archive"]["sha256"],
        "bundle_tree_sha256": receipt["artifact"]["bundle_tree"]["sha256"],
        "receipt_sha256": sha256_file(receipt_path),
        "receipt_path": str(receipt_path.resolve()),
        "artifact_path": str(artifact),
        "verified": True,
        "publish_eligible": False,
    }


def test_candidate_archive_rejects_traversal_before_extraction(tmp_path: Path) -> None:
    archive = tmp_path / "unsafe.zip"
    _write_archive(archive, traversal=True)

    with pytest.raises(RuntimeError, match="traversal"):
        validate_candidate_archive(archive)


def test_candidate_root_cannot_escape_harness(
    tmp_path: Path, clean_repository: None
) -> None:
    repo = tmp_path / "repo"
    (repo / "engineering-quality").mkdir(parents=True)
    source = tmp_path / "built.zip"
    _write_archive(source)

    with pytest.raises(ValueError, match="engineering-quality"):
        create_candidate_receipt(
            source,
            repo_root=repo,
            candidate_root=tmp_path / "outside",
            candidate_version="1.2.3-dev",
            artifact_policy="development",
            build_command=["build"],
            artifact_inspector=_artifact_inspector,
            extractor=_extract_for_test,
        )


def test_candidate_root_rejects_symlink_ancestor_without_writing_outside(
    tmp_path: Path, clean_repository: None
) -> None:
    repo = tmp_path / "repo"
    harness = repo / "engineering-quality"
    harness.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    (harness / "escaped").symlink_to(outside, target_is_directory=True)
    source = tmp_path / "built.zip"
    _write_archive(source)

    with pytest.raises(ValueError, match="symlink escape"):
        create_candidate_receipt(
            source,
            repo_root=repo,
            candidate_root=harness / "escaped" / "candidates",
            candidate_version="1.2.3-dev",
            artifact_policy="development",
            build_command=["build"],
            artifact_inspector=_artifact_inspector,
            extractor=_extract_for_test,
        )
    assert not (outside / "candidates").exists()


def test_candidate_requires_clean_source_and_reviewed_build_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repo = tmp_path / "repo"
    harness = repo / "engineering-quality"
    harness.mkdir(parents=True)
    source = tmp_path / "built.zip"
    _write_archive(source)
    monkeypatch.setattr(
        candidate_artifact,
        "machine_snapshot",
        lambda _root: (
            {},
            {
                "commit": "b" * 40,
                "branch": "codex/release-gate",
                "status_porcelain": [" M production.py"],
            },
        ),
    )
    with pytest.raises(RuntimeError, match="clean source commit"):
        create_candidate_receipt(
            source,
            repo_root=repo,
            candidate_root=harness / "candidates",
            candidate_version="1.2.3-dev",
            artifact_policy="development",
            build_command=["build"],
            build_environment={"API_TOKEN": "must-not-persist"},
            artifact_inspector=_artifact_inspector,
            extractor=_extract_for_test,
        )

    monkeypatch.setattr(
        candidate_artifact,
        "machine_snapshot",
        lambda _root: (
            {},
            {
                "commit": "b" * 40,
                "branch": "codex/release-gate",
                "status_porcelain": [],
            },
        ),
    )
    with pytest.raises(ValueError, match="unreviewed build environment"):
        create_candidate_receipt(
            source,
            repo_root=repo,
            candidate_root=harness / "candidates",
            candidate_version="1.2.3-dev",
            artifact_policy="development",
            build_command=["build"],
            build_environment={"API_TOKEN": "must-not-persist"},
            artifact_inspector=_artifact_inspector,
            extractor=_extract_for_test,
        )
    persisted_text = "\n".join(
        path.read_text(encoding="utf-8", errors="replace")
        for path in harness.rglob("*")
        if path.is_file()
    )
    assert "must-not-persist" not in persisted_text


def test_archive_rejects_symlink_that_escapes_app(tmp_path: Path) -> None:
    archive_path = tmp_path / "symlink.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        link = zipfile.ZipInfo("VODForge.app/Contents/Frameworks/escape")
        link.create_system = 3
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(link, "../../../outside")

    with pytest.raises(RuntimeError, match="symlink escapes"):
        validate_candidate_archive(archive_path)
