"""Profile actual native drag of an isolated full VODForge source UI.

This is source-native performance evidence, never a packaged release receipt.
Only startup services and private state are isolated by the maintained preview
context; layout/render owners are unmodified. A ready screenshot/geometry is
written before input. Create output/continue after inspecting it to start.
"""

import argparse
import cProfile
import ctypes as C
import hashlib
import io
import json
import os
import platform
import pstats
import subprocess
import sys
import threading
import time
import traceback
from ctypes import wintypes as W
from pathlib import Path
from unittest.mock import patch

parser = argparse.ArgumentParser()
parser.add_argument("--source", type=Path, required=True)
parser.add_argument("--output", type=Path, required=True)
parser.add_argument("--rows", type=int, choices=(0, 25, 5000), default=25)
parser.add_argument(
    "--profile", action="store_true", help="Enable cProfile for attribution only"
)
parser.add_argument("--view", choices=("library", "forge"), default="library")
args = parser.parse_args()
run = args.output.resolve()
run.mkdir(parents=True, exist_ok=False)
source = args.source.resolve()
sys.path.insert(0, str(source))
os.environ["VODFORGE_DISABLE_TELEMETRY"] = "1"
from PIL import ImageGrab

from scripts.focus_ui_preview import approved_metadata, isolated_preview_services
from yt_downloader.analytics_startup import AnalyticsStartup
from yt_downloader.app import DownloaderApp
from yt_downloader.engagement_ui import EngagementUI

if sys.platform == "win32":
    u = C.windll.user32
    u.GetAncestor.argtypes = [W.HWND, W.UINT]
    u.GetAncestor.restype = W.HWND
    u.GetForegroundWindow.restype = W.HWND
    u.GetWindowRect.argtypes = [W.HWND, C.POINTER(W.RECT)]
    u.GetWindowThreadProcessId.argtypes = [W.HWND, C.POINTER(W.DWORD)]
    u.SetForegroundWindow.argtypes = [W.HWND]
    u.GetDpiForWindow.argtypes = [W.HWND]
    u.GetDpiForWindow.restype = W.UINT
else:
    import AppKit
    import Quartz

finished = threading.Event()
events = []
configures = []
heartbeats = []
native_rects = []
profile = cProfile.Profile()
failure = []
callback_errors = []
pid = os.getpid()


def record(name, **fields):
    events.append({"t": time.perf_counter(), "event": name, **fields})


def mac_windows():
    return [
        dict(w)
        for w in Quartz.CGWindowListCopyWindowInfo(
            Quartz.kCGWindowListOptionOnScreenOnly, 0
        )
        if w.get("kCGWindowOwnerPID") == pid
        and w.get("kCGWindowName") == "VODForge Resize QA"
    ]


def rect(hwnd):
    if sys.platform == "win32":
        result = W.RECT()
        if not u.GetWindowRect(hwnd, C.byref(result)):
            raise RuntimeError("QA window rectangle unavailable")
        return [result.left, result.top, result.right, result.bottom]
    matches = [w for w in mac_windows() if w["kCGWindowNumber"] == hwnd]
    if len(matches) != 1:
        raise RuntimeError("Owned native window is not uniquely visible")
    b = matches[0]["kCGWindowBounds"]
    return [b["X"], b["Y"], b["X"] + b["Width"], b["Y"] + b["Height"]]


def own_foreground():
    if sys.platform == "win32":
        owner = W.DWORD()
        foreground = u.GetForegroundWindow()
        u.GetWindowThreadProcessId(foreground, C.byref(owner))
        actual = owner.value
    else:
        actual = (
            AppKit.NSWorkspace.sharedWorkspace()
            .frontmostApplication()
            .processIdentifier()
        )
    if actual != pid:
        raise RuntimeError("foreground is not owned by this QA process")


def cursor(x, y, *, dragged=False):
    if sys.platform == "win32":
        u.SetCursorPos(x, y)
    else:
        kind = Quartz.kCGEventLeftMouseDragged if dragged else Quartz.kCGEventMouseMoved
        Quartz.CGEventPost(
            Quartz.kCGHIDEventTap,
            Quartz.CGEventCreateMouseEvent(
                None, kind, (x, y), Quartz.kCGMouseButtonLeft
            ),
        )


