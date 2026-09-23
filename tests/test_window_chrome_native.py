"""Native Mac header alignment without replacing native window controls."""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from pathlib import Path
from threading import Thread
from unittest.mock import patch

import pytest

from scripts.focus_ui_preview import isolated_preview_services
from yt_downloader.analytics_startup import AnalyticsStartup
from yt_downloader.app import DownloaderApp
from yt_downloader.engagement_ui import EngagementUI
from yt_downloader.platforms.macos.windowing import _native_window

pytestmark = pytest.mark.skipif(
    sys.platform != "darwin" or os.environ.get("VODFORGE_NATIVE_UI_TESTS") != "1",
    reason="explicit Mac native window and OS input required",
)


def test_native_header_alignment_retains_navigation_search_minimize_and_fullscreen(
    tmp_path,
):
    import subprocess

    import Quartz
    from AppKit import NSApplication

    output = Path(os.environ.get("VODFORGE_NATIVE_EVIDENCE_DIR", str(tmp_path)))
    output.mkdir(parents=True, exist_ok=True)
    evidence = {
        "scope": "Mac source native AppKit header; OS pointer navigation/minimize; root fullscreen requested through Tk, explicit reactivation on return",
        "checks": [],
        "captures": [],
        "callback_errors": [],
        "geometry": [],
    }
    app = None

    def pump(seconds=0.3, predicate=lambda: False):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            app.update()
            if predicate():
                return True
            time.sleep(0.01)
        return predicate()

    def check(name, truth):
        evidence["checks"].append({"name": name, "passed": bool(truth)})
        assert truth, name

    def point(x, y):
        def send():
            for kind in (
                Quartz.kCGEventMouseMoved,
                Quartz.kCGEventLeftMouseDown,
                Quartz.kCGEventLeftMouseUp,
            ):
                event = Quartz.CGEventCreateMouseEvent(
                    None, kind, (float(x), float(y)), Quartz.kCGMouseButtonLeft
                )
                Quartz.CGEventSetFlags(event, 0)
                Quartz.CGEventSetIntegerValueField(
                    event, Quartz.kCGMouseEventClickState, 1
                )
                Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)
                time.sleep(0.10)

        worker = Thread(target=send, daemon=True)
        worker.start()
        pump(0.65)
        worker.join(1)
        check("input driver completed", not worker.is_alive())

    def click(widget):
        point(
            widget.winfo_rootx() + widget.winfo_width() / 2,
            widget.winfo_rooty() + widget.winfo_height() / 2,
        )

    def navigate(name):
        click(app._focus_nav_buttons[name])
        check("native navigation " + name, app._focus_selected_view == name)

    def capture(name):
        path = output / f"header-{name}.png"
        result = subprocess.run(
            [
                "/usr/sbin/screencapture",
                "-x",
                "-o",
                "-l",
                str(_native_window(app).windowNumber()),
                str(path),
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
        assert result.returncode == 0, result.stderr
        evidence["captures"].append(
            {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        )

    def native_rect(kind):
        window = _native_window(app)
        button = window.standardWindowButton_(kind)
        rect = window.convertRectToScreen_(
            button.convertRect_toView_(button.bounds(), None)
        )
        return (
            rect.origin.x,
            float(Quartz.CGDisplayPixelsHigh(Quartz.CGMainDisplayID()))
            - rect.origin.y
            - rect.size.height,
            rect.size.width,
            rect.size.height,
        )

    def geometry(label):
        buttons = [native_rect(kind) for kind in (0, 1, 2)]
        nav = app._focus_nav_buttons["watch"]
        brand = app._focus_brand_labels[0].master
        alignment_owner = brand if app._focus_header_stacked else nav
        center = alignment_owner.winfo_rooty() + alignment_owner.winfo_height() / 2
        check(
            label + " native controls share header row center",
            all(abs(y + h / 2 - center) <= 2 for x, y, w, h in buttons),
        )
        check(
            label + " native controls clear wordmark",
            max(x + w for x, y, w, h in buttons) < brand.winfo_rootx(),
        )
        widgets = [
            brand,
            *app._focus_nav_buttons.values(),
            app._global_search_field,
            app.focus_settings_button,
        ]
        boxes = [
            (w.winfo_rootx(), w.winfo_rooty(), w.winfo_width(), w.winfo_height())
            for w in widgets
        ]
        check(
            label + " header controls do not overlap",
            all(
                boxes[i][0] + boxes[i][2] <= boxes[i + 1][0]
                or boxes[i + 1][0] + boxes[i + 1][2] <= boxes[i][0]
                or boxes[i][1] + boxes[i][3] <= boxes[i + 1][1]
                or boxes[i + 1][1] + boxes[i + 1][3] <= boxes[i][1]
                for i in range(len(boxes) - 1)
            ),
        )
        evidence["geometry"].append(
            {
                "label": label,
                "native_buttons": buttons,
                "navigation_center": center,
                "widgets": boxes,
            }
        )

    try:
        with (
            isolated_preview_services(),
            patch.object(AnalyticsStartup, "start", lambda _: None),
            patch.object(EngagementUI, "start", lambda _: None),
        ):
            app = DownloaderApp()
            app.report_callback_exception = lambda *_a: evidence[
                "callback_errors"
            ].append(str(_a[1]))
            app.geometry("1414x1008+70+50")
            app.deiconify()
            NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
            pump(1.5)
            check("AppKit header installed", app._native_toolbar_header)
            native = _native_window(app)
            check(
                "native toolbar has no extra controls",
                len(native.toolbar().items()) == 0,
            )
            check(
                "window retains accessible name",
                native.accessibilityTitle() == "VODForge",
            )
            for index, width in enumerate((1414, 980, 820, 1414)):
                app.geometry(f"{width}x1008+70+50")
                pump(0.5)
                geometry(str(width))
                navigate("library")
                if index == 0:
                    scene = app.library_scene
                    labels = [
                        scene.canvas.itemcget(item, "text")
                        for _box, item, _c, _a in scene._button_labels
                    ]
                    check(
                        "empty Library has one pair of starting actions",
                        labels.count("Go to Forge") == 1
                        and labels.count("Import Media") == 1,
                    )
                    check(
                        "empty Library omits browse controls",
                        not set(labels)
                        & {"Newest first", "Filter", "Select", "See All"},
                    )
                    capture("library-empty")
                navigate("watch")
                capture(f"{width}-{index}")
            click(app._global_search_field.entry)
            entry = app._global_search_field.entry
            evidence["search_click"] = {
                "entry": (
                    entry.winfo_rootx(),
                    entry.winfo_rooty(),
                    entry.winfo_width(),
                    entry.winfo_height(),
                ),
                "focus": str(app.focus_get()),
                "active": bool(NSApplication.sharedApplication().isActive()),
            }
            check(
                "native pointer focuses search",
                app.focus_get() == entry,
            )
            x, y, w, h = native_rect(1)
            point(x + w / 2, y + h / 2)
            check(
                "native yellow button minimizes",
                pump(3, lambda: app.state() == "iconic"),
            )
            app.deiconify()
            NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
            pump(0.8)
            geometry("restored")
            navigate("library")
            app.attributes("-fullscreen", True)
            check(
                "root fullscreen enters",
                pump(4, lambda: bool(app.attributes("-fullscreen"))),
            )
            pump(2)
            capture("fullscreen")
            app.attributes("-fullscreen", False)
            pump(2)
            NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
            app.focus_force()
            pump(0.6)
            check("root fullscreen returns", not bool(app.attributes("-fullscreen")))
            geometry("fullscreen-return")
            navigate("watch")
            capture("fullscreen-return")
            check("callbacks clean", not evidence["callback_errors"])
            evidence["passed"] = True
    finally:
        if app is not None:
            app.destroy()
        (output / "header-native.json").write_text(
            json.dumps(evidence, indent=2) + "\n"
        )


def test_os_resize_release_then_pointer_move_matches_minimal_tk(tmp_path):
    """OS-injected drag comparison; does not certify a physical mouse/trackpad."""
    import tkinter as tk

    import Quartz
    from AppKit import NSApplication

    output = Path(os.environ.get("VODFORGE_NATIVE_EVIDENCE_DIR", str(tmp_path)))
    output.mkdir(parents=True, exist_ok=True)
    observations = []
    for kind in ("minimal-tk", "library", "watch"):
        app = None
        errors = []
        try:
            with (
                isolated_preview_services(),
                patch.object(AnalyticsStartup, "start", lambda _: None),
                patch.object(EngagementUI, "start", lambda _: None),
            ):
                app = tk.Tk() if kind == "minimal-tk" else DownloaderApp()
                app.report_callback_exception = lambda *args, errors=errors: (
                    errors.append(str(args[1]))
                )
                app.geometry("980x600+100+100")
                app.deiconify()
                if kind != "minimal-tk":
                    app._select_focus_view(kind)
                NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
                deadline = time.monotonic() + 0.8
                while time.monotonic() < deadline:
                    app.update()
                    time.sleep(0.01)
                number = int(_native_window(app).windowNumber())

                def bounds(number=number):
                    windows = Quartz.CGWindowListCopyWindowInfo(
                        Quartz.kCGWindowListOptionIncludingWindow, number
                    )
                    row = next(
                        w for w in windows if int(w["kCGWindowNumber"]) == number
                    )
                    return dict(row["kCGWindowBounds"])

                before = bounds()
                trace = []

                def post(event_kind, x, y):
                    event = Quartz.CGEventCreateMouseEvent(
                        None,
                        event_kind,
                        (float(x), float(y)),
                        Quartz.kCGMouseButtonLeft,
                    )
                    Quartz.CGEventSetFlags(event, 0)
                    Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)

                def drag(before=before, trace=trace, bounds=bounds, post=post):
                    x = before["X"] + before["Width"] - 2
                    y = before["Y"] + before["Height"] - 2
                    post(Quartz.kCGEventMouseMoved, x, y)
                    time.sleep(0.1)
                    post(Quartz.kCGEventLeftMouseDown, x, y)
                    for step in range(1, 13):
                        post(
                            Quartz.kCGEventLeftMouseDragged, x + step * 8, y + step * 4
                        )
                        time.sleep(0.035)
                    post(Quartz.kCGEventLeftMouseUp, x + 96, y + 48)
                    time.sleep(0.3)
                    trace.append(("after-release", bounds()))
                    for step in range(1, 9):
                        post(
                            Quartz.kCGEventMouseMoved,
                            x + 96 + step * 7,
                            y + 48 - step * 5,
                        )
                        time.sleep(0.045)
                    trace.append(("after-free-pointer", bounds()))

                worker = Thread(target=drag, daemon=True)
                worker.start()
                intervals = []
                previous = time.monotonic()
                deadline = previous + 8
                while worker.is_alive() and time.monotonic() < deadline:
                    app.update()
                    now = time.monotonic()
                    intervals.append((now - previous) * 1000)
                    previous = now
                    time.sleep(0.005)
                worker.join(0.5)
                assert not worker.is_alive()
                assert len(trace) == 2
                assert trace[0][1]["Width"] > before["Width"] + 40, (
                    "Driver must actually resize"
                )
                assert trace[1][1] == trace[0][1], (
                    "Released window followed unpressed pointer"
                )
                assert not errors
                observations.append(
                    {
                        "view": kind,
                        "before": before,
                        "trace": trace,
                        "max_pump_interval_ms": max(intervals),
                        "callback_errors": errors,
                    }
                )
        finally:
            if app is not None:
                app.destroy()
            (output / "resize-release-comparison.json").write_text(
                json.dumps(
                    {
                        "scope": "OS-injected source native comparison; physical report remains separate",
                        "observations": observations,
                        "last_errors": errors,
                    },
                    indent=2,
                )
                + "\n"
            )
