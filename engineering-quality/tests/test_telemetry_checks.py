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


def test_backend_gate_rejects_feature_vocabulary_drift(tmp_path):
    import json

    from quality_harness.telemetry_checks import assert_feature_vocabulary

    from yt_downloader.product_telemetry import PRODUCT_EVENT_NAMES
    from yt_downloader.telemetry_features import DIMENSION_CHOICES, FEATURE_ACTIONS

    source = tmp_path / "src/lib/product-telemetry.ts"
    source.parent.mkdir(parents=True)
    text = (
        "export const PRODUCT_EVENT_NAMES = "
        + json.dumps(sorted(PRODUCT_EVENT_NAMES))
        + " as const;\n"
    )
    for name, values in [
        ("FEATURE_ACTIONS", FEATURE_ACTIONS),
        ("DIMENSION_CHOICES", DIMENSION_CHOICES),
    ]:
        text += (
            "export const "
            + name
            + ": Record<string, readonly string[]> = "
            + json.dumps({key: sorted(value) for key, value in values.items()})
            + ";\n"
        )
    source.write_text(text)
    assert_feature_vocabulary(tmp_path)
    source.write_text(text.replace("notes_saved", "private_notes"))
    with pytest.raises(AssertionError, match="vocabulary drift"):
        assert_feature_vocabulary(tmp_path)