def mouse_button(down):
    if sys.platform == "win32":
        u.mouse_event(2 if down else 4, 0, 0, 0, 0)
    else:
        point = Quartz.CGEventGetLocation(Quartz.CGEventCreate(None))
        Quartz.CGEventPost(
            Quartz.kCGHIDEventTap,
            Quartz.CGEventCreateMouseEvent(
                None,
                Quartz.kCGEventLeftMouseDown if down else Quartz.kCGEventLeftMouseUp,
                point,
                Quartz.kCGMouseButtonLeft,
            ),
        )


def window_dpi(hwnd):
    return u.GetDpiForWindow(hwnd) if sys.platform == "win32" else None


def shot(name):
    if sys.platform == "win32":
        ImageGrab.grab().save(run / name)
    else:
        x, y, right, bottom = rect(hwnd)
        rectangle = ",".join(str(round(v)) for v in (x, y, right - x, bottom - y))
        subprocess.run(
            ["/usr/sbin/screencapture", "-x", f"-R{rectangle}", str(run / name)],
            check=True,
            timeout=10,
        )


def drag(hwnd, target_width, target_height, number):
    own_foreground()
    box = rect(hwnd)
    start = (box[2] - 2, box[3] - 2)
    end = (box[0] + target_width - 2, box[1] + target_height - 2)
    cursor(*start)
    time.sleep(0.10)
    own_foreground()
    record(
        "drag_start",
        rect=box,
        target=[target_width, target_height],
        cpu=time.process_time(),
    )
    mouse_button(True)
    try:
        began = time.perf_counter()
        for index in range(1, 91):
            own_foreground()
            fraction = index / 90
            cursor(
                round(start[0] + (end[0] - start[0]) * fraction),
                round(start[1] + (end[1] - start[1]) * fraction),
                dragged=True,
            )
            native_rects.append({"t": time.perf_counter(), "rect": rect(hwnd)})
            time.sleep(max(0, began + index / 30 - time.perf_counter()))
    finally:
        mouse_button(False)
    record("drag_end", rect=rect(hwnd), cpu=time.process_time())
    time.sleep(0.65)
    shot(f"settled-{number}.png")


def drive(hwnd, screen):
    try:
        deadline = time.monotonic() + 180
        while not (run / "continue").exists():
            if time.monotonic() > deadline:
                raise RuntimeError("ready window was not released for input")
            time.sleep(0.1)
        own_foreground()
        max_width = min(1450, screen[0] - 80)
        max_height = min(900, screen[1] - 80)
        for index, size in enumerate(
            [(880, 610), (max_width, max_height), (920, 650), (max_width, max_height)]
        ):
            drag(hwnd, *size, index)
        record("driver_complete")
    except Exception as exc:  # noqa: BLE001 - preserve any native driver failure
        failure.append(f"{type(exc).__name__}: {exc}")
        record("driver_failed", error=failure[-1])
    finally:
        finished.set()


