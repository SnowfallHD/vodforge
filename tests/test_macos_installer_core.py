"""Exercise production filesystem transaction code without opening installer UI."""

import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.skipif(sys.platform != "darwin", reason="Native macOS filesystem/API test")
def test_compiled_installer_transactions_in_owned_temporary_directory(tmp_path):
    source = Path(__file__).with_name("native_macos_installer_core.m")
    executable = tmp_path / "installer-core"
    subprocess.run(
        [
            "/usr/bin/clang",
            "-fobjc-arc",
            "-framework",
            "AppKit",
            "-framework",
            "Security",
            str(source),
            "-o",
            str(executable),
        ],
        check=True,
        capture_output=True,
        timeout=30,
    )
    result = subprocess.run(
        [str(executable)], check=True, capture_output=True, text=True, timeout=30
    )
    assert (
        len([line for line in result.stdout.splitlines() if line.startswith("PASS:")])
        == 10
    )
    assert "compile-time signature/running-state substitutes" in result.stdout
