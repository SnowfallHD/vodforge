"""Native Watch prose and contextual player description with actual provider."""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.focus_ui_preview import isolated_preview_services
from yt_downloader import app as app_module
from yt_downloader.analytics_startup import AnalyticsStartup
from yt_downloader.engagement_ui import EngagementUI
from yt_downloader.libvlc_backend import LibVLCEngineOwner

pytestmark = pytest.mark.skipif(
    os.environ.get("VODFORGE_ACTUAL_PLAYBACK_TESTS") != "1" or sys.platform != "darwin",
    reason="explicit Mac source-native real-provider run required",
)


@pytest.mark.parametrize("width", [820, 980, 1414])
def test_native_read_more_preserves_original_description_and_short_text_stays_quiet(
    tmp_path, width
):
    import ctypes
    import subprocess

    import objc
    import Quartz
    from AppKit import NSApplication

    runtime = app_module.find_libvlc_runtime()
    assert runtime
    fixture = os.environ.get("VODFORGE_LIBRARY_FIXTURE")
    if fixture:
        row = json.loads(Path(fixture).read_text())[0]
    else:
        from tests.test_archive_models import saved
        from yt_downloader.platform_services import find_runtime_executable

        ffmpeg = find_runtime_executable("ffmpeg")
        assert ffmpeg
        media = tmp_path / "description.mp4"
        result = subprocess.run(
            [
                ffmpeg,
                "-nostdin",
                "-v",
                "error",
                "-f",
                "lavfi",
                "-i",
                "testsrc2=size=640x360:rate=24",
                "-t",
                "8",
                "-c:v",
                "libx264",
                "-preset",
                "ultrafast",
                "-pix_fmt",
                "yuv420p",
                str(media),
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        row = dict(
            saved(media, video="description-native", channel="Fixture channel"),
            title="A quiet journey",
            duration=8,
        )
    original = (
        "A peaceful journey across the mountains and forests with a winding river below. "
        * 12
    )
    row = dict(row, description=original)
    output = Path(os.environ.get("VODFORGE_NATIVE_EVIDENCE_DIR", str(tmp_path)))
    output.mkdir(parents=True, exist_ok=True)
    evidence = {
        "width": width,
        "checks": [],
        "captures": [],
        "callback_errors": [],
        "scope": "Source native with actual provider and OS-injected Read more; synthetic metadata",
    }
    app = None

    def pump(seconds=0.25, predicate=lambda: False):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            app.update()
            if predicate():
                return True
            time.sleep(0.01)
        return predicate()

    def check(name, value):
        evidence["checks"].append({"name": name, "passed": bool(value)})
        assert value, name

    def capture(name):
        get_root = ctypes.CDLL(None).TkMacOSXGetRootControl
        get_root.argtypes = (ctypes.c_void_p,)
        get_root.restype = ctypes.c_void_p
        view = objc.objc_object(c_void_p=int(get_root(int(app.winfo_id()))))
        wid = int(view.window().windowNumber())
        path = output / f"description-{width}-{name}.png"
        result = subprocess.run(
            ["/usr/sbin/screencapture", "-x", "-o", "-l", str(wid), str(path)],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        evidence["captures"].append(
            {
                "name": name,
                "path": str(path),
                "window_id": wid,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
        return path

    def open_player():
        app.focus_watch._on_play(0)
        check(
            "actual provider reaches Playing",
            pump(
                10,
                lambda: (
                    app._media_player_window is not None
                    and app._media_player_window.playback.snapshot.status == "Playing"
                ),
            ),
        )
        pump(0.5)
        return app._media_player_window

    try:
        with (
            isolated_preview_services(),
            patch.object(AnalyticsStartup, "start", lambda _: None),
            patch.object(EngagementUI, "start", lambda _: None),
        ):
            app = app_module.DownloaderApp()
            app.report_callback_exception = lambda *_a: evidence[
                "callback_errors"
            ].append(str(_a[1]))
            app.geometry(f"{width}x1008+70+50")
            app.deiconify()
            NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
            app.download_history = [row]
            app._reconcile_library_projection()
            if width == 820:
                app._select_focus_view("library")
                app.library_scene.navigate("home")
                pump(1)
                library = app.library_scene
                labels = [
                    library.canvas.itemcget(i, "text")
                    for i in library.canvas.find_all()
                    if library.canvas.type(i) == "text"
                ]
                check(
                    "Collections subtitle remains complete at 820",
                    "Your playlists and personal collections." in labels,
                )
                library.canvas.yview_moveto(1)
                pump(0.2)
                capture("collections")
            app._select_focus_view("watch")
            app.focus_watch.show_home()
            pump(2)
            scene = app.focus_watch
            description = next(
                scene.canvas.itemcget(i, "text")
                for i in scene.canvas.find_all()
                if scene.canvas.type(i) == "text"
                and scene.canvas.itemcget(i, "text").startswith("A peaceful journey")
            )
            check(
                "Watch summary has a complete final word",
                description.endswith("\u2026")
                and original[len(description) - 1].isspace(),
            )
            capture("watch")
            app.playback_engine = LibVLCEngineOwner(runtime=runtime)
            app.playback_engine.start()
            player = open_player()
            button = player._description_more
            if width < 1000:
                title = next(
                    widget
                    for widget in player._identity_header.winfo_children()
                    if isinstance(widget, app_module.ttk.Label)
                )
                check(
                    "narrow player title has the full row",
                    int(title.grid_info()["columnspan"]) == 2
                    and all(
                        widget.winfo_rooty()
                        >= title.winfo_rooty() + title.winfo_height()
                        for group in player._identity_header.winfo_children()
                        for widget in group.winfo_children()
                        if isinstance(widget, app_module.ttk.Button)
                    ),
                )
            check(
                "Read more only after measured truncation",
                button.winfo_ismapped()
                and player._description_excerpt.cget("text") != original,
            )
            screenshot = capture("collapsed")
            from PIL import Image

            pixels = Image.open(screenshot).convert("RGB")
            sx = player.stage.winfo_rootx() - app.winfo_rootx()
            sy = player.stage.winfo_rooty() - app.winfo_rooty()
            sw = player.stage.winfo_width()
            sh = player.stage.winfo_height()
            scale = pixels.width / app.winfo_width()
            sample = lambda point: pixels.getpixel(
                (round(point[0] * scale), round(point[1] * scale))
            )
            backdrop = sample((max(0, sx - 4), sy + 12))
            corner_points = [
                (sx + 1, sy + 1),
                (sx + sw - 2, sy + 1),
                (sx + 1, sy + sh - 2),
                (sx + sw - 2, sy + sh - 2),
            ]
            evidence["player_corner_pixels"] = {
                "backdrop": backdrop,
                "corners": [sample(point) for point in corner_points],
                "points": corner_points,
            }
            check(
                "all four native player corners reveal the surrounding surface",
                all(
                    max(abs(a - b) for a, b in zip(sample(point), backdrop)) < 6
                    for point in corner_points
                ),
            )
            viewport = player._page_surface.viewport
            assert viewport is not None
            region = tuple(float(v) for v in viewport.cget("scrollregion").split())
            target_y = (
                button.winfo_rooty() - viewport.winfo_rooty() + viewport.canvasy(0)
            )
            viewport.yview_moveto(
                max(0, target_y - viewport.winfo_height() / 2) / region[3]
            )
            pump(0.3)
            check(
                "Read more is reachable in the scrollable player page",
                viewport.winfo_rooty() <= button.winfo_rooty()
                and button.winfo_rooty() + button.winfo_height()
                <= viewport.winfo_rooty() + viewport.winfo_height(),
            )
            x = button.winfo_rootx() + button.winfo_width() / 2
            y = button.winfo_rooty() + button.winfo_height() / 2
            for kind in (
                Quartz.kCGEventMouseMoved,
                Quartz.kCGEventLeftMouseDown,
                Quartz.kCGEventLeftMouseUp,
            ):
                event = Quartz.CGEventCreateMouseEvent(
                    None, kind, (float(x), float(y)), Quartz.kCGMouseButtonLeft
                )
                Quartz.CGEventSetFlags(event, 0)
                Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)
                time.sleep(0.05)
            pump(0.5)
            body = player._description_body
            check(
                "native click expands description in place",
                player._description_expanded
                and player._description_panel.winfo_ismapped()
                and player._details_visible
                and button.cget("text") == "Show less",
            )
            check(
                "expansion is adjacent to the excerpt",
                abs(body.winfo_rootx() - button.winfo_rootx()) < 5
                and 0 < button.winfo_rooty() - body.winfo_rooty() < 140,
            )
            content = body.get("1.0", "end-1c")
            check(
                "full original description retained",
                original == content and body.cget("state") == "disabled",
            )
            check(
                "expanded description height stays bounded",
                int(body.cget("height")) == 4 and body.winfo_height() < 110,
            )
            check("long text can scroll to its final line", body.yview()[1] < 1)
            body.yview_moveto(1)
            pump(0.1)
            check("final line remains reachable", body.yview()[1] == 1)
            body.yview_moveto(0)
            pump(0.1)
            capture("expanded")
            button.focus_set()
            for pressed in (True, False):
                event = Quartz.CGEventCreateKeyboardEvent(None, 49, pressed)
                Quartz.CGEventSetFlags(event, 0)
                Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)
                time.sleep(0.05)
            pump(0.3)
            check(
                "keyboard Show less restores quiet excerpt",
                not player._description_expanded
                and not player._description_panel.winfo_ismapped()
                and player._description_excerpt.winfo_ismapped()
                and button.cget("text") == "Read more",
            )
            player.close()
            pump(0.6)
            app.download_history = [dict(row, description="A quiet afternoon.")]
            app._reconcile_library_projection()
            player = open_player()
            check(
                "short description does not add a control",
                not player._description_more.winfo_ismapped(),
            )
            capture("short")
            check("native callbacks clean", not evidence["callback_errors"])
            evidence["passed"] = True
    finally:
        if app is not None:
            app.destroy()
        (output / f"description-{width}.json").write_text(
            json.dumps(evidence, indent=2) + "\n"
        )
