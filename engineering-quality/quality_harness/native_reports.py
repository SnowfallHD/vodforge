"""Write each native result immediately, including failures before a timeout."""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import sys
from pathlib import Path

_case_snapshots = {}
_evidence_rows = []
_INDEX_NAMES = {
    "native-results.jsonl",
    "native-evidence.jsonl",
    "native-evidence.json",
    "native-source-before.json",
    "native-source-after.json",
    "native.xml",
    "native-command.json",
}


def artifact_snapshot(directory):
    """Observe files changed during a test, not infer their interaction phase."""
    return {
        path.relative_to(directory).as_posix(): (
            path.stat().st_size,
            path.stat().st_mtime_ns,
        )
        for path in directory.rglob("*")
        if path.is_file() and path.name not in _INDEX_NAMES
    }


def changed_artifacts(directory, before):
    result = []
    for name, stamp in artifact_snapshot(directory).items():
        if before.get(name) == stamp:
            continue
        path = directory / name
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        result.append({"path": name, "bytes": stamp[0], "sha256": digest})
    return sorted(result, key=lambda row: row["path"])


def verify_artifacts(directory, rows):
    """Overwritten evidence stays visible, but cannot pass as its earlier bytes."""
    verified = []
    for row in rows:
        entries = []
        for artifact in row["artifacts"]:
            path = directory / artifact["path"]
            if not path.is_file():
                integrity = "missing"
            else:
                with path.open("rb") as stream:
                    actual = hashlib.file_digest(stream, "sha256").hexdigest()
                integrity = (
                    "intact" if actual == artifact["sha256"] else "changed_after_test"
                )
            entries.append({**artifact, "integrity": integrity})
        verified.append({**row, "artifacts": entries})
    return verified


def pytest_runtest_logstart(nodeid, location):
    destination = os.environ.get("VODFORGE_NATIVE_EVIDENCE_DIR")
    if destination:
        path = Path(destination)
        path.mkdir(parents=True, exist_ok=True)
        _case_snapshots[nodeid] = artifact_snapshot(path)


def pytest_runtest_logfinish(nodeid, location):
    destination = os.environ.get("VODFORGE_NATIVE_EVIDENCE_DIR")
    if destination:
        path = Path(destination)
        row = {
            "nodeid": nodeid,
            "artifacts": changed_artifacts(path, _case_snapshots.pop(nodeid, {})),
        }
        _evidence_rows.append(row)
        with (path / "native-evidence.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(row) + "\n")


def pytest_sessionfinish(session, exitstatus):
    destination = os.environ.get("VODFORGE_NATIVE_EVIDENCE_DIR")
    if destination:
        from .source_identity import source_manifest

        path = Path(destination)
        source = source_manifest(Path.cwd())
        (path / "native-source-after.json").write_text(json.dumps(source, indent=2))
        before_path = path / "native-source-before.json"
        before = json.loads(before_path.read_text()) if before_path.exists() else {}
        (path / "native-evidence.json").write_text(
            json.dumps(
                {
                    "scope": "Files created or changed during each pytest case. Pytest phases are not user-interaction phases; files and hashes do not certify visual or temporal acceptance.",
                    "source_before": before.get("sha256"),
                    "source_after": source["sha256"],
                    "source_unchanged": before.get("sha256") == source["sha256"],
                    "pytest_exitstatus": int(exitstatus),
                    "checks": verify_artifacts(path, _evidence_rows),
                },
                indent=2,
            )
        )


def pytest_configure(config):
    # A green JUnit result must not conceal failed finalizers or worker crashes.
    # There are no blanket Tk/thread lifecycle warning exemptions.
    for category in (
        "PytestUnraisableExceptionWarning",
        "PytestUnhandledThreadExceptionWarning",
    ):
        config.addinivalue_line("filterwarnings", f"error::pytest.{category}")
    if sys.platform == "darwin":
        config.addinivalue_line("filterwarnings", "error::objc.ObjCPointerWarning")


def pytest_runtest_logreport(report):
    destination = os.environ.get("VODFORGE_NATIVE_EVIDENCE_DIR")
    if not destination:
        return
    path = Path(destination) / "native-results.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(
            json.dumps(
                {
                    "nodeid": report.nodeid,
                    "phase": report.when,
                    "outcome": report.outcome,
                    "duration_seconds": report.duration,
                    "failure": str(report.longrepr) if report.failed else None,
                }
            )
            + "\n"
        )


def pytest_sessionstart(session):
    destination = os.environ.get("VODFORGE_NATIVE_EVIDENCE_DIR")
    if not destination:
        return
    import pytest

    from .source_identity import source_manifest

    _case_snapshots.clear()
    _evidence_rows.clear()
    source_output = Path(destination)
    source_output.mkdir(parents=True, exist_ok=True)
    (source_output / "native-source-before.json").write_text(
        json.dumps(source_manifest(Path.cwd()), indent=2)
    )

    modules = {
        name: str(Path(importlib.import_module(name).__file__).resolve())
        for name in (
            "yt_downloader.app",
            "yt_downloader.product_telemetry",
            "quality_harness.native_reports",
        )
    }
    expected = {
        "source": os.environ.get("VODFORGE_NATIVE_SOURCE_ROOT"),
        "harness": os.environ.get("VODFORGE_NATIVE_HARNESS_ROOT"),
    }
    receipt = {
        "argv": sys.argv,
        "cwd": str(Path.cwd()),
        "python": sys.executable,
        "imported_modules": modules,
        "expected_roots": expected,
    }
    output = Path(destination)
    output.mkdir(parents=True, exist_ok=True)
    (output / "native-imports.json").write_text(json.dumps(receipt, indent=2) + "\n")
    for name, actual in modules.items():
        root = expected["harness" if name.startswith("quality_harness.") else "source"]
        if root and not Path(actual).is_relative_to(Path(root).resolve()):
            raise pytest.UsageError(
                f"Native evidence imported {name} outside expected root: {actual}"
            )
