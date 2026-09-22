"""Read-only presentation must preserve scene continuity and native input."""

import os
import sys
import tkinter as tk
from pathlib import Path
from tkinter import ttk

import pytest
from PIL import Image

from tests.test_archive_native import application as _application
from tests.test_archive_native import pump
from tests.test_matte_native import save_native_capture
from yt_downloader.ui_materials import MatteTextProjection, attach_matte_frame
from yt_downloader.ui_theme import THEME

application = _application
pytestmark = pytest.mark.skipif(
    sys.platform != "darwin" or os.environ.get("VODFORGE_NATIVE_UI_TESTS") != "1",
    reason="native Mac presentation required",
)


def test_shared_backdrop_replacement_plateaus_and_retires(
    application, monkeypatch, tmp_path
):
    import gc
    import json
    import subprocess

    from yt_downloader.platform_services import surface_backing_scale
    from yt_downloader.ui_materials import draw_matte_backdrop

    popup = tk.Toplevel(application)
    popup.geometry("700x400+40+40")
    canvases = [
        tk.Canvas(popup, width=350, height=400, highlightthickness=0) for _ in range(2)
    ]
    for canvas in canvases:
        canvas.pack(side="left", fill="both", expand=True)
    owners = [draw_matte_backdrop(canvas) for canvas in canvases]
    pump(application, 0.1)
    names = set()
    rss = []
    errors = []

    def step(cycle=0):
        try:
            monkeypatch.setitem(
                THEME, "accent", ("#80c6db", "#bc91ef", "#d6ba77")[cycle % 3]
            )
            for owner in owners:
                owner.draw()
            assert owners[0].photo is owners[1].photo
            assert all(
                len(canvas.find_withtag("matte-decoration")) == 1 for canvas in canvases
            )
            name = str(owners[0].photo)
            names.add(name)
            assert popup.tk.call("image", "width", name) == 1200
            assert popup.tk.call("image", "height", name) == 800
            gc.collect()
            live = set(popup.tk.splitlist(popup.tk.call("image", "names")))
            assert names & live == {name}, "Retired theme backdrops remain in Tcl"
            application.after(120, lambda: checkpoint(cycle))
        except Exception as exc:  # noqa: BLE001 - retain callback failure and stop owned loop
            errors.append(repr(exc))
            application.quit()

    def checkpoint(cycle):
        rss.append(
            int(subprocess.check_output(["ps", "-o", "rss=", "-p", str(os.getpid())]))
            * 1024
        )
        if cycle == 11:
            application.quit()
        else:
            application.after(0, lambda: step(cycle + 1))

    # Match native_surface_memory: return to the actual mainloop between
    # replacements so normal native autorelease boundaries can run.
    deadline = application.after(
        15000, lambda: (errors.append("timeout"), application.quit())
    )
    application.after(0, step)
    application.mainloop()
    application.after_cancel(deadline)
    assert not errors and len(rss) == 12, errors
    # Allow two old/new native texture representations plus the existing8MiB
    # reuse allowance. Compare current RSS after warmup, never lifetime peak.
    budget = 2 * 1200 * 800 * surface_backing_scale(popup) ** 2 * 8 + 8 * 1024 * 1024
    growth = max(rss[4:]) - min(rss[3:5])
    out = Path(os.environ.get("VODFORGE_NATIVE_EVIDENCE_DIR", str(tmp_path)))
    (out / "backdrop-memory.json").write_text(
        json.dumps(
            {
                "rss_bytes": rss,
                "growth_bytes": growth,
                "budget_bytes": budget,
                "scope": "two canvases share one root texture;12palette replacements; source-native only",
            },
            indent=2,
        )
    )
    assert growth <= budget
    popup.destroy()
    owners.clear()
    canvases.clear()
    canvas = popup = None
    gc.collect()
    pump(application, 0.1)
    live = set(application.tk.splitlist(application.tk.call("image", "names")))
    assert not names & live


