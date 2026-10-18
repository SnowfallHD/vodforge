"""Opt-in hidden AppKit components; no ordered window or native input."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform != "darwin" or os.environ.get("VODFORGE_NATIVE_UI_TESTS") != "1",
    reason="requires an isolated native macOS run",
)
_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def child_binding_driver(tmp_path_factory: pytest.TempPathFactory) -> Path:
    if not shutil.which("xcrun"):
        pytest.skip("Apple compiler tools unavailable")
    binary = tmp_path_factory.mktemp("header-child-native") / "driver"
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
            str(_ROOT / "tests/native/header_child_binding_driver.m"),
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
        "negative_offset",
        "same_resize",
        "update_and_mismatch",
        "foreign_reparent_fd",
        "foreign_adoption_refused",
        "partial_container_setter",
        "partial_flag_enable",
        "flag_restore_retry",
        "child_detach_first",
        "native_close_release_only",
        "update_exception_rollback",
        "child_external_release_first",
    ],
)
def test_actual_native_child_binding(child_binding_driver: Path, case: str) -> None:
    result = subprocess.run(
        [str(child_binding_driver), case],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout) == {
        "case": case,
        "passed": True,
        "hidden": True,
        "inactive": True,
    }
