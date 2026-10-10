from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, ClassVar

import psutil
import pytest
from quality_harness import packaged_e2e
from quality_harness import windows_e2e_platform as windows
from quality_harness.candidate_artifact import (
    create_candidate_receipt,
    load_and_verify_candidate,
    materialize_candidate_for_e2e,
    validate_candidate_archive,
)
from quality_harness.e2e_provenance import (
    bundle_tree_receipt,
    preexisting_vodforge_processes,
)
from quality_harness.util import CommandResult


def test_windows_state_is_contained_and_uses_actual_platform_directories(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(packaged_e2e.sys, "platform", "win32")
    paths = packaged_e2e._isolated_state_paths(tmp_path)
    assert paths["application_data"] == str(tmp_path / "home/AppData/Local/VODForge")
    assert paths["diagnostics"] == str(tmp_path / "home/AppData/Local/VODForge/logs")
    assert all(Path(p).is_relative_to(tmp_path) for p in paths.values())


def test_exe_name_is_admitted_by_preexisting_process_guard(tmp_path):
    class Process:
        pid = 100
        info: ClassVar[dict[str, Any]] = {
            "pid": 100,
            "name": "VODForge.exe",
            "exe": str(tmp_path / "foreign.exe"),
            "cmdline": [],
            "create_time": 1,
        }

    assert preexisting_vodforge_processes(
        tmp_path / "VODForge.exe", process_iter=[Process()]
    )


def test_foreign_windows_cleanup_token_fails_before_enumerating_or_terminating(
    monkeypatch,
):
    class Job:
        token = "owned"

        def members(self):
            raise AssertionError("Foreign job must never be queried")

    monkeypatch.setitem(windows._JOBS, 123, Job())
    with pytest.raises(RuntimeError, match="ownership token"):
        windows.owned_windows_survivors({"pid": 123, "windows_job_token": "foreign"})
    with pytest.raises(RuntimeError, match="ownership token"):
        windows.terminate_owned_windows(
            None, {"pid": 123, "windows_job_token": "foreign"}, 1
        )


def _win_archive(path, extra=None):
    import zipfile

    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("VODForge/VODForge.exe", b"executable")
        archive.writestr("VODForge/_internal/VODFORGE_VERSION", b"1.2.3")
        if extra:
            archive.writestr(extra, b"unsafe")


@pytest.mark.parametrize(
    "extra",
    [
        "VODForge/CON.txt",
        "VODForge/_internal/aux.dll",
        "VODForge/COM9.txt",
        "VODForge/file.",
        "VODForge/folder /child",
        "VODForge/file:stream",
        "VODForge/../../escape",
        "VODForge/VODFORGE.EXE",
        "VODForge.app/Contents/MacOS/VODForge",
        "__MACOSX/resource",
    ],
)
def test_windows_archive_refuses_alias_escape_and_mixed_platforms(tmp_path, extra):
    archive = tmp_path / "candidate.zip"
    _win_archive(archive, extra)
    with pytest.raises(RuntimeError):
        validate_candidate_archive(archive)


def test_windows_archive_refuses_symlinks(tmp_path):
    import stat
    import zipfile

    archive = tmp_path / "candidate.zip"
    _win_archive(archive)
    with zipfile.ZipFile(archive, "a") as z:
        member = zipfile.ZipInfo("VODForge/linked")
        member.external_attr = (stat.S_IFLNK | 0o777) << 16
        z.writestr(member, "VODForge.exe")
    with pytest.raises(RuntimeError, match="symlinks"):
        validate_candidate_archive(archive)


def test_windows_candidate_freezes_and_freshly_materializes_bound_bytes(
    tmp_path, monkeypatch
):
    from quality_harness import candidate_artifact

    repo = tmp_path / "repo"
    (repo / "engineering-quality").mkdir(parents=True)
    archive = tmp_path / "windows.zip"
    _win_archive(archive)
    monkeypatch.setattr(
        candidate_artifact,
        "machine_snapshot",
        lambda _: (
            {"system": "Windows"},
            {"commit": "a" * 40, "branch": "main", "status_porcelain": []},
        ),
    )

    def inspect(artifact, repo_root, policy):
        return {
            "platform": "windows",
            "artifact": str(artifact),
            "artifact_policy": policy,
            "bundle_tree": bundle_tree_receipt(artifact),
            "bundle_version": "1.2.3",
            "runtime_version": "1.2.3",
            "policy_verified": True,
            "release_eligible": True,
        }

    path, receipt = create_candidate_receipt(
        archive,
        repo_root=repo,
        candidate_root=repo / "engineering-quality/candidates",
        candidate_version="1.2.3",
        artifact_policy="release",
        build_command=["build-windows"],
        artifact_inspector=inspect,
    )
    assert load_and_verify_candidate(path)["publish_eligible"] is True
    first = Path(receipt["artifact"]["artifact"]) / "VODForge.exe"
    first.write_bytes(b"prior extraction mutation")
    artifact, binding = materialize_candidate_for_e2e(path, tmp_path / "fresh")
    assert (artifact / "VODForge.exe").read_bytes() == b"executable"
    assert binding["verified"] is True


@pytest.mark.parametrize(
    "defect",
    [None, "signature", "publisher", "timestamp", "version", "revision", "probe"],
)
def test_windows_release_identity_fails_closed_on_each_boundary(
    tmp_path, monkeypatch, defect
):
    artifact = tmp_path / "VODForge"
    internal = artifact / "_internal"
    internal.mkdir(parents=True)
    for name in (
        "VODForge.exe",
        "_internal/ffmpeg.exe",
        "_internal/ffprobe.exe",
        "_internal/deno.exe",
    ):
        (artifact / name).write_bytes(b"fixture")
    (internal / "VODFORGE_VERSION").write_text("1.2.3")
    (internal / "VODFORGE_BUILD_REVISION").write_text(
        "b" * 40 if defect == "revision" else "a" * 40
    )
    monkeypatch.setattr(windows.sys, "platform", "win32")
    monkeypatch.setenv("SystemRoot", str(tmp_path))
    facts = {
        "status": "Invalid" if defect == "signature" else "Valid",
        "timestamp": defect != "timestamp",
        "subject": 'O="Other"'
        if defect == "publisher"
        else 'CN="Kryden Ventures, LLC", O="Kryden Ventures, LLC"',
        "version": "9.9.9" if defect == "version" else "1.2.3",
    }

    def run(argv, **kwargs):
        if "-EncodedCommand" in argv:
            output = json.dumps(facts)
            code = 0
        elif argv[0] == "git":
            output = "a" * 40
            code = 0
        else:
            output = "ffprobe version fixture"
            code = 1 if defect == "probe" else 0
        return CommandResult(argv, code, 0.01, output, "", False)

    monkeypatch.setattr(windows, "run_command", run)
    result = windows.windows_artifact_receipt(artifact, tmp_path, "release")
    assert result["verified"] is (defect is None)
    assert result["release_eligible"] is (defect is None)


@pytest.mark.skipif(
    sys.platform != "win32", reason="requires actual Windows job kernel"
)
def test_windows_job_keeps_orphan_child_and_cleanup_preserves_unrelated_process(
    tmp_path,
):
    sentinel = subprocess.Popen(
        [sys.executable, "-c", "import time;time.sleep(90)"], stdin=subprocess.DEVNULL
    )
    pid_path = tmp_path / "child.pid"
    child_script = "import time;time.sleep(90)"
    parent_script = f"import subprocess,sys,pathlib; p=subprocess.Popen([sys.executable,'-c',{child_script!r}]); pathlib.Path({str(pid_path)!r}).write_text(str(p.pid))"
    owned = windows.launch_owned_windows(
        Path(sys.executable),
        os.environ.copy(),
        subprocess.DEVNULL,
        subprocess.DEVNULL,
        arguments=["-c", parent_script],
    )
    launch = {"pid": owned.pid, "windows_job_token": windows.job_token(owned.pid)}
    try:
        owned.wait(timeout=15)
        child_pid = int(pid_path.read_text())
        assert child_pid in {r["pid"] for r in windows.owned_windows_survivors(launch)}
        receipt = windows.terminate_owned_windows(owned, launch, 10)
        assert receipt["verified_owned"] and receipt["survivors_after"] == []
        assert sentinel.poll() is None
        assert not psutil.pid_exists(child_pid)
    finally:
        windows.terminate_owned_windows(owned, launch, 10)
        windows.close_owned_windows_job(launch)
        sentinel.kill()
        sentinel.wait(timeout=10)
