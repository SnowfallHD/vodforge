from __future__ import annotations

from pathlib import Path

import pytest

from yt_downloader.process_lifecycle import (
    ActiveChildProcessRegistry,
    ProcessOwnershipError,
    terminate_recorded_children,
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


def test_recorded_child_rejects_reused_pid_without_staging_identity() -> None:
    with pytest.raises(ProcessOwnershipError, match="Refusing to stop PID 321"):
        terminate_recorded_children(
            [{"pid": 321, "argv": ["/bundle/ffmpeg"]}],
            [],
            command_reader=lambda _pid: "/bundle/ffmpeg unrelated.mp4",
            pid_terminator=lambda _pid: pytest.fail("must not terminate"),
        )


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
