"""Ancestor motion may reproject the matte without rebuilding static controls."""

from __future__ import annotations

import os
import tkinter as tk
from tkinter import ttk

import pytest

from yt_downloader.ui_materials import MatteTextProjection, draw_matte_backdrop
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
        label = tk.Label(
            anchor, text="Static label", anchor="w", bg=THEME["bg"], fg=THEME["text"]
        )
        label.place(x=35, y=30, width=130, height=30)
        owner = MatteTextProjection(label, anchor)
        root.update()
        root.update_idletasks()
        assert owner.canvas.find_withtag("matte-text")
        first_items = owner.canvas.find_withtag("matte-text")
        owner.request()
        root.update()
        assert owner.canvas.find_withtag("matte-text") == first_items
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
        assert text_calls == 0
        label.event_generate(
            "<Configure>", width=label.winfo_width(), height=label.winfo_height(), x=45
        )
        label.event_generate("<Expose>")
        root.update()
        assert text_calls == 0
        label.configure(text="Updated label")
        root.update()
        assert text_calls >= 1
        assert owner.canvas.find_withtag("matte-text") != first_items
    finally:
        root.destroy()


@pytest.mark.skipif(
    os.environ.get("VODFORGE_NATIVE_UI_TESTS") != "1",
    reason="Native Tk display required",
)
def test_shared_artwork_covers_each_resize_geometry() -> None:
    root = tk.Tk()
    try:
        canvas = tk.Canvas(root, bd=0, highlightthickness=0)
        canvas.pack(fill="both", expand=True)
        owner = draw_matte_backdrop(canvas)
        photo = owner.photo
        sizes = (
            (1100, 740),
            (
                min(1250, root.winfo_screenwidth() - 40),
                min(800, root.winfo_screenheight() - 40),
            ),
            (
                min(1350, root.winfo_screenwidth() - 40),
                min(860, root.winfo_screenheight() - 40),
            ),
        )
        for width, height in sizes:
            root.geometry(f"{width}x{height}+20+20")
            root.update()
            owner.draw()
            assert owner.item is not None
            x, y = canvas.coords(owner.item)
            image_width = int(root.tk.call("image", "width", str(owner.photo)))
            image_height = int(root.tk.call("image", "height", str(owner.photo)))
            assert x - image_width <= 0 <= x - width
            assert y <= 0 and y + image_height >= height
            assert owner.photo is photo, "resize rebuilt the shared artwork"
    finally:
        root.destroy()
