"""Compile and exercise actual Objective-C owner without creating a GUI app."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform != "darwin", reason="Public AppKit native owner"
)
_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def native_driver(tmp_path_factory: pytest.TempPathFactory) -> Path:
    if not shutil.which("xcrun"):
        pytest.skip("Apple compiler tools unavailable")
    binary = tmp_path_factory.mktemp("window-controls-native") / "driver"
    result = subprocess.run(
        [
            "xcrun",
            "clang",
            "-fno-objc-arc",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-framework",
            "AppKit",
            str(_ROOT / "tests/native/window_controls_driver.m"),
            "-o",
            str(binary),
        ],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return binary


@pytest.mark.parametrize(
    "case",
    [
        "basic",
        "bounds_finite",
        "foreign_recovery",
        "replacement",
        "setter_failure",
        "flipped_resize",
        "close_late",
        "reparent_reconcile",
        "reparent_stale_close",
        "wrong_thread",
        "diagnostics",
        "support_basic",
        "support_resize",
        "support_failure",
        "support_reset",
        "support_guards",
        "support_child_failure",
        "support_native_close",
        "support_residual",
        "support_foreign_recovery",
        "support_inverse_failure",
        "support_replacement",
        "support_necessary_growth",
        "support_thread",
    ],
)
def test_actual_native_window_control_owner(native_driver: Path, case: str) -> None:
    result = subprocess.run(
        [str(native_driver), case],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout) == {
        "case": case,
        "passed": True,
        "gui_created": False,
    }
