"""Independent own-window pixel recorder for native diagnostic comparisons.

This process never drives input or calls into the application's widget runtime.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path


def _windows_capture(number: int, owner_pid: int, *, screen_crop: bool = False):
    import ctypes as C
    from ctypes import wintypes as W

    from PIL import ImageGrab

    user32 = C.windll.user32
    user32.IsWindow.argtypes = [W.HWND]
    user32.IsWindowVisible.argtypes = [W.HWND]
    user32.GetWindowThreadProcessId.argtypes = [W.HWND, C.POINTER(W.DWORD)]
    user32.GetWindowRect.argtypes = [W.HWND, C.POINTER(W.RECT)]
    if not user32.IsWindow(W.HWND(number)) or not user32.IsWindowVisible(
        W.HWND(number)
    ):
        raise RuntimeError("Owned Windows window is no longer visible")
    actual_pid = W.DWORD()
    user32.GetWindowThreadProcessId(W.HWND(number), C.byref(actual_pid))
    if actual_pid.value != owner_pid:
        raise RuntimeError("Windows capture target changed owner")
    bounds = W.RECT()
    if not user32.GetWindowRect(W.HWND(number), C.byref(bounds)):
        raise RuntimeError("Owned Windows bounds unavailable")
    if screen_crop:
        user32.GetForegroundWindow.restype = W.HWND
        user32.GetTopWindow.restype = W.HWND
        user32.GetWindow.argtypes = [W.HWND, W.UINT]
        user32.GetWindow.restype = W.HWND

        def unobscured() -> bool:
            foreground = user32.GetForegroundWindow()
            foreground_pid = W.DWORD()
            user32.GetWindowThreadProcessId(foreground, C.byref(foreground_pid))
            if foreground_pid.value != owner_pid:
                return False
            upper = user32.GetTopWindow(None)
            while upper and upper != number:
                if user32.IsWindowVisible(upper):
                    other = W.RECT()
                    if user32.GetWindowRect(upper, C.byref(other)) and (
                        other.left < bounds.right
                        and other.right > bounds.left
                        and other.top < bounds.bottom
                        and other.bottom > bounds.top
                    ):
                        return False
                upper = user32.GetWindow(upper, 2)
            return bool(upper)

        if not unobscured():
            raise RuntimeError("Owned Windows window is obscured during screen crop")
        bitmap = ImageGrab.grab(
            bbox=(bounds.left, bounds.top, bounds.right, bounds.bottom)
        )
        if not unobscured():
            raise RuntimeError("Owned Windows window was obscured during screen crop")
    else:
        bitmap = ImageGrab.grab(window=number)
    if bitmap.width <= 0 or bitmap.height <= 0:
        raise RuntimeError("Owned Windows pixels unavailable")
    return bitmap.convert("RGB"), [bounds.left, bounds.top, bounds.right, bounds.bottom]


def main() -> int:
    if sys.platform == "darwin":
        import Quartz
        from PIL import Image

    parser = argparse.ArgumentParser()
    parser.add_argument("number", type=int)
    parser.add_argument("origin", type=float)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--interval", type=float, default=0.020)
    parser.add_argument("--owner-pid", type=int)
    parser.add_argument("--screen-crop", action="store_true")
    args = parser.parse_args()
    if sys.platform == "win32" and (args.owner_pid is None or args.owner_pid <= 0):
        parser.error("Windows own-window capture requires --owner-pid")
    if args.screen_crop and sys.platform != "win32":
        parser.error("--screen-crop requires Windows")
    if sys.platform not in {"darwin", "win32"}:
        parser.error("Own-window pixel capture is supported on Mac and Windows")
    if not 0.020 <= args.interval <= 1:
        parser.error("capture interval must be between .020 and 1 second")
    number, origin, directory = args.number, args.origin, args.directory
    frames, errors = [], []
    deadline = time.monotonic() + 20
    try:
        while not (directory / "capture.stop").exists() and time.monotonic() < deadline:
            begin = time.monotonic() - origin
            if sys.platform == "win32":
                bitmap, bounds = _windows_capture(
                    number, args.owner_pid, screen_crop=args.screen_crop
                )
            else:
                raw = Quartz.CGWindowListCreateImage(
                    Quartz.CGRectNull,
                    Quartz.kCGWindowListOptionIncludingWindow,
                    number,
                    Quartz.kCGWindowImageBoundsIgnoreFraming
                    | Quartz.kCGWindowImageNominalResolution,
                )
                if raw is None:
                    raise RuntimeError("Own-window capture unavailable")
                data = bytes(
                    Quartz.CGDataProviderCopyData(Quartz.CGImageGetDataProvider(raw))
                )
                bitmap = Image.frombytes(
                    "RGB",
                    (Quartz.CGImageGetWidth(raw), Quartz.CGImageGetHeight(raw)),
                    data,
                    "raw",
                    "BGRX",
                    Quartz.CGImageGetBytesPerRow(raw),
                )
                bounds = None
            frames.append(
                {
                    "begin": begin,
                    "end": time.monotonic() - origin,
                    "bitmap": bitmap,
                    "bounds": bounds,
                }
            )
            if len(frames) == 1:
                (directory / "capture.ready").touch()
            time.sleep(max(0, args.interval - (time.monotonic() - origin - begin)))
        if not (directory / "capture.stop").exists():
            errors.append("Recorder deadline exceeded")
    except Exception as exc:  # noqa: BLE001 - retain unavailable evidence
        errors.append(repr(exc))
    for index, row in enumerate(frames):
        bitmap = row.pop("bitmap")
        name = f"resize-frame-{index:04d}.png"
        row.update(
            {
                "file": name,
                "size": list(bitmap.size),
                "sha256": hashlib.sha256(bitmap.tobytes()).hexdigest(),
            }
        )
        bitmap.save(directory / name, compress_level=0)
    (directory / "capture.json").write_text(
        json.dumps(
            {
                "frames": frames,
                "errors": errors,
                "requested_interval_seconds": args.interval,
                "observer": (
                    "separate process; foreground unobscured owned window crop"
                    if args.screen_crop
                    else "separate process; exact owned window; no application GIL"
                ),
            },
            indent=2,
        )
    )
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
