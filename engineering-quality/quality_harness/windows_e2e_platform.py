"""Windows artifact inspection and OS-owned process cleanup for packaged QA.

No input or product state is owned here. The existing recorder owns observations.
"""

from __future__ import annotations

import base64
import ctypes as C
import json
import os
import re
import subprocess  # nosec B404
import sys
import time
import uuid
from pathlib import Path
from typing import Any

from .util import run_command, sha256_file


def windows_artifact_receipt(
    artifact: Path, repo_root: Path, policy: str
) -> dict[str, Any]:
    from .e2e_provenance import bundle_tree_receipt

    if policy not in {"development", "release"}:
        raise ValueError("Unsupported Windows artifact policy")
    if sys.platform != "win32":
        raise RuntimeError("Authenticode artifact inspection requires Windows")
    executable = artifact / "VODForge.exe"
    internal = artifact / "_internal"
    version_path = internal / "VODFORGE_VERSION"
    revision_path = internal / "VODFORGE_BUILD_REVISION"
    dependencies = {
        name: internal / (name + ".exe") for name in ("ffmpeg", "ffprobe", "deno")
    }
    if any(
        not p.is_file() or p.is_symlink()
        for p in [executable, version_path, revision_path, *dependencies.values()]
    ):
        raise RuntimeError("Windows packaged artifact is incomplete")
    # Encode fixed PowerShell code and one literal path; never interpolate a shell command.
    literal = "'" + str(executable).replace("'", "''") + "'"
    script = (
        "$ErrorActionPreference='Stop';$p="
        + literal
        + ";$s=Get-AuthenticodeSignature -LiteralPath $p;@{status=[string]$s.Status;subject=$s.SignerCertificate.Subject;timestamp=($null -ne $s.TimeStamperCertificate);version=(Get-Item -LiteralPath $p).VersionInfo.ProductVersion}|ConvertTo-Json -Compress"
    )
    powershell = (
        Path(os.environ["SystemRoot"])
        / "System32/WindowsPowerShell/v1.0/powershell.exe"
    )
    check = run_command(
        [
            str(powershell),
            "-NoProfile",
            "-EncodedCommand",
            base64.b64encode(script.encode("utf-16le")).decode(),
        ],
        cwd=repo_root,
        timeout=60,
    )
    facts = json.loads(check.stdout) if check.returncode == 0 else {}
    version = version_path.read_text(encoding="utf-8").strip()
    revision = revision_path.read_text(encoding="utf-8").strip()
    commit = run_command(
        ["git", "rev-parse", "HEAD"], cwd=repo_root, timeout=15
    ).stdout.strip()
    publisher = 'O="Kryden Ventures, LLC"' in str(facts.get("subject") or "")
    signature = (
        facts.get("status") == "Valid" and facts.get("timestamp") is True and publisher
    )
    bundle_version = version.split("-", 1)[0]
    consistent = facts.get("version") == bundle_version and bool(
        re.fullmatch(r"\d+\.\d+\.\d+(?:-[a-zA-Z0-9.-]+)?", version)
    )
    revision_verified = (
        bool(re.fullmatch(r"[a-f0-9]{40}", revision)) and revision == commit
    )
    probe = run_command(
        [str(dependencies["ffprobe"]), "-version"], cwd=repo_root, timeout=30
    )
    eligible = signature and consistent and revision_verified and probe.returncode == 0
    # Development archives may be unsigned, but never become release eligible.
    verified = (
        eligible
        if policy == "release"
        else consistent and revision_verified and probe.returncode == 0
    )
    return {
        "artifact_policy": policy,
        "platform": "windows",
        "artifact": str(artifact),
        "executable": str(executable),
        "executable_sha256": sha256_file(executable),
        "bundle_tree": bundle_tree_receipt(artifact),
        "bundle_version": bundle_version,
        "runtime_version": version,
        "runtime_version_sha256": sha256_file(version_path),
        "build_revision": revision,
        "build_revision_verified": revision_verified,
        "version_consistent": consistent,
        "identity_verified": signature,
        "release_identity_verified": signature,
        "signature_state": "authenticode" if signature else "invalid_or_unsigned",
        "authenticode": facts,
        "checks": {"authenticode": check.as_dict()},
        "bundled_ffprobe": {
            "path": str(dependencies["ffprobe"]),
            "sha256": sha256_file(dependencies["ffprobe"]),
            "version": probe.as_dict(),
            "runnable": probe.returncode == 0,
        },
        "bundled_dependencies": {
            name: {"path": str(p), "sha256": sha256_file(p)}
            for name, p in dependencies.items()
        },
        "policy_verified": verified,
        "release_eligible": eligible,
        "verified": verified,
    }


