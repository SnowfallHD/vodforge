from __future__ import annotations

import os
import signal
from pathlib import Path
from typing import Any

import pytest
from quality_harness import e2e_provenance
from quality_harness.e2e_provenance import (
    bundle_tree_receipt,
    preexisting_vodforge_processes,
    terminate_owned_group,
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
        os, "killpg", lambda pgid, sig: killpg_calls.append((pgid, sig))
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
        os, "killpg", lambda pgid, sig: killpg_calls.append((pgid, sig))
    )

    receipt = terminate_owned_group(
        process, {"pid": 912, "pgid": 912, "create_time": 100.0}, timeout=0.25
    )

    assert receipt["attempted"] is True
    assert receipt["verified_owned"] is True
    assert receipt["survivors_after"] == []
    assert killpg_calls == [(912, signal.SIGTERM)]
    assert process.wait_calls == [0.1]
