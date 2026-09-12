from __future__ import annotations

import os
import signal
import sys
from collections.abc import Iterator, Mapping
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from quality_harness import e2e_provenance
from quality_harness.e2e_provenance import (
    bundle_tree_receipt,
    preexisting_vodforge_processes,
    terminate_owned_group,
    verify_native_window_identity,
)


class _ProcessDouble:
    def __init__(self, info: dict[str, Any]) -> None:
        self.info = info
        self.pid = int(info["pid"])
        self.mutation_attempts: list[str] = []

    def kill(self) -> None:
        self.mutation_attempts.append("kill")

    def terminate(self) -> None:
        self.mutation_attempts.append("terminate")


class _PsutilDouble:
    class AccessDenied(Exception):
        pass

    class NoSuchProcess(Exception):
        pass

    class ZombieProcess(Exception):
        pass


class _PopenDouble:
    def __init__(self) -> None:
        self.wait_calls: list[float] = []

    def wait(self, timeout: float) -> int:
        self.wait_calls.append(timeout)
        return 0


class _NSDictionaryLike(Mapping[str, Any]):
    """Exercise the Mapping contract used by PyObjC without being a dict."""

    def __init__(self, values: dict[str, Any]) -> None:
        self._values = values

    def __getitem__(self, key: str) -> Any:
        return self._values[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._values)

    def __len__(self) -> int:
        return len(self._values)


def test_bundle_tree_receipt_detects_same_size_bundle_mutation(tmp_path: Path) -> None:
    bundle = tmp_path / "VODForge.app"
    executable = bundle / "Contents" / "MacOS" / "VODForge"
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"first-build")
    first = bundle_tree_receipt(bundle)

    executable.write_bytes(b"other-build")
    second = bundle_tree_receipt(bundle)

    assert executable.stat().st_size == len(b"first-build")
    assert first["entry_count"] == second["entry_count"]
    assert first["sha256"] != second["sha256"]


