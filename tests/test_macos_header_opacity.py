import json
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


@pytest.fixture(scope="module")
def screen_visibility_driver(tmp_path_factory):
    from pathlib import Path

    binary = tmp_path_factory.mktemp("header-screen-visibility") / "driver"
    source = Path(__file__).with_name("native") / "header_screen_visibility_driver.m"
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
            str(source),
            "-o",
            str(binary),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    return binary


def read_screen_visibility(driver, case):
    result = subprocess.run(
        [str(driver), case],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    value = json.loads(result.stdout)
    assert value["nsapp_nil"] is True
    return value


@pytest.mark.parametrize(
    ("case", "status", "bounds"),
    [
        ("single", 1, [70, 20, 20, 44]),
        ("adjacent", 1, [70, 20, 60, 44]),
        ("adjacent-reversed", 1, [70, 20, 60, 44]),
        ("vertical-negative", 1, [-80, -20, 44, 60]),
        ("mirrored", 1, [20, 20, 60, 44]),
        ("overlap", 1, [40, 20, 80, 44]),
        # Bounds enclose the fragments; they are not a painted region or hit mask.
        ("gap", 1, [70, 20, 80, 44]),
        ("inside-gap", 2, [0, 0, 0, 0]),
        ("staggered", 1, [70, 0, 60, 64]),
        ("clipped", 1, [0, 20, 40, 44]),
        ("offscreen", 2, [0, 0, 0, 0]),
        ("no-screens", 2, [0, 0, 0, 0]),
        ("alpha-zero", 2, [0, 0, 0, 0]),
        ("hidden", 2, [0, 0, 0, 0]),
    ],
)
def test_public_screen_intersections_without_gui(
    screen_visibility_driver, case, status, bounds
):
    result = read_screen_visibility(screen_visibility_driver, case)["visibility"]
    assert result == {"status": status, "bounds": bounds}


def test_native_multiscreen_visibility_preserves_packet_clearance(
    screen_visibility_driver,
):
    from yt_downloader.qt_quick.mac_header_packet import NativeRowRefused, packet

    result = read_screen_visibility(screen_visibility_driver, "packet")
    assert result["host"]["status"] == 1
    sample = {
        "owner": "unified-toolbar",
        "current": True,
        "host_visible": result["host"]["status"] == 1,
        "toolbar_owned": True,
        "delegate_unchanged": True,
        "full_size": True,
        "transparent": True,
        "title_hidden": True,
        "transition": 0,
        "fullscreen": True,
        "host": [0, 40, 180, 44],
        "content": [0, 0, 200, 100],
        "buttons": [
            {
                "identity": i + 1,
                "visibility": {0: "unknown", 1: "visible", 2: "hidden"}[
                    visibility["status"]
                ],
                "visible_screen": visibility["bounds"],
                "screen_bounds": [20 + 23 * i, 55, 14, 14],
            }
            for i, visibility in enumerate(result["buttons"])
        ],
    }
    layout = packet(sample, 44, 1, 10)
    assert layout["host_visible"] is True
    assert layout["state"] == "controls-visible"
    assert layout["leading"] == layout["reserve"] == 90
    # The bounding envelope never authorizes coordinates outside real controls.
    sample["buttons"][1]["visible_screen"][2] += 1
    with pytest.raises(NativeRowRefused, match="current full bounds"):
        packet(sample, 44, 2, 10)
