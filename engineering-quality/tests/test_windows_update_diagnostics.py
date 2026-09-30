"""Failed upgrades retain useful evidence without accepting invisible apps."""

import ctypes
import subprocess
import sys
from types import SimpleNamespace

import psutil
import pytest
from quality_harness import windows_update_diagnostics as diagnostics


def test_native_enumerator_preserves_pointer_sized_handles_and_inspection_errors(
    monkeypatch,
):
    handle = 0x123456789

    class NativeCall:
        def __init__(self, call):
            self.call = call

        def __call__(self, *args):
            return self.call(*args)

    def owner(_handle, pid):
        pid._obj.value = 4321

    def title(_handle, buffer, _size):
        buffer.value = "VODForge QA"

    api = SimpleNamespace(
        EnumWindows=NativeCall(lambda visit, _: visit(handle, 0)),
        GetWindowThreadProcessId=NativeCall(owner),
        GetWindowTextW=NativeCall(title),
    )
    monkeypatch.setattr(ctypes, "WinDLL", lambda *args, **kwargs: api, raising=False)
    monkeypatch.setattr(ctypes, "WINFUNCTYPE", ctypes.CFUNCTYPE, raising=False)
    monkeypatch.setattr(
        diagnostics,
        "_verify_windows_window_identity",
        lambda hwnd, pid, name: {"window_id": hwnd, "owner_pid": pid, "title": name},
    )
    assert diagnostics.window_snapshot({4321}) == [
        {"window_id": handle, "owner_pid": 4321, "title": "VODForge QA"}
    ]
    assert diagnostics.window_snapshot({99}) == []

    def unreadable(*args):
        raise OSError("window inspection unavailable")

    monkeypatch.setattr(diagnostics, "_verify_windows_window_identity", unreadable)
    with pytest.raises(RuntimeError, match="Native window inspection failed"):
        diagnostics.window_snapshot({4321})


def test_actual_owned_process_then_confirmed_exit_is_distinguished():
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        rows, owners = diagnostics.process_snapshot(child.pid)
        assert child.pid in owners
        assert rows[0]["exe"]
        assert rows[0]["status"] != psutil.STATUS_ZOMBIE
        assert "inspection_error" not in rows[0]
    finally:
        child.terminate()
        child.wait(timeout=10)
    rows, owners = diagnostics.process_snapshot(child.pid)
    assert rows == [{"pid": child.pid, "inspection_error": "NoSuchProcess"}]


def test_unreadable_process_is_explicit_and_never_replaced_with_empty_success(
    monkeypatch,
):
    def denied(pid):
        raise psutil.AccessDenied(pid)

    monkeypatch.setattr(diagnostics.psutil, "Process", denied)
    rows, owners = diagnostics.process_snapshot(123)
    assert rows == [{"pid": 123, "inspection_error": "AccessDenied"}]
    assert owners == {123}


def test_only_bounded_isolated_logs_are_copied(tmp_path):
    run = tmp_path / "run"
    logs = run / "profile" / "VODForge" / "logs"
    logs.mkdir(parents=True)
    (logs / "activity.log").write_bytes(b"prefix" + b"last 16 bytes!!!")
    (logs / "settings.json").write_text("PRIVATE_SETTINGS")
    (logs / "cookie.log").write_text("PRIVATE_COOKIE")
    outside = tmp_path / "outside.log"
    outside.write_text("PRIVATE_OUTSIDE")
    (logs / "latest.log").symlink_to(outside)
    output = run / "failure-diagnostics"
    output.mkdir()
    rows = diagnostics.copy_isolated_logs(run, output, limit=16)
    assert rows[0] == {"name": "latest.log", "error": "outside_isolated_run"}
    assert rows[1]["copied_bytes"] == 16
    assert (output / "activity.log").read_bytes() == (
        logs / "activity.log"
    ).read_bytes()[-16:]
    assert sorted(path.name for path in output.iterdir()) == ["activity.log"]
