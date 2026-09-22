"""Explicit support forms scale without submitting any message or review."""

import os
import tkinter as tk
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
from yt_downloader.support_diagnostics import FailureContext
from yt_downloader.ui_layout import (
    install_window_logical_metrics,
    window_logical_metrics,
)
from yt_downloader.ui_theme import FONT_UI

application = _application
metrics_application = _metrics_application
pytestmark = pytest.mark.skipif(
    os.environ.get("VODFORGE_NATIVE_UI_TESTS") != "1", reason="Native display required"
)


@pytest.mark.parametrize("kind", ["feedback", "review"])
def test_explicit_support_form_dpi_and_diagnostics(
    metrics_application, monkeypatch, tmp_path, kind
):
    app, dpi = metrics_application
    original = tk.Toplevel.__init__

    def admitted(self, *args, **kwargs):
        original(self, *args, **kwargs)
        if dpi:
            install_window_logical_metrics(self, dpi=dpi)

    monkeypatch.setattr(tk.Toplevel, "__init__", admitted)
    app.engagement.latest_failure = FailureContext(
        "Controlled QA diagnostics\n" * 40, ""
    )
    getattr(app.engagement, kind)()
    panel = app.engagement.panel
    metrics = window_logical_metrics(panel.frame)
    pump(app)
    actual = tkfont.Font(root=app, font=panel.message.cget("font"))
    expected = tkfont.Font(root=app, font=metrics.font(FONT_UI))
    assert actual.metrics("linespace") == expected.metrics("linespace")
    panel.message.insert("1.0", "Controlled local QA text; never submitted.")
    if kind == "feedback":
        panel.reply.set(True)
        panel._reply_changed()
    else:
        panel.star_buttons[2].invoke()
        assert panel.stars.get() == 3
    out = Path(os.environ.get("VODFORGE_NATIVE_EVIDENCE_DIR", str(tmp_path)))
    for width, height in ((1180, 780), (820, 560), (1180, 780)):
        app.geometry(f"{width}x{height}")
        pump(app)
        assert panel.frame.winfo_width() <= app.winfo_width()
        assert panel.frame.winfo_height() <= app.winfo_height()
        assert panel.message.winfo_height() >= actual.metrics("linespace") * 2
        for button in (panel.cancel, panel.send):
            assert panel.surface.action_is_visible(button)
            assert button.winfo_width() >= button.winfo_reqwidth()
        for widget in panel._descendants(panel.surface.body):
            if not widget.winfo_ismapped():
                continue
            assert widget.winfo_rootx() + widget.winfo_width() <= (
                panel.surface.body.winfo_rootx() + panel.surface.body.winfo_width()
            ), str(widget)
            if isinstance(widget, ttk.Label):
                assert widget.winfo_height() >= widget.winfo_reqheight()
        save_native_capture(panel.frame, out / f"support-{kind}-{dpi}-{width}.png")
    if kind == "feedback":
        panel._review_diagnostics()
        popup = next(
            w
            for w in app.winfo_children()
            if isinstance(w, tk.Toplevel) and w.title() == "Review diagnostics"
        )
        pump(app)
        document = next(w for w in panel._descendants(popup) if isinstance(w, tk.Text))
        font = tkfont.Font(root=popup, font=document.cget("font"))
        expected = tkfont.Font(
            root=popup, font=window_logical_metrics(popup).font(FONT_UI)
        )
        assert font.metrics("linespace") == expected.metrics("linespace")
        done = next(
            w
            for w in panel._descendants(popup)
            if isinstance(w, ttk.Button) and w.cget("text") == "Done"
        )
        assert (
            done.winfo_rooty() + done.winfo_height()
            <= popup.winfo_rooty() + popup.winfo_height()
        )
        document.yview_moveto(1)
        pump(app)
        save_native_capture(popup, out / f"diagnostics-{dpi}.png")
        done.invoke()
        pump(app)
        assert app.grab_current() is panel.frame
    panel.cancel.invoke()
    pump(app)
    assert app.engagement.panel is None
    assert not panel.sent and not panel.busy
