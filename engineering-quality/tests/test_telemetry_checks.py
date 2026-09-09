"""Test the harness guard itself without a production network request."""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from quality_harness.telemetry_checks import (
    _OWNERSHIP_ORIGINS,
    _validate_ownership_cases,
)


def ownership_cases():
    return [
        {
            "origin": origin,
            "statuses": [200, 200, 409, 401],
            "client_count": 1,
            "legacy": {"unchanged": True, "accepted": 0},
        }
        for origin in _OWNERSHIP_ORIGINS
    ]


def test_ownership_receipt_requires_every_entry_point():
    cases = ownership_cases()
    _validate_ownership_cases(cases)
    with pytest.raises(AssertionError, match="Incomplete"):
        _validate_ownership_cases(cases[:-1])
    with pytest.raises(AssertionError, match="Incomplete"):
        _validate_ownership_cases([])


@pytest.mark.parametrize(
    "field,value",
    [
        ("statuses", [200, 200, 200, 200]),
        ("client_count", 2),
        ("legacy", {"unchanged": False, "accepted": 0}),
        ("legacy", {"unchanged": True, "accepted": 1}),
    ],
)
def test_green_delivery_cannot_hide_ownership_failure(field, value):
    cases = ownership_cases()
    cases[1][field] = value
    with pytest.raises(AssertionError):
        _validate_ownership_cases(cases)


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
