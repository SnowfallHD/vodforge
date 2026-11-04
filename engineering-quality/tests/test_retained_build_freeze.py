from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import zipfile
from pathlib import Path

import pytest
from quality_harness.candidate_artifact import (
    create_candidate_receipt,
    load_and_verify_candidate,
    materialize_candidate_for_e2e,
)
from quality_harness.e2e_provenance import bundle_tree_receipt
from quality_harness.retained_candidate import (
    committed_manifest,
    create_retained_candidate,
    load_evidence,
)
from quality_harness.source_identity import source_manifest
from quality_harness.util import sha256_file


def git(root, *args):
    return (
        subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)
        .stdout.decode()
        .strip()
    )


@pytest.fixture
def retained(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q")
    # Keep blobs byte-identical to the checkout on Windows runners too, where
    # Git's default line-ending conversion would otherwise rewrite them.
    git(root, "config", "core.autocrlf", "false")
    (root / "engineering-quality").mkdir()
    writer = root / "scripts/write_build_revision.py"
    writer.parent.mkdir()
    # The audit pins the committed (LF) bytes; a Windows checkout may hold CRLF.
    writer.write_bytes(
        (Path(__file__).parents[2] / "scripts/write_build_revision.py")
        .read_bytes()
        .replace(b"\r\n", b"\n")
    )
    product = root / "yt_downloader/demo.py"
    product.parent.mkdir()
    product.write_text("VALUE = 1\n")
    qml = root / "yt_downloader/qt_quick/Test.qml"
    qml.parent.mkdir()
    qml.write_text("import QtQuick\nItem {}\n")
    (root / ".gitignore").write_text("engineering-quality/candidates/\n")
    git(root, "add", ".")
    git(
        root,
        "-c",
        "user.name=Fixture",
        "-c",
        "user.email=fixture@example.invalid",
        "commit",
        "-qm",
        "original",
    )
    revision = git(root, "rev-parse", "HEAD")
    manifest = committed_manifest(root, revision)
    assert manifest == source_manifest(root)
    proof = tmp_path / "source-binding.json"
    proof.write_text(
        json.dumps(
            {
                "source_commit": revision,
                "version": "1.2.3",
                "compiled_modules_bound": 1,
                "modules": ["yt_downloader.demo"],
                "qml_bound": ["Test.qml"],
            }
        )
    )
    archive = tmp_path / "app.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("VODForge.app/Contents/MacOS/VODForge", b"executable")
        z.writestr("VODForge.app/Contents/Resources/VODFORGE_VERSION", "1.2.3")
        z.writestr("VODForge.app/Contents/Resources/VODFORGE_BUILD_REVISION", revision)
    evidence = {
        "format": "vodforge-retained-build-v1",
        "source_commit": revision,
        "source_manifest": manifest,
        "version": "1.2.3",
        "archive_sha256": sha256_file(archive),
        "executable_sha256": hashlib.sha256(b"executable").hexdigest(),
        "source_binding": {"path": proof.name, "sha256": sha256_file(proof)},
        "build_command": ["build-existing-app"],
        "build_environment": {"VODFORGE_UI": "qt"},
    }
    path = tmp_path / "retained.json"
    path.write_text(json.dumps(evidence))
    return root, revision, archive, path, evidence, proof


def extract(archive, directory):
    with zipfile.ZipFile(archive) as z:
        z.extractall(directory)


def inspect(app, source):
    return {
        "artifact_policy": "release",
        "artifact": str(app),
        "executable_sha256": sha256_file(app / "Contents/MacOS/VODForge"),
        "bundle_tree": bundle_tree_receipt(app),
        "bundle_version": "1.2.3",
        "runtime_version": "1.2.3",
        "policy_verified": True,
        "release_eligible": True,
    }


def test_retained_freeze_keeps_original_identity_without_claiming_dirty_checkout_clean(
    retained, tmp_path
):
    root, revision, archive, path, evidence, _proof = retained
    (root / "yt_downloader/demo.py").write_text("qualification checkout differs\n")
    before = git(root, "status", "--porcelain")
    with pytest.raises(RuntimeError, match="clean source"):
        create_candidate_receipt(
            archive,
            repo_root=root,
            candidate_root=root / "engineering-quality/candidates",
            candidate_version="1.2.3",
            artifact_policy="release",
            build_command=["build"],
        )
    receipt_path = create_retained_candidate(
        archive,
        evidence_path=path,
        repo_root=root,
        candidate_root=root / "engineering-quality/candidates",
        inspector=inspect,
        extractor=extract,
    )
    value = load_and_verify_candidate(receipt_path)
    assert value["source"]["commit"] == revision
    assert value["source"]["snapshot_kind"] == "immutable_git_commit"
    assert value["source"]["clean_scope"].startswith("original build")
    assert value["qualification_checkout"]["status_porcelain"]
    assert git(root, "status", "--porcelain") == before
    assert value["immutable_archive"]["sha256"] == evidence["archive_sha256"]
    app, binding = materialize_candidate_for_e2e(
        receipt_path, tmp_path / "fresh", extractor=extract
    )
    assert binding["retained_source"]["commit"] == revision
    assert (app / "Contents/Resources/VODFORGE_BUILD_REVISION").read_text() == revision
    assert committed_manifest(root, revision) == evidence["source_manifest"]


@pytest.mark.parametrize(
    "defect",
    [
        "archive",
        "proof_hash",
        "proof_commit",
        "proof_module",
        "proof_count",
        "qml_count",
        "writer",
        "manifest",
        "embedded",
        "executable",
    ],
)
def test_retained_freeze_refuses_changed_or_unbound_evidence(retained, defect):
    root, _revision, archive, path, evidence, proof_path = retained
    data = copy.deepcopy(evidence)
    proof = json.loads(proof_path.read_text())
    if defect == "archive":
        data["archive_sha256"] = "0" * 64
    elif defect == "proof_hash":
        data["source_binding"]["sha256"] = "0" * 64
    elif defect == "proof_commit":
        proof["source_commit"] = "0" * 40
    elif defect == "proof_module":
        proof["modules"] = ["yt_downloader.absent"]
    elif defect == "proof_count":
        proof["compiled_modules_bound"] = 2
    elif defect == "qml_count":
        proof["qml_bound"] = []
    elif defect == "writer":
        data["source_manifest"]["files"]["scripts/write_build_revision.py"][
            "sha256"
        ] = "0" * 64
        payload = {k: data["source_manifest"][k] for k in ["format", "files"]}
        data["source_manifest"]["sha256"] = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
    elif defect == "manifest":
        data["source_manifest"]["sha256"] = "0" * 64
    elif defect == "executable":
        data["executable_sha256"] = "0" * 64
    elif defect == "embedded":
        with zipfile.ZipFile(archive, "w") as z:
            z.writestr("VODForge.app/Contents/MacOS/VODForge", b"executable")
            z.writestr("VODForge.app/Contents/Resources/VODFORGE_VERSION", "1.2.3")
            z.writestr(
                "VODForge.app/Contents/Resources/VODFORGE_BUILD_REVISION", "unknown"
            )
        data["archive_sha256"] = sha256_file(archive)
    if defect.startswith("proof_") and defect != "proof_hash" or defect == "qml_count":
        proof_path.write_text(json.dumps(proof))
        data["source_binding"]["sha256"] = sha256_file(proof_path)
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        create_retained_candidate(
            archive,
            evidence_path=path,
            repo_root=root,
            candidate_root=root / "engineering-quality/candidates",
            inspector=inspect,
            extractor=extract,
        )
    assert not list(
        (root / "engineering-quality/candidates").rglob("candidate-artifact.json")
    )


def test_original_commit_rejects_short_revision_and_changed_proof_file(retained):
    root, revision, _archive, path, _evidence, proof = retained
    with pytest.raises(ValueError, match="Full original"):
        committed_manifest(root, revision[:7])
    proof.write_text("{}")
    with pytest.raises(ValueError, match="proof changed"):
        load_evidence(path)
