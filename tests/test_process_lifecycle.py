from __future__ import annotations

import signal
from pathlib import Path
from types import SimpleNamespace

import psutil
import pytest

from yt_downloader import process_lifecycle as lifecycle
from yt_downloader.process_lifecycle import (
    ActiveChildProcessRegistry,
    ProcessOwnershipError,
    terminate_recorded_children,
)


@pytest.mark.parametrize("condition", ["dead", "live", "denied", "empty"])
def test_process_inspection_distinguishes_dead_from_unreadable(monkeypatch, condition):
    def native_process(pid):
        if condition == "dead":
            raise psutil.NoSuchProcess(pid)
        if condition == "denied":
            raise psutil.AccessDenied(pid)
        return SimpleNamespace(
            is_running=lambda: True,
            status=lambda: psutil.STATUS_RUNNING,
            cmdline=lambda: (
                ["/owned/ffmpeg", "stage/input.mp4"] if condition == "live" else []
            ),
        )

    monkeypatch.setattr(psutil, "Process", native_process)
    monkeypatch.setattr(
        lifecycle.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(
            stdout="/owned/ffmpeg stage/input.mp4" if condition == "live" else "",
        ),
    )
    if condition in {"denied", "empty"}:
        with pytest.raises(ProcessOwnershipError):
            lifecycle.process_command(321)
    else:
        assert lifecycle.process_command(321) == (
            "/owned/ffmpeg stage/input.mp4" if condition == "live" else None
        )


def test_recorded_child_requires_exact_executable_and_staging_identity() -> None:
    terminated: list[int] = []
    stage = Path("/output/.vfstage/transaction")

    terminate_recorded_children(
        [
            {
                "pid": 321,
                "argv": ["/bundle/ffmpeg", "-i", f"{stage}/source.mp4"],
            }
        ],
        [stage],
        command_reader=lambda _pid: f"/bundle/ffmpeg -i {stage}/source.mp4",
        pid_terminator=lambda pid: terminated.append(pid) is None or True,
    )

    assert terminated == [321]


def test_signalled_orphan_waits_for_conclusive_exit_after_transient_denial(monkeypatch):
    signals = []
    reads = iter([ProcessOwnershipError("transient exit inspection"), None])

    def command(_pid):
        value = next(reads)
        if isinstance(value, Exception):
            raise value
        return value

    monkeypatch.setattr(lifecycle, "process_command", command)
    monkeypatch.setattr(
        lifecycle.os, "kill", lambda pid, sig: signals.append((pid, sig))
    )
    monkeypatch.setattr(lifecycle.time, "sleep", lambda _seconds: None)
    assert lifecycle.terminate_pid(321) is True
    assert signals == [(321, signal.SIGTERM)]


def test_persistent_exit_inspection_denial_never_authorizes_sigkill(monkeypatch):
    signals = []
    clock = iter([0.0, 6.0])

    def unreadable(_pid):
        raise ProcessOwnershipError("persistent inspection denial")

    monkeypatch.setattr(lifecycle, "process_command", unreadable)
    monkeypatch.setattr(lifecycle.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(
        lifecycle.os, "kill", lambda pid, sig: signals.append((pid, sig))
    )
    with pytest.raises(ProcessOwnershipError, match="persistent inspection denial"):
        lifecycle.terminate_pid(321)
    assert signals == [(321, signal.SIGTERM)]


def test_sigkill_exit_is_also_confirmed_after_transient_denial(monkeypatch):
    # This fully mocked POSIX escalation also runs on Windows, which has no SIGKILL.
    monkeypatch.setattr(signal, "SIGKILL", 9, raising=False)
    signals = []
    reads = iter(["owned fixture", ProcessOwnershipError("exit inspection"), None])
    clock = iter([0.0, 6.0, 6.0, 6.1])

    def command(_pid):
        value = next(reads)
        if isinstance(value, Exception):
            raise value
        return value

    monkeypatch.setattr(lifecycle, "process_command", command)
    monkeypatch.setattr(lifecycle.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(
        lifecycle.os, "kill", lambda pid, sig: signals.append((pid, sig))
    )
    monkeypatch.setattr(lifecycle.time, "sleep", lambda _seconds: None)
    assert lifecycle.terminate_pid(321) is True
    assert signals == [(321, signal.SIGTERM), (321, signal.SIGKILL)]


def test_recorded_child_rejects_reused_pid_without_staging_identity() -> None:
    with pytest.raises(ProcessOwnershipError, match="Refusing to stop PID 321"):
        terminate_recorded_children(
            [{"pid": 321, "argv": ["/bundle/ffmpeg"]}],
            [],
            command_reader=lambda _pid: "/bundle/ffmpeg unrelated.mp4",
            pid_terminator=lambda _pid: pytest.fail("must not terminate"),
        )


def test_recorded_child_accepts_resolved_executable_identity(
    tmp_path: Path,
) -> None:
    real = tmp_path / "real-ffmpeg"
    alias = tmp_path / "ffmpeg"
    real.write_bytes(b"")
    alias.symlink_to(real)
    stage = tmp_path / ".vfstage" / "transaction"
    terminated: list[int] = []

    terminate_recorded_children(
        [{"pid": 654, "argv": [str(alias), str(stage / "input.mp4")]}],
        [stage],
        command_reader=lambda _pid: f"{real.resolve()} {stage / 'input.mp4'}",
        pid_terminator=lambda pid: terminated.append(pid) is None or True,
    )

    assert terminated == [654]


def test_registry_observes_process_before_and_after_confirmed_exit() -> None:
    events: list[tuple[str, int]] = []
    registry = ActiveChildProcessRegistry()
    registry.set_observer(
        lambda event, process: events.append((event, int(process.pid)))
    )

    class Process:
        pid = 4321

        @staticmethod
        def poll() -> int:
            return 0

    process = Process()

    registry.register(process, timeout_seconds=0.1)
    assert registry.finalize(process, timeout_seconds=0.1) is True

    assert events == [("started", 4321), ("exited", 4321)]
    assert registry.processes == set()
