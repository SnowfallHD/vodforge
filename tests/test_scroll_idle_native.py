"""Scroll drawing cannot recursively drain or act on retired view ownership."""

from __future__ import annotations

import os
import sys
import tkinter as tk

import pytest

from tests.test_archive_native import application as _application
from tests.test_archive_native import pump
from yt_downloader import platform_services, ui_scrolling

application = _application
pytestmark = pytest.mark.skipif(
    sys.platform != "darwin" or os.environ.get("VODFORGE_NATIVE_UI_TESTS") != "1",
    reason="Native Mac idle queue required",
)


def viewport(app):
    canvas = tk.Canvas(app, width=300, height=150, scrollregion=(0, 0, 1000, 1000))
    canvas.place(x=20, y=80, width=300, height=150)
    tk.Label(canvas, text="Child viewport").place(x=0, y=0)
    pump(app)
    return canvas


def test_scroll_bounds_idle_batches_and_defers_rescheduled_work(application):
    app = application
    canvas = viewport(app)
    binding = ui_scrolling.bind_smooth_scroll(canvas)
    calls, pending = [], []

    def again():
        calls.append(True)
        pending.append(app.after_idle(again))

    pending.append(app.after_idle(again))
    try:
        binding.scroll(0, 36)
        assert 1 <= len(calls) <= 6, (
            "Scroll drained newly queued idle work without a bound"
        )
        assert not app._vodforge_scroll_drawing
    finally:
        for token in pending:
            app.after_cancel(token)
        canvas.destroy()


@pytest.mark.parametrize("action", ["destroy", "replace"])
def test_idle_retirement_is_respected_before_next_scroll(application, action):
    app = application
    canvas = viewport(app)
    used, replacement = [], []
    old = ui_scrolling.bind_smooth_scroll(canvas, on_scroll=lambda: used.append("old"))

    def retire():
        if action == "destroy":
            canvas.destroy()
        else:
            replacement.append(
                ui_scrolling.bind_smooth_scroll(
                    canvas, on_scroll=lambda: used.append("new")
                )
            )

    app.after_idle(retire)
    old.scroll(0, 36)
    assert old.closed and used == ["old"]
    old.scroll(0, 36)
    assert used == ["old"], "Retired binding accepted another operation"
    if replacement:
        replacement[0].scroll(0, 36)
        assert used == ["old", "new"]
        canvas.destroy()
    assert not app._vodforge_scroll_drawing


def test_nested_diagonal_scroll_draws_once_for_child_and_parent(
    application, monkeypatch
):
    app = application
    outer = viewport(app)
    inner = tk.Canvas(outer, width=200, height=80, scrollregion=(0, 0, 1000, 80))
    outer.create_window(0, 0, window=inner, anchor="nw")
    tk.Label(inner, text="nested").place(x=0, y=0)
    parent = ui_scrolling.bind_smooth_scroll(outer)
    child = ui_scrolling.bind_smooth_scroll(inner, axis="horizontal")
    pump(app)
    calls = []
    original = platform_services.present_scrolled_canvas

    def present(widget):
        calls.append(widget)
        original(widget)

    monkeypatch.setattr(ui_scrolling, "present_scrolled_canvas", present)
    child.scroll(36, 36)
    assert inner.canvasx(0) > 0 and outer.canvasy(0) > 0
    assert calls == [inner], "Ancestor routing drained the same idle queue repeatedly"
    outer.destroy()
    assert parent.closed and child.closed


def test_nested_scroll_from_idle_does_not_recursively_drain(application):
    app = application
    canvas = viewport(app)
    binding = ui_scrolling.bind_smooth_scroll(canvas)
    calls, pending = [], []

    def nested():
        calls.append("nested")
        pending.append(app.after_idle(lambda: calls.append("later")))
        binding.scroll(0, 12)
        assert calls == ["nested"]

    pending.append(app.after_idle(nested))
    try:
        binding.scroll(0, 12)
        assert calls == ["nested", "later"] and not app._vodforge_scroll_drawing
    finally:
        for token in pending:
            app.after_cancel(token)
        canvas.destroy()


@pytest.mark.parametrize("destination", ["child-canvas", "frame"])
def test_idle_root_destruction_does_not_call_retired_tk_commands(destination):
    root = tk.Tk()
    canvas = tk.Canvas(root, width=200, height=100)
    canvas.pack()
    tk.Label(canvas, text="Owned child").place(x=0, y=0)
    root.update()
    root.after_idle(root.destroy)
    try:
        if destination == "child-canvas":
            platform_services.present_scrolled_canvas(canvas)
        else:
            platform_services.present_pending_drawing(root)
        assert not root.tk.call("info", "commands", ".")
        assert not root._vodforge_scroll_drawing
    finally:
        if root.tk.call("info", "commands", "."):
            root.destroy()
