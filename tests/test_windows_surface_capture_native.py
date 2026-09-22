"""Owned native child composition, including the prior partial-print failure."""

import ctypes
import os
import sys
import time
import tkinter as tk
from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import ImageChops

from yt_downloader.platform_services import capture_own_widget

pytestmark = pytest.mark.skipif(
    sys.platform != "win32" or os.environ.get("VODFORGE_NATIVE_UI_TESTS") != "1",
    reason="Explicit Windows native display required",
)


def test_owned_capture_contains_nested_children_and_preserves_dark_content(tmp_path):
    root = tk.Tk()
    out = Path(os.environ.get("VODFORGE_NATIVE_EVIDENCE_DIR", str(tmp_path)))
    out.mkdir(parents=True, exist_ok=True)
    try:
        root.geometry("460x240+40+40")
        frame = tk.Frame(root, bg="#273951")
        frame.pack(fill="both", expand=True)
        canvas = tk.Canvas(frame, bg="#36714c", highlightthickness=0)
        canvas.place(x=20, y=20, width=160, height=140)
        canvas.create_rectangle(30, 30, 100, 100, fill="#c78b32", outline="")
        nested = tk.Frame(frame, bg="#714367")
        nested.place(x=210, y=20, width=200, height=160)
        tk.Label(nested, text="Owned child", bg="#714367", fg="white").pack()
        black = tk.Canvas(nested, bg="#000000", highlightthickness=0)
        black.place(x=20, y=40, width=120, height=90)
        until = time.monotonic() + 0.25
        while time.monotonic() < until:
            root.update()
            time.sleep(0.005)

        def matches(image):
            assert image is not None
            for point, expected in [
                ((10, 190), (39, 57, 81)),
                ((30, 30), (54, 113, 76)),
                ((75, 75), (199, 139, 50)),
                ((400, 160), (113, 67, 103)),
                ((270, 100), (0, 0, 0)),
            ]:
                assert image.convert("RGB").getpixel(point) == expected

        actual = capture_own_widget(frame)
        actual.save(out / "nested-composition.png")
        matches(actual)
        user = ctypes.windll.user32
        original = user.PrintWindow
        # Exercise the same adapter with its former legacy-print flag.
        with patch.object(
            user, "PrintWindow", lambda hwnd, dc, flags: original(hwnd, dc, 1)
        ):
            broken = capture_own_widget(frame)
            broken.save(out / "prior-print-fault.png")
            with pytest.raises(AssertionError):
                matches(broken)
        restored = capture_own_widget(frame)
        matches(restored)
        assert ImageChops.difference(actual, restored).getbbox() is None
        with patch.object(user, "PrintWindow", lambda *args: 0):
            assert capture_own_widget(frame) is None
    finally:
        root.destroy()
