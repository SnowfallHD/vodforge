"""First mapping and ancestor motion must reconcile existing surface geometry."""

import os
import tkinter as tk
from pathlib import Path
from tkinter import ttk

import pytest

from tests.test_archive_native import pump
from tests.test_matte_native import save_native_capture
from tests.test_root_logical_metrics_native import application as _application
from tests.test_root_logical_metrics_native import (
    metrics_application as _metrics_application,
)
from yt_downloader.ui_layout import install_window_logical_metrics
from yt_downloader.ui_materials import attach_matte_frame

application = _application
metrics_application = _metrics_application

pytestmark = pytest.mark.skipif(
    os.environ.get("VODFORGE_NATIVE_UI_TESTS") != "1",
    reason="explicit native run required",
)


def test_matte_frame_tracks_ancestor_motion_and_retires(application, tmp_path):
    root = tk.Toplevel(application)
    root.geometry("760x520+30+30")
    anchor = ttk.Frame(root)
    anchor.pack(fill="both", expand=True)
    parent = ttk.Frame(anchor)
    parent.place(x=80, y=60, width=400, height=180)
    child = ttk.Frame(parent)
    child.place(x=20, y=15, width=220, height=100)
    canvas = attach_matte_frame(child, anchor=anchor)
    owner = canvas._matte_backdrop
    pump(root)
    photo = owner.photo

    def aligned():
        return canvas.coords(owner.item) == [
            anchor.winfo_rootx() + anchor.winfo_width() - canvas.winfo_rootx(),
            anchor.winfo_rooty() - canvas.winfo_rooty(),
        ]

    assert aligned()
    for x, y in ((230, 170), (80, 60), (300, 200)):
        parent.place_configure(x=x, y=y)
        pump(root)
        assert aligned(), "same-size ancestor movement left a stale texture origin"
        assert owner.photo is photo
    parent.place_forget()
    pump(root)
    parent.place(x=90, y=110, width=400, height=180)
    pump(root)
    assert aligned()
    out = Path(os.environ.get("VODFORGE_NATIVE_EVIDENCE_DIR", str(tmp_path)))
    save_native_capture(root, out / "matte-ancestor-motion.png")
    # A stale-position mutation must be visible to the independent coordinate oracle.
    canvas.move(owner.item, 9, 7)
    assert not aligned()
    owner.request()
    pump(root)
    assert aligned()
    owner.request()
    root.destroy()
    pump(application)
    assert owner.pending is None and owner.geometry_bindings == []


def test_settings_first_map_fits_viewport_before_any_resize(
    metrics_application, monkeypatch, tmp_path
):
    app, dpi = metrics_application
    original = tk.Toplevel.__init__

    def admitted(self, *args, **kwargs):
        original(self, *args, **kwargs)
        if dpi:
            install_window_logical_metrics(self, dpi=dpi)

    monkeypatch.setattr(tk.Toplevel, "__init__", admitted)
    app._show_focus_settings()
    dialog = app._focus_settings_dialog
    surface = dialog.dialog_surface
    pump(app)
    assert surface.body.winfo_width() == surface.viewport.winfo_width()
    assert dialog.pro_button.winfo_rootx() + dialog.pro_button.winfo_width() <= (
        surface.viewport.winfo_rootx() + surface.viewport.winfo_width()
    )
    out = Path(os.environ.get("VODFORGE_NATIVE_EVIDENCE_DIR", str(tmp_path)))
    save_native_capture(dialog.popup, out / f"settings-first-map-{dpi or 96}.png")
    # Simulate the same Tk child-request replacement seen during Windows mapping.
    # The existing body Configure path must restore allocation without a resize.
    surface.viewport.itemconfigure(
        surface._body_window, width=surface.viewport.winfo_width() + 140
    )
    pump(app)
    assert surface.body.winfo_width() == surface.viewport.winfo_width()
    surface._body_resized(None)
    assert surface._body_width_pending is not None
    dialog.close()
    assert surface._body_width_pending is None
