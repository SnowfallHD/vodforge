"""Process identity and callback epochs must outlive a download-slot handoff."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from yt_downloader import process_lifecycle as lifecycle


def observer_binding_contract(owner):
    calls = []
    registry = owner.ActiveChildProcessRegistry()
    process = object()
    registry.set_observer(lambda event, _p: calls.append(("old", event)))
    registry.register(process, timeout_seconds=1)
    registry.set_observer(lambda event, _p: calls.append(("new", event)))
    registry.unregister(process)
    registry.unregister(process)
    assert calls == [("old", "started"), ("old", "exited")]


def reused_pid_contract(owner, monkeypatch):
    stage = Path("/fictional/output/.vfstage/owned")
    calls = []
    monkeypatch.setattr(
        owner.psutil, "Process", lambda _pid: SimpleNamespace(create_time=lambda: 2.0)
    )
    owner.terminate_recorded_children(
        [{"pid": 4321, "birth_time": 1.0, "argv": ["/owned/ffmpeg", str(stage)]}],
        [stage],
        command_reader=lambda _pid: f"/owned/ffmpeg {stage}/media.part",
        pid_terminator=lambda pid: calls.append(pid) or True,
    )
    assert (
        calls == []
    )  # same executable/staging arguments are insufficient after PID reuse


def test_registry_exit_remains_bound_to_its_admitting_observer():
    observer_binding_contract(lifecycle)


def test_reused_pid_is_never_signalled_even_with_matching_command(monkeypatch):
    reused_pid_contract(lifecycle, monkeypatch)


@pytest.mark.parametrize("birth", [None, 0, float("nan"), float("inf"), True])
def test_unverified_live_child_preserved_without_signal(birth):
    calls = []
    with pytest.raises(lifecycle.ProcessOwnershipError):
        lifecycle.terminate_recorded_children(
            [{"pid": 4321, "birth_time": birth, "argv": ["/owned/ffmpeg"]}],
            [Path("/owned/stage")],
            command_reader=lambda _pid: "/owned/ffmpeg /owned/stage",
            pid_terminator=lambda pid: calls.append(pid) or True,
        )
    assert not calls


@pytest.mark.parametrize("pid", [True, 0, -1, 1])
def test_invalid_child_identity_is_not_conclusive_absence(pid):
    with pytest.raises(lifecycle.ProcessOwnershipError):
        lifecycle.terminate_recorded_children(
            [{"pid": pid}], [], command_reader=lambda _pid: None
        )
