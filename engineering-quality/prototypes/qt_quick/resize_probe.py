"""Native two-drag comparison for the isolated Qt Quick Forge prototype.

It uses the maintained VODForge pointer and transition-pixel oracles. This
source-native result does not qualify a signed or installed application.
"""

from __future__ import annotations

import argparse
import ctypes as C
import json
import os
import subprocess
import sys
import threading
import time
from ctypes import wintypes as W
from pathlib import Path

import psutil

SOURCE = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(SOURCE / "engineering-quality"))
from quality_harness.resize_observations import assess_pointer_tracking

if sys.platform == "win32":
    from PIL import ImageGrab

    user32 = C.windll.user32
    ENUM_WINDOW_PROC = C.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)
    user32.EnumWindows.argtypes = [ENUM_WINDOW_PROC, W.LPARAM]
    user32.GetWindowThreadProcessId.argtypes = [W.HWND, C.POINTER(W.DWORD)]
    user32.GetWindowRect.argtypes = [W.HWND, C.POINTER(W.RECT)]
    user32.GetForegroundWindow.restype = W.HWND
    user32.SetForegroundWindow.argtypes = [W.HWND]
else:
    import AppKit
    import Quartz


def window_for_pid(pid: int, reported_hwnd: int | None = None) -> int | None:
    if sys.platform == "win32":
        if reported_hwnd:
            owner = W.DWORD()
            user32.GetWindowThreadProcessId(reported_hwnd, C.byref(owner))
            bounds = W.RECT()
            user32.GetWindowRect(reported_hwnd, C.byref(bounds))
            if (
                owner.value == pid
                and user32.IsWindowVisible(reported_hwnd)
                and bounds.right - bounds.left >= 500
                and bounds.bottom - bounds.top >= 400
            ):
                return reported_hwnd
        matches: list[int] = []

        @ENUM_WINDOW_PROC
        def callback(hwnd: int, _value: int) -> bool:
            owner = W.DWORD()
            user32.GetWindowThreadProcessId(hwnd, C.byref(owner))
            if owner.value == pid and user32.IsWindowVisible(hwnd):
                bounds = W.RECT()
                if user32.GetWindowRect(hwnd, C.byref(bounds)) and (
                    bounds.right - bounds.left >= 500
                    and bounds.bottom - bounds.top >= 400
                ):
                    matches.append(hwnd)
            return True

        user32.EnumWindows(callback, 0)
        return matches[0] if len(matches) == 1 else None
    matches = [
        w
        for w in Quartz.CGWindowListCopyWindowInfo(
            Quartz.kCGWindowListOptionOnScreenOnly, Quartz.kCGNullWindowID
        )
        if w.get("kCGWindowOwnerPID") == pid
        and "VODForge" in str(w.get("kCGWindowName") or "")
        and "prototype" in str(w.get("kCGWindowName") or "")
    ]
    return int(matches[0]["kCGWindowNumber"]) if len(matches) == 1 else None


def windows_inventory(pid: int, reported_hwnd: int | None = None) -> list[dict]:
    if sys.platform != "win32":
        return []
    inventory: list[dict] = []

    @ENUM_WINDOW_PROC
    def callback(hwnd: int, _value: int) -> bool:
        owner = W.DWORD()
        user32.GetWindowThreadProcessId(hwnd, C.byref(owner))
        if owner.value == pid:
            length = user32.GetWindowTextLengthW(hwnd)
            title = C.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, title, length + 1)
            bounds = W.RECT()
            user32.GetWindowRect(hwnd, C.byref(bounds))
            inventory.append(
                {
                    "hwnd": hwnd,
                    "visible": bool(user32.IsWindowVisible(hwnd)),
                    "title": title.value,
                    "rect": [bounds.left, bounds.top, bounds.right, bounds.bottom],
                }
            )
        return True

    user32.EnumWindows(callback, 0)
    if reported_hwnd:
        owner = W.DWORD()
        user32.GetWindowThreadProcessId(reported_hwnd, C.byref(owner))
        bounds = W.RECT()
        user32.GetWindowRect(reported_hwnd, C.byref(bounds))
        inventory.append(
            {
                "reported_hwnd": reported_hwnd,
                "owner": owner.value,
                "visible": bool(user32.IsWindowVisible(reported_hwnd)),
                "rect": [bounds.left, bounds.top, bounds.right, bounds.bottom],
            }
        )
    return inventory