with (
    isolated_preview_services(),
    patch.object(AnalyticsStartup, "start", return_value=None),
    patch.object(EngagementUI, "start", return_value=None),
):
    app = DownloaderApp()
    app.title("VODForge Resize QA")
    app.geometry("1100x740+30+30")
    base = approved_metadata()
    app.metadata_items = [
        {
            **base[i % len(base)],
            "id": f"resize-qa-{i}",
            "title": f"Generated resize fixture {i:05d}",
            "vodforge_projection_owner": f"preview:resize:{i}",
            "vodforge_annotation_owner": f"preview:resize:{i}",
        }
        for i in range(args.rows)
    ]
    app._render_metadata_tree(selected_index=0 if args.rows else None)
    app._select_focus_view(args.view)

    def callback_failed(*items):
        callback_errors.append("".join(traceback.format_exception(*items)))
        (run / "callback-error.txt").write_text("\n".join(callback_errors))
        app.destroy()

    app.report_callback_exception = callback_failed
    app.update()
    if sys.platform == "win32":
        hwnd = u.GetAncestor(app.winfo_id(), 2)
        u.SetForegroundWindow(hwnd)
        if u.GetForegroundWindow() != hwnd:
            u.keybd_event(0x12, 0, 0, 0)
            u.SetForegroundWindow(hwnd)
            u.keybd_event(0x12, 0, 2, 0)
        screen = (u.GetSystemMetrics(0), u.GetSystemMetrics(1))
    else:
        native = AppKit.NSRunningApplication.runningApplicationWithProcessIdentifier_(
            pid
        )
        native.activateWithOptions_(AppKit.NSApplicationActivateIgnoringOtherApps)
        candidates = mac_windows()
        if len(candidates) != 1:
            raise RuntimeError("QA native window was not uniquely identified")
        hwnd = candidates[0]["kCGWindowNumber"]
        screen = (
            int(Quartz.CGDisplayBounds(Quartz.CGMainDisplayID()).size.width),
            int(Quartz.CGDisplayBounds(Quartz.CGMainDisplayID()).size.height),
        )
    app.bind(
        "<Configure>",
        lambda e: (
            configures.append(
                {"t": time.perf_counter(), "width": e.width, "height": e.height}
            )
            if e.widget is app
            else None
        ),
        add="+",
    )
    last = [time.perf_counter()]
    began = time.perf_counter()
    cpu_began = time.process_time()

    def beat():
        now = time.perf_counter()
        heartbeats.append({"t": now, "gap_ms": (now - last[0]) * 1000})
        last[0] = now
        if finished.is_set():
            complete()
        else:
            app.after(16, beat)

    def complete():
        if args.profile:
            profile.disable()
            profile.dump_stats(str(run / "resize.prof"))
            stream = io.StringIO()
            pstats.Stats(profile, stream=stream).strip_dirs().sort_stats(
                "cumulative"
            ).print_stats(70)
            (run / "profile.txt").write_text(stream.getvalue())
        starts = [x for x in events if x["event"] == "drag_start"]
        ends = [x for x in events if x["event"] == "drag_end"]
        intervals = list(zip(starts, ends, strict=False))
        active = [
            x["gap_ms"]
            for x in heartbeats
            if any(
                a["t"] <= x["t"] - x["gap_ms"] / 1000 <= x["t"] <= b["t"]
                for a, b in intervals
            )
        ]
        summary = {
            "pid": pid,
            "profiling_enabled": args.profile,
            "python": sys.version,
            "executable": sys.executable,
            "os": platform.platform(),
            "driver_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "rows": args.rows,
            "view": args.view,
            "tk": str(app.tk.call("info", "patchlevel")),
            "dpi": window_dpi(hwnd),
            "tk_scaling": app.tk.call("tk", "scaling"),
            "screen": screen,
            "final_rect": rect(hwnd),
            "elapsed_seconds": time.perf_counter() - began,
            "cpu_seconds": time.process_time() - cpu_began,
            "configure_count": len(configures),
            "heartbeat_count": len(heartbeats),
            "max_gap_ms": max(active, default=0),
            "drag_cpu_seconds": sum(b["cpu"] - a["cpu"] for a, b in intervals),
            "drag_wall_seconds": sum(b["t"] - a["t"] for a, b in intervals),
            "drag_p95_gap_ms": sorted(active)[int((len(active) - 1) * 0.95)]
            if active
            else 0,
            "measurement": "quiet native drag, no screen capture during measured intervals",
            "gaps_over_50ms": sum(x > 50 for x in active),
            "gaps_over_100ms": sum(x > 100 for x in active),
            "errors": failure,
            "callback_errors": callback_errors,
            "source_hashes": {
                str(f.relative_to(source)): hashlib.sha256(f.read_bytes()).hexdigest()
                for f in (source / "yt_downloader").glob("*.py")
            },
        }
        (run / "receipt.json").write_text(json.dumps(summary, indent=2))
        (run / "trace.json").write_text(
            json.dumps(
                {
                    "events": events,
                    "heartbeats": heartbeats,
                    "configures": configures,
                    "native_rects": native_rects,
                },
                indent=2,
            )
        )
        shot("final.png")
        app.destroy()

    def ready():
        shot("ready.png")
        (run / "ready.json").write_text(
            json.dumps(
                {
                    "pid": pid,
                    "hwnd": hwnd,
                    "rect": rect(hwnd),
                    "screen": screen,
                    "rows": args.rows,
                    "view": args.view,
                    "dpi": window_dpi(hwnd),
                }
            )
        )
        if args.profile:
            profile.enable()
        threading.Thread(target=drive, args=(hwnd, screen), daemon=True).start()
        beat()

    app.after(1200, ready)
    app.mainloop()
sys.exit(1 if failure or callback_errors else 0)
