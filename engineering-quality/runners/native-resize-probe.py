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
import tkinter as tk
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
parser.add_argument(
    "--baseline",
    action="store_true",
    help="Representative Tk controls without app layout work",
)
parser.add_argument("--hz", type=int, choices=(30, 60), default=30)
parser.add_argument("--drag-count", type=int, choices=(2, 4), default=4)
parser.add_argument(
    "--timing",
    action="store_true",
    help="Time existing layout/render calls; attribution only",
)
parser.add_argument(
    "--timing-details",
    action="store_true",
    help="Include nested scene work; attribution only, requires --timing",
)
parser.add_argument(
    "--no-observer",
    action="store_true",
    help="Paired observer-overhead control; no continuous native-frame evidence",
)
parser.add_argument("--edge", choices=("corner", "right"), default="corner")
parser.add_argument(
    "--baseline-chrome",
    action="store_true",
    help="Use app native chrome on the Tk baseline",
)
parser.add_argument(
    "--pixel-capture",
    action="store_true",
    help="Bounded separate-process own-window pixels during drag; pair with no-capture control",
)
parser.add_argument(
    "--windows-composited",
    action="store_true",
    help="Diagnostic Win32 descendant double-buffering experiment",
)
parser.add_argument(
    "--pixel-screen-crop",
    action="store_true",
    help="Diagnostic unobscured foreground screen pixels within owned Windows HWND",
)
args = parser.parse_args()
if args.timing_details and not args.timing:
    parser.error("--timing-details requires --timing")
if args.pixel_capture and sys.platform not in {"darwin", "win32"}:
    parser.error("--pixel-capture requires a Mac or Windows own-window recorder")
if args.windows_composited and sys.platform != "win32":
    parser.error("--windows-composited requires Windows")
if args.pixel_screen_crop and (sys.platform != "win32" or not args.pixel_capture):
    parser.error("--pixel-screen-crop requires Windows --pixel-capture")
run = args.output.resolve()
run.mkdir(parents=True, exist_ok=False)
source = args.source.resolve()
source_before = {
    str(f.relative_to(source)): hashlib.sha256(f.read_bytes()).hexdigest()
    for f in (source / "yt_downloader").rglob("*.py")
}
sys.path.insert(0, str(source))
sys.path.insert(0, str(source / "engineering-quality"))
os.environ["VODFORGE_DISABLE_TELEMETRY"] = "1"
from PIL import ImageGrab
from quality_harness.resize_observations import overlapping_heartbeat_gaps

from scripts.focus_ui_preview import approved_metadata, isolated_preview_services
from yt_downloader.analytics_startup import AnalyticsStartup
from yt_downloader.app import DownloaderApp
from yt_downloader.engagement_ui import EngagementUI

if sys.platform == "win32":
    u = C.windll.user32
    u.IsWindow.argtypes = [W.HWND]
    u.IsWindowVisible.argtypes = [W.HWND]
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
work_calls = []
observer_stop = threading.Event()
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
        # Win32 expects integer screen coordinates; the right-edge midpoint
        # may be fractional on an odd-height window.
        u.SetCursorPos(round(x), round(y))
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
        # Keep even setup and settled evidence inside the attested HWND. A
        # desktop grab can capture unrelated users' windows beside VODForge.
        if not u.IsWindow(hwnd) or not u.IsWindowVisible(hwnd):
            raise RuntimeError("Owned QA window unavailable for capture")
        owner = W.DWORD()
        u.GetWindowThreadProcessId(hwnd, C.byref(owner))
        if owner.value != pid:
            raise RuntimeError("QA window changed owner before capture")
        ImageGrab.grab(window=hwnd).save(run / name)
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
    if args.edge == "right":
        start = (box[2] - 2, (box[1] + box[3]) / 2)
        end = (box[0] + target_width - 2, start[1])
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
        for index in range(1, 3 * args.hz + 1):
            own_foreground()
            fraction = index / (3 * args.hz)
            point = (
                round(start[0] + (end[0] - start[0]) * fraction),
                round(start[1] + (end[1] - start[1]) * fraction),
            )
            post_start = time.perf_counter()
            cursor(
                *point,
                dragged=True,
            )
            record("drag_post", point=point, post_start=post_start)
            time.sleep(max(0, began + index / args.hz - time.perf_counter()))
    finally:
        mouse_button(False)
    record("drag_end", rect=rect(hwnd), cpu=time.process_time())
    time.sleep(0.65)
    shot(f"settled-{number}.png")


