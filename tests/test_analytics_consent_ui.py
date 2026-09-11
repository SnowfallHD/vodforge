"""Native visual geometry contracts; screenshot review is also required."""

import os
import sys
import tkinter as tk
from tkinter import ttk

import pytest

from yt_downloader.analytics_consent_ui import AnalyticsConsentPanel
from yt_downloader.ui_chrome import ProductChromeOwner

pytestmark = pytest.mark.skipif(
    os.environ.get("VODFORGE_NATIVE_UI_TESTS") != "1", reason="requires native Tcl/Tk"
)


def test_primary_hover_has_distinct_rendered_pixels():
    root = tk.Tk()
    # Drain the native showRootWindow idle callback before destroying this root;
    # otherwise Tk 9 on macOS can run it against the next test's dead NSWindow.
    root.update()
    try:
        chrome = ProductChromeOwner(root)
        chrome.request(ttk.Style(root))
        normal = root.tk.call(str(chrome.images["accent"]), "get", 14, 14)
        hover = root.tk.call(str(chrome.images["accent_hover"]), "get", 14, 14)
        assert normal != hover
        chrome.images.clear()
    finally:
        root.destroy()


@pytest.mark.parametrize("size", [(1100, 740), (860, 600)])
def test_consent_is_centered_child_and_keeps_all_actions_visible(size):
    root = tk.Tk()
    root.geometry(f"{size[0]}x{size[1]}+100+80")
    root.update()
    choices = []
    panel = AnalyticsConsentPanel(root, choices.append, lambda: None)
    try:
        root.update()
        if sys.platform in {"darwin", "win32"}:
            assert len(panel.backdrop.views) == 4
        assert isinstance(panel.privacy, tk.Label)
        assert int(panel.privacy.cget("borderwidth")) == 0
        assert int(panel.privacy.cget("highlightthickness")) == 0
        assert panel.privacy.bind("<Return>")
        assert panel.privacy.bind("<Button-1>")
        assert panel.allow.winfo_width() < panel.frame.winfo_width() / 2
        assert panel.deny.winfo_width() < panel.frame.winfo_width() / 2
        assert len(panel.benefit_labels) == 4
        for label in panel.benefit_labels:
            assert float(label.cget("wraplength")) <= label.winfo_width() - 8
            assert label.winfo_reqwidth() <= label.winfo_width()
        assert all(
            str(label.cget("justify")) == "center" for label in panel.benefit_labels
        )
        assert panel.frame.winfo_toplevel() is root
        assert not any(isinstance(w, tk.Toplevel) for w in root.winfo_children())
        assert (
            abs(
                panel.frame.winfo_x()
                + panel.frame.winfo_width() / 2
                - root.winfo_width() / 2
            )
            <= 1
        )
        assert (
            abs(
                panel.frame.winfo_y()
                + panel.frame.winfo_height() / 2
                - root.winfo_height() / 2
            )
            <= 1
        )
        for button in panel.controls:
            assert button.winfo_ismapped()
            assert (
                button.winfo_rooty() + button.winfo_height()
                <= panel.frame.winfo_rooty() + panel.frame.winfo_height()
            )
        root.geometry("900x640+200+120")
        root.update()
        assert (
            abs(
                panel.frame.winfo_x()
                + panel.frame.winfo_width() / 2
                - root.winfo_width() / 2
            )
            <= 1
        )
        panel.deny.invoke()
        assert choices == [False]
        assert root.grab_current() is None
    finally:
        root.destroy()
