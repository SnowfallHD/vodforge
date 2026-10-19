import subprocess
import sys

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform != "darwin", reason="Public AppKit opacity consumer"
)


@pytest.fixture(scope="module")
def opacity_driver(tmp_path_factory):
    from pathlib import Path

    binary = tmp_path_factory.mktemp("header-opacity") / "driver"
    source = Path(__file__).with_name("native") / "header_opacity_driver.m"
    r = subprocess.run(
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
            str(source),
            "-o",
            str(binary),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert r.returncode == 0, r.stderr
    return binary


@pytest.mark.parametrize(
    "case",
    [
        "alpha_zero",
        "ancestor_zero",
        "layer_zero",
        "presentation_positive",
        "presentation_zero",
        "positive",
    ],
)
def test_public_opacity_consumer_without_gui(opacity_driver, case):
    r = subprocess.run(
        [str(opacity_driver), case],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert r.returncode == 0, r.stderr
    assert "NSApp=nil" in r.stdout
