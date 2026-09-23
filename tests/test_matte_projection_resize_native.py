"""Ancestor motion may reproject the matte without rebuilding static controls."""

from __future__ import annotations

import os
import tkinter as tk
from tkinter import ttk

import pytest

from yt_downloader.ui_materials import MatteTextProjection
from yt_downloader.ui_theme import THEME


@pytest.mark.skipif(
    os.environ.get("VODFORGE_NATIVE_UI_TESTS") != "1",
    reason="Native Tk display required",
)
def test_anchor_resize_only_moves_shared_matte() -> None:
    root = tk.Tk()
    try:
        root.geometry("500x250+40+40")
        anchor = ttk.Frame(root)
        anchor.pack(fill="both", expand=True)
        label = tk.Label(anchor, text="Static label", bg=THEME["bg"], fg=THEME["text"])
        label.place(x=35, y=30, width=130, height=30)
        owner = MatteTextProjection(label, anchor)
        root.update()
        root.update_idletasks()
        assert owner.canvas.find_withtag("matte-text")
        assert owner.backdrop.item is not None
        text_calls = 0
        backdrop_calls = 0
        original_label = owner._label
        original_backdrop = owner.backdrop.draw

        def count_label() -> None:
            nonlocal text_calls
            text_calls += 1
            original_label()

        def count_backdrop() -> None:
            nonlocal backdrop_calls
            backdrop_calls += 1
            original_backdrop()

        owner._label = count_label
        owner.backdrop.draw = count_backdrop
        anchor.event_generate("<Configure>", width=520, height=250)
        root.update()
        assert backdrop_calls >= 1
        assert text_calls == 0
        assert owner.canvas.find_withtag("matte-text")

        label.event_generate("<Configure>", width=140, height=30)
        root.update()
        assert text_calls >= 1
    finally:
        root.destroy()
