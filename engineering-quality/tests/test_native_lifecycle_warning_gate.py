"""The native reporter rejects lifecycle failures even with passing assertions."""

import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    "fault",
    [
        "none",
        "finalizer",
        "worker",
        pytest.param(
            "bridge",
            marks=pytest.mark.skipif(
                sys.platform != "darwin", reason="macOS color reference bridge"
            ),
        ),
    ],
)
def test_native_plugin_lifecycle_warning_gate(tmp_path, fault):
    bodies = {
        "none": "def test_case():\n    assert True\n",
        "finalizer": (
            "def test_case():\n"
            "    class Retired:\n"
            "        def __del__(self):\n"
            "            raise RuntimeError('unexpected finalizer failure')\n"
            "    retired = Retired()\n"
            "    del retired\n"
            "    assert True\n"
        ),
        "bridge": (
            "def test_case():\n"
            "    from AppKit import NSColor\n"
            "    NSColor.colorWithCalibratedWhite_alpha_(0.035, 0.96).CGColor()\n"
        ),
        "worker": (
            "def test_case():\n"
            "    from threading import Thread\n"
            "    def work():\n"
            "        raise RuntimeError('unexpected worker failure')\n"
            "    worker = Thread(target=work)\n"
            "    worker.start()\n"
            "    worker.join()\n"
            "    assert True\n"
        ),
    }
    source = tmp_path / "test_case.py"
    source.write_text(bodies[fault])
    repo = Path(__file__).resolve().parents[2]
    env = {
        **os.environ,
        "PYTHONPATH": os.pathsep.join([str(repo), str(repo / "engineering-quality")]),
    }
    env.pop("VODFORGE_NATIVE_EVIDENCE_DIR", None)
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-p",
            "quality_harness.native_reports",
            str(source),
            "-q",
            "-c",
            os.devnull,
        ],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == (0 if fault == "none" else 1), (
        result.stdout + result.stderr
    )
    if fault == "bridge":
        assert "ObjCPointerWarning" in result.stdout
    elif fault != "none":
        assert (
            "unexpected " + ("finalizer" if fault == "finalizer" else "worker")
            in result.stdout
        )
