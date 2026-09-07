"""Test the harness guard itself without a production network request."""

import os
import subprocess
import sys
from pathlib import Path


def test_guard_detects_swallowed_production_attempt_before_network():
    root = Path(__file__).resolve().parents[2]
    code = """
import sys
from quality_harness.telemetry_checks import install_telemetry_guard, isolation_receipt
install_telemetry_guard()
assert isolation_receipt()[0]['status']=='passed'
try:
    sys.audit('urllib.Request','https://getvodforge.com/api/funnel/launch',None,{},'POST')
except RuntimeError:
    pass
else:
    raise AssertionError('guard did not reject')
assert isolation_receipt()[0]['status']=='failed'
sys.audit('urllib.Request','http://127.0.0.1:12345/events',None,{},'POST')
"""
    env = {**os.environ, "PYTHONPATH": str(root / "engineering-quality")}
    result = subprocess.run(
        [sys.executable, "-c", code],
        check=False,
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
