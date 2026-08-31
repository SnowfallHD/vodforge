from __future__ import annotations

import hashlib
import json
import os
import signal
import stat
import subprocess
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .util import sha256_file

E2E_ENV_KEYS = (
    "HOME",
    "XDG_DATA_HOME",
    "LOCALAPPDATA",
    "TMPDIR",
    "TMP",
    "TEMP",
    "VODFORGE_QUALITY_E2E",
    "VODFORGE_QUALITY_E2E_ISOLATION_ROOT",
    "VODFORGE_QUALITY_E2E_SESSION_NONCE",
    "VODFORGE_QUALITY_E2E_WINDOW_TOKEN",
)


def bundle_tree_receipt(bundle: Path) -> dict[str, Any]:
    """Hash the complete bundle layout without following symlinks."""
    root = bundle.resolve()
    entries: list[dict[str, Any]] = []
    for path in sorted(
        root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()
    ):
        metadata = path.lstat()
        entry: dict[str, Any] = {
            "path": path.relative_to(root).as_posix(),
            "mode": stat.S_IMODE(metadata.st_mode),
        }
        if path.is_symlink():
            entry.update({"type": "symlink", "target": os.readlink(path)})
        elif path.is_file():
            entry.update(
                {
                    "type": "file",
                    "size_bytes": metadata.st_size,
                    "sha256": sha256_file(path),
                }
            )
        elif path.is_dir():
            entry["type"] = "directory"
        else:
            entry["type"] = "other"
        entries.append(entry)
    digest = hashlib.sha256()
    for entry in entries:
        digest.update(
            json.dumps(entry, sort_keys=True, separators=(",", ":")).encode("utf-8")
        )
        digest.update(b"\n")
    return {
        "root": str(root),
        "sha256": digest.hexdigest(),
        "entry_count": len(entries),
        "file_count": sum(item["type"] == "file" for item in entries),
        "symlink_count": sum(item["type"] == "symlink" for item in entries),
    }


def _psutil() -> Any:
    try:
        import psutil
    except ImportError as exc:  # pragma: no cover - doctor installs this dependency
        raise RuntimeError("psutil is required for packaged E2E provenance") from exc
    return psutil


def _resolved(value: str | Path) -> Path:
    return Path(value).expanduser().resolve()


def _process_row(process: Any) -> dict[str, Any]:
    info = getattr(process, "info", {}) or {}
    missing = object()

    def read(name: str, fallback: Any = None) -> Any:
        value = info.get(name, missing)
        if value is not missing:
            return value
        method = getattr(process, name, None)
        return method() if callable(method) else fallback

    cmdline = read("cmdline", []) or []
    return {
        "pid": int(read("pid", getattr(process, "pid", -1))),
        "name": str(read("name", "") or ""),
        "executable": str(read("exe", "") or ""),
        "cmdline": [str(item) for item in cmdline],
        "create_time": float(read("create_time", 0.0) or 0.0),
    }


def _looks_like_vodforge(row: dict[str, Any], expected_executable: Path) -> bool:
    executable = str(row.get("executable") or "")
    command = row.get("cmdline") or []
    candidates = [str(row.get("name") or "")]
    if executable:
        candidates.append(Path(executable).name)
    if command:
        candidates.append(Path(str(command[0])).name)
    if any(value.casefold() == "vodforge" for value in candidates):
        return True
    try:
        return (
            bool(executable) and _resolved(executable) == expected_executable.resolve()
        )
    except OSError:
        return False


def preexisting_vodforge_processes(
    expected_executable: Path,
    *,
    process_iter: Any | None = None,
) -> list[dict[str, Any]]:
    """Return possible VODForge processes without mutating any of them."""
    psutil = _psutil()
    iterator = process_iter or psutil.process_iter(
        ["pid", "name", "exe", "cmdline", "create_time"]
    )
    matches: list[dict[str, Any]] = []
    for process in iterator:
        try:
            row = _process_row(process)
        except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess):
            continue
        if row["pid"] != os.getpid() and _looks_like_vodforge(row, expected_executable):
            matches.append(row)
    return sorted(matches, key=lambda item: int(item["pid"]))