def rect(hwnd: int, pid: int) -> list[float]:
    if sys.platform == "win32":
        owner = W.DWORD()
        user32.GetWindowThreadProcessId(hwnd, C.byref(owner))
        if owner.value != pid:
            raise RuntimeError("Window ownership changed")
        result = W.RECT()
        if not user32.GetWindowRect(hwnd, C.byref(result)):
            raise RuntimeError("Window rectangle unavailable")
        return [result.left, result.top, result.right, result.bottom]
    matches = [
        w
        for w in Quartz.CGWindowListCopyWindowInfo(
            Quartz.kCGWindowListOptionOnScreenOnly, Quartz.kCGNullWindowID
        )
        if w.get("kCGWindowOwnerPID") == pid and w.get("kCGWindowNumber") == hwnd
    ]
    if len(matches) != 1:
        raise RuntimeError("Owned Mac window unavailable")
    bounds = matches[0]["kCGWindowBounds"]
    return [
        bounds["X"],
        bounds["Y"],
        bounds["X"] + bounds["Width"],
        bounds["Y"] + bounds["Height"],
    ]


def foreground(hwnd: int, pid: int) -> None:
    if sys.platform == "win32":
        user32.SetForegroundWindow(hwnd)
        active = user32.GetForegroundWindow()
        owner = W.DWORD()
        user32.GetWindowThreadProcessId(active, C.byref(owner))
        if owner.value != pid:
            raise RuntimeError("Qt QA window is not foreground")
    else:
        application = (
            AppKit.NSRunningApplication.runningApplicationWithProcessIdentifier_(pid)
        )
        if application is None:
            raise RuntimeError("Qt QA application unavailable")
        application.activateWithOptions_(AppKit.NSApplicationActivateIgnoringOtherApps)
        time.sleep(0.1)
        active = AppKit.NSWorkspace.sharedWorkspace().frontmostApplication()
        if active.processIdentifier() != pid:
            raise RuntimeError("Qt QA application is not foreground")


def pointer() -> tuple[list[float], bool]:
    if sys.platform == "win32":
        point = W.POINT()
        user32.GetCursorPos(C.byref(point))
        return [point.x, point.y], bool(user32.GetAsyncKeyState(1) & 0x8000)
    point = Quartz.CGEventGetLocation(Quartz.CGEventCreate(None))
    pressed = Quartz.CGEventSourceButtonState(
        Quartz.kCGEventSourceStateCombinedSessionState,
        Quartz.kCGMouseButtonLeft,
    )
    return [float(point.x), float(point.y)], bool(pressed)


def move(x: float, y: float, *, dragged: bool = False) -> None:
    if sys.platform == "win32":
        user32.SetCursorPos(round(x), round(y))
    else:
        event = Quartz.CGEventCreateMouseEvent(
            None,
            Quartz.kCGEventLeftMouseDragged if dragged else Quartz.kCGEventMouseMoved,
            (x, y),
            Quartz.kCGMouseButtonLeft,
        )
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)


def button(down: bool) -> None:
    if sys.platform == "win32":
        user32.mouse_event(2 if down else 4, 0, 0, 0, 0)
    else:
        point = Quartz.CGEventGetLocation(Quartz.CGEventCreate(None))
        event = Quartz.CGEventCreateMouseEvent(
            None,
            Quartz.kCGEventLeftMouseDown if down else Quartz.kCGEventLeftMouseUp,
            point,
            Quartz.kCGMouseButtonLeft,
        )
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)