def test_text_scene_seams_selection_resize_and_retirement(
    application, tmp_path, monkeypatch
):
    import yt_downloader.ui_materials as materials

    # Strong two-tone background is a fault amplifier, not product artwork.
    def pixels(*_args):
        image = Image.new("RGB", (1200, 800), "#283d57")
        image.paste("#6d354e", (850, 0, 1200, 800))
        return image

    monkeypatch.setattr(materials, "backdrop_pixels", pixels)
    popup = tk.Toplevel(application)
    popup.geometry("600x300+80+80")
    frame = ttk.Frame(popup)
    frame.pack(fill="both", expand=True)
    attach_matte_frame(frame)
    document = tk.Text(
        frame,
        bg=THEME["bg"],
        fg=THEME["text"],
        height=3,
        bd=0,
        highlightthickness=0,
        pady=7,
    )
    document.insert("1.0", "Selectable facts\nFormat: MP4\nSave to: /Downloads")
    document.configure(state="disabled")
    document.place(x=80, y=65, width=450, height=160)
    owner = MatteTextProjection(document, frame)
    pump(application, 0.3)
    out = Path(os.environ.get("VODFORGE_NATIVE_EVIDENCE_DIR", str(tmp_path)))

    def seam():
        capture = save_native_capture(popup, out / "text-continuity-native.png")
        scale = capture.width / popup.winfo_width()
        # Same global x; compare untouched art above with blank text margin.
        for x in (100, 300, 500):
            a = capture.getpixel((round(x * scale), round(35 * scale)))[:3]
            b = capture.getpixel((round(x * scale), round(200 * scale)))[:3]
            assert max(abs(a[i] - b[i]) for i in range(3)) <= 1

    seam()
    fault = owner.canvas.create_rectangle(
        0, 0, 450, 160, fill=THEME["bg"], outline="", tags="opaque-fault"
    )
    pump(application, 0.1)
    with pytest.raises(AssertionError):
        seam()
    owner.canvas.delete(fault)
    pump(application, 0.1)
    seam()
    before = document.get("1.0", "end-1c")
    first = document.bbox("1.0")
    last = document.bbox("1.10")
    assert first and last
    owner.canvas.event_generate("<ButtonPress-1>", x=first[0] + 1, y=first[1] + 3)
    owner.canvas.event_generate("<B1-Motion>", x=last[0] + 3, y=last[1] + 3, state=256)
    owner.canvas.event_generate("<ButtonRelease-1>", x=last[0] + 3, y=last[1] + 3)
    pump(application, 0.1)
    assert document.tag_ranges("sel")
    assert document.get("sel.first", "sel.last")
    assert document.get("1.0", "end-1c") == before
    for width in (720, 540, 650):
        popup.geometry(f"{width}x300")
        pump(application, 0.1)
        seam()
    document.destroy()
    assert owner.retired and owner.pending is None and not owner.bindings
    owner.request()
    assert owner.pending is None
    popup.destroy()


def test_projected_button_input_and_shaped_backdrop(application, tmp_path, monkeypatch):
    from PIL import ImageDraw
    from quality_harness.surface_artifacts import (
        outside_allowed_surface,
        stale_decoration,
    )

    import yt_downloader.ui_materials as materials
    from yt_downloader.ui_button_contract import ProductButton

    def pixels(*_args):
        image = Image.new("RGB", (1200, 800), "#343139")
        draw = ImageDraw.Draw(image)
        for x in range(0, 1200, 19):
            draw.rectangle((x, 0, x + 5, 800), fill="#474250")
        return image

    monkeypatch.setattr(materials, "backdrop_pixels", pixels)
    popup = tk.Toplevel(application)
    popup.geometry("320x180+80+80")
    frame = ttk.Frame(popup)
    frame.pack(fill="both", expand=True)
    attach_matte_frame(frame)
    pump(application, 0.15)
    out = Path(os.environ.get("VODFORGE_NATIVE_EVIDENCE_DIR", str(tmp_path)))
    background = save_native_capture(popup, out / "button-backdrop-native.png")
    calls = []
    button = ProductButton(
        frame,
        text="Primary action",
        style="Accent.TButton",
        command=lambda: calls.append("invoke"),
    )
    button.place(x=60, y=65, width=190, height=44)
    owner = MatteTextProjection(button, frame)
    pump(application, 0.15)
    scale = background.width / popup.winfo_width()
    allowed = Image.new("L", background.size)
    ImageDraw.Draw(allowed).rounded_rectangle(
        tuple(round(n * scale) for n in (60, 65, 250, 109)),
        radius=round(13 * scale),
        fill=255,
    )
    for state in ("idle", "hover", "pressed", "disabled", "focus", "exit"):
        button.state(["!active", "!pressed", "!disabled"])
        if state == "hover":
            button.state(["active"])
        if state == "pressed":
            button.state(["pressed"])
        if state == "disabled":
            button.state(["disabled"])
        if state == "focus":
            button.focus_force()
        if state == "exit":
            frame.focus_force()
        owner.request()
        pump(application, 0.12)
        image = save_native_capture(
            popup, out / (f"projected-button-{state}-native.png")
        )
        assert outside_allowed_surface(image, background, allowed).clean
        if state == "idle":
            idle = image
        if state == "focus":
            assert button.instate(["focus"])
            assert not stale_decoration(
                image, idle, Image.new("L", image.size, 255)
            ).clean
        if state == "exit":
            assert not button.instate(["focus"])
            assert stale_decoration(image, idle, Image.new("L", image.size, 255)).clean
    owner.canvas.event_generate("<ButtonPress-1>", x=60, y=20)
    owner.canvas.event_generate("<ButtonRelease-1>", x=60, y=20)
    pump(application, 0.1)
    assert calls == ["invoke"]
    button.state(["disabled"])
    owner.canvas.event_generate("<ButtonPress-1>", x=60, y=20)
    owner.canvas.event_generate("<ButtonRelease-1>", x=60, y=20)
    assert calls == ["invoke"]
    button.state(["!disabled"])
    button.focus_force()
    pump(application, 0.1)
    button.event_generate("<KeyPress-space>")
    button.event_generate("<KeyRelease-space>")
    pump(application, 0.1)
    assert calls == ["invoke", "invoke"]
    button.destroy()
    owner.request()
    assert owner.retired and owner.pending is None and owner.control_photo is None
    popup.destroy()


