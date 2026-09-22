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
    from yt_downloader.telemetry_features import (
        DIMENSION_CHOICES,
        DIMENSION_PATTERNS,
        DIMENSION_RANGES,
        FEATURE_ACTIONS,
        OPERATION_FEATURES,
    )

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
    for name, values in [
        ("DIMENSION_PATTERNS", DIMENSION_PATTERNS),
        ("DIMENSION_RANGES", DIMENSION_RANGES),
    ]:
        text += (
            "export const "
            + name
            + ": Record<string,unknown> = "
            + json.dumps(values)
            + ";"
            + chr(10)
        )
    from yt_downloader.failure_diagnostics import (
        ERROR_TYPES,
        FAILURE_CODES,
        FAILURE_REASONS,
        FAILURE_STAGES,
        FIRST_PARTY_MODULES,
    )

    for key, values in (
        ("FAILURE_REASONS", FAILURE_REASONS),
        ("failure_code", FAILURE_CODES),
        ("source_module", FIRST_PARTY_MODULES),
        ("source_scope", {"first_party_frame"}),
        ("stage", FAILURE_STAGES),
        ("error_type", ERROR_TYPES),
    ):
        prefix = "const " + key + " =" if key == "FAILURE_REASONS" else key + ":"
        text += prefix + " new Set(" + json.dumps(sorted(values)) + ");\n"
    text += (
        "const OPERATION_FEATURES = new Set("
        + json.dumps(sorted(OPERATION_FEATURES))
        + ");\n"
    )
    source.write_text(text)
    assert_feature_vocabulary(tmp_path)
    source.write_text(text.replace("notes_saved", "private_notes"))
    with pytest.raises(AssertionError, match="vocabulary drift"):
        assert_feature_vocabulary(tmp_path)


@pytest.mark.parametrize(
    "before,after",
    [
        ('"AttributeError"', '"UnexpectedPrivateError"'),
        ('"libvlc_backend"', '"private_module"'),
        ('"image_preparation"', '"private_stage"'),
    ],
)
def test_backend_gate_rejects_diagnostic_vocabulary_drift(tmp_path, before, after):
    from quality_harness.telemetry_checks import assert_feature_vocabulary

    # Construct a known-valid contract first. A stale unrelated checkout must not
    # cause the wrong rejection to mask the deliberate diagnostic mutation.
    test_backend_gate_rejects_feature_vocabulary_drift(tmp_path)
    source = tmp_path / "src/lib/product-telemetry.ts"
    text = source.read_text().replace("private_notes", "notes_saved")
    assert before in text
    source.write_text(text.replace(before, after, 1))
    with pytest.raises(AssertionError, match="diagnostic vocabulary drift"):
        assert_feature_vocabulary(tmp_path)