def capture(hwnd: int, pid: int, path: Path) -> None:
    if sys.platform == "win32":
        owner = W.DWORD()
        user32.GetWindowThreadProcessId(hwnd, C.byref(owner))
        if owner.value != pid:
            raise RuntimeError("Capture target changed owner")
        ImageGrab.grab(window=hwnd).save(path)
    else:
        box = rect(hwnd, pid)
        region = ",".join(
            str(round(v)) for v in (box[0], box[1], box[2] - box[0], box[3] - box[1])
        )
        subprocess.run(
            ["/usr/sbin/screencapture", "-x", f"-R{region}", str(path)],
            check=True,
            timeout=10,
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--qt-python", type=Path, required=True)
    parser.add_argument(
        "--app-script", type=Path, default=Path(__file__).with_name("main.py")
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--pixel-capture", action="store_true")
    parser.add_argument("--corner-stress", action="store_true")
    args = parser.parse_args()
    if args.corner_stress and args.pixel_capture:
        parser.error(
            "corner stress and sustained-epoch pixel capture are separate runs"
        )
    run = args.output.resolve()
    run.mkdir(parents=True, exist_ok=False)
    ready = run / "ready.json"
    log = (run / "qt.log").open("w", encoding="utf-8")
    child = subprocess.Popen(
        [
            str(args.qt_python),
            str(args.app_script.resolve()),
            "--ready-file",
            str(ready),
            "--event-log",
            str(run / "actions.jsonl"),
        ],
        cwd=SOURCE,
        stdout=log,
        stderr=subprocess.STDOUT,
    )
    events: list[dict] = []
    samples: list[dict] = []
    stop = threading.Event()
    errors: list[str] = []
    recorder: subprocess.Popen | None = None
    recorder_log = None
    app_pid: int | None = None
    try:
        deadline = time.monotonic() + 60
        hwnd = None
        while time.monotonic() < deadline:
            if child.poll() is not None:
                raise RuntimeError(f"Qt app exited {child.returncode}")
            if ready.exists():
                ready_data = json.loads(ready.read_text())
                candidate_pid = int(ready_data["pid"])
                if candidate_pid != child.pid and child.pid not in {
                    parent.pid for parent in psutil.Process(candidate_pid).parents()
                }:
                    raise RuntimeError(
                        "Qt ready PID is not descended from launched process"
                    )
                app_pid = candidate_pid
                hwnd = window_for_pid(app_pid, ready_data.get("window_id"))
                if hwnd is not None:
                    break
            time.sleep(0.1)
        if hwnd is None:
            (run / "window-inventory.json").write_text(
                json.dumps(
                    {
                        "ready": json.loads(ready.read_text())
                        if ready.exists()
                        else None,
                        "launcher_pid": child.pid,
                        "windows": windows_inventory(
                            app_pid or child.pid,
                            json.loads(ready.read_text()).get("window_id")
                            if ready.exists()
                            else None,
                        ),
                    },
                    indent=2,
                )
            )
            raise RuntimeError("Qt window did not become visible")
        time.sleep(0.5)
        if app_pid is None:
            raise RuntimeError("Qt ready PID missing")
        foreground(hwnd, app_pid)
        capture(hwnd, app_pid, run / "ready.png")

        def observe() -> None:
            try:
                while not stop.is_set():
                    began = time.perf_counter()
                    position, pressed = pointer()
                    pointer_end = time.perf_counter()
                    bounds = rect(hwnd, app_pid)
                    ended = time.perf_counter()
                    samples.append(
                        {
                            "sample_start": began,
                            "pointer_end": pointer_end,
                            "t": ended,
                            "pointer": position,
                            "pressed": pressed,
                            "rect": bounds,
                            "query_ms": (ended - began) * 1000,
                        }
                    )
                    stop.wait(max(0, 0.01 - (time.perf_counter() - began)))
            except Exception as exc:  # noqa: BLE001 - invalidates evidence
                errors.append(f"observer: {exc}")

        observer = threading.Thread(target=observe, daemon=True)
        observer.start()
        if args.pixel_capture:
            pixels = run / "pixels"
            pixels.mkdir()
            origin = time.monotonic()
            (pixels / "origin.json").write_text(
                json.dumps(
                    {
                        "monotonic": origin,
                        "perf_counter": time.perf_counter(),
                        "pid": app_pid,
                        "window": hwnd,
                        "scope": "owned-window server pixels; not physical display refresh",
                    }
                )
            )
            recorder_log = (pixels / "recorder.log").open("w")
            command = [
                sys.executable,
                "-m",
                "quality_harness.window_capture",
                str(hwnd),
                str(origin),
                str(pixels),
                "--interval",
                ".05",
            ]
            if sys.platform == "win32":
                command += [
                    "--owner-pid",
                    str(app_pid),
                    "--method",
                    "screen-interior",
                    "--interior-width",
                    "900",
                    "--interior-inset",
                    "60",
                ]
            recorder = subprocess.Popen(
                command,
                cwd=SOURCE,
                stdout=recorder_log,
                stderr=subprocess.STDOUT,
                env={**os.environ, "PYTHONPATH": str(SOURCE / "engineering-quality")},
            )
            capture_deadline = time.monotonic() + 10
            while not (pixels / "capture.ready").exists():
                if recorder.poll() is not None or time.monotonic() > capture_deadline:
                    raise RuntimeError("pixel recorder not ready")
                time.sleep(0.05)

        screen = (
            (user32.GetSystemMetrics(0), user32.GetSystemMetrics(1))
            if sys.platform == "win32"
            else (
                int(Quartz.CGDisplayBounds(Quartz.CGMainDisplayID()).size.width),
                int(Quartz.CGDisplayBounds(Quartz.CGMainDisplayID()).size.height),
            )
        )
        max_width = min(1450, screen[0] - 80)
        target_widths = [max_width, 1100]
        for index, target_width in enumerate(target_widths):
            foreground(hwnd, app_pid)
            box = rect(hwnd, app_pid)
            if args.corner_stress:
                start = (box[2] - 3, box[3] - 3)
                end = (start[0] - 220, start[1] - 150)
            else:
                start = (box[2] - 2, (box[1] + box[3]) / 2)
                end = (box[0] + target_width - 2, start[1])
            move(*start)
            time.sleep(0.1)
            foreground(hwnd, app_pid)
            events.append(
                {
                    "event": "drag_start",
                    "t": time.perf_counter(),
                    "rect": box,
                    "target": target_width,
                }
            )
            button(True)
            try:
                began = time.perf_counter()
                hold_elapsed = 0.0
                steps = 120 if args.corner_stress else 90
                for step in range(1, steps + 1):
                    fraction = step / steps
                    if args.corner_stress:
                        # Two rapid diagonal in/out sweeps under one press.
                        fraction = 1 - abs((step % 60) / 30 - 1)
                    move(
                        round(start[0] + (end[0] - start[0]) * fraction),
                        round(start[1] + (end[1] - start[1]) * fraction),
                        dragged=True,
                    )
                    time.sleep(
                        max(
                            0,
                            began
                            + step / (120 if args.corner_stress else 30)
                            + hold_elapsed
                            - time.perf_counter(),
                        )
                    )
                    if args.pixel_capture and step in {20, 40, 60, 80}:
                        # Stable in-flight epochs allow the independent screen
                        # grab to compare painting 200 ms after a geometry step.
                        time.sleep(0.35)
                        hold_elapsed += 0.35
            finally:
                button(False)
            events.append(
                {
                    "event": "drag_end",
                    "t": time.perf_counter(),
                    "rect": rect(hwnd, app_pid),
                }
            )
            time.sleep(0.65)
            capture(hwnd, app_pid, run / f"settled-{index}.png")
        stop.set()
        observer.join(timeout=2)
        pointer_result = assess_pointer_tracking(samples, events)
        if args.corner_stress:
            vertical = [
                {
                    **row,
                    "pointer": [row["pointer"][1], row["pointer"][0]],
                    "rect": [
                        row["rect"][0],
                        row["rect"][1],
                        row["rect"][3],
                        row["rect"][2],
                    ],
                }
                for row in samples
            ]
            vertical_result = assess_pointer_tracking(vertical, events)
            stationary = [
                {
                    "left_px": abs(end["rect"][0] - start["rect"][0]),
                    "top_px": abs(end["rect"][1] - start["rect"][1]),
                }
                for start, end in zip(
                    (event for event in events if event["event"] == "drag_start"),
                    (event for event in events if event["event"] == "drag_end"),
                    strict=False,
                )
            ]
            pointer_result = {
                "passed": pointer_result["passed"]
                and vertical_result["passed"]
                and all(
                    row["left_px"] <= 8 and row["top_px"] <= 8 for row in stationary
                ),
                "horizontal": pointer_result,
                "vertical": vertical_result,
                "stationary_edges": stationary,
                "trajectory": "two 220x150 px diagonal in/out sweeps per held drag; 120 moves/s",
            }
        (run / "pointer-assessment.json").write_text(
            json.dumps(pointer_result, indent=2)
        )
        pixel_result = None
        if recorder is not None:
            (run / "pixels" / "capture.stop").touch()
            recorder.wait(timeout=30)
            from quality_harness.resize_pixels import assess_static_resize_frames

            report = run / "pixels" / "capture.json"
            if report.exists():
                data = json.loads(report.read_text())
                pixel_result = assess_static_resize_frames(
                    data["frames"], run / "pixels", drag_events=events
                )
                if data["errors"]:
                    errors.extend(data["errors"])
            else:
                pixel_result = {"passed": False, "reason": "capture missing"}
            (run / "pixel-assessment.json").write_text(
                json.dumps(pixel_result, indent=2)
            )
        result = {
            "passed": pointer_result["passed"]
            and (pixel_result is None or pixel_result["passed"])
            and not errors,
            "pointer": pointer_result,
            "pixels": pixel_result,
            "errors": errors,
            "qt_pid": app_pid,
            "launcher_pid": child.pid,
            "window": hwnd,
        }
        (run / "result.json").write_text(json.dumps(result, indent=2))
        return 0 if result["passed"] else 1
    except Exception as exc:  # noqa: BLE001 - evidence includes failure
        errors.append(f"{type(exc).__name__}: {exc}")
        (run / "result.json").write_text(
            json.dumps({"passed": False, "errors": errors}, indent=2)
        )
        return 2
    finally:
        stop.set()
        if recorder is not None and recorder.poll() is None:
            (run / "pixels" / "capture.stop").touch()
            try:
                recorder.wait(timeout=10)
            except subprocess.TimeoutExpired:
                recorder.terminate()
        if recorder_log is not None:
            recorder_log.close()
        if app_pid is not None and app_pid != child.pid and psutil.pid_exists(app_pid):
            psutil.Process(app_pid).terminate()
        child.terminate()
        try:
            child.wait(timeout=5)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait(timeout=5)
        log.close()


if __name__ == "__main__":
    raise SystemExit(main())
