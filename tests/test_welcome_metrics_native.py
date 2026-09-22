"""Enabled Welcome uses its owning window's units and keeps actions reachable."""

import os
from pathlib import Path
from tkinter import font as tkfont
from tkinter import ttk

import pytest

from tests.test_archive_native import pump
from tests.test_matte_native import save_native_capture
from tests.test_root_logical_metrics_native import application as _application
from tests.test_root_logical_metrics_native import (
    metrics_application as _metrics_application,
)
from yt_downloader.ui_layout import window_logical_metrics

application = _application
metrics_application = _metrics_application
pytestmark = pytest.mark.skipif(
    os.environ.get("VODFORGE_NATIVE_UI_TESTS") != "1", reason="Native display required"
)


def test_enabled_welcome_fonts_caption_and_actions_fit(metrics_application, tmp_path):
    app, dpi = metrics_application
    app.engagement.welcome()
    panel = app.engagement.panel
    assert panel is not None
    metrics = window_logical_metrics(panel.frame)
    role = tuple(app.tk.splitlist(ttk.Style(app).lookup("FocusTitle.TLabel", "font")))
    expected = tkfont.Font(root=app, font=metrics.font(role))
    pump(app)
    actual = tkfont.Font(root=app, font=panel.title.cget("font") or role)
    assert actual.metrics("linespace") == expected.metrics("linespace")
    out = Path(os.environ.get("VODFORGE_NATIVE_EVIDENCE_DIR", str(tmp_path)))
    for width, height in ((1180, 780), (820, 560), (1180, 780)):
        app.geometry(f"{width}x{height}")
        pump(app)
        for index in range(len(panel.highlights)):
            panel.render(index)
            pump(app)
            panel._cancel_transition()
            panel._transition(10)
            pump(app)
            assert panel.frame.winfo_width() <= app.winfo_width()
            assert panel.frame.winfo_height() <= app.winfo_height()
            for widget in (panel.description, panel.title):
                assert widget.winfo_height() >= widget.winfo_reqheight(), (
                    dpi,
                    index,
                    str(widget),
                )
                assert widget.winfo_rootx() >= panel.frame.winfo_rootx()
                assert (
                    widget.winfo_rootx() + widget.winfo_width()
                    <= panel.frame.winfo_rootx() + panel.frame.winfo_width()
                )
            for widget in panel.controls:
                if widget.winfo_ismapped():
                    assert panel.surface.action_is_visible(widget), (
                        dpi,
                        width,
                        index,
                        str(widget),
                    )
                    assert widget.winfo_width() >= widget.winfo_reqwidth(), (
                        dpi,
                        width,
                        index,
                        str(widget),
                        "clipped action",
                    )
            if panel.surface.viewport is not None:
                assert panel.title.winfo_rooty() >= panel.surface.viewport.winfo_rooty()
                assert panel.title.winfo_rooty() + panel.title.winfo_height() <= (
                    panel.surface.viewport.winfo_rooty()
                    + panel.surface.viewport.winfo_height()
                )
                offset = (
                    panel.description.winfo_rooty() - panel.surface.body.winfo_rooty()
                )
                panel.surface.viewport.yview_moveto(
                    offset / panel.surface.body.winfo_height()
                )
                pump(app)
                assert (
                    panel.description.winfo_rooty()
                    >= panel.surface.viewport.winfo_rooty() - 1
                )
                assert (
                    panel.description.winfo_rooty() + panel.description.winfo_height()
                    <= (
                        panel.surface.viewport.winfo_rooty()
                        + panel.surface.viewport.winfo_height()
                    )
                )
                if index in (0, len(panel.highlights) - 1):
                    save_native_capture(
                        panel.frame, out / f"welcome-caption-{dpi}-{width}-{index}.png"
                    )
                panel.surface.viewport.yview_moveto(0)
                pump(app)
                before = panel.surface.viewport.yview()
                panel.description.event_generate("<MouseWheel>", delta=-120)
                pump(app)
                assert panel.surface.viewport.yview()[0] > before[0]
                panel.surface.viewport.yview_moveto(0)
                pump(app)
            if index == 4:
                from yt_downloader.whats_new_feature_preview import FeaturePreview

                assert isinstance(panel.activity_demo, FeaturePreview)
                eyebrow = next(
                    w
                    for w in panel.activity_demo.winfo_children()
                    if isinstance(w, ttk.Label)
                )
                role = tuple(
                    app.tk.splitlist(
                        ttk.Style(app).lookup("FocusEyebrow.TLabel", "font")
                    )
                )
                actual = tkfont.Font(root=app, font=eyebrow.cget("font"))
                expected = tkfont.Font(root=app, font=metrics.font(role))
                assert actual.metrics("linespace") == expected.metrics("linespace")
            if index in (0, len(panel.highlights) - 1):
                save_native_capture(
                    panel.frame, out / f"welcome-{dpi}-{width}-{index}.png"
                )
    panel.finish_button.invoke()
    pump(app)
    assert app.engagement.panel is None
    assert app.grab_current() is None
