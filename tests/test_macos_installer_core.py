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
    expected = {
        "automatic fresh destination is selected without mutation",
        "backup payload unchanged",
        "confirmed same-version replacement retains backup",
        "exclusive move preserves competing destination and original",
        "existing verified destination retains snapshot for explicit Replace confirmation",
        "explicit fallback folder uses the same checked destination owner",
        "fresh installation",
        "installed bytes match payload",
        "main thread services completion while worker work is serialized",
        "newer destination preflight preserves app and requires fallback",
        "newer installed version is preserved",
        "routine UI owner checks Applications without requesting a folder picker",
        "routine destination is fixed system Applications",
        "running-app admission stops installation",
        "slow worker starts without blocking the caller/main thread",
        "stale destination refuses without mutation",
        "symlinked app is refused",
        "unsafe default or fallback folder refuses before mutation",
        "unverified existing destination is preserved and requires fallback",
        "unwritable destination requires explicit fallback without mutation",
        "verification work runs off the main thread",
        "work queue serializes operations",
        "worker completion returns to main thread",
        "wrong payload hash makes no destination",
    }
    observed = [
        line.removeprefix("PASS: ")
        for line in result.stdout.splitlines()
        if line.startswith("PASS: ")
    ]
    assert len(observed) == len(set(observed)), (
        "Core assertions must have unique labels"
    )
    assert set(observed) == expected
    assert "compile-time signature/running-state substitutes" in result.stdout
