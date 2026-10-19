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
def header_driver(tmp_path_factory: pytest.TempPathFactory) -> Path:
    if not shutil.which("xcrun"):
        pytest.skip("Apple compiler tools unavailable")
    binary = tmp_path_factory.mktemp("header-toolbar-native") / "driver"
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
            "-framework",
            "QuartzCore",
            str(_ROOT / "tests/native/header_toolbar_driver.m"),
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
        "callback",
        "brand",
        "guards",
        "duplicate_host",
        "events",
        "foreign_notification",
        "foreign",
        "window_delegate",
        "changed_toolbar_delegate",
        "changed_item_view",
        "changed_style",
        "foreign_accessory",
        "bound_subview",
        "setter_failure",
        "setter_before_failure",
    ],
)
def test_actual_native_header_toolbar_owner(header_driver: Path, case: str) -> None:
    result = subprocess.run(
        [str(header_driver), case],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout) == {
        "case": case,
        "passed": True,
        "nsapp_created": False,
    }