def drive(hwnd, screen):
    recorder = None
    capture_log = None
    capture_dir = run / "pixels"
    try:
        deadline = time.monotonic() + 180
        while not (run / "continue").exists():
            if time.monotonic() > deadline:
                raise RuntimeError("ready window was not released for input")
            time.sleep(0.1)
        own_foreground()
        if args.pixel_capture:
            capture_dir.mkdir()
            origin = time.monotonic()
            (capture_dir / "origin.json").write_text(
                json.dumps(
                    {
                        "monotonic": origin,
                        "perf_counter": time.perf_counter(),
                        "pid": pid,
                        "window": int(hwnd),
                        "scope": "own-window server pixels; not physical display refresh",
                    }
                )
            )
            capture_log = (capture_dir / "recorder.log").open("w")
            recorder = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "quality_harness.window_capture",
                    str(hwnd),
                    str(origin),
                    str(capture_dir),
                    "--interval",
                    ".05" if sys.platform == "win32" else ".1",
                    *(["--owner-pid", str(pid)] if sys.platform == "win32" else []),
                    *(["--screen-crop"] if args.pixel_screen_crop else []),
                ],
                stdout=capture_log,
                stderr=subprocess.STDOUT,
            )
            capture_deadline = time.monotonic() + 10
            while not (capture_dir / "capture.ready").exists():
                if recorder.poll() is not None or time.monotonic() > capture_deadline:
                    raise RuntimeError("pixel recorder did not become ready")
                time.sleep(0.05)
            record("pixel_recorder_ready", recorder_pid=recorder.pid)
        max_width = min(1450, screen[0] - 80)
        max_height = min(900, screen[1] - 80)
        # Stay above admitted minimums; constraint clamping is not frame lag.
        sizes = [
            (max_width, max_height),
            (1100, 740),
            (max_width, max_height),
            (1100, 740),
        ]
        for index, size in enumerate(sizes[: args.drag_count]):
            drag(hwnd, *size, index)
        record("driver_complete")
    except Exception as exc:  # noqa: BLE001 - preserve any native driver failure
        failure.append(f"{type(exc).__name__}: {exc}")
        record("driver_failed", error=failure[-1])
    finally:
        if recorder is not None:
            (capture_dir / "capture.stop").touch()
            try:
                code = recorder.wait(timeout=30)
                if code:
                    failure.append(f"pixel recorder exited {code}")
            except subprocess.TimeoutExpired:
                recorder.terminate()
                try:
                    recorder.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    recorder.kill()
                    recorder.wait(timeout=5)
                failure.append("pixel recorder did not finish within its bound")
            capture_log.close()
        observer_stop.set()
        finished.set()


def observe_frame(hwnd):
    """Independent cursor/frame samples with explicit query intervals, no pixels."""
    try:
        while not observer_stop.is_set():
            begin = time.perf_counter()
            if sys.platform == "darwin":
                point = Quartz.CGEventGetLocation(Quartz.CGEventCreate(None))
                pointer = [float(point.x), float(point.y)]
                pressed = bool(
                    Quartz.CGEventSourceButtonState(
                        Quartz.kCGEventSourceStateCombinedSessionState,
                        Quartz.kCGMouseButtonLeft,
                    )
                )
            else:
                point = W.POINT()
                u.GetCursorPos(C.byref(point))
                pointer = [point.x, point.y]
                pressed = bool(u.GetAsyncKeyState(1) & 0x8000)
            pointer_end = time.perf_counter()
            box = rect(hwnd)
            end = time.perf_counter()
            native_rects.append(
                {
                    "sample_start": begin,
                    "pointer_end": pointer_end,
                    "t": end,
                    "pointer": pointer,
                    "pressed": pressed,
                    "rect": box,
                    "query_ms": (end - begin) * 1000,
                }
            )
            observer_stop.wait(max(0, 0.01 - (time.perf_counter() - begin)))
    except Exception as exc:  # noqa: BLE001 - observer failure invalidates evidence
        failure.append("observer: " + repr(exc))


