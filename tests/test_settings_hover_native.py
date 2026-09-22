"""Actual Settings footer material transitions through native ttk bindings."""

import os
import tkinter as tk
from pathlib import Path
from tkinter import ttk

import pytest
from PIL import ImageChops

from tests.test_archive_native import pump
from tests.test_root_logical_metrics_native import (
    application as _application,
)
from tests.test_root_logical_metrics_native import (
    metrics_application as _metrics_application,
)
from yt_downloader.platform_services import capture_own_widget

application = _application
metrics_application = _metrics_application

pytestmark = pytest.mark.skipif(
    os.environ.get("VODFORGE_NATIVE_UI_TESTS") != "1", reason="Native display required"
)


def test_settings_done_and_secondary_hover_return(
    metrics_application, monkeypatch, tmp_path
):
    app, dpi = metrics_application
    from yt_downloader.ui_layout import install_window_logical_metrics

    original = tk.Toplevel

    class AdmittedPopup(original):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            if dpi:
                install_window_logical_metrics(self, dpi=dpi)

    monkeypatch.setattr(tk, "Toplevel", AdmittedPopup)
    app._show_focus_settings()
    dialog = app._focus_settings_dialog
    pump(app)
    out = Path(os.environ.get("VODFORGE_NATIVE_EVIDENCE_DIR", str(tmp_path)))
    for text in ("Done", "Preview metadata"):
        button = next(
            w
            for w in dialog.dialog_surface.footer.winfo_children()
            if isinstance(w, ttk.Button) and w.cget("text") == text
        )
        button.state(["!focus", "!pressed", "!active"])
        pump(app, 0.08)
        idle = capture_own_widget(button).convert("RGB")
        button.event_generate("<Enter>")
        pump(app, 0.08)
        assert button.instate(["active"])
        hover = capture_own_widget(button).convert("RGB")
        idle.save(out / f"footer-{dpi}-{text}-idle.png")
        hover.save(out / f"footer-{dpi}-{text}-hover.png")
        assert ImageChops.difference(idle, hover).getbbox(), text
        button.event_generate("<Leave>")
        pump(app, 0.08)
        assert not button.instate(["active"])
        returned = capture_own_widget(button).convert("RGB")
        assert ImageChops.difference(idle, returned).getbbox() is None, text
    button = next(
        w
        for w in dialog.dialog_surface.footer.winfo_children()
        if isinstance(w, ttk.Button) and w.cget("text") == "Done"
    )
    button.invoke()
    pump(app)
    assert app._focus_settings_dialog is None


@pytest.mark.skipif(
    __import__("sys").platform != "darwin", reason="macOS native pointer"
)
def test_mac_settings_done_physical_pointer(application, tmp_path):
    import Quartz
    from AppKit import NSWorkspace
    from quality_harness.native_input import hit_test_pid

    from yt_downloader.platform_services import request_window_foreground

    app = application
    app._show_focus_settings()
    dialog = app._focus_settings_dialog
    pump(app)
    request_window_foreground(dialog.popup)
    pump(app)
    done = next(
        w
        for w in dialog.dialog_surface.footer.winfo_children()
        if isinstance(w, ttk.Button) and w.cget("text") == "Done"
    )
    neutral = (dialog.popup.winfo_rootx() + 10, dialog.popup.winfo_rooty() + 80)
    center = (
        done.winfo_rootx() + done.winfo_width() / 2,
        done.winfo_rooty() + done.winfo_height() / 2,
    )

    def move(point):
        assert (
            NSWorkspace.sharedWorkspace().frontmostApplication().processIdentifier()
            == os.getpid()
        )
        assert hit_test_pid(point) == os.getpid(), (
            "Owned button is occluded; no pointer input sent"
        )
        event = Quartz.CGEventCreateMouseEvent(
            None, Quartz.kCGEventMouseMoved, point, Quartz.kCGMouseButtonLeft
        )
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)
        pump(app, 0.15)

    out = Path(os.environ.get("VODFORGE_NATIVE_EVIDENCE_DIR", str(tmp_path)))
    move(neutral)
    idle = capture_own_widget(done).convert("RGB")
    move(center)
    assert done.instate(["active"])
    hover = capture_own_widget(done).convert("RGB")
    move(neutral)
    returned = capture_own_widget(done).convert("RGB")
    for name, image in [("idle", idle), ("hover", hover), ("return", returned)]:
        image.save(out / f"mac-done-physical-{name}.png")
    assert ImageChops.difference(idle, hover).getbbox()
    assert ImageChops.difference(idle, returned).getbbox() is None
    dialog.close()
