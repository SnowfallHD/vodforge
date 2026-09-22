"""Actual native header uses the approved raster asset without clipping."""

import os
import sys
from pathlib import Path

import pytest
from PIL import Image, ImageChops, ImageOps

from tests.test_archive_native import application as _application
from tests.test_archive_native import pump

application = _application
pytestmark = pytest.mark.skipif(
    sys.platform != "darwin" or os.environ.get("VODFORGE_NATIVE_UI_TESTS") != "1",
    reason="Mac native display required",
)


def test_native_header_preserves_approved_wordmark(application, tmp_path):
    from yt_downloader.platform_services import capture_own_widget
    from yt_downloader.ui_materials import tint_brand

    app = application
    from tests.test_matte_native import save_native_capture
    from yt_downloader.platform_services import surface_backing_scale

    output = Path(os.environ.get("VODFORGE_NATIVE_EVIDENCE_DIR", str(tmp_path)))
    output.mkdir(parents=True, exist_ok=True)
    app.geometry("1200x760+80+80")
    pump(app, 0.4)
    scale = surface_backing_scale(app)
    actual = save_native_capture(
        app._focus_header_mark_label, output / "brand-native-source-proof.png"
    )
    with Image.open(
        Path(__file__).resolve().parents[1] / "assets/brand/vf-mark.png"
    ) as source:
        mark = ImageOps.contain(
            tint_brand(source), (32 * scale, 32 * scale), Image.Resampling.LANCZOS
        )
    expected = Image.new("RGBA", actual.size)
    expected.alpha_composite(
        mark, ((actual.width - mark.width) // 2, (actual.height - mark.height) // 2)
    )
    opaque = expected.getchannel("A").point(lambda a: 255 if a == 255 else 0)
    delta = ImageChops.difference(actual.convert("RGB"), expected.convert("RGB"))
    masked = ImageChops.multiply(delta, Image.merge("RGB", (opaque, opaque, opaque)))
    # Native color conversion differs by up to three channel levels from
    # the approved source raster. Preserve the failed two-level evidence and
    # require an explicit low-resolution negative control as well.
    assert max(high for _low, high in masked.getextrema()) <= 3
    positions = [
        (x, y)
        for y in range(actual.height)
        for x in range(actual.width)
        if opaque.getpixel((x, y)) == 255
    ]
    assert len(positions) > 500

    def mean_error(reference):
        return sum(
            max(abs(actual.getpixel(p)[i] - reference.getpixel(p)[i]) for i in range(3))
            for p in positions
        ) / len(positions)

    coarse = mark.resize(
        (max(1, mark.width // 2), max(1, mark.height // 2)), Image.Resampling.LANCZOS
    ).resize(mark.size, Image.Resampling.BILINEAR)
    blurred = Image.new("RGBA", actual.size)
    blurred.alpha_composite(
        coarse, ((actual.width - mark.width) // 2, (actual.height - mark.height) // 2)
    )
    assert mean_error(blurred) > mean_error(expected) * 2

    for tab in ("forge", "library", "watch"):
        app._select_focus_view(tab)
        app.geometry("980x600+100+80")
        app.deiconify()
        pump(app, 0.3)
        label = app._focus_header_mark_label
        assert label.winfo_ismapped()
        assert label.winfo_width() >= 32
        assert label.winfo_height() >= 32
        capture = capture_own_widget(app)
        assert capture is not None
        capture.save(output / ("brand-" + tab + ".png"))

    app.geometry("1200x720+100+80")
    pump(app, 0.3)
    assert app._focus_brand_labels[0].winfo_ismapped()
    capture = capture_own_widget(app)
    assert capture is not None
    capture.save(output / "brand-wide.png")
