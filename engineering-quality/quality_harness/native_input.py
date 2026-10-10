"""Bounded native macOS input for an attested packaged QA session.

This controls OS input only; the existing E2E recorder still owns proof.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import math

# Only the fixed native screenshot executable is invoked, without a shell.
import subprocess  # nosec B404
import time
from pathlib import Path

from .e2e_provenance import verify_live_launch, verify_native_window_identity


def image_point(bounds, x, y, image_width, image_height):
    """Convert explicitly sized image pixels to global desktop points once."""
    values = (x, y, image_width, image_height)
    if not all(math.isfinite(value) for value in values):
        raise ValueError("Coordinates must be finite")
    if image_width <= 0 or image_height <= 0:
        raise ValueError("Image dimensions must be positive")
    if not 0 <= x < image_width or not 0 <= y < image_height:
        raise ValueError("Point is outside the observed image")
    return (
        bounds["X"] + x * bounds["Width"] / image_width,
        bounds["Y"] + y * bounds["Height"] / image_height,
    )


def wait_for(predicate, description, *, timeout=5.0):
    deadline = time.monotonic() + timeout
    while True:
        result = predicate()
        if result:
            return result
        if time.monotonic() >= deadline:
            raise RuntimeError(f"Timed out waiting for {description}; no retry sent")
        time.sleep(0.05)


def focused_window_title(pid):
    """Read AX focus without changing it or resolving an app by bundle name."""
    cf = ctypes.CDLL(
        "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation"
    )
    ax = ctypes.CDLL(
        "/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices"
    )
    pointer = ctypes.c_void_p
    cf.CFRelease.argtypes = [pointer]
    cf.CFStringCreateWithCString.argtypes = [pointer, ctypes.c_char_p, ctypes.c_uint32]
    cf.CFStringCreateWithCString.restype = pointer
    cf.CFStringGetCString.argtypes = [
        pointer,
        ctypes.c_void_p,
        ctypes.c_long,
        ctypes.c_uint32,
    ]
    cf.CFStringGetCString.restype = ctypes.c_bool
    ax.AXUIElementCreateApplication.argtypes = [ctypes.c_int]
    ax.AXUIElementCreateApplication.restype = pointer
    ax.AXUIElementCopyAttributeValue.argtypes = [
        pointer,
        pointer,
        ctypes.POINTER(pointer),
    ]
    ax.AXUIElementCopyAttributeValue.restype = ctypes.c_int
    owned = []
    try:
        application = ax.AXUIElementCreateApplication(pid)
        owned.append(application)
        current = application
        for attribute in (b"AXFocusedWindow", b"AXTitle"):
            name = cf.CFStringCreateWithCString(None, attribute, 0x08000100)
            owned.append(name)
            value = pointer()
            error = ax.AXUIElementCopyAttributeValue(current, name, ctypes.byref(value))
            if error or not value.value:
                return _modal_sheet_title(pid, cf, ax, application)
            owned.append(value)
            current = value
        buffer = ctypes.create_string_buffer(4096)
        if cf.CFStringGetCString(current, buffer, len(buffer), 0x08000100):
            return buffer.value.decode("utf-8")
        return None
    finally:
        for value in reversed(owned):
            if value:
                cf.CFRelease(value)


def _modal_sheet_title(pid, cf, ax, application):
    """Resolve an AppKit modal sheet when AXFocusedWindow is unavailable.

    Require a single AXSheet attached to AXMainWindow and an exact native
    rectangle match in this PID. A different window cannot satisfy this fallback.
    """
    import Quartz

    pointer = ctypes.c_void_p
    cf.CFArrayGetCount.argtypes = [pointer]
    cf.CFArrayGetCount.restype = ctypes.c_long
    cf.CFArrayGetValueAtIndex.argtypes = [pointer, ctypes.c_long]
    cf.CFArrayGetValueAtIndex.restype = pointer
    ax.AXValueGetValue.argtypes = [pointer, ctypes.c_int, pointer]
    ax.AXValueGetValue.restype = ctypes.c_bool
    owned = []

    def attribute(element, name):
        key = cf.CFStringCreateWithCString(None, name, 0x08000100)
        owned.append(key)
        value = pointer()
        error = ax.AXUIElementCopyAttributeValue(element, key, ctypes.byref(value))
        if error or not value.value:
            return None
        owned.append(value)
        return value

    try:
        main = attribute(application, b"AXMainWindow")
        children = attribute(main, b"AXChildren") if main else None
        if not children:
            return None
        sheets = []
        for index in range(cf.CFArrayGetCount(children)):
            child = cf.CFArrayGetValueAtIndex(children, index)
            role = attribute(child, b"AXRole")
            buffer = ctypes.create_string_buffer(64)
            if (
                role
                and cf.CFStringGetCString(role, buffer, len(buffer), 0x08000100)
                and buffer.value == b"AXSheet"
            ):
                sheets.append(child)
        if len(sheets) != 1:
            return None
        coordinates = []
        for name, kind in ((b"AXPosition", 1), (b"AXSize", 2)):
            value = attribute(sheets[0], name)
            pair = (ctypes.c_double * 2)()
            if not value or not ax.AXValueGetValue(value, kind, ctypes.byref(pair)):
                return None
            coordinates.extend(pair)
        windows = Quartz.CGWindowListCopyWindowInfo(
            Quartz.kCGWindowListOptionOnScreenOnly, 0
        )
        matches = [
            w.get("kCGWindowName")
            for w in windows
            if w.get("kCGWindowOwnerPID") == pid
            and w.get("kCGWindowLayer") == 0
            and [
                w.get("kCGWindowBounds", {}).get(k)
                for k in ("X", "Y", "Width", "Height")
            ]
            == coordinates
        ]
        return matches[0] if len(matches) == 1 else None
    finally:
        for value in reversed(owned):
            if value:
                cf.CFRelease(value)


def hit_test_pid(point):
    """Ask the desktop who would receive this click, including OS overlays."""
    ax = ctypes.CDLL(
        "/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices"
    )
    cf = ctypes.CDLL(
        "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation"
    )
    pointer = ctypes.c_void_p
    cf.CFRelease.argtypes = [pointer]
    ax.AXUIElementCreateSystemWide.restype = pointer
    ax.AXUIElementCopyElementAtPosition.argtypes = [
        pointer,
        ctypes.c_float,
        ctypes.c_float,
        ctypes.POINTER(pointer),
    ]
    ax.AXUIElementGetPid.argtypes = [pointer, ctypes.POINTER(ctypes.c_int)]
    system = ax.AXUIElementCreateSystemWide()
    element = pointer()
    try:
        if ax.AXUIElementCopyElementAtPosition(system, *point, ctypes.byref(element)):
            return None
        pid = ctypes.c_int()
        if ax.AXUIElementGetPid(element, ctypes.byref(pid)):
            return None
        return pid.value
    finally:
        if element:
            cf.CFRelease(element)
        cf.CFRelease(system)


def post_click(quartz, point, guard, on_dispatch=lambda: None, *, right=False):
    def post(event_type):
        event = quartz.CGEventCreateMouseEvent(
            None,
            event_type,
            point,
            quartz.kCGMouseButtonRight if right else quartz.kCGMouseButtonLeft,
        )
        # A preceding Command shortcut otherwise leaks into newly created events.
        quartz.CGEventSetFlags(event, 0)
        quartz.CGEventSetIntegerValueField(event, quartz.kCGMouseEventClickState, 1)
        on_dispatch()
        quartz.CGEventPost(quartz.kCGHIDEventTap, event)
        time.sleep(0.1)

    guard()
    post(quartz.kCGEventMouseMoved)
    guard()
    try:
        post(quartz.kCGEventRightMouseDown if right else quartz.kCGEventLeftMouseDown)
    finally:
        # A mouse-down binding can open a dialog. Always release our button.
        post(quartz.kCGEventRightMouseUp if right else quartz.kCGEventLeftMouseUp)


def post_key(quartz, key, flags, guard, on_dispatch=lambda: None):
    guard()
    try:
        for down in (True, False):
            if down:
                guard()
            event = quartz.CGEventCreateKeyboardEvent(None, key, down)
            quartz.CGEventSetFlags(event, flags if down else 0)
            on_dispatch()
            quartz.CGEventPost(quartz.kCGHIDEventTap, event)
            time.sleep(0.1)
    finally:
        # Explicitly release synthetic modifier state, including exceptional paths.
        event = quartz.CGEventCreateKeyboardEvent(None, key, False)
        quartz.CGEventSetFlags(event, 0)
        quartz.CGEventPost(quartz.kCGHIDEventTap, event)


def post_text(quartz, text, guard, on_dispatch=lambda: None):
    """Native Unicode input without replacing the user's clipboard."""
    if len(text) > 10000:
        raise ValueError("Text exceeds bounded native input size")
    for character in text:
        guard()
        for down in (True, False):
            event = quartz.CGEventCreateKeyboardEvent(None, 0, down)
            quartz.CGEventSetFlags(event, 0)
            quartz.CGEventKeyboardSetUnicodeString(
                event, len(character.encode("utf-16-le")) // 2, character
            )
            on_dispatch()
            quartz.CGEventPost(quartz.kCGHIDEventTap, event)
        time.sleep(0.005)