@pytest.mark.parametrize(
    "movement", ["vertical-scrollbar", "horizontal-scrollbar", "see"]
)
def test_projected_document_tracks_native_view(application, movement):
    popup = tk.Toplevel(application)
    popup.geometry("600x280+80+80")
    frame = ttk.Frame(popup)
    frame.pack(fill="both", expand=True)
    attach_matte_frame(frame)
    doc = tk.Text(frame, bg=THEME["bg"], fg=THEME["text"], wrap="none", height=5)
    doc.insert(
        "1.0",
        "\n".join(
            f"{i:03d} abcdefghijklmnopqrstuvwxyz " + ("wide content " * 20)
            for i in range(100)
        ),
    )
    doc.configure(state="disabled")
    doc.place(x=40, y=40, width=450, height=150)
    owner = MatteTextProjection(doc, frame)
    pump(application, 0.2)

    def visible():
        return [
            (owner.canvas.itemcget(i, "text"), owner.canvas.coords(i))
            for i in owner.canvas.find_withtag("matte-text")
            if owner.canvas.type(i) == "text"
        ]

    before = visible()
    if movement == "vertical-scrollbar":
        doc.yview("moveto", 0.7)
    elif movement == "horizontal-scrollbar":
        doc.xview("moveto", 0.4)
    else:
        doc.see("85.0")
    pump(application, 0.2)
    observed = visible()
    owner.request()
    pump(application, 0.1)
    refreshed = visible()
    assert refreshed != before, "positive control: native document actually moved"
    assert observed == refreshed, (
        "projection retained old content after native viewport moved"
    )
    popup.destroy()


def test_projection_draws_each_visible_row_of_wide_document(application, tmp_path):
    popup = tk.Toplevel(application)
    popup.geometry("600x280+80+80")
    frame = ttk.Frame(popup)
    frame.pack(fill="both", expand=True)
    attach_matte_frame(frame)
    document = tk.Text(frame, bg=THEME["bg"], fg=THEME["text"], wrap="none")
    document.insert(
        "1.0", "\n".join(f"ROW-{i:03d} " + "wide content " * 300 for i in range(100))
    )
    document.configure(state="disabled")
    document.place(x=40, y=40, width=450, height=150)
    owner = MatteTextProjection(document, frame)
    pump(application, 0.2)
    out = Path(os.environ.get("VODFORGE_NATIVE_EVIDENCE_DIR", str(tmp_path)))
    save_native_capture(popup, out / "wide-document-native.png")
    visible_rows = [i for i in range(1, 100) if document.dlineinfo(f"{i}.0")]
    assert len(visible_rows) >= 4
    rendered = "".join(
        owner.canvas.itemcget(i, "text")
        for i in owner.canvas.find_withtag("matte-text")
        if owner.canvas.type(i) == "text"
    )
    for line in visible_rows:
        assert f"ROW-{line - 1:03d}" in rendered
    assert len(owner.canvas.find_withtag("matte-text")) < 1000
    popup.destroy()


