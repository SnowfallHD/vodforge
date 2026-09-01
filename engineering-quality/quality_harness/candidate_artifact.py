from __future__ import annotations

import hashlib
import json
import os
import secrets
import shutil
import stat

# The only subprocess boundary is fixed /usr/bin/ditto with an argv list.
import subprocess  # nosec B404
import zipfile
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Literal, cast

from .e2e_provenance import bundle_tree_receipt
from .schema_validation import validate_receipt_schema
from .util import machine_snapshot, sha256_file, utc_now

ArtifactPolicy = Literal["development", "release"]
ArtifactInspector = Callable[[Path, Path, ArtifactPolicy], dict[str, Any]]
ArchiveExtractor = Callable[[Path, Path], None]

CANDIDATE_SCHEMA_VERSION = "1.0.0"
MAX_ARCHIVE_ENTRIES = 250_000
MAX_UNCOMPRESSED_BYTES = 16 * 1024 * 1024 * 1024
SAFE_BUILD_ENVIRONMENT_KEYS = frozenset(
    {
        "VODFORGE_BUILD_VERSION",
        "VODFORGE_PYTHON",
        "VODFORGE_UNSIGNED_REVIEW",
    }
)


def _default_artifact_inspector(
    artifact: Path, repo_root: Path, policy: ArtifactPolicy
) -> dict[str, Any]:
    # Import lazily so archive validation and receipt self-tests do not import the
    # packaged-app driver or require macOS inspection tools.
    from .packaged_e2e import _artifact_receipt

    return _artifact_receipt(artifact, repo_root, artifact_policy=policy)


def _require_harness_owned_root(candidate_root: Path, repo_root: Path) -> Path:
    harness_root = (repo_root.resolve() / "engineering-quality").resolve()
    requested = candidate_root.expanduser()
    if not requested.is_absolute():
        requested = repo_root.resolve() / requested
    try:
        requested.relative_to(repo_root.resolve() / "engineering-quality")
    except ValueError as exc:
        raise ValueError(
            "candidate root must remain beneath the repository engineering-quality directory"
        ) from exc
    existing_ancestor = requested
    while not existing_ancestor.exists():
        if existing_ancestor == existing_ancestor.parent:
            raise ValueError("candidate root has no existing safe ancestor")
        existing_ancestor = existing_ancestor.parent
    try:
        existing_ancestor.resolve().relative_to(harness_root)
    except ValueError as exc:
        raise ValueError("candidate root contains a symlink escape") from exc
    requested.mkdir(parents=True, exist_ok=True, mode=0o700)
    resolved = requested.resolve()
    try:
        resolved.relative_to(harness_root)
    except ValueError as exc:
        raise ValueError(
            "candidate root must remain beneath the repository engineering-quality directory"
        ) from exc
    if resolved == harness_root:
        raise ValueError("candidate root must be a child of engineering-quality")
    if requested.is_symlink() or not requested.is_dir():
        raise ValueError("candidate root must be a real directory")
    return resolved


def _validate_member_path(name: str) -> tuple[str, ...]:
    if not name or "\x00" in name or "\\" in name:
        raise RuntimeError("candidate archive contains an invalid member path")
    path = PurePosixPath(name)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise RuntimeError("candidate archive contains a traversal path")
    if not path.parts or ":" in path.parts[0]:
        raise RuntimeError("candidate archive contains an absolute or drive path")
    top_level = path.parts[0]
    if top_level not in {"VODForge.app", "__MACOSX"}:
        raise RuntimeError(
            "candidate archive must contain only VODForge.app and macOS metadata"
        )
    return path.parts


def _symlink_escapes_archive_root(parts: tuple[str, ...], target: str) -> bool:
    if not target or "\x00" in target or "\\" in target:
        return True
    target_path = PurePosixPath(target)
    if target_path.is_absolute():
        return True
    stack = list(parts[:-1])
    for part in target_path.parts:
        if part in {"", "."}:
            continue
        if part == "..":
            if not stack:
                return True
            stack.pop()
        else:
            stack.append(part)
    return not stack or stack[0] != parts[0]


