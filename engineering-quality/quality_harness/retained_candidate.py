"""Freeze an existing signed build using its retained original-source evidence.

The ordinary clean-checkout freezer is unchanged. This path never claims the
qualification checkout is clean or changes a package's embedded source identity.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import secrets
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from .candidate_artifact import (
    _extract_archive,
    _extracted_app,
    _freeze_archive,
    _require_harness_owned_root,
    _validate_build_environment,
    _write_private_json,
    validate_candidate_archive,
    verify_candidate_receipt,
)
from .schema_validation import validate_receipt_schema
from .source_identity import validate_manifest
from .util import machine_snapshot, sha256_file

FORMAT = "vodforge-retained-build-v1"
# Audited writer: returns a revision only for a clean Git working tree.
REVISION_WRITER_SHA256 = (
    "7071af764de2646d673f5da7aceb67a4bb01a36088f657426f9202a19bf6057a"
)


def validate_retained_source_claim(source) -> None:
    manifest = source.get("manifest", {})
    if (
        source.get("snapshot_kind") != "immutable_git_commit"
        or source.get("clean") is not True
        or source.get("clean_scope")
        != "original build; not the current qualification checkout"
        or not re.fullmatch(r"[a-f0-9]{40}", source.get("commit", ""))
        or not validate_manifest(manifest, source.get("manifest_sha256", ""))
        or manifest["files"].get("scripts/write_build_revision.py", {}).get("sha256")
        != REVISION_WRITER_SHA256
        or not re.fullmatch(r"[a-f0-9]{64}", source.get("source_proof_sha256", ""))
    ):
        raise ValueError("Invalid retained original-source claim")


def committed_manifest(repo: Path, revision: str) -> dict:
    """Read immutable Git blobs, never the mutable checkout or Git attributes."""
    if not re.fullmatch(r"[a-f0-9]{40}", revision):
        raise ValueError("Full original commit required")
    kind = subprocess.run(
        ["git", "-C", str(repo), "cat-file", "-t", revision],
        capture_output=True,
        check=True,
    ).stdout.strip()
    if kind != b"commit":
        raise ValueError("Original source must be a commit")
    entries = subprocess.run(
        ["git", "-C", str(repo), "ls-tree", "-rz", "--full-tree", revision],
        capture_output=True,
        check=True,
    ).stdout.split(b"\0")
    files = {}
    with subprocess.Popen(
        ["git", "-C", str(repo), "cat-file", "--batch"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
    ) as proc:
        assert proc.stdin is not None and proc.stdout is not None
        for entry in entries:
            if not entry:
                continue
            meta, raw_name = entry.split(b"\t", 1)
            mode, kind, oid = meta.split()
            name = raw_name.decode("utf-8")
            if mode not in {b"100644", b"100755"} or kind != b"blob":
                raise ValueError("Retained source supports regular Git blobs only")
            if name.startswith("/") or ".." in Path(name).parts or "\\" in name:
                raise ValueError("Unsafe source path")
            proc.stdin.write(oid + b"\n")
            proc.stdin.flush()
            observed, observed_kind, size = proc.stdout.readline().split()
            if observed != oid or observed_kind != b"blob":
                raise ValueError("Git blob identity mismatch")
            raw = proc.stdout.read(int(size))
            if len(raw) != int(size) or proc.stdout.read(1) != b"\n":
                raise ValueError("Incomplete Git blob")
            files[name] = {"kind": "file", "sha256": hashlib.sha256(raw).hexdigest()}
        proc.stdin.close()
        if proc.wait() != 0:
            raise ValueError("Git source read failed")
    payload = {"format": "vodforge-source-files-v1", "files": files}
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return {**payload, "sha256": digest}


def retained_source(evidence: dict, proof: dict) -> dict:
    """Validate the explicit historical build claim; never infer it from HEAD."""
    if evidence.get("format") != FORMAT:
        raise ValueError("Unsupported retained build evidence")
    commit = evidence.get("source_commit", "")
    manifest = evidence.get("source_manifest", {})
    if not re.fullmatch(r"[a-f0-9]{40}", commit) or not validate_manifest(
        manifest, manifest.get("sha256", "")
    ):
        raise ValueError("Invalid original source manifest")
    if (
        manifest["files"].get("scripts/write_build_revision.py", {}).get("sha256")
        != REVISION_WRITER_SHA256
    ):
        raise ValueError("Original clean-revision writer is not audited")
    if proof.get("source_commit") != commit or proof.get("version") != evidence.get(
        "version"
    ):
        raise ValueError("Retained source proof identity mismatch")
    modules = proof.get("modules", [])
    if (
        not modules
        or len(set(modules)) != len(modules)
        or proof.get("compiled_modules_bound") != len(modules)
    ):
        raise ValueError("Missing complete compiled-module evidence")
    for module in modules:
        name = module.replace(".", "/")
        if (
            name + ".py" not in manifest["files"]
            and name + "/__init__.py" not in manifest["files"]
        ):
            raise ValueError("Bound module absent from original source")
    qml_count = sum(
        p.startswith("yt_downloader/qt_quick/") and p.endswith(".qml")
        for p in manifest["files"]
    )
    qml = proof.get("qml_bound")
    expected_qml = {
        Path(p).name
        for p in manifest["files"]
        if p.startswith("yt_downloader/qt_quick/") and p.endswith(".qml")
    }
    qml_valid = (
        isinstance(qml, list)
        and set(qml) == expected_qml
        and len(qml) == len(expected_qml)
    )
    if qml_count == 0 or not qml_valid:
        raise ValueError("Incomplete QML source proof")
    for key in ("archive_sha256", "executable_sha256"):
        if not re.fullmatch(r"[a-f0-9]{64}", evidence.get(key, "")):
            raise ValueError("Missing artifact digest")
    if (
        proof.get("executable_sha256", evidence["executable_sha256"])
        != evidence["executable_sha256"]
    ):
        raise ValueError("Executable source proof mismatch")
    return {
        "commit": commit,
        "branch": "immutable-original-commit",
        "clean": True,
        "clean_scope": "original build; not the current qualification checkout",
        "clean_basis": "Signed embedded revision from audited clean-only writer plus retained compiled/QML binding",
        "snapshot_kind": "immutable_git_commit",
        "status_porcelain": [],
        "manifest": manifest,
        "manifest_sha256": manifest["sha256"],
    }


def load_evidence(path: Path) -> tuple[dict, dict, dict]:
    if path.is_symlink() or not path.is_file():
        raise ValueError("Evidence must be a regular file")
    evidence = json.loads(path.read_text())
    ref = evidence["source_binding"]
    relative = Path(ref["path"])
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("Source proof must be local to evidence directory")
    proof_path = path.parent / relative
    if (
        proof_path.is_symlink()
        or not proof_path.resolve().is_relative_to(path.parent.resolve())
        or proof_path.stat().st_size > 16 * 1024 * 1024
    ):
        raise ValueError("Unsafe source proof")
    if sha256_file(proof_path) != ref["sha256"]:
        raise ValueError("Retained source proof changed")
    proof = json.loads(proof_path.read_text())
    source = retained_source(evidence, proof)
    source["source_proof_sha256"] = ref["sha256"]
    validate_retained_source_claim(source)
    return evidence, proof, source


def create_retained_candidate(
    archive: Path,
    *,
    evidence_path: Path,
    repo_root: Path,
    candidate_root: Path,
    inspector=None,
    extractor=None,
) -> Path:
    evidence, proof, source = load_evidence(evidence_path)
    environment = _validate_build_environment(evidence["build_environment"])
    command = evidence["build_command"]
    if (
        not isinstance(command, list)
        or not command
        or not all(isinstance(v, str) and v for v in command)
    ):
        raise ValueError("Exact retained build command required")
    if sha256_file(archive) != evidence["archive_sha256"]:
        raise ValueError("Archive differs from retained build")
    owned_root = _require_harness_owned_root(candidate_root, repo_root)
    machine, checkout = machine_snapshot(repo_root)
    candidate_id = (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        + "-"
        + secrets.token_hex(4)
    )
    directory = owned_root / candidate_id
    directory.mkdir(mode=0o700)
    # Failures retain diagnostic inputs and never become a canonical receipt.
    frozen = _freeze_archive(archive, directory)
    validation = validate_candidate_archive(Path(frozen["path"]))
    extraction = directory / "extracted"
    extraction.mkdir()
    (extractor or _extract_archive)(Path(frozen["path"]), extraction)
    app = _extracted_app(extraction)
    revision = (
        (
            app
            / (
                "_internal/VODFORGE_BUILD_REVISION"
                if app.name == "VODForge"
                else "Contents/Resources/VODFORGE_BUILD_REVISION"
            )
        )
        .read_text()
        .strip()
    )
    if revision != source["commit"]:
        raise ValueError("Signed embedded revision differs from original source")
    exe = app / (
        "VODForge.exe" if app.name == "VODForge" else "Contents/MacOS/VODForge"
    )
    if sha256_file(exe) != evidence["executable_sha256"]:
        raise ValueError("Extracted executable differs from retained source proof")
    if inspector is not None:
        artifact = inspector(app, source)
    elif app.name == "VODForge":
        from .windows_e2e_platform import windows_artifact_receipt

        artifact = windows_artifact_receipt(
            app,
            repo_root,
            "release",
            expected_source_commit=source["commit"],
            retained_source=source,
        )
    else:
        from .packaged_e2e import _artifact_receipt

        artifact = _artifact_receipt(
            app,
            repo_root,
            artifact_policy="release",
            expected_source_commit=source["commit"],
        )
    if artifact.get("executable_sha256") != evidence["executable_sha256"]:
        raise ValueError("Inspector executable identity mismatch")
    receipt = {
        "schema_version": "1.0.0",
        "receipt_kind": "vodforge-candidate-artifact",
        "candidate_id": candidate_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "candidate_directory": str(directory.resolve()),
        "candidate_version": evidence["version"],
        "artifact_policy": "release",
        "source": source,
        "build": {"command": command, "environment": environment},
        "machine": machine,
        "qualification_checkout": checkout,
        "retained_build": {
            "evidence_sha256": sha256_file(evidence_path),
            "source_binding_sha256": evidence["source_binding"]["sha256"],
            "proof_created_at": proof.get("at"),
        },
        "immutable_archive": frozen,
        "archive_validation": validation,
        "artifact": artifact,
    }
    verification = verify_candidate_receipt(receipt)
    receipt.update(
        verification=verification,
        packaged_e2e_eligible=verification["packaged_e2e_eligible"],
        publish_eligible=verification["publish_eligible"],
    )
    if not verification["verified"]:
        raise ValueError(
            "Retained candidate failed verification: "
            + "; ".join(verification["failures"])
        )
    validate_receipt_schema(
        receipt,
        Path(__file__).resolve().parents[1] / "schemas/candidate-artifact.schema.json",
    )
    target = directory / "candidate-artifact.json"
    _write_private_json(target, receipt)
    target.chmod(0o400)
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--candidate-root", type=Path, required=True)
    args = parser.parse_args()
    print(
        create_retained_candidate(
            args.archive.resolve(),
            evidence_path=args.evidence.resolve(),
            repo_root=args.repo_root.resolve(),
            candidate_root=args.candidate_root.resolve(),
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