def test_preexisting_scan_is_read_only_and_finds_unrelated_vodforge(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    expected = (
        tmp_path / "candidate" / "VODForge.app" / "Contents" / "MacOS" / "VODForge"
    )
    candidate = _ProcessDouble(
        {
            "pid": 40102,
            "name": "VODForge",
            "exe": "/Applications/VODForge.app/Contents/MacOS/VODForge",
            "cmdline": ["/Applications/VODForge.app/Contents/MacOS/VODForge"],
            "create_time": 11.0,
        }
    )
    benign = _ProcessDouble(
        {
            "pid": 40103,
            "name": "python",
            "exe": "/usr/bin/python3",
            "cmdline": ["python3", "worker.py"],
            "create_time": 12.0,
        }
    )
    monkeypatch.setattr(e2e_provenance, "_psutil", lambda: _PsutilDouble)

    matches = preexisting_vodforge_processes(expected, process_iter=[benign, candidate])

    assert [item["pid"] for item in matches] == [40102]
    assert candidate.mutation_attempts == []
    assert benign.mutation_attempts == []


def test_owned_cleanup_refuses_group_with_prelaunch_process(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    process = _PopenDouble()
    older = {
        "pid": 811,
        "create_time": 99.0,
        "owned_create_time": False,
    }
    killpg_calls: list[tuple[int, signal.Signals]] = []
    monkeypatch.setattr(
        e2e_provenance, "owned_group_survivors", lambda _launch: [older]
    )
    monkeypatch.setattr(
        os,
        "killpg",
        lambda pgid, sig: killpg_calls.append((pgid, sig)),
        raising=False,
    )

    receipt = terminate_owned_group(process, {"pgid": 811, "create_time": 100.0})

    assert receipt["attempted"] is False
    assert receipt["verified_owned"] is False
    assert "older" in receipt["error"]
    assert killpg_calls == []
    assert process.wait_calls == []


def test_owned_cleanup_signals_only_attested_process_group(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    process = _PopenDouble()
    owned = {
        "pid": 912,
        "create_time": 100.0,
        "owned_create_time": True,
    }
    survivor_snapshots = iter([[owned], [owned], []])
    killpg_calls: list[tuple[int, signal.Signals]] = []
    monkeypatch.setattr(
        e2e_provenance,
        "owned_group_survivors",
        lambda _launch: next(survivor_snapshots),
    )
    monkeypatch.setattr(
        os,
        "killpg",
        lambda pgid, sig: killpg_calls.append((pgid, sig)),
        raising=False,
    )

    receipt = terminate_owned_group(
        process, {"pid": 912, "pgid": 912, "create_time": 100.0}, timeout=0.25
    )

    assert receipt["attempted"] is True
    assert receipt["verified_owned"] is True
    assert receipt["survivors_after"] == []
    assert killpg_calls == [(912, signal.SIGTERM)]
    assert process.wait_calls == [0.1]


def test_native_window_identity_uses_core_graphics_owner_and_title(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_quartz = SimpleNamespace(
        kCGWindowListOptionIncludingWindow=1,
        kCGWindowListExcludeDesktopElements=2,
        kCGWindowNumber="number",
        kCGWindowOwnerPID="pid",
        kCGWindowName="title",
        kCGWindowOwnerName="owner",
        kCGWindowLayer="layer",
        kCGWindowIsOnscreen="onscreen",
        kCGWindowBounds="bounds",
        CGWindowListCopyWindowInfo=lambda _options, _window_id: [
            {
                "number": 55,
                "pid": 987,
                "title": "VODForge [VFQ-0123456789ab-L1]",
                "owner": "VODForge",
                "layer": 0,
                "onscreen": True,
                "bounds": {"X": 10, "Y": 20, "Width": 800, "Height": 600},
            }
        ],
    )
    monkeypatch.setitem(sys.modules, "Quartz", fake_quartz)
    monkeypatch.setattr(e2e_provenance.sys, "platform", "darwin")

    receipt = verify_native_window_identity(
        window_id=55,
        expected_pid=987,
        expected_title="VODForge [VFQ-0123456789ab-L1]",
    )

    assert receipt["verified"] is True
    assert receipt["owner_pid"] == 987
    assert receipt["onscreen"] is True

    mismatch = verify_native_window_identity(
        window_id=55,
        expected_pid=988,
        expected_title="VODForge [VFQ-0123456789ab-L1]",
    )
    assert mismatch["verified"] is False
    assert mismatch["errors"] == ["native window owner PID mismatch"]


def test_native_window_identity_accepts_pyobjc_mapping_semantics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bounds = _NSDictionaryLike({"X": 10, "Y": 20, "Width": 800, "Height": 600})
    window = _NSDictionaryLike(
        {
            "number": 55,
            "pid": 987,
            "title": "VODForge [VFQ-0123456789ab-L1]",
            "owner": "VODForge",
            "layer": 0,
            "onscreen": True,
            "bounds": bounds,
        }
    )
    fake_quartz = SimpleNamespace(
        kCGWindowListOptionIncludingWindow=1,
        kCGWindowListExcludeDesktopElements=2,
        kCGWindowNumber="number",
        kCGWindowOwnerPID="pid",
        kCGWindowName="title",
        kCGWindowOwnerName="owner",
        kCGWindowLayer="layer",
        kCGWindowIsOnscreen="onscreen",
        kCGWindowBounds="bounds",
        CGWindowListCopyWindowInfo=lambda _options, _window_id: [
            {"number": object()},
            window,
        ],
    )
    monkeypatch.setitem(sys.modules, "Quartz", fake_quartz)
    monkeypatch.setattr(e2e_provenance.sys, "platform", "darwin")

    receipt = verify_native_window_identity(
        window_id=55,
        expected_pid=987,
        expected_title="VODForge [VFQ-0123456789ab-L1]",
    )

    assert not isinstance(window, dict)
    assert not isinstance(bounds, dict)
    assert receipt["verified"] is True
    assert receipt["window_id"] == 55
    assert receipt["owner_pid"] == 987
    assert receipt["bounds"] == {
        "X": 10,
        "Y": 20,
        "Width": 800,
        "Height": 600,
    }


@pytest.mark.skipif(sys.platform != "win32", reason="real Windows window required")
def test_windows_native_identity_rejects_wrong_owner_title_and_hidden_window() -> None:
    import ctypes
    import tkinter as tk
    from ctypes import wintypes

    root = tk.Tk()
    root.title("VODForge native provenance regression")
    root.geometry("400x200+40+40")
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
    user32.GetAncestor.restype = wintypes.HWND
    try:
        root.update()
        hwnd = user32.GetAncestor(root.winfo_id(), 2)
        assert (
            verify_native_window_identity(
                window_id=hwnd, expected_pid=os.getpid(), expected_title=root.title()
            )["verified"]
            is True
        )
        assert (
            verify_native_window_identity(
                window_id=hwnd,
                expected_pid=os.getpid() + 1,
                expected_title=root.title(),
            )["verified"]
            is False
        )
        assert (
            verify_native_window_identity(
                window_id=hwnd, expected_pid=os.getpid(), expected_title="Wrong title"
            )["verified"]
            is False
        )
        root.withdraw()
        root.update()
        assert (
            verify_native_window_identity(
                window_id=hwnd, expected_pid=os.getpid(), expected_title=root.title()
            )["verified"]
            is False
        )
    finally:
        root.destroy()


@pytest.mark.skipif(sys.platform != "win32", reason="real Windows process required")
def test_windows_live_process_binding_retains_parent_time_environment_and_hash(
    tmp_path: Path,
) -> None:
    import json
    import subprocess
    import time

    from quality_harness.util import sha256_file

    state_paths = {
        key: str(tmp_path / key)
        for key in ("isolation_root", "home", "xdg_data", "local_app_data", "tmp")
    }
    env = dict(os.environ)
    env.update(
        {
            "VODFORGE_QUALITY_E2E": "1",
            "VODFORGE_QUALITY_E2E_ISOLATION_ROOT": state_paths["isolation_root"],
            "VODFORGE_QUALITY_E2E_SESSION_NONCE": "test-nonce",
            "VODFORGE_QUALITY_E2E_WINDOW_TOKEN": "test-token",
            "HOME": state_paths["home"],
            "XDG_DATA_HOME": state_paths["xdg_data"],
            "LOCALAPPDATA": state_paths["local_app_data"],
            "TMPDIR": state_paths["tmp"],
            "TMP": state_paths["tmp"],
            "TEMP": state_paths["tmp"],
        }
    )
    process = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)"], env=env
    )
    try:
        time.sleep(0.5)
        observed = e2e_provenance._psutil().Process(process.pid)
        executable = Path(observed.exe()).resolve()
        attestation = tmp_path / "attestation.json"
        attestation.write_text(json.dumps({"fixture": "process binding only"}))
        assert (
            e2e_provenance._read_private_attestation(attestation)["fixture"]
            == "process binding only"
        )
        launch = {
            "pid": process.pid,
            "create_time": observed.create_time(),
            "expected_executable": str(executable),
            "executable_sha256": sha256_file(executable),
            "pgid": None,
            "harness_pid": os.getpid(),
            "state_paths": state_paths,
            "session_nonce": "test-nonce",
            "window_token": "test-token",
            "attestation_path": str(attestation),
            "attestation_sha256": sha256_file(attestation),
        }
        assert e2e_provenance.verify_live_launch(launch)["verified"] is True
        for key, value in (
            ("harness_pid", 1),
            ("create_time", 1.0),
            ("session_nonce", "wrong"),
            ("executable_sha256", "wrong"),
        ):
            assert (
                e2e_provenance.verify_live_launch({**launch, key: value})["verified"]
                is False
            )
    finally:
        process.terminate()
        process.wait(timeout=5)
