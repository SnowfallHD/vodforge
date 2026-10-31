"""Native header materials must render upright in AppKit's flipped views.

The header draws the shared Qt button image (`action_button_image`) with
NSImage nine-part drawing, which ignores `respectFlipped`. A previous version
rendered it upside down: raised buttons looked sunken and the pressed button's
shadow flipped. This compiles header_items.m and checks real drawn pixels.
"""

import ctypes
import io
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

pytestmark = pytest.mark.skipif(
    sys.platform != "darwin" or shutil.which("xcrun") is None,
    reason="AppKit drawing requires macOS",
)


@pytest.fixture(scope="module")
def library(tmp_path_factory):
    out = tmp_path_factory.mktemp("header-items") / "libheaderitems.dylib"
    subprocess.run(
        [
            "/usr/bin/xcrun",
            "clang",
            "-dynamiclib",
            "-fno-objc-arc",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-framework",
            "AppKit",
            "-framework",
            "Foundation",
            str(ROOT / "yt_downloader/platforms/macos/header_items.m"),
            "-o",
            str(out),
        ],
        check=True,
        capture_output=True,
    )
    lib = ctypes.CDLL(str(out))
    lib.vf_toolbar_probe_material.restype = ctypes.c_int
    lib.vf_toolbar_probe_material.argtypes = [
        ctypes.c_char_p,
        ctypes.c_size_t,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_char_p,
    ]
    return lib


@pytest.mark.parametrize("state", ["normal", "pressed"])
def test_button_material_draws_upright_in_flipped_view(library, state):
    from PIL import Image

    from yt_downloader.visual_chrome import action_button_image

    width, height, scale = 105, 44, 2
    source = action_button_image(
        width, height, accent=False, state=state, density=scale
    )
    png = io.BytesIO()
    source.save(png, format="PNG")
    data = png.getvalue()
    pw, ph = width * scale, height * scale
    buffer = ctypes.create_string_buffer(pw * ph * 4)
    assert library.vf_toolbar_probe_material(
        data, len(data), width, height, 14, pw, ph, buffer
    )
    drawn = Image.frombuffer("RGBA", (pw, ph), buffer.raw, "raw", "RGBA", 0, 1)

    def profile(image, column):
        flat = Image.new("RGBA", image.size, (47, 43, 54, 255))
        flat.alpha_composite(image.convert("RGBA"))
        gray = flat.convert("L")
        return [gray.getpixel((column, y)) for y in range(image.height)]

    reference = source.convert("RGBA").resize((pw, ph))
    for column in (20, pw // 2):
        got, upright = profile(drawn, column), profile(reference, column)
        flipped = upright[::-1]
        upright_error = sum(abs(a - b) for a, b in zip(got, upright)) / ph
        flipped_error = sum(abs(a - b) for a, b in zip(got, flipped)) / ph
        assert upright_error < 1.5, (column, upright_error)
        assert upright_error < flipped_error, (column, upright_error, flipped_error)