def validate_candidate_archive(archive: Path) -> dict[str, Any]:
    """Reject archive layouts that could escape or ambiguously replace the app."""
    metadata = archive.lstat()
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise RuntimeError("candidate archive must be a regular no-follow file")
    if archive.suffix.casefold() != ".zip":
        raise RuntimeError("candidate artifact must be a ZIP archive")

    seen_paths: set[str] = set()
    seen_casefolded_paths: set[str] = set()
    app_member_count = 0
    total_uncompressed = 0
    try:
        with zipfile.ZipFile(archive) as bundle_zip:
            members = bundle_zip.infolist()
            if not members or len(members) > MAX_ARCHIVE_ENTRIES:
                raise RuntimeError("candidate archive entry count is invalid")
            for member in members:
                if member.flag_bits & 0x1:
                    raise RuntimeError("candidate archive must not be encrypted")
                parts = _validate_member_path(member.filename)
                normalized = "/".join(parts)
                casefolded = normalized.casefold()
                if normalized in seen_paths or casefolded in seen_casefolded_paths:
                    raise RuntimeError(
                        "candidate archive contains colliding member paths"
                    )
                seen_paths.add(normalized)
                seen_casefolded_paths.add(casefolded)
                if parts[0] == "VODForge.app":
                    app_member_count += 1

                total_uncompressed += int(member.file_size)
                if total_uncompressed > MAX_UNCOMPRESSED_BYTES:
                    raise RuntimeError(
                        "candidate archive expands beyond the safety limit"
                    )

                mode = member.external_attr >> 16
                file_type = stat.S_IFMT(mode)
                allowed_types = {0, stat.S_IFREG, stat.S_IFDIR, stat.S_IFLNK}
                if file_type not in allowed_types:
                    raise RuntimeError("candidate archive contains a special file")
                if file_type == stat.S_IFLNK:
                    if member.file_size > 4096:
                        raise RuntimeError("candidate archive has an oversized symlink")
                    try:
                        target = bundle_zip.read(member).decode("utf-8")
                    except UnicodeDecodeError as exc:
                        raise RuntimeError(
                            "candidate archive has an invalid symlink target"
                        ) from exc
                    if _symlink_escapes_archive_root(parts, target):
                        raise RuntimeError(
                            "candidate archive symlink escapes VODForge.app"
                        )
    except zipfile.BadZipFile as exc:
        raise RuntimeError("candidate artifact is not a readable ZIP archive") from exc

    if app_member_count == 0:
        raise RuntimeError("candidate archive does not contain VODForge.app")
    return {
        "entry_count": len(seen_paths),
        "app_entry_count": app_member_count,
        "uncompressed_bytes": total_uncompressed,
        "layout_verified": True,
    }