with (
    isolated_preview_services(),
    patch.object(AnalyticsStartup, "start", return_value=None),
    patch.object(EngagementUI, "start", return_value=None),
):
    if args.baseline:
        from tkinter import ttk

        app = tk.Tk()
        app.minsize(880, 610)
        if args.baseline_chrome:
            from yt_downloader.platforms.macos.windowing import integrate_main_window

            integrate_main_window(app, "VODForge Resize QA", print)
        shell = ttk.Frame(app, padding=20)
        shell.pack(fill="both", expand=True)
        ttk.Label(shell, text="Representative Tk resize baseline").pack(anchor="w")
        ttk.Button(shell, text="Ordinary native control").pack(anchor="w")
        canvas = tk.Canvas(shell, background="#302c38", highlightthickness=0)
        canvas.pack(fill="both", expand=True)
        for i in range(25):
            canvas.create_text(
                20,
                20 + i * 20,
                text=f"Representative row {i}",
                anchor="nw",
                fill="#eeeeee",
            )
        app._request_application_close = app.destroy
    else:
        app = DownloaderApp()
    app.title("VODForge Resize QA")
    app.geometry("1100x740+30+30")
    base = approved_metadata()
    if not args.baseline:
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
        if args.timing:
            timing_stack = []

            def timed(owner, name, label=None):
                original = getattr(owner, name)

                def call(*a, **kw):
                    start = time.perf_counter()
                    entry = {
                        "name": label or name,
                        "start": start,
                        "depth": len(timing_stack),
                    }
                    timing_stack.append(entry)
                    try:
                        return original(*a, **kw)
                    finally:
                        entry["end"] = time.perf_counter()
                        timing_stack.pop()
                        work_calls.append(entry)

                setattr(owner, name, call)

            timed(app, "_apply_focus_layout")
            timed(app.library_scene, "_render")
            if args.timing_details:
                for name in (
                    "_browse",
                    "_categories",
                    "_collection_card",
                    "_surface",
                    "_toolbar",
                    "_media_card",
                    "_artwork_begin",
                    "_artwork_image",
                    "_artwork_request",
                    "_fit",
                    "_presentation_settle",
                ):
                    timed(app.library_scene, name)
                timed(app.library_scene._depth, "draw", "surface_cache.draw")

    def callback_failed(*items):
        callback_errors.append("".join(traceback.format_exception(*items)))
        (run / "callback-error.txt").write_text("\n".join(callback_errors))
        # Never recursively destroy Tcl widgets from its exception callback.
        # Exit the loop; the outer owner performs cleanup and records the error.
        app.quit()

    app.report_callback_exception = callback_failed
    app.update()
    if sys.platform == "win32":
        hwnd = u.GetAncestor(app.winfo_id(), 2)
        if args.windows_composited:
            u.GetWindowLongW.argtypes = [W.HWND, C.c_int]
            u.SetWindowLongW.argtypes = [W.HWND, C.c_int, C.c_long]
            u.SetWindowPos.argtypes = [W.HWND, W.HWND, C.c_int, C.c_int, C.c_int, C.c_int, W.UINT]
            current = u.GetWindowLongW(hwnd, -20)
            C.set_last_error(0)
            previous = u.SetWindowLongW(hwnd, -20, current | 0x02000000)
            if not previous and C.get_last_error():
                raise RuntimeError("Windows composited style could not be applied")
            if not u.SetWindowPos(hwnd, None, 0, 0, 0, 0, 0x0027):
                raise RuntimeError("Windows composited frame refresh failed")
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
        # Timers can be deferred for the whole native drag. Contained-only
        # samples omit that gap when the next callback runs after mouse-up.
        overlapping = overlapping_heartbeat_gaps(
            heartbeats, [(a["t"], b["t"]) for a, b in intervals]
        )
        summary = {
            "pid": pid,
            "profiling_enabled": args.profile,
            "pixel_capture_enabled": args.pixel_capture,
            "pixel_screen_crop": args.pixel_screen_crop,
            "windows_composited": args.windows_composited,
            "baseline": args.baseline,
            "baseline_chrome": args.baseline_chrome,
            "edge": args.edge,
            "work_timing_enabled": args.timing,
            "work_timing_details": args.timing_details,
            "frame_observer_enabled": not args.no_observer,
            "input_hz": args.hz,
            "window_minimum": app.minsize(),
            "python": sys.version,
            "executable": sys.executable,
            "os": platform.platform(),
            "driver_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "rows": args.rows,
            "view": args.view,
            "tcl": str(app.tk.call("info", "patchlevel")),
            "tk": str(app.tk.call("package", "provide", "Tk")),
            "dpi": window_dpi(hwnd),
            "tk_scaling": app.tk.call("tk", "scaling"),
            "screen": screen,
            "final_rect": rect(hwnd),
            "elapsed_seconds": time.perf_counter() - began,
            "cpu_seconds": time.process_time() - cpu_began,
            "configure_count": len(configures),
            "heartbeat_count": len(heartbeats),
            "max_gap_ms": max(active, default=0),
            "heartbeat_scope": "legacy contained intervals; crossing gaps reported separately",
            "overlapping_heartbeat_count": len(overlapping),
            "overlapping_max_gap_ms": max(overlapping, default=0),
            "drag_cpu_seconds": sum(b["cpu"] - a["cpu"] for a, b in intervals),
            "drag_wall_seconds": sum(b["t"] - a["t"] for a, b in intervals),
            "drag_p95_gap_ms": sorted(active)[int((len(active) - 1) * 0.95)]
            if active
            else 0,
            "measurement": (
                "attribution native drag"
                if args.timing or args.profile
                else "quiet native drag"
            )
            + (
                ", independent own-window frame capture during measured intervals"
                if args.pixel_capture
                else ", no screen capture during measured intervals"
            ),
            "gaps_over_50ms": sum(x > 50 for x in active),
            "gaps_over_100ms": sum(x > 100 for x in active),
            "errors": failure,
            "callback_errors": callback_errors,
            "source_hashes": {
                str(f.relative_to(source)): hashlib.sha256(f.read_bytes()).hexdigest()
                for f in (source / "yt_downloader").rglob("*.py")
            },
        }
        summary["source_hashes_before"] = source_before
        summary["source_unchanged"] = source_before == summary["source_hashes"]
        if not summary["source_unchanged"]:
            failure.append("runtime source changed during native measurement")
        summary["application_closed"] = False
        (run / "measurement.json").write_text(json.dumps(summary, indent=2))
        (run / "trace.json").write_text(
            json.dumps(
                {
                    "events": events,
                    "heartbeats": heartbeats,
                    "configures": configures,
                    "native_rects": native_rects,
                    "work_calls": work_calls,
                },
                indent=2,
            )
        )
        shot("final.png")
        app._request_application_close()

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
        if not args.no_observer:
            threading.Thread(target=observe_frame, args=(hwnd,), daemon=True).start()
        threading.Thread(target=drive, args=(hwnd, screen), daemon=True).start()
        beat()

    app.after(1200, ready)
    app.mainloop()
    try:
        if app.winfo_exists():
            # Error/early-loop exit only; normal completion closes through the
            # application's own worker/settings/telemetry shutdown authority.
            app.destroy()
    except tk.TclError:
        pass
    try:
        closed = not bool(app.winfo_exists())
    except tk.TclError:
        closed = True
    measurement = run / "measurement.json"
    if measurement.exists():
        summary = json.loads(measurement.read_text())
        summary["callback_errors"] = list(callback_errors)
        summary["errors"] = list(failure)
        summary["application_closed"] = closed
        (run / "receipt.json").write_text(json.dumps(summary, indent=2))
    else:
        failure.append("native measurement did not complete")
sys.exit(1 if failure or callback_errors or not closed else 0)