def _read_private_attestation(path: Path) -> dict[str, Any]:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise RuntimeError(
            "startup attestation is not a readable no-follow file"
        ) from exc
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise RuntimeError("startup attestation is not a regular no-follow file")
        if stat.S_IMODE(metadata.st_mode) != 0o600:
            raise RuntimeError("startup attestation permissions are not 0600")
        if metadata.st_uid != os.getuid():
            raise RuntimeError("startup attestation is not owned by the E2E user")
        with os.fdopen(descriptor, "r", encoding="utf-8") as handle:
            descriptor = -1
            payload = json.load(handle)
    except (json.JSONDecodeError, OSError) as exc:
        raise RuntimeError("startup attestation is unreadable") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    if not isinstance(payload, dict):
        raise TypeError("startup attestation is not a JSON object")
    return payload


def _path_is_within(path: str | Path, root: Path) -> bool:
    try:
        _resolved(path).relative_to(root.resolve())
    except (OSError, ValueError):
        return False
    return True


def _attestation_errors(
    attestation: dict[str, Any],
    *,
    pid: int,
    ppid: int,
    executable: Path,
    session_nonce: str,
    window_token: str,
    app_version: str,
    state_paths: dict[str, str],
) -> list[str]:
    expected = {
        "schema_version": "1.0.0",
        "session_nonce": session_nonce,
        "pid": pid,
        "ppid": ppid,
        "executable": str(executable.resolve()),
        "app_version": app_version,
        "window_title": f"VODForge [{window_token}]",
        "home": state_paths["home"],
        "application_data_dir": state_paths["application_data"],
        "history_path": state_paths["history"],
        "diagnostics_dir": state_paths["diagnostics"],
        "diagnostics_path": state_paths["diagnostics_log"],
        "output_root": state_paths["output"],
        "tmp_dir": state_paths["tmp"],
    }
    errors = [
        f"attestation {key} mismatch"
        for key, value in expected.items()
        if attestation.get(key) != value
    ]
    isolation_root = _resolved(state_paths["isolation_root"])
    for key in (
        "home",
        "application_data_dir",
        "history_path",
        "diagnostics_dir",
        "diagnostics_path",
        "output_root",
        "tmp_dir",
    ):
        value = attestation.get(key)
        if not isinstance(value, str) or not _path_is_within(value, isolation_root):
            errors.append(f"attestation {key} escaped the isolation root")
    return errors


def attest_owned_launch(
    process: subprocess.Popen[bytes],
    *,
    expected_executable: Path,
    expected_executable_sha256: str,
    expected_bundle_tree_sha256: str,
    expected_app_version: str,
    expected_environment: dict[str, str],
    state_paths: dict[str, str],
    session_nonce: str,
    launch_id: str,
    launch_sequence: int,
    window_token: str,
    attestation_path: Path,
    timeout_seconds: float = 20.0,
) -> dict[str, Any]:
    """Fail closed until the direct child and app-reported state agree."""
    psutil = _psutil()
    deadline = time.monotonic() + timeout_seconds
    last_errors: list[str] = ["startup attestation has not appeared"]
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(
                f"packaged app exited before provenance verification: {process.returncode}"
            )
        try:
            observed = psutil.Process(process.pid)
            observed_executable = _resolved(observed.exe())
            observed_environment = observed.environ()
            create_time = float(observed.create_time())
            parent_pid = int(observed.ppid())
            process_group_id = int(os.getpgid(process.pid))
        except (OSError, psutil.AccessDenied, psutil.NoSuchProcess) as exc:
            last_errors = [f"live process inspection failed: {type(exc).__name__}"]
            time.sleep(0.05)
            continue

        errors: list[str] = []
        if observed_executable != expected_executable.resolve():
            errors.append("live executable path mismatch")
        elif sha256_file(observed_executable) != expected_executable_sha256:
            errors.append("live executable hash mismatch")
        if parent_pid != os.getpid():
            errors.append("live process parent mismatch")
        if process_group_id != process.pid:
            errors.append("live process group is not harness-owned")
        for key in E2E_ENV_KEYS:
            if observed_environment.get(key) != expected_environment.get(key):
                errors.append(f"live process environment mismatch: {key}")
        if not attestation_path.is_file():
            last_errors = [*errors, "startup attestation has not appeared"]
            time.sleep(0.05)
            continue
        try:
            attestation = _read_private_attestation(attestation_path)
        except RuntimeError as exc:
            last_errors = [*errors, str(exc)]
            time.sleep(0.05)
            continue
        errors.extend(
            _attestation_errors(
                attestation,
                pid=process.pid,
                ppid=parent_pid,
                executable=expected_executable,
                session_nonce=session_nonce,
                window_token=window_token,
                app_version=expected_app_version,
                state_paths=state_paths,
            )
        )
        if errors:
            last_errors = errors
            time.sleep(0.05)
            continue
        return {
            "schema_version": "1.0.0",
            "verified": True,
            "session_nonce": session_nonce,
            "launch_id": launch_id,
            "launch_sequence": launch_sequence,
            "pid": process.pid,
            "create_time": create_time,
            "ppid": parent_pid,
            "harness_pid": os.getpid(),
            "pgid": process_group_id,
            "expected_executable": str(expected_executable.resolve()),
            "observed_executable": str(observed_executable),
            "executable_sha256": expected_executable_sha256,
            "bundle_tree_sha256": expected_bundle_tree_sha256,
            "window_title": f"VODForge [{window_token}]",
            "window_token": window_token,
            "state_paths": state_paths,
            "attestation_path": str(attestation_path.resolve()),
            "attestation_sha256": sha256_file(attestation_path),
            "attestation": attestation,
        }
    raise RuntimeError(
        "packaged app provenance did not verify before driver handoff: "
        + "; ".join(dict.fromkeys(last_errors))
    )


