"""File decisions retain readable context and reachable, nonexecuted actions."""

import os
import tkinter as tk
import tkinter.font as tkfont
from pathlib import Path

import pytest

from tests.test_archive_native import pump
from tests.test_matte_native import save_native_capture
from yt_downloader.library_file_actions_ui import FileActionDialog
from yt_downloader.ui_layout import install_window_logical_metrics
from yt_downloader.ui_styles import apply_product_styles
from yt_downloader.ui_theme import FONT_UI

pytestmark = pytest.mark.skipif(
    os.environ.get("VODFORGE_NATIVE_UI_TESTS") != "1",
    reason="explicit native run required",
)


@pytest.mark.parametrize("dpi", [None, 192])
def test_file_decision_fonts_wrap_actions_and_cancel(dpi, monkeypatch, tmp_path):
    original = tk.Toplevel.__init__

    def admitted(self, *args, **kwargs):
        original(self, *args, **kwargs)
        if dpi:
            install_window_logical_metrics(self, dpi=dpi)

    monkeypatch.setattr(tk.Toplevel, "__init__", admitted)
    root = tk.Tk()
    try:
        root.geometry("1180x900+20+40")
        apply_product_styles(root)
        calls = []
        dialog = FileActionDialog(
            root,
            "Delete selected media?",
            lambda: (calls.append("cancel"), dialog.popup.destroy()),
        )
        pump(root)
        expected = tkfont.Font(root=root, font=(FONT_UI[0], -59 if dpi else 22, "bold"))
        actual = tkfont.Font(root=root, font=dialog.heading.cget("font"))
        assert actual.metrics("linespace") == expected.metrics("linespace")
        dialog.message.set(
            "Destination\n"
            + "C:/QA/long-folder/" * 18
            + "\nCollections and playback progress will follow your media."
        )
        dialog.note.set("These files could not be verified and will be kept. " * 12)
        dialog.offer("Move to Trash", lambda: calls.append("forbidden"))
        pump(root)
        for width in (700 if dpi else 480, 1100 if dpi else 760, 700 if dpi else 480):
            dialog.popup.geometry(f"{width}x{560 if dpi else 420}")
            pump(root)
            for label in (dialog.heading, dialog.description, dialog.note_label):
                assert label.winfo_height() >= label.winfo_reqheight()
                assert (
                    label.cget("wraplength")
                    and int(label.cget("wraplength"))
                    <= dialog.surface.body.winfo_width()
                )
            for button in (dialog.primary, dialog.secondary):
                assert button.winfo_width() >= button.winfo_reqwidth()
                assert dialog.surface.action_is_visible(button)
        out = Path(os.environ.get("VODFORGE_NATIVE_EVIDENCE_DIR", str(tmp_path)))
        save_native_capture(
            dialog.popup, out / f"file-decision-{dpi or 'default'}-top.png"
        )
        if dialog.surface.viewport is not None:
            dialog.surface.viewport.yview_moveto(1)
            pump(root)
            assert dialog.surface.viewport.yview()[1] == 1
            assert (
                dialog.note_label.winfo_rooty() + dialog.note_label.winfo_height()
                <= dialog.surface.viewport.winfo_rooty()
                + dialog.surface.viewport.winfo_height()
                + 1
            )
            save_native_capture(dialog.popup, out / f"file-decision-{dpi}-bottom.png")
        assert calls == []
        dialog.secondary.invoke()
        pump(root)
        assert calls == ["cancel"] and not dialog.exists()
    finally:
        root.destroy()