def test_projection_preserves_replaced_view_callbacks_and_retirement(application):
    popup = tk.Toplevel(application)
    frame = ttk.Frame(popup)
    frame.pack()
    calls = []
    document = tk.Text(
        frame, height=4, width=30, yscrollcommand=lambda *v: calls.append(("first", v))
    )
    document.insert("1.0", "\n".join(str(i) for i in range(100)))
    document.configure(state="disabled")
    document.pack()
    owner = MatteTextProjection(document, frame)
    pump(application, 0.1)
    assert calls and calls[-1][0] == "first"
    document.configure(yscrollcommand=lambda *v: calls.append(("second", v)))
    calls.clear()
    document.yview_moveto(0.5)
    pump(application, 0.1)
    assert calls and all(name == "second" for name, _ in calls)
    commands = [command for _, command in owner.view_callbacks.values()]
    owner.canvas.destroy()
    assert owner.retired and not owner.view_callbacks
    for command in commands:
        assert not document.tk.call("info", "commands", command)
    calls.clear()
    document.yview_moveto(0.8)
    pump(application, 0.1)
    assert calls and all(name == "second" for name, _ in calls)
    document.destroy()
    popup.destroy()


def test_projection_retains_native_images_and_hidden_tokens(application, tmp_path):
    from yt_downloader.activity_ui import ActivityLogText

    popup = tk.Toplevel(application)
    popup.geometry("620x320+80+80")
    frame = ttk.Frame(popup)
    frame.pack(fill="both", expand=True)
    attach_matte_frame(frame)
    document = ActivityLogText(frame, bg=THEME["bg"], fg=THEME["text"], wrap="word")
    document.insert(
        "1.0",
        "[success] Saved media\n[warning] Source unavailable\n[error] Retry failed\n",
    )
    document.configure(state="disabled")
    document.place(x=30, y=30, width=550, height=240)
    original = document.get("1.0", "end-1c")
    owner = MatteTextProjection(document, frame)
    pump(application, 0.2)
    out = Path(os.environ.get("VODFORGE_NATIVE_EVIDENCE_DIR", str(tmp_path)))
    save_native_capture(popup, out / "activity-document-native.png")
    projected_images = [
        owner.canvas.itemcget(i, "image")
        for i in owner.canvas.find_withtag("matte-text")
        if owner.canvas.type(i) == "image"
    ]
    native_images = [
        document.image_cget(name, "image") for name in document.image_names()
    ]
    assert projected_images and sorted(projected_images) == sorted(native_images)
    painted = "".join(
        owner.canvas.itemcget(i, "text")
        for i in owner.canvas.find_withtag("matte-text")
        if owner.canvas.type(i) == "text"
    )
    assert (
        "[success]" not in painted
        and "[warning]" not in painted
        and "[error]" not in painted
    )
    assert (
        "Saved media" in painted
        and "Source unavailable" in painted
        and "Retry failed" in painted
    )
    assert document.get("1.0", "end-1c") == original
    popup.destroy()


def test_hidden_projection_defers_work_and_remap_uses_latest_native_document(
    application, monkeypatch
):
    popup = tk.Toplevel(application)
    popup.geometry("400x180+80+80")
    document = tk.Text(popup)
    document.pack(fill="both", expand=True)
    document.insert("1.0", "initial")
    owner = MatteTextProjection(document, popup)
    pump(application, 0.15)
    popup.withdraw()
    pump(application, 0.05)
    calls = []
    original = owner._document

    def render():
        calls.append(True)
        original()

    monkeypatch.setattr(owner, "_document", render)
    document.delete("1.0", "end")
    document.insert("1.0", "latest native content")
    owner.request()
    pump(application, 0.1)
    assert calls == [], "Hidden read-only presentation consumed renderer work"
    popup.deiconify()
    pump(application, 0.15)
    assert calls
    rendered = "".join(
        owner.canvas.itemcget(item, "text")
        for item in owner.canvas.find_withtag("matte-text")
        if owner.canvas.type(item) == "text"
    )
    assert rendered == "latest native content"
    assert document.get("1.0", "end-1c") == "latest native content"
    popup.destroy()
    pump(application, 0.05)
    assert owner.retired and owner.pending is None
