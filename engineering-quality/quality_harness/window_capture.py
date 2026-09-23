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


def _windows_capture(
    number: int, owner_pid: int, *, method: str, box: tuple[int, int, int, int] | None
):
    import ctypes as C
    from ctypes import wintypes as W

    from PIL import ImageGrab

    user32 = C.windll.user32
    user32.IsWindow.argtypes = [W.HWND]
    user32.IsWindowVisible.argtypes = [W.HWND]
    user32.GetWindowThreadProcessId.argtypes = [W.HWND, C.POINTER(W.DWORD)]
    user32.GetWindowRect.argtypes = [W.HWND, C.POINTER(W.RECT)]
    user32.GetWindow.argtypes = [W.HWND, W.UINT]
    user32.GetWindow.restype = W.HWND
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
    if method == "screen-interior":
        if box is None:
            raise RuntimeError("Interior capture box missing")
        left, top, right, bottom = box
        if not (
            bounds.left + 20 <= left < right <= bounds.right - 20
            and bounds.top + 20 <= top < bottom <= bounds.bottom - 20
        ):
            raise RuntimeError("Interior capture left the owned window")
        def reject_foreign_overlap() -> None:
            # A different top-level window could cover the crop during the
            # grab, so inspect z-order on both sides of that operation.
            above = user32.GetWindow(W.HWND(number), 3)  # GW_HWNDPREV
            while above:
                if user32.IsWindowVisible(above):
                    other = W.RECT()
                    if user32.GetWindowRect(above, C.byref(other)):
                        foreign_pid = W.DWORD()
                        user32.GetWindowThreadProcessId(above, C.byref(foreign_pid))
                        if (
                            foreign_pid.value != owner_pid
                            and other.left < right
                            and other.right > left
                            and other.top < bottom
                            and other.bottom > top
                        ):
                            raise RuntimeError("Foreign window covers interior QA capture")
                above = user32.GetWindow(above, 3)

        reject_foreign_overlap()
        bitmap = ImageGrab.grab(bbox=box)
        owner_after = W.DWORD()
        if (
            not user32.IsWindow(W.HWND(number))
            or not user32.IsWindowVisible(W.HWND(number))
            or not user32.GetWindowThreadProcessId(
                W.HWND(number), C.byref(owner_after)
            )
            or owner_after.value != owner_pid
        ):
            raise RuntimeError("Windows capture target changed owner during grab")
        after = W.RECT()
        if not user32.GetWindowRect(W.HWND(number), C.byref(after)) or not (
            after.left + 20 <= left < right <= after.right - 20
            and after.top + 20 <= top < bottom <= after.bottom - 20
        ):
            raise RuntimeError("Interior capture crossed a moving window edge")
        reject_foreign_overlap()
        if (
            bounds.left, bounds.top, bounds.right, bounds.bottom
        ) != (after.left, after.top, after.right, after.bottom):
            # The screenshot spans two geometry epochs. Treating it as a
            # same-size sample invents delayed paint at responsive breakpoints.
            return None, None
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
    parser.add_argument(
        "--method", choices=("printwindow", "screen-interior"), default="printwindow"
    )
    args = parser.parse_args()
    if sys.platform == "win32" and (args.owner_pid is None or args.owner_pid <= 0):
        parser.error("Windows own-window capture requires --owner-pid")
    if sys.platform not in {"darwin", "win32"}:
        parser.error("Own-window pixel capture is supported on Mac and Windows")
    if not 0.020 <= args.interval <= 1:
        parser.error("capture interval must be between .020 and 1 second")
    number, origin, directory = args.number, args.origin, args.directory
    box = None
    if sys.platform == "win32" and args.method == "screen-interior":
        import ctypes as C
        from ctypes import wintypes as W

        initial = W.RECT()
        if not C.windll.user32.GetWindowRect(W.HWND(number), C.byref(initial)):
            parser.error("Windows capture target has no initial rectangle")
        box = (
            initial.left + 20,
            initial.top + 20,
            initial.left + min(1080, initial.right - initial.left - 20),
            initial.top + min(720, initial.bottom - initial.top - 20),
        )
    frames, errors = [], []
    deadline = time.monotonic() + 20
    try:
        while not (directory / "capture.stop").exists() and time.monotonic() < deadline:
            begin = time.monotonic() - origin
            if sys.platform == "win32":
                bitmap, bounds = _windows_capture(
                    number, args.owner_pid, method=args.method, box=box
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
            if bitmap is None:
                time.sleep(max(0, args.interval - (time.monotonic() - origin - begin)))
                continue
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
                    "separate process; fixed verified on-screen HWND interior; no WM_PRINT"
                    if args.method == "screen-interior"
                    else "separate process; exact owned window; synchronous WM_PRINT"
                ),
            },
            indent=2,
        )
    )
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