def _freeze_archive(source: Path, candidate_dir: Path) -> dict[str, Any]:
    source = source.expanduser()
    if not source.is_absolute():
        source = Path.cwd() / source
    source_metadata = source.lstat()
    if stat.S_ISLNK(source_metadata.st_mode) or not stat.S_ISREG(
        source_metadata.st_mode
    ):
        raise RuntimeError("candidate archive source must be a regular no-follow file")

    frozen = candidate_dir / "candidate.zip"
    temporary = candidate_dir / ".candidate.zip.incomplete"
    binary_flag = getattr(os, "O_BINARY", 0)
    read_flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | binary_flag
    write_flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | binary_flag
    digest = hashlib.sha256()
    source_fd = os.open(source, read_flags)
    try:
        initial = os.fstat(source_fd)
        frozen_fd = os.open(temporary, write_flags, 0o600)
        try:
            while True:
                chunk = os.read(source_fd, 1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
                view = memoryview(chunk)
                while view:
                    written = os.write(frozen_fd, view)
                    if written <= 0:
                        raise OSError("candidate archive copy made no progress")
                    view = view[written:]
            os.fsync(frozen_fd)
        finally:
            os.close(frozen_fd)
        final = os.fstat(source_fd)
    finally:
        os.close(source_fd)

    stable_fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
    if any(getattr(initial, key) != getattr(final, key) for key in stable_fields):
        temporary.unlink(missing_ok=True)
        raise RuntimeError("candidate archive changed while it was being frozen")
    if initial.st_size != temporary.stat().st_size:
        temporary.unlink(missing_ok=True)
        raise RuntimeError("candidate archive copy is incomplete")

    os.replace(temporary, frozen)
    frozen.chmod(0o444)
    archive_hash = digest.hexdigest()
    if sha256_file(frozen) != archive_hash:
        raise RuntimeError("frozen candidate archive hash verification failed")
    return {
        "source_path": str(source.resolve()),
        "path": str(frozen.resolve()),
        "sha256": archive_hash,
        "size_bytes": frozen.stat().st_size,
        "mode": "0444",
        "read_only": True,
    }


def _ditto_extract(archive: Path, destination: Path) -> None:
    ditto = Path("/usr/bin/ditto")
    if not ditto.is_file():
        raise RuntimeError(
            "/usr/bin/ditto is required to preserve macOS bundle metadata"
        )
    # The executable is an absolute local system path and shell execution is disabled.
    completed = subprocess.run(  # nosec B603
        [str(ditto), "-x", "-k", str(archive), str(destination)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError("candidate archive extraction failed")


def _extracted_app(extraction_root: Path) -> Path:
    expected = extraction_root / "VODForge.app"
    if expected.is_symlink() or not expected.is_dir():
        raise RuntimeError("candidate archive did not extract one real VODForge.app")
    unexpected: list[Path] = []
    for path in extraction_root.rglob("*.app"):
        if "__MACOSX" in path.parts:
            continue
        if path != expected and path.is_dir():
            unexpected.append(path)
    if unexpected:
        raise RuntimeError("candidate archive extracted multiple application bundles")
    return expected.resolve()


def _source_and_machine(repo_root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    machine, repository = machine_snapshot(repo_root)
    commit = repository.get("commit")
    branch = repository.get("branch")
    if not commit or not branch:
        raise RuntimeError(
            "candidate source commit and branch could not be established"
        )
    status = list(repository.get("status_porcelain") or [])
    source = {
        "repo_root": str(repo_root.resolve()),
        "commit": commit,
        "branch": branch,
        "status_porcelain": status,
        "clean": not status,
    }
    return machine, source


def _validate_build_environment(
    environment: Mapping[str, str] | None,
) -> dict[str, str]:
    values = dict(environment or {})
    unsupported = sorted(set(values).difference(SAFE_BUILD_ENVIRONMENT_KEYS))
    if unsupported:
        raise ValueError(
            "candidate receipt cannot persist unreviewed build environment keys: "
            + ", ".join(unsupported)
        )
    return values


def _write_private_json(path: Path, payload: Mapping[str, Any]) -> None:
    encoded = (
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=False) + "\n"
    ).encode("utf-8")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    descriptor = os.open(path, flags, 0o600)
    try:
        view = memoryview(encoded)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("candidate receipt write made no progress")
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def verify_candidate_receipt(receipt: Mapping[str, Any]) -> dict[str, Any]:
    """Re-hash the frozen ZIP and extracted app without mutating either."""
    failures: list[str] = []
    archive_payload = receipt.get("immutable_archive")
    artifact_payload = receipt.get("artifact")
    source_payload = receipt.get("source")
    if not isinstance(archive_payload, Mapping):
        return {"verified": False, "failures": ["immutable archive receipt missing"]}
    if not isinstance(artifact_payload, Mapping):
        return {"verified": False, "failures": ["artifact receipt missing"]}
    if not isinstance(source_payload, Mapping):
        return {"verified": False, "failures": ["source receipt missing"]}

    archive = Path(str(archive_payload.get("path") or ""))
    artifact = Path(str(artifact_payload.get("artifact") or ""))
    observed_archive_hash: str | None = None
    try:
        archive_metadata = archive.lstat()
        if stat.S_ISLNK(archive_metadata.st_mode) or not stat.S_ISREG(
            archive_metadata.st_mode
        ):
            raise RuntimeError("frozen archive is not a regular no-follow file")
        if stat.S_IMODE(archive_metadata.st_mode) & 0o222:
            failures.append("frozen archive is writable")
        if archive_metadata.st_size != archive_payload.get("size_bytes"):
            failures.append("frozen archive size changed")
        observed_archive_hash = sha256_file(archive)
        if observed_archive_hash != archive_payload.get("sha256"):
            failures.append("frozen archive hash changed")
        validate_candidate_archive(archive)
    except (OSError, RuntimeError):
        failures.append("frozen archive is unavailable or unsafe")

    try:
        artifact_metadata = artifact.lstat()
        if stat.S_ISLNK(artifact_metadata.st_mode) or not stat.S_ISDIR(
            artifact_metadata.st_mode
        ):
            raise OSError("artifact is not a real directory")
        current_tree = bundle_tree_receipt(artifact)
    except OSError:
        current_tree = {}
        failures.append("extracted artifact is unavailable")
    expected_tree = artifact_payload.get("bundle_tree")
    if not isinstance(expected_tree, Mapping) or current_tree.get(
        "sha256"
    ) != expected_tree.get("sha256"):
        failures.append("extracted artifact tree hash changed")

    policy = receipt.get("artifact_policy")
    if policy not in {"development", "release"}:
        failures.append("artifact policy is invalid")
    if artifact_payload.get("artifact_policy") != policy:
        failures.append("artifact receipt policy mismatch")
    if artifact_payload.get("policy_verified") is not True:
        failures.append("artifact did not satisfy its declared policy")
    if policy == "release" and artifact_payload.get("release_eligible") is not True:
        failures.append("release candidate is not release eligible")
    if source_payload.get("clean") is not True:
        failures.append("candidate source was not a clean commit")

    expected_version = receipt.get("candidate_version")
    if artifact_payload.get("runtime_version") != expected_version:
        failures.append("runtime version does not match candidate version")
    expected_bundle_version = str(expected_version or "").split("-", 1)[0]
    if artifact_payload.get("bundle_version") != expected_bundle_version:
        failures.append("bundle version does not match candidate version")

    return {
        "verified": not failures,
        "failures": failures,
        "archive_sha256": observed_archive_hash,
        "bundle_tree_sha256": current_tree.get("sha256"),
        "artifact_policy": policy,
        "packaged_e2e_eligible": not failures,
        "publish_eligible": not failures and policy == "release",
        "verified_at": utc_now(),
    }


def create_candidate_receipt(
    archive: Path,
    *,
    repo_root: Path,
    candidate_root: Path,
    candidate_version: str,
    artifact_policy: ArtifactPolicy,
    build_command: Sequence[str],
    build_environment: Mapping[str, str] | None = None,
    artifact_inspector: ArtifactInspector | None = None,
    extractor: ArchiveExtractor | None = None,
) -> tuple[Path, dict[str, Any]]:
    """Freeze and inspect one ZIP produced from one clean source commit."""
    if artifact_policy not in {"development", "release"}:
        raise ValueError(f"unsupported artifact policy: {artifact_policy}")
    if not candidate_version or not build_command:
        raise ValueError("candidate version and exact build command are required")
    repo_root = repo_root.resolve()
    owned_root = _require_harness_owned_root(candidate_root, repo_root)
    machine, source = _source_and_machine(repo_root)
    if not source["clean"]:
        raise RuntimeError("candidate artifacts require a clean source commit")
    safe_environment = _validate_build_environment(build_environment)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    candidate_id = f"{timestamp}-{secrets.token_hex(4)}"
    candidate_dir = owned_root / candidate_id
    candidate_dir.mkdir(mode=0o700)
    try:
        frozen = _freeze_archive(archive, candidate_dir)
        archive_validation = validate_candidate_archive(Path(frozen["path"]))
        extraction_root = candidate_dir / "extracted"
        extraction_root.mkdir(mode=0o700)
        (extractor or _ditto_extract)(Path(frozen["path"]), extraction_root)
        artifact = _extracted_app(extraction_root)
        inspector = artifact_inspector or _default_artifact_inspector
        artifact_receipt = inspector(artifact, repo_root, artifact_policy)
        tree_before = bundle_tree_receipt(artifact)
        if artifact_receipt.get("bundle_tree", {}).get("sha256") != tree_before.get(
            "sha256"
        ):
            raise RuntimeError("artifact inspector and candidate tree hash disagree")

        receipt: dict[str, Any] = {
            "schema_version": CANDIDATE_SCHEMA_VERSION,
            "receipt_kind": "vodforge-candidate-artifact",
            "candidate_id": candidate_id,
            "created_at": utc_now(),
            "candidate_directory": str(candidate_dir.resolve()),
            "candidate_version": candidate_version,
            "artifact_policy": artifact_policy,
            "source": source,
            "build": {
                "command": [str(value) for value in build_command],
                "environment": safe_environment,
            },
            "machine": machine,
            "immutable_archive": frozen,
            "archive_validation": archive_validation,
            "artifact": artifact_receipt,
        }
        verification = verify_candidate_receipt(receipt)
        receipt["verification"] = verification
        receipt["packaged_e2e_eligible"] = verification["packaged_e2e_eligible"]
        receipt["publish_eligible"] = verification["publish_eligible"]
        if not verification["verified"]:
            raise RuntimeError(
                "candidate receipt verification failed: "
                + "; ".join(verification["failures"])
            )
        validate_receipt_schema(
            receipt,
            Path(__file__).resolve().parents[1]
            / "schemas"
            / "candidate-artifact.schema.json",
        )
        receipt_path = candidate_dir / "candidate-artifact.json"
        _write_private_json(receipt_path, receipt)
        receipt_path.chmod(0o400)
        return receipt_path, receipt
    except Exception:
        shutil.rmtree(candidate_dir)
        raise


def load_candidate_receipt(path: Path) -> dict[str, Any]:
    metadata = path.lstat()
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise RuntimeError("candidate receipt must be a regular no-follow file")
    if metadata.st_uid != os.getuid() or stat.S_IMODE(metadata.st_mode) != 0o400:
        raise RuntimeError("candidate receipt ownership or permissions are unsafe")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError("candidate receipt must contain one JSON object")
    if payload.get("schema_version") != CANDIDATE_SCHEMA_VERSION:
        raise RuntimeError("candidate receipt schema is unsupported")
    if payload.get("receipt_kind") != "vodforge-candidate-artifact":
        raise RuntimeError("candidate receipt kind is invalid")
    return payload


def _receipt_path_failures(receipt: Mapping[str, Any], receipt_path: Path) -> list[str]:
    failures: list[str] = []
    candidate_dir = receipt_path.parent.resolve()
    if receipt_path.name != "candidate-artifact.json":
        failures.append("candidate receipt filename is not canonical")
    if receipt.get("candidate_directory") != str(candidate_dir):
        failures.append("candidate directory is not bound to the receipt location")
    archive_payload = receipt.get("immutable_archive")
    if not isinstance(archive_payload, Mapping) or archive_payload.get("path") != str(
        (candidate_dir / "candidate.zip").resolve()
    ):
        failures.append("frozen archive path is not bound to the candidate directory")
    artifact_payload = receipt.get("artifact")
    if not isinstance(artifact_payload, Mapping) or artifact_payload.get(
        "artifact"
    ) != str((candidate_dir / "extracted" / "VODForge.app").resolve()):
        failures.append("artifact path is not bound to the candidate directory")
    return failures


def load_and_verify_candidate(receipt_path: Path) -> dict[str, Any]:
    """Load a candidate only when its receipt, frozen ZIP, and first tree agree."""
    receipt_path = receipt_path.expanduser()
    if not receipt_path.is_absolute():
        receipt_path = Path.cwd() / receipt_path
    receipt = load_candidate_receipt(receipt_path)
    receipt_path = receipt_path.resolve()
    verification = verify_candidate_receipt(receipt)
    failures = [*_receipt_path_failures(receipt, receipt_path)]
    failures.extend(str(item) for item in verification.get("failures") or [])
    if failures:
        raise RuntimeError("candidate verification failed: " + "; ".join(failures))
    receipt["readback_verification"] = verification
    return receipt


def _verify_frozen_archive_for_materialization(
    receipt: Mapping[str, Any], receipt_path: Path
) -> tuple[Path, str]:
    failures = _receipt_path_failures(receipt, receipt_path)
    archive_payload = receipt.get("immutable_archive")
    artifact_payload = receipt.get("artifact")
    source_payload = receipt.get("source")
    if not isinstance(archive_payload, Mapping):
        failures.append("immutable archive receipt missing")
    if not isinstance(artifact_payload, Mapping):
        failures.append("artifact receipt missing")
    if not isinstance(source_payload, Mapping):
        failures.append("source receipt missing")
    if failures:
        raise RuntimeError("candidate binding failed: " + "; ".join(failures))
    archive_payload = cast(Mapping[str, Any], archive_payload)
    artifact_payload = cast(Mapping[str, Any], artifact_payload)
    source_payload = cast(Mapping[str, Any], source_payload)

    archive = Path(str(archive_payload["path"]))
    metadata = archive.lstat()
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise RuntimeError("frozen archive is not a regular no-follow file")
    if stat.S_IMODE(metadata.st_mode) & 0o222:
        failures.append("frozen archive is writable")
    observed_hash = sha256_file(archive)
    if observed_hash != archive_payload.get("sha256"):
        failures.append("frozen archive hash changed")
    if metadata.st_size != archive_payload.get("size_bytes"):
        failures.append("frozen archive size changed")
    validate_candidate_archive(archive)

    policy = receipt.get("artifact_policy")
    if policy not in {"development", "release"}:
        failures.append("artifact policy is invalid")
    if artifact_payload.get("artifact_policy") != policy:
        failures.append("artifact receipt policy mismatch")
    if artifact_payload.get("policy_verified") is not True:
        failures.append("artifact did not satisfy its declared policy")
    if policy == "release" and artifact_payload.get("release_eligible") is not True:
        failures.append("release candidate is not release eligible")
    if source_payload.get("clean") is not True:
        failures.append("candidate source was not a clean commit")
    if artifact_payload.get("runtime_version") != receipt.get("candidate_version"):
        failures.append("runtime version does not match candidate version")
    expected_bundle_version = str(receipt.get("candidate_version") or "").split("-", 1)[
        0
    ]
    if artifact_payload.get("bundle_version") != expected_bundle_version:
        failures.append("bundle version does not match candidate version")
    if failures:
        raise RuntimeError("candidate binding failed: " + "; ".join(failures))
    return archive, observed_hash


def materialize_candidate_for_e2e(
    receipt_path: Path,
    destination: Path,
    *,
    extractor: ArchiveExtractor | None = None,
) -> tuple[Path, dict[str, Any]]:
    """Freshly extract the frozen ZIP and bind that tree to the E2E session."""
    receipt_path = receipt_path.expanduser()
    if not receipt_path.is_absolute():
        receipt_path = Path.cwd() / receipt_path
    receipt = load_candidate_receipt(receipt_path)
    receipt_path = receipt_path.resolve()
    archive, archive_hash = _verify_frozen_archive_for_materialization(
        receipt, receipt_path
    )

    destination = destination.expanduser()
    if not destination.is_absolute():
        destination = Path.cwd() / destination
    if destination.exists() or destination.is_symlink():
        raise RuntimeError("candidate E2E destination must not already exist")
    parent = destination.parent.resolve()
    if not parent.is_dir() or destination.parent.is_symlink():
        raise RuntimeError("candidate E2E destination parent must be a real directory")
    destination.mkdir(mode=0o700)
    try:
        (extractor or _ditto_extract)(archive, destination)
        artifact = _extracted_app(destination)
        fresh_tree = bundle_tree_receipt(artifact)
        artifact_payload = receipt["artifact"]
        expected_tree = artifact_payload.get("bundle_tree")
        expected_tree_hash = (
            expected_tree.get("sha256") if isinstance(expected_tree, Mapping) else None
        )
        if fresh_tree.get("sha256") != expected_tree_hash:
            raise RuntimeError(
                "fresh E2E artifact tree does not match the frozen candidate"
            )
        if sha256_file(archive) != archive_hash:
            raise RuntimeError("candidate archive changed during E2E materialization")
        binding = {
            "candidate_id": receipt.get("candidate_id"),
            "candidate_version": receipt.get("candidate_version"),
            "artifact_policy": receipt.get("artifact_policy"),
            "source_commit": receipt.get("source", {}).get("commit"),
            "archive_sha256": archive_hash,
            "bundle_tree_sha256": fresh_tree["sha256"],
            "receipt_sha256": sha256_file(receipt_path),
            "receipt_path": str(receipt_path),
            "artifact_path": str(artifact),
            "verified": True,
            "publish_eligible": (
                receipt.get("artifact_policy") == "release"
                and artifact_payload.get("release_eligible") is True
            ),
        }
        return artifact, binding
    except Exception:
        shutil.rmtree(destination)
        raise
