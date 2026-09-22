"""Local conversion dialog owns its DPI, caption wrapping and preview backing."""

import os
import tkinter as tk
from pathlib import Path
from tkinter import font as tkfont
from tkinter import ttk

import pytest
from PIL import Image

from tests.test_archive_native import pump
from tests.test_matte_native import save_native_capture
from tests.test_root_logical_metrics_native import application as _application
from tests.test_root_logical_metrics_native import (
    metrics_application as _metrics_application,
)
from yt_downloader.platform_services import surface_backing_scale
from yt_downloader.ui_layout import (
    install_window_logical_metrics,
    window_logical_metrics,
)

application = _application
metrics_application = _metrics_application
pytestmark = pytest.mark.skipif(
    os.environ.get("VODFORGE_NATIVE_UI_TESTS") != "1", reason="Native display required"
)


def test_local_conversion_owns_fonts_and_native_preview(
    metrics_application, monkeypatch, tmp_path
):
    app, dpi = metrics_application
    original = tk.Toplevel.__init__

    def admitted(self, *args, **kwargs):
        original(self, *args, **kwargs)
        if dpi:
            install_window_logical_metrics(self, dpi=dpi)

    monkeypatch.setattr(tk.Toplevel, "__init__", admitted)
    app._show_local_audio_video()
    dialog = app._local_audio_video_dialog
    popup = dialog.popup
    metrics = window_logical_metrics(popup)

    def descendants(widget):
        for child in widget.winfo_children():
            yield child
            yield from descendants(child)

    title = next(
        w
        for w in descendants(popup)
        if isinstance(w, ttk.Label) and w.cget("text") == "Create MP4 from audio"
    )
    pump(app)
    role = tuple(app.tk.splitlist(ttk.Style(app).lookup("FocusTitle.TLabel", "font")))
    expected = tkfont.Font(root=popup, font=metrics.font(role))
    actual = tkfont.Font(root=popup, font=title.cget("font") or role)
    assert actual.metrics("linespace") == expected.metrics("linespace")
    out = Path(os.environ.get("VODFORGE_NATIVE_EVIDENCE_DIR", str(tmp_path)))
    for width, height in (popup.minsize(), (1180, 900), popup.minsize()):
        popup.geometry(f"{width}x{height}")
        pump(app)
        for widget in descendants(dialog.dialog_surface.body):
            if isinstance(widget, ttk.Label):
                assert widget.winfo_height() >= widget.winfo_reqheight(), str(widget)
            if widget.winfo_ismapped():
                assert widget.winfo_rootx() >= dialog.dialog_surface.body.winfo_rootx()
                assert widget.winfo_rootx() + widget.winfo_width() <= (
                    dialog.dialog_surface.body.winfo_rootx()
                    + dialog.dialog_surface.body.winfo_width()
                ), str(widget)
        for button in (dialog.cancel_button, dialog.create_button):
            assert dialog.dialog_surface.action_is_visible(button)
            assert button.winfo_width() >= button.winfo_reqwidth()
        assert dialog.create_button.instate(["disabled"])
        viewport = dialog.dialog_surface.viewport
        if viewport is not None:
            before = viewport.yview()
            title.event_generate("<MouseWheel>", delta=-120)
            pump(app)
            assert viewport.yview()[0] > before[0]
            viewport.yview_moveto(1)
            pump(app)
            assert (
                dialog.destination_entry.winfo_rooty()
                + dialog.destination_entry.winfo_height()
                <= (viewport.winfo_rooty() + viewport.winfo_height())
            )
            save_native_capture(popup, out / f"local-audio-bottom-{dpi}-{width}.png")
            viewport.yview_moveto(0)
            pump(app)
    for shape in ((800, 400), (400, 800)):
        path = tmp_path / f"preview-{shape[0]}.png"
        Image.new("RGB", shape, "#347abc").save(path)
        assert dialog._render_preview(path)
        pump(app)
        assert (dialog._preview_image.width(), dialog._preview_image.height()) == (
            metrics.px(166),
            metrics.px(92),
        )
        if surface_backing_scale(popup) > 1:
            assert app.tk.call("image", "type", str(dialog._preview_image)) == "nsimage"
    # Requested text widths are not authoritative while a popup is hidden.
    copy = next(
        w
        for w in descendants(popup)
        if isinstance(w, ttk.Label) and int(w.cget("wraplength") or 0) > 0
    )
    popup.withdraw()
    pump(app)
    old_wrap = copy.cget("wraplength")
    copy.event_generate("<Configure>", width=1, height=1)
    pump(app)
    assert copy.cget("wraplength") == old_wrap
    popup.deiconify()
    pump(app)
    save_native_capture(popup, out / f"local-audio-{dpi}.png")
    dialog.cancel_button.invoke()
    pump(app)
    assert app._local_audio_video_dialog is None