def post_pointer_trace(
    quartz,
    points,
    guard,
    on_frame,
    on_dispatch=lambda: None,
    *,
    duration=1.0,
    drag=False,
    scroll_delta=None,
):
    """Keep a bounded input sequence and release a held button on every exit."""
    if (
        not 2 <= len(points) <= 40
        or not math.isfinite(duration)
        or not 0.05 <= duration <= 8
    ):
        raise ValueError("Native trace requires 2–40 samples and 0.05–8 seconds")
    if scroll_delta is not None and (
        not isinstance(scroll_delta, int) or not 1 <= abs(scroll_delta) <= 100
    ):
        raise ValueError("Native scroll delta must be a bounded nonzero integer")

    def mouse(kind, point):
        event = quartz.CGEventCreateMouseEvent(
            None, kind, point, quartz.kCGMouseButtonLeft
        )
        quartz.CGEventSetFlags(event, 0)
        on_dispatch()
        quartz.CGEventPost(quartz.kCGHIDEventTap, event)

    guard()
    held = False
    last_point = points[0]
    try:
        mouse(quartz.kCGEventMouseMoved, last_point)
        if drag:
            guard()
            held = True
            mouse(quartz.kCGEventLeftMouseDown, last_point)
        for index, point in enumerate(points):
            guard()
            last_point = point
            mouse(
                quartz.kCGEventLeftMouseDragged if drag else quartz.kCGEventMouseMoved,
                point,
            )
            if scroll_delta is not None:
                event = quartz.CGEventCreateScrollWheelEvent(
                    None, quartz.kCGScrollEventUnitPixel, 1, scroll_delta
                )
                quartz.CGEventSetFlags(event, 0)
                quartz.CGEventSetIntegerValueField(
                    event, quartz.kCGScrollWheelEventIsContinuous, 1
                )
                on_dispatch()
                quartz.CGEventPost(quartz.kCGHIDEventTap, event)
            time.sleep(duration / len(points))
            guard()
            on_frame(index, held)
    finally:
        if held:
            mouse(quartz.kCGEventLeftMouseUp, last_point)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session", type=Path, required=True)
    parser.add_argument("--window-title", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expect-window")
    parser.add_argument("--expect-closed", action="store_true")
    actions = parser.add_subparsers(dest="action", required=True)
    actions.add_parser("observe")
    click = actions.add_parser("click")
    click.add_argument("--right", action="store_true")
    for name in ("x", "y", "image-width", "image-height"):
        click.add_argument(f"--{name}", type=float, required=True)
    for action in ("hover", "drag", "scroll"):
        trace = actions.add_parser(action)
        for name in ("x", "y", "image-width", "image-height"):
            trace.add_argument(f"--{name}", type=float, required=True)
        trace.add_argument("--steps", type=int, default=12)
        trace.add_argument("--duration", type=float, default=1.2)
        if action == "drag":
            trace.add_argument("--to-x", type=float, required=True)
            trace.add_argument("--to-y", type=float, required=True)
        if action == "scroll":
            trace.add_argument("--delta", type=int, required=True)
    key = actions.add_parser("key")
    key.add_argument("--code", type=int, required=True)
    key.add_argument("--command", action="store_true")
    key.add_argument("--shift", action="store_true")
    text = actions.add_parser("text")
    text.add_argument("--value", required=True)
    args = parser.parse_args(argv)
    if args.output.exists() or args.output.with_suffix(".png").exists():
        raise RuntimeError("Refusing to overwrite an input receipt")
    import AppKit
    import Quartz

    session = json.loads(args.session.read_text())
    if session.get("driver_ready") is not True:
        raise RuntimeError("Session is not ready")
    launch = session["current_launch"]
    identity = verify_live_launch(launch)
    if identity.get("verified") is not True:
        raise RuntimeError(f"Launch identity rejected: {identity.get('errors')}")
    pid = launch["pid"]

    def windows():
        return [
            dict(w)
            for w in Quartz.CGWindowListCopyWindowInfo(
                Quartz.kCGWindowListOptionOnScreenOnly, 0
            )
            if w.get("kCGWindowOwnerPID") == pid
            and w.get("kCGWindowLayer") in (0, 8)
            and w.get("kCGWindowName")
        ]

    def named(title):
        return [w for w in windows() if w["kCGWindowName"] == title]

    matches = named(args.window_title)
    if len(matches) != 1:
        raise RuntimeError("Target window must be uniquely visible; observe first")
    target = matches[0]
    window_id = target["kCGWindowNumber"]
    application = AppKit.NSRunningApplication.runningApplicationWithProcessIdentifier_(
        pid
    )
    if application is None:
        raise RuntimeError("Attested process exited")
    application.activateWithOptions_(AppKit.NSApplicationActivateIgnoringOtherApps)
    wait_for(
        lambda: (
            AppKit.NSWorkspace.sharedWorkspace()
            .frontmostApplication()
            .processIdentifier()
            == pid
        ),
        "attested application foreground",
    )

    def guard():
        if (
            AppKit.NSWorkspace.sharedWorkspace()
            .frontmostApplication()
            .processIdentifier()
            != pid
        ):
            raise RuntimeError("Input refused: foreground process changed")
        verified = verify_native_window_identity(
            window_id=window_id,
            expected_pid=pid,
            expected_title=args.window_title,
            allow_modal=True,
        )
        if verified.get("verified") is not True:
            raise RuntimeError("Input refused: target window changed")
        if focused_window_title(pid) != args.window_title:
            raise RuntimeError("Input refused: another window has keyboard focus")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    receipt = {
        "pid": pid,
        "window_id": window_id,
        "title": args.window_title,
        "action": args.action,
        "input_sent": False,
        "status": "failed",
    }

    def dispatched():
        receipt["input_sent"] = True

    try:
        if args.action != "observe":
            guard()
        if args.action == "click":
            point = image_point(
                dict(target["kCGWindowBounds"]),
                args.x,
                args.y,
                args.image_width,
                args.image_height,
            )
            receipt["desktop_point"] = point

            def click_guard():
                guard()
                receiver = hit_test_pid(point)
                if receiver != pid:
                    raise RuntimeError(
                        f"Click blocked by desktop surface owned by PID {receiver}; "
                        "inspect desktop capture, do not resend"
                    )

            post_click(Quartz, point, click_guard, dispatched, right=args.right)
        elif args.action in {"hover", "drag", "scroll"}:
            bounds = dict(target["kCGWindowBounds"])
            start = image_point(
                bounds, args.x, args.y, args.image_width, args.image_height
            )
            end = (
                image_point(
                    bounds, args.to_x, args.to_y, args.image_width, args.image_height
                )
                if args.action == "drag"
                else start
            )
            if not 2 <= args.steps <= 40:
                raise ValueError("Native trace sample count is out of bounds")
            if hit_test_pid(start) != pid:
                raise RuntimeError(
                    "Native trace start is covered by another desktop surface"
                )
            points = [
                (
                    start[0] + (end[0] - start[0]) * i / (args.steps - 1),
                    start[1] + (end[1] - start[1]) * i / (args.steps - 1),
                )
                for i in range(args.steps)
            ]
            frame_root = args.output.with_name(args.output.stem + "-frames")
            frame_root.mkdir(exist_ok=False)
            receipt["in_flight_frames"] = []

            def frame(index, held):
                match = named(args.window_title)
                if len(match) != 1:
                    raise RuntimeError("Trace window became ambiguous")
                current = dict(match[0]["kCGWindowBounds"])
                rectangle = ",".join(
                    str(round(current[k])) for k in ("X", "Y", "Width", "Height")
                )
                path = frame_root / f"{index:03d}.png"
                subprocess.run(
                    ["/usr/sbin/screencapture", "-x", f"-R{rectangle}", str(path)],
                    check=True,
                    timeout=10,
                )  # nosec B603
                from .util import sha256_file, utc_now

                receipt["in_flight_frames"].append(
                    {
                        "index": index,
                        "at": utc_now(),
                        "monotonic_ns": time.monotonic_ns(),
                        "button_held": held,
                        "bounds": current,
                        "image_path": str(path),
                        "image_sha256": sha256_file(path),
                    }
                )

            post_pointer_trace(
                Quartz,
                points,
                guard,
                frame,
                dispatched,
                duration=args.duration,
                drag=args.action == "drag",
                scroll_delta=args.delta if args.action == "scroll" else None,
            )
        elif args.action == "key":
            if not 0 <= args.code <= 127:
                raise ValueError("Invalid native key code")
            post_key(
                Quartz,
                args.code,
                (Quartz.kCGEventFlagMaskCommand if args.command else 0)
                | (Quartz.kCGEventFlagMaskShift if args.shift else 0),
                guard,
                dispatched,
            )
        elif args.action == "text":
            post_text(Quartz, args.value, guard, dispatched)
        if args.expect_window:
            wait_for(
                lambda: (
                    len(named(args.expect_window)) == 1
                    and focused_window_title(pid) == args.expect_window
                ),
                f"focused window {args.expect_window}",
            )
        if args.expect_closed:
            wait_for(lambda: not named(args.window_title), "target window closure")
        receipt["windows_after"] = [
            {
                "title": w["kCGWindowName"],
                "id": w["kCGWindowNumber"],
                "bounds": dict(w["kCGWindowBounds"]),
            }
            for w in windows()
        ]
        receipt["focused_title_after"] = focused_window_title(pid)
        capture = named(args.expect_window or args.window_title)
        if len(capture) == 1:
            image_path = args.output.with_suffix(".png")
            capture_bounds = dict(capture[0]["kCGWindowBounds"])
            rectangle = ",".join(
                str(round(capture_bounds[key])) for key in ("X", "Y", "Width", "Height")
            )
            subprocess.run(  # nosec B603
                [
                    "/usr/sbin/screencapture",
                    "-x",
                    f"-R{rectangle}",
                    str(image_path),
                ],
                check=True,
                timeout=10,
            )
            receipt["image_desktop_bounds"] = capture_bounds
            from PIL import Image

            with Image.open(image_path) as image:
                receipt["image_size"] = list(image.size)
            receipt["image_path"] = str(image_path)
        receipt["status"] = "observed" if args.action == "observe" else "dispatched"
        # Dispatch and window transition do not imply feature/E2E success.
    except Exception as exc:
        receipt["error"] = str(exc)
        raise
    finally:
        # Window-only captures omit native alerts and other applications' overlays.
        # Keep this local: desktop evidence may contain unrelated private content.
        desktop = args.output.with_name(args.output.stem + "-desktop.png")
        try:
            subprocess.run(  # nosec B603
                ["/usr/sbin/screencapture", "-x", str(desktop)], check=True, timeout=10
            )
            receipt["desktop_image_path"] = str(desktop)
        except (OSError, subprocess.SubprocessError) as exc:
            receipt["desktop_capture_error"] = str(exc)
        args.output.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt))


if __name__ == "__main__":
    main()
