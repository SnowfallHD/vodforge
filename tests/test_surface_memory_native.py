"""Native RSS must plateau independently of the declared image cache."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform != "darwin" or os.environ.get("VODFORGE_NATIVE_UI_TESTS") != "1",
    reason="Mac native resource evidence required",
)


WORKLOAD_NAMES = (
    ["normal", "long_scale3", "heldout_scale1", "heldout_scale2"]
    if os.environ.get("VODFORGE_NATIVE_PROFILE") == "deep"
    else ["normal"]
)


@pytest.mark.parametrize("workload_name", WORKLOAD_NAMES)
def test_surface_replacement_native_memory_plateaus(tmp_path, workload_name):
    checkout = Path(__file__).resolve().parents[1]
    output = Path(os.environ.get("VODFORGE_NATIVE_EVIDENCE_DIR", str(tmp_path))) / (
        "surface-memory.json"
        if workload_name == "normal"
        else f"surface-memory-{workload_name}.json"
    )
    code = (
        "from Foundation import NSUserDefaults;"
        "NSUserDefaults.standardUserDefaults().registerDefaults_"
        "({'ApplePersistenceIgnoreState':True,'NSQuitAlwaysKeepsWindows':False});"
        "from quality_harness.native_surface_memory import run_probe;"
        "from pathlib import Path;"
        f"report=run_probe(Path({str(output)!r}), {workload_name!r});"
        "raise SystemExit(0 if report['evaluation']['status']=='passed' else 1)"
    )
    result = subprocess.run(
        [sys.executable, "-c", code, "-ApplePersistenceIgnoreState", "YES"],
        cwd=checkout,
        env={
            **os.environ,
            "PYTHONPATH": os.pathsep.join(
                [str(checkout), str(checkout / "engineering-quality")]
            ),
        },
        capture_output=True,
        text=True,
        timeout=140 if workload_name != "normal" else 60,
        check=False,
    )
    assert output.exists(), result.stdout + result.stderr
    report = json.loads(output.read_text())
    assert result.returncode == 0, report["evaluation"]
    assert report["evaluation"]["status"] == "passed", report["evaluation"]
