"""Actual child process interruption and fresh interpreter recovery."""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from yt_downloader import history


@pytest.mark.parametrize(
    "boundary", ["normal-control", "accepted-journal", "saved-before-retirement"]
)
def test_process_death_preserves_accepted_history(tmp_path, boundary):
    script = Path(__file__).parents[1] / "fixtures" / "history_journal_child.py"
    repo = Path(__file__).parents[2]
    env = {**os.environ, "PYTHONPATH": str(repo), "VODFORGE_DISABLE_TELEMETRY": "1"}
    marker = tmp_path / "boundary"
    errors = tmp_path / "child-stderr"
    with errors.open("w") as err:
        process = subprocess.Popen(
            [sys.executable, str(script), str(tmp_path), boundary],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=err,
            cwd=repo,
            env=env,
        )
        try:
            deadline = time.monotonic() + 5
            while (
                not marker.exists()
                and time.monotonic() < deadline
                and process.poll() is None
            ):
                time.sleep(0.02)
            assert marker.exists(), errors.read_text()
            ledger = tmp_path / "history.json"
            original = json.loads(ledger.read_text())["items"]
            assert {r["id"] for r in original} == (
                {"first"} if boundary == "accepted-journal" else {"first", "second"}
            )
            if boundary == "normal-control":
                assert process.wait(3) == 0
            else:
                assert history.pending_history_path(ledger).is_file()
                process.kill()
                assert process.wait(3) != 0
            # A distinct new interpreter owns recovery, with no inherited state.
            code = "import json,sys; from pathlib import Path; from yt_downloader.history import load_history; print(json.dumps(load_history(Path(sys.argv[1]))))"
            recovery = subprocess.run(
                [sys.executable, "-c", code, str(ledger)],
                capture_output=True,
                text=True,
                timeout=5,
                cwd=repo,
                env=env,
                check=False,
            )
            assert recovery.returncode == 0, recovery.stderr
            actual = json.loads(recovery.stdout)
            assert len(actual) == 2
            assert {r["id"]: r["title"] for r in actual} == {
                "first": "Original preserved",
                "second": "Accepted pending",
            }
            assert history.load_history(ledger) == actual
            assert not history.pending_history_path(ledger).exists()
            assert not list(tmp_path.glob("*.mp4"))
        finally:
            if process.poll() is None:
                process.kill()
            process.wait(3)
