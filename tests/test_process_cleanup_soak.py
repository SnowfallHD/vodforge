"""Real OS children must settle across repeated work and abandoned-run recovery."""

from __future__ import annotations

import gc
import json
import os
import subprocess
import sys
import time
import weakref
from pathlib import Path

import psutil
import pytest

from yt_downloader import app as app_module
from yt_downloader.process_lifecycle import process_command
from yt_downloader.run_state import ActiveRunStore, recover_interrupted_run


def _handles(process: psutil.Process) -> int:
    return process.num_handles() if sys.platform == "win32" else process.num_fds()


@pytest.mark.parametrize("outcome", ["complete", "cancel", "timeout"])
def test_repeated_capture_reaps_children_and_releases_resources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, outcome: str
) -> None:
    original = subprocess.Popen
    pids: list[int] = []
    references: list[weakref.ReferenceType] = []

    def observed(*args, **kwargs):
        child = original(*args, **kwargs)
        pids.append(child.pid)
        references.append(weakref.ref(child))
        return child

    monkeypatch.setattr(app_module.subprocess, "Popen", observed)
    parent = psutil.Process()
    before_handles = _handles(parent)
    before_rss = parent.memory_info().rss
    samples = []
    for _cycle in range(12):
        command = [
            sys.executable,
            "-c",
            "print('done')" if outcome == "complete" else "import time; time.sleep(30)",
        ]

        def cancelled():
            raise RuntimeError("synthetic cancellation")

        if outcome == "complete":
            assert (
                app_module.run_cancellable_process_capture(
                    command, timeout_seconds=10, check=True
                ).stdout.strip()
                == "done"
            )
        else:
            expected = (
                RuntimeError if outcome == "cancel" else subprocess.TimeoutExpired
            )
            with pytest.raises(expected):
                app_module.run_cancellable_process_capture(
                    command,
                    timeout_seconds=0.03 if outcome == "timeout" else 10,
                    control_check=cancelled if outcome == "cancel" else None,
                )
        assert all(not psutil.pid_exists(pid) for pid in pids)
        # Windows communicate() uses pipe-reader threads; OS exit precedes
        # their final reference release. Require bounded settling, not zero
        # scheduler latency, and do not permit live children during it.
        deadline = time.monotonic() + 2
        while True:
            gc.collect()
            if all(reference() is None for reference in references):
                break
            assert time.monotonic() < deadline, "Child resources did not settle"
            time.sleep(0.01)
        assert all(reference() is None for reference in references)
        with app_module._ACTIVE_CHILD_PROCESS_LOCK:
            assert not app_module._ACTIVE_CHILD_PROCESSES
        samples.append({"rss": parent.memory_info().rss, "handles": _handles(parent)})

    assert max(sample["handles"] for sample in samples) <= before_handles + 4
    assert samples[-1]["rss"] <= before_rss + 32 * 1024 * 1024
    receipt = {"outcome": outcome, "children_reaped": len(pids), "samples": samples}
    (tmp_path / "process-cleanup.json").write_text(
        json.dumps(receipt), encoding="utf-8"
    )
    if destination := os.environ.get("VODFORGE_PROCESS_EVIDENCE_DIR"):
        target = Path(destination)
        target.mkdir(parents=True, exist_ok=True)
        (target / f"capture-{outcome}.json").write_text(
            json.dumps(receipt, indent=2), encoding="utf-8"
        )


def test_repeated_actual_abandoned_children_are_stopped_before_staging_cleanup(
    tmp_path: Path,
) -> None:
    checkout = Path(__file__).resolve().parents[1]
    pids = []
    for cycle in range(5):
        root = tmp_path / str(cycle)
        root.mkdir()
        code = """
import os, subprocess, sys
import psutil
from pathlib import Path
from tests.test_run_state import _job
from yt_downloader.run_state import ActiveRunStore
root=Path(sys.argv[1])
job=_job(root)
store=ActiveRunStore(root/'active-run.json')
store.begin(job)
stage=root/'.vfstage'/'deadbeef'
stage.mkdir(parents=True)
(stage/'source.mp4').write_bytes(b'partial fixture')
store.add_staging_dir(job.run_id,stage)
# Framework Python rewrites a venv launcher argv after startup on macOS.
# Use the actual native executable so the recorded identity stays stable.
child=subprocess.Popen([psutil.Process().exe(),'-c','import time; time.sleep(30)',str(stage)],
    stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
store.child_started(child.pid,child.args)
os._exit(0)
"""
        subprocess.run(
            [sys.executable, "-c", code, str(root)],
            cwd=checkout,
            check=True,
            timeout=20,
        )
        store = ActiveRunStore(root / "active-run.json")
        payload = store.load()
        child_pid = payload["children"][0]["pid"]
        pids.append(child_pid)
        assert process_command(child_pid) is not None
        recovered = recover_interrupted_run(store)
        assert len(recovered) == 1
        assert recovered[0].terminal_status == "Paused"
        assert not (root / ".vfstage" / "deadbeef").exists()
        assert all(process_command(pid) is None for pid in pids)

    if destination := os.environ.get("VODFORGE_PROCESS_EVIDENCE_DIR"):
        target = Path(destination)
        target.mkdir(parents=True, exist_ok=True)
        (target / "abandoned-children.json").write_text(
            json.dumps({"cycles": len(pids), "live_children_after": 0}, indent=2),
            encoding="utf-8",
        )
