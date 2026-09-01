from __future__ import annotations

import os
import signal
import subprocess  # nosec B404 - fixed local process-inspection argv only
import sys
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any


class ProcessOwnershipError(RuntimeError):
    """Raised when an abandoned child cannot be identified or stopped safely."""


class ActiveChildProcessRegistry:
    """Own live child registration, cancellation, reaping, and durable observation."""

    def __init__(self, *, diagnostic: Callable[[str], None] | None = None) -> None:
        self.processes: set[Any] = set()
        self._lock = threading.RLock()
        self._termination_lock = threading.RLock()
        self._observer: Callable[[str, Any], None] | None = None
        self._diagnostic = diagnostic or (lambda _message: None)

    def set_diagnostic(self, diagnostic: Callable[[str], None]) -> None:
        self._diagnostic = diagnostic

    @property
    def inspection_lock(self) -> threading.RLock:
        """Expose read-side synchronization for compatibility and diagnostics."""

        return self._lock

    def set_observer(self, observer: Callable[[str, Any], None] | None) -> None:
        with self._lock:
            self._observer = observer

    @staticmethod
    def has_exited(process: Any, *, confirmed_exited: bool = False) -> bool:
        if confirmed_exited:
            return True
        poll = getattr(process, "poll", None)
        return bool(callable(poll) and poll() is not None)

    def terminate_and_reap(self, process: Any, *, timeout_seconds: float) -> None:
        with self._termination_lock:
            if self.has_exited(process):
                return
            try:
                process.terminate()
            except Exception as exc:  # noqa: BLE001 - provider adapters vary
                self._diagnostic(
                    f"child process terminate request failed: {type(exc).__name__}"
                )
            try:
                process.wait(timeout=timeout_seconds)
                return
            except subprocess.TimeoutExpired:
                pass
            try:
                process.kill()
            except Exception as exc:  # noqa: BLE001 - provider adapters vary
                self._diagnostic(
                    f"child process kill request failed: {type(exc).__name__}"
                )
            try:
                process.wait(timeout=timeout_seconds)
            except subprocess.TimeoutExpired as exc:
                raise RuntimeError(
                    "Child process did not stop after terminate and kill requests"
                ) from exc

    def register(self, process: Any, *, timeout_seconds: float) -> None:
        with self._lock:
            self.processes.add(process)
            observer = self._observer
        if observer is not None:
            try:
                observer("started", process)
            except Exception:
                self.finalize(process, timeout_seconds=timeout_seconds)
                raise

    def unregister(self, process: Any) -> None:
        with self._lock:
            self.processes.discard(process)
            observer = self._observer
        if observer is not None:
            try:
                observer("exited", process)
            except Exception as exc:  # noqa: BLE001 - exit remains authoritative
                self._diagnostic(
                    "active child exit receipt could not be saved: "
                    f"{type(exc).__name__}: {exc}"
                )

    def finalize(
        self,
        process: Any,
        *,
        timeout_seconds: float,
        confirmed_exited: bool = False,
    ) -> bool:
        if self.has_exited(process, confirmed_exited=confirmed_exited):
            self.unregister(process)
            return True
        try:
            self.terminate_and_reap(process, timeout_seconds=timeout_seconds)
        except Exception as exc:  # noqa: BLE001 - retain unconfirmed ownership
            self._diagnostic(
                "active child process remains live after cleanup attempt: "
                f"{type(exc).__name__}: {exc}"
            )
        if self.has_exited(process):
            self.unregister(process)
            return True
        self._diagnostic(
            "active child process remains registered because exit could not be confirmed"
        )
        return False

    def terminate_all(
        self,
        *,
        timeout_seconds: float,
        deadline_monotonic: float | None = None,
    ) -> None:
        with self._lock:
            active = tuple(self.processes)
        for process in active:
            child_timeout = timeout_seconds
            if deadline_monotonic is not None:
                remaining = deadline_monotonic - time.monotonic()
                if remaining <= 0:
                    self._diagnostic(
                        "active child process cleanup deadline reached before every child was reaped"
                    )
                    break
                child_timeout = max(0.01, min(timeout_seconds, remaining / 2))
            try:
                self.terminate_and_reap(process, timeout_seconds=child_timeout)
            except Exception as exc:  # noqa: BLE001 - shutdown continues
                self._diagnostic(
                    f"active child process cleanup failed: {type(exc).__name__}: {exc}"
                )
            finally:
                if self.has_exited(process):
                    self.unregister(process)


ACTIVE_CHILD_PROCESS_REGISTRY = ActiveChildProcessRegistry()


def process_command(pid: int) -> str | None:
    if pid <= 1:
        return None
    if sys.platform.startswith("win"):
        command = [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            f"(Get-CimInstance Win32_Process -Filter 'ProcessId={pid}').CommandLine",
        ]
    else:
        command = ["/bin/ps", "-p", str(pid), "-o", "command="]
    try:
        completed = subprocess.run(  # nosec B603 - fixed local process inspection
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    value = completed.stdout.strip()
    return value or None


def terminate_pid(pid: int, *, timeout_seconds: float = 5.0) -> bool:
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return True
    except OSError:
        return False
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if process_command(pid) is None:
            return True
        time.sleep(0.05)
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        return True
    except OSError:
        return False
    return process_command(pid) is None


def terminate_recorded_children(
    children: Sequence[Mapping[str, Any]],
    staging_dirs: Sequence[Path],
    *,
    command_reader: Callable[[int], str | None] = process_command,
    pid_terminator: Callable[[int], bool] = terminate_pid,
) -> None:
    """Terminate only children identity- and transaction-bound by recorded argv."""

    stage_markers = [str(path) for path in staging_dirs]
    for child in children:
        pid = child.get("pid")
        if not isinstance(pid, int):
            raise ProcessOwnershipError("The active-run child record is invalid.")
        command = command_reader(pid)
        if command is None:
            continue
        argv = child.get("argv")
        expected_executable = str(argv[0]) if isinstance(argv, list) and argv else ""
        executable_identities = {expected_executable}
        if expected_executable:
            try:
                executable_identities.add(
                    str(Path(expected_executable).expanduser().resolve(strict=False))
                )
            except OSError:
                pass
        if (
            not expected_executable
            or not any(identity in command for identity in executable_identities)
            or not any(marker in command for marker in stage_markers)
        ):
            raise ProcessOwnershipError(
                f"Refusing to stop PID {pid}; its identity is not bound to the "
                "recorded VODForge staging transaction."
            )
        if not pid_terminator(pid):
            raise ProcessOwnershipError(
                f"VODForge could not stop abandoned child PID {pid}."
            )