def verify_live_launch(launch: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    psutil = _psutil()
    try:
        process = psutil.Process(int(launch["pid"]))
        observed_create_time = float(process.create_time())
        observed_executable = _resolved(process.exe())
        observed_environment = process.environ()
        observed_pgid = int(os.getpgid(int(launch["pid"])))
    except (
        KeyError,
        OSError,
        ValueError,
        psutil.AccessDenied,
        psutil.NoSuchProcess,
    ) as exc:
        return {
            "verified": False,
            "errors": [f"live launch unavailable: {type(exc).__name__}"],
        }
    if abs(observed_create_time - float(launch.get("create_time") or 0.0)) > 0.01:
        errors.append("live launch create time mismatch")
    if observed_executable != _resolved(str(launch.get("expected_executable") or "")):
        errors.append("live launch executable mismatch")
    elif sha256_file(observed_executable) != launch.get("executable_sha256"):
        errors.append("live launch executable hash mismatch")
    if observed_pgid != int(launch.get("pgid") or -1):
        errors.append("live launch process group mismatch")
    if int(process.ppid()) != int(launch.get("harness_pid") or -1):
        errors.append("live launch parent mismatch")
    expected_environment = {
        "VODFORGE_QUALITY_E2E": "1",
        "VODFORGE_QUALITY_E2E_ISOLATION_ROOT": launch.get("state_paths", {}).get(
            "isolation_root"
        ),
        "VODFORGE_QUALITY_E2E_SESSION_NONCE": launch.get("session_nonce"),
        "VODFORGE_QUALITY_E2E_WINDOW_TOKEN": launch.get("window_token"),
        "HOME": launch.get("state_paths", {}).get("home"),
        "XDG_DATA_HOME": launch.get("state_paths", {}).get("xdg_data"),
        "LOCALAPPDATA": launch.get("state_paths", {}).get("local_app_data"),
        "TMPDIR": launch.get("state_paths", {}).get("tmp"),
        "TMP": launch.get("state_paths", {}).get("tmp"),
        "TEMP": launch.get("state_paths", {}).get("tmp"),
    }
    for key, value in expected_environment.items():
        if observed_environment.get(key) != value:
            errors.append(f"live launch environment mismatch: {key}")
    attestation_path = Path(str(launch.get("attestation_path") or ""))
    try:
        attestation_hash = sha256_file(attestation_path)
    except OSError:
        errors.append("live launch attestation is unavailable")
    else:
        if attestation_hash != launch.get("attestation_sha256"):
            errors.append("live launch attestation hash mismatch")
    return {
        "verified": not errors,
        "errors": errors,
        "pid": int(launch["pid"]),
        "create_time": observed_create_time,
        "executable": str(observed_executable),
        "pgid": observed_pgid,
    }


def verify_native_window_identity(
    *, window_id: int, expected_pid: int, expected_title: str
) -> dict[str, Any]:
    """Verify one macOS window through CoreGraphics, independent of the driver."""
    if window_id <= 0 or expected_pid <= 0 or not expected_title:
        return {
            "verified": False,
            "errors": ["native window identity inputs are invalid"],
        }
    try:
        import Quartz
    except ImportError:
        return {
            "verified": False,
            "errors": ["Quartz window inspection is unavailable"],
        }
    options = (
        Quartz.kCGWindowListOptionIncludingWindow
        | Quartz.kCGWindowListExcludeDesktopElements
    )
    raw_windows = Quartz.CGWindowListCopyWindowInfo(options, window_id)

    def normalized_mapping(value: Any) -> dict[Any, Any] | None:
        if not isinstance(value, Mapping):
            return None
        try:
            return dict(value)
        except (TypeError, ValueError):
            return None

    def integer(value: Any, default: int = 0) -> int:
        try:
            return int(value)
        except (OverflowError, TypeError, ValueError):
            return default

    windows = [
        normalized
        for item in raw_windows or []
        if (normalized := normalized_mapping(item)) is not None
    ]
    matching = [
        item
        for item in windows
        if integer(item.get(Quartz.kCGWindowNumber)) == window_id
    ]
    if len(matching) != 1:
        return {
            "verified": False,
            "errors": ["native window ID was not uniquely observable"],
            "window_count": len(matching),
        }
    window = matching[0]
    owner_pid = integer(window.get(Quartz.kCGWindowOwnerPID))
    title = str(window.get(Quartz.kCGWindowName, "") or "")
    owner_name = str(window.get(Quartz.kCGWindowOwnerName, "") or "")
    layer = integer(window.get(Quartz.kCGWindowLayer), -1)
    errors = []
    if owner_pid != expected_pid:
        errors.append("native window owner PID mismatch")
    if title != expected_title:
        errors.append("native window title mismatch")
    if layer != 0:
        errors.append("native window is not an application-layer window")
    onscreen = bool(window.get(Quartz.kCGWindowIsOnscreen, False))
    if not onscreen:
        errors.append("native window is not onscreen")
    bounds = normalized_mapping(window.get(Quartz.kCGWindowBounds)) or {}
    return {
        "verified": not errors,
        "errors": errors,
        "window_id": window_id,
        "owner_pid": owner_pid,
        "owner_name": owner_name,
        "title": title,
        "layer": layer,
        "onscreen": onscreen,
        "bounds": bounds,
    }


def owned_group_survivors(launch: dict[str, Any]) -> list[dict[str, Any]]:
    psutil = _psutil()
    pgid = int(launch.get("pgid") or -1)
    launched_at = float(launch.get("create_time") or 0.0)
    survivors: list[dict[str, Any]] = []
    if pgid <= 0:
        return survivors
    for process in psutil.process_iter(
        ["pid", "name", "exe", "cmdline", "create_time"]
    ):
        try:
            if os.getpgid(process.pid) != pgid:
                continue
            row = _process_row(process)
        except (
            OSError,
            psutil.AccessDenied,
            psutil.NoSuchProcess,
            psutil.ZombieProcess,
        ):
            continue
        row["owned_create_time"] = row["create_time"] + 0.01 >= launched_at
        survivors.append(row)
    return sorted(survivors, key=lambda item: int(item["pid"]))


def terminate_owned_group(
    process: subprocess.Popen[bytes], launch: dict[str, Any], *, timeout: float = 10.0
) -> dict[str, Any]:
    """Terminate only the attested new process group; never search by app name."""
    survivors_before = owned_group_survivors(launch)
    if any(not item["owned_create_time"] for item in survivors_before):
        return {
            "attempted": False,
            "verified_owned": False,
            "survivors_before": survivors_before,
            "survivors_after": survivors_before,
            "error": "process group contains a process older than the attested launch",
        }
    if int(launch.get("pgid") or -1) != int(launch.get("pid") or -2):
        return {
            "attempted": False,
            "verified_owned": False,
            "survivors_before": survivors_before,
            "survivors_after": survivors_before,
            "error": "attested process group is not led by the launched process",
        }
    attempted = bool(survivors_before)

    def wait_until_empty(seconds: float) -> list[dict[str, Any]]:
        deadline = time.monotonic() + seconds
        remaining = owned_group_survivors(launch)
        while remaining and time.monotonic() < deadline:
            time.sleep(0.05)
            remaining = owned_group_survivors(launch)
        return remaining

    survivors_after = survivors_before
    if attempted:
        try:
            os.killpg(int(launch["pgid"]), signal.SIGTERM)
        except OSError:
            pass
        survivors_after = wait_until_empty(timeout)
        if survivors_after:
            try:
                os.killpg(int(launch["pgid"]), signal.SIGKILL)
            except OSError:
                pass
            survivors_after = wait_until_empty(timeout)
        try:
            process.wait(timeout=0.1)
        except subprocess.TimeoutExpired:
            pass
    return {
        "attempted": attempted,
        "verified_owned": True,
        "survivors_before": survivors_before,
        "survivors_after": survivors_after,
        "error": None if not survivors_after else "owned process group did not exit",
    }