class _JobAPI:
    """Win32 calls are initialized only on Windows, including pointer widths."""

    def __init__(self):
        if sys.platform != "win32":
            raise RuntimeError("Windows job ownership requires Windows")
        from ctypes import wintypes as W

        self.dll = C.WinDLL("kernel32", use_last_error=True)
        for name, args, result in (
            ("CreateJobObjectW", [C.c_void_p, W.LPCWSTR], W.HANDLE),
            (
                "SetInformationJobObject",
                [W.HANDLE, C.c_int, C.c_void_p, W.DWORD],
                W.BOOL,
            ),
            ("AssignProcessToJobObject", [W.HANDLE, W.HANDLE], W.BOOL),
            (
                "QueryInformationJobObject",
                [W.HANDLE, C.c_int, C.c_void_p, W.DWORD, C.c_void_p],
                W.BOOL,
            ),
            ("TerminateJobObject", [W.HANDLE, W.UINT], W.BOOL),
            ("CloseHandle", [W.HANDLE], W.BOOL),
            ("OpenThread", [W.DWORD, W.BOOL, W.DWORD], W.HANDLE),
            ("ResumeThread", [W.HANDLE], W.DWORD),
        ):
            f = getattr(self.dll, name)
            f.argtypes = args
            f.restype = result

        class Basic(C.Structure):
            _fields_ = [
                ("process_time", C.c_int64),
                ("job_time", C.c_int64),
                ("flags", W.DWORD),
                ("minimum", C.c_size_t),
                ("maximum", C.c_size_t),
                ("active", W.DWORD),
                ("affinity", C.c_size_t),
                ("priority", W.DWORD),
                ("scheduling", W.DWORD),
            ]

        class Extended(C.Structure):
            _fields_ = [
                ("basic", Basic),
                ("io", C.c_uint64 * 6),
                ("process_memory", C.c_size_t),
                ("job_memory", C.c_size_t),
                ("peak_process_memory", C.c_size_t),
                ("peak_job_memory", C.c_size_t),
            ]

        self.Extended = Extended

    def require(self, ok):
        if not ok:
            raise C.WinError(C.get_last_error())

    def create(self):
        handle = self.dll.CreateJobObjectW(None, None)
        self.require(handle)
        limits = self.Extended()
        limits.basic.flags = 0x2000  # KILL_ON_JOB_CLOSE; no breakaway.
        try:
            self.require(
                self.dll.SetInformationJobObject(
                    handle, 9, C.byref(limits), C.sizeof(limits)
                )
            )
        except Exception:
            self.close(handle)
            raise
        return handle

    def assign_and_resume(self, handle, process):
        import psutil

        self.require(self.dll.AssignProcessToJobObject(handle, int(process._handle)))
        threads = psutil.Process(process.pid).threads()
        if len(threads) != 1:
            raise RuntimeError(
                "Suspended QA process must have exactly one initial thread"
            )
        thread = self.dll.OpenThread(2, False, threads[0].id)
        self.require(thread)
        try:
            if self.dll.ResumeThread(thread) != 1:
                raise RuntimeError(
                    "QA process initial thread was not suspended exactly once"
                )
        finally:
            self.close(thread)

    def members(self, handle):
        # Query all OS job members, including children whose parent already exited.
        for capacity in (64, 1024, 16384):

            class PIDs(C.Structure):
                _fields_ = [
                    ("assigned", C.c_uint32),
                    ("count", C.c_uint32),
                    ("ids", C.c_size_t * capacity),
                ]

            data = PIDs()
            if self.dll.QueryInformationJobObject(
                handle, 3, C.byref(data), C.sizeof(data), None
            ):
                return [int(data.ids[i]) for i in range(data.count)]
            if C.get_last_error() != 234:  # ERROR_MORE_DATA
                self.require(False)
        raise RuntimeError("QA job membership exceeded the bounded query size")

    def terminate(self, handle):
        self.require(self.dll.TerminateJobObject(handle, 1))

    def close(self, handle):
        self.require(self.dll.CloseHandle(handle))


class OwnedWindowsJob:
    def __init__(self, process, api, handle):
        self.process = process
        self.api = api
        self.handle = handle
        self.token = uuid.uuid4().hex

    def members(self):
        return self.api.members(self.handle)

    def close(self):
        self.api.close(self.handle)


_JOBS: dict[int, OwnedWindowsJob] = {}


def launch_owned_windows(executable, environment, stdout, stderr, *, arguments=None):
    api = _JobAPI()
    handle = api.create()
    process = None
    try:
        # Assignment while suspended prevents a child from escaping before ownership.
        process = subprocess.Popen(
            [str(executable), *(arguments or [])],  # nosec B603
            cwd=executable.parent,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=stdout,
            stderr=stderr,
            creationflags=0x4,
        )
        api.assign_and_resume(handle, process)
        job = OwnedWindowsJob(process, api, handle)
        _JOBS[process.pid] = job
        return process
    except Exception:
        # Only this newly created, still suspended child can be terminated here.
        if process is not None:
            process.kill()
            process.wait(timeout=10)
        api.close(handle)
        raise


def job_token(pid):
    if pid not in _JOBS:
        raise RuntimeError("QA process has no harness-owned Windows job")
    return _JOBS[pid].token


def _owned_job(launch):
    job = _JOBS.get(int(launch["pid"]))
    if job is None or launch.get("windows_job_token") != job.token:
        raise RuntimeError(
            "Windows cleanup ownership token does not match this harness"
        )
    return job


def owned_windows_survivors(launch):
    import psutil

    job = _owned_job(launch)
    rows = []
    for pid in job.members():
        try:
            p = psutil.Process(pid)
            rows.append(
                {
                    "pid": pid,
                    "name": p.name(),
                    "exe": p.exe(),
                    "create_time": p.create_time(),
                    "owned_create_time": True,
                }
            )
        except psutil.NoSuchProcess:
            continue
    return rows


def terminate_owned_windows(process, launch, timeout):
    job = _owned_job(launch)
    if process is not job.process:
        raise RuntimeError(
            "Windows cleanup process handle does not belong to the launch"
        )
    before = owned_windows_survivors(launch)
    if before:
        job.api.terminate(job.handle)
    deadline = time.monotonic() + timeout
    while job.members() and time.monotonic() < deadline:
        time.sleep(0.05)
    after = owned_windows_survivors(launch)
    process.wait(timeout=1)
    return {
        "attempted": bool(before),
        "verified_owned": True,
        "survivors_before": before,
        "survivors_after": after,
        "error": None if not after else "owned Windows job did not exit",
    }


def close_owned_windows_job(launch):
    job = _owned_job(launch)
    if job.members():
        raise RuntimeError("Refusing to retire a QA job with surviving processes")
    job.close()
    del _JOBS[int(launch["pid"])]
