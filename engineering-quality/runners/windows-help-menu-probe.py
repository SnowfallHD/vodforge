"""Exercise the real Windows menu with native input and visible modal receipts.

Coordinate input is bounded to this generated 900x650 native QA surface. The
driver verifies process foreground ownership before input. It never sends
support/review messages. Run against an explicit source snapshot and retain
failure evidence; this is not exact packaged-artifact release proof.
"""

import argparse
import ctypes as C
import hashlib
import json
import os
import sys
import threading
import time
import tkinter as tk
import traceback
from ctypes import wintypes as W
from pathlib import Path
from tkinter import ttk

from PIL import ImageGrab

parser = argparse.ArgumentParser(
    description="Native Windows Help menu regression; isolated source evidence only."
)
parser.add_argument("--source", type=Path, required=True)
parser.add_argument("--output", type=Path, required=True)
parser.add_argument(
    "--entry",
    choices=("feedback", "review", "welcome", "escape", "outside", "reopen"),
    required=True,
)
args = parser.parse_args()
SOURCE = args.source.resolve()
RUN = args.output.resolve()
RUN.mkdir(parents=True, exist_ok=False)
os.environ["VODFORGE_DISABLE_TELEMETRY"] = "1"
sys.path.insert(0, str(SOURCE))
from yt_downloader.engagement_ui import EngagementUI
from yt_downloader.ui_styles import apply_product_styles

u = C.windll.user32
u.GetAncestor.argtypes = [W.HWND, W.UINT]
u.GetAncestor.restype = W.HWND
u.GetForegroundWindow.restype = W.HWND
u.SetForegroundWindow.argtypes = [W.HWND]
root = tk.Tk()
root.title("VODForge Help Native Regression")
root.geometry("900x650+80+60")
apply_product_styles(root)
events = []


def trace(name):
    try:
        grab = str(root.grab_current())
    except (tk.TclError, KeyError) as exc:
        grab = repr(exc)
    events.append(
        {
            "t": time.monotonic(),
            "event": name,
            "grab": grab,
            "panel": type(owner.panel).__name__ if owner.panel else None,
        }
    )
    (RUN / "trace.json").write_text(json.dumps(events, indent=2))


owner = EngagementUI(
    root, RUN / "engagement.json", ready=lambda: True, suppress_showcase=lambda: None
)
owner.state.presented_welcome()
for name in ("welcome", "review", "feedback"):
    original = getattr(owner, name)

    def wrapped(original=original, name=name):
        trace(name + "-entered")
        original()
        trace(name + "-returned")

    setattr(owner, name, wrapped)


def menu():
    trace("menu-entered")
    owner.menu(button)
    trace("menu-returned")


button = ttk.Button(root, text="Help & feedback", command=menu)
button.pack(pady=40)
root.report_callback_exception = lambda *args: (RUN / "callback-error.txt").write_text(
    "".join(traceback.format_exception(*args))
)
root.update()
hwnd = u.GetAncestor(root.winfo_id(), 2)
u.SetForegroundWindow(hwnd)
button.focus_force()
rect = (
    root.winfo_rootx(),
    root.winfo_rooty(),
    root.winfo_rootx() + root.winfo_width(),
    root.winfo_rooty() + root.winfo_height(),
)


def key(k):
    pid = W.DWORD()
    u.GetWindowThreadProcessId(u.GetForegroundWindow(), C.byref(pid))
    if pid.value != os.getpid():
        raise RuntimeError("Input refused: another process owns foreground")
    u.keybd_event(k, 0, 0, 0)
    time.sleep(0.05)
    u.keybd_event(k, 0, 2, 0)


def input_worker():
    try:
        time.sleep(0.4)
        u.keybd_event(18, 0, 0, 0)
        u.keybd_event(18, 0, 2, 0)
        u.SetForegroundWindow(hwnd)
        time.sleep(0.2)
        pid = W.DWORD()
        u.GetWindowThreadProcessId(u.GetForegroundWindow(), C.byref(pid))
        if pid.value != os.getpid():
            raise RuntimeError("Activation failed: no input sent")
        u.SetCursorPos(rect[0] + 450, rect[1] + 57)
        u.mouse_event(2, 0, 0, 0, 0)
        time.sleep(0.05)
        u.mouse_event(4, 0, 0, 0, 0)
        time.sleep(0.6)
        ImageGrab.grab(bbox=rect).save(RUN / "popup.png")
        pid = W.DWORD()
        u.GetWindowThreadProcessId(u.GetForegroundWindow(), C.byref(pid))
        if pid.value != os.getpid():
            raise RuntimeError("Foreign foreground")
        if args.entry in {"escape", "reopen"}:
            key(27)
            if args.entry == "escape":
                return
            time.sleep(0.2)
            u.SetCursorPos(rect[0] + 450, rect[1] + 57)
            u.mouse_event(2, 0, 0, 0, 0)
            time.sleep(0.05)
            u.mouse_event(4, 0, 0, 0, 0)
            time.sleep(0.3)
        if args.entry == "outside":
            u.SetCursorPos(rect[0] + 200, rect[1] + 300)
            u.mouse_event(2, 0, 0, 0, 0)
            time.sleep(0.05)
            u.mouse_event(4, 0, 0, 0, 0)
            return
        y = {"feedback": 92, "review": 111, "welcome": 138, "reopen": 92}[args.entry]
        u.SetCursorPos(rect[0] + 460, rect[1] + y)
        u.mouse_event(2, 0, 0, 0, 0)
        time.sleep(0.06)
        u.mouse_event(4, 0, 0, 0, 0)
        time.sleep(0.6)
        ImageGrab.grab(bbox=rect).save(RUN / "selected.png")
    except Exception:  # noqa: BLE001 -- retain all native-driver failures as failed evidence
        (RUN / "input-error.txt").write_text(traceback.format_exc())


threading.Thread(target=input_worker, daemon=True).start()


def finish():
    trace("final-observation")
    global passed
    visible = bool(owner.panel and owner.panel.frame.winfo_ismapped())
    expected = {
        "welcome": "WhatsNewPanel",
        "feedback": "SupportPanel",
        "review": "SupportPanel",
        "reopen": "SupportPanel",
    }.get(args.entry)
    actual = type(owner.panel).__name__ if owner.panel else None
    passed = (
        actual == expected
        and visible == (expected is not None)
        and not (RUN / "input-error.txt").exists()
        and not (RUN / "callback-error.txt").exists()
    )
    if expected:
        passed = (
            passed
            and root.grab_current() is owner.panel.frame
            and len(
                [
                    x
                    for x in events
                    if x["event"].endswith("-entered") and x["event"] != "menu-entered"
                ]
            )
            == 1
        )
    ImageGrab.grab(bbox=rect).save(RUN / "final.png")
    (RUN / "receipt.json").write_text(
        json.dumps(
            {
                "passed": passed,
                "evidence_tier": "source_native_windows",
                "entry": args.entry,
                "pid": os.getpid(),
                "tk": root.tk.call("info", "patchlevel"),
                "module_sha256": hashlib.sha256(
                    (SOURCE / "yt_downloader/engagement_ui.py").read_bytes()
                ).hexdigest(),
                "panel": actual,
                "panel_visible": visible,
                "events": events,
            },
            indent=2,
        )
    )
    owner.close()
    root.destroy()


root.after(4000, finish)
passed = False
root.mainloop()
sys.exit(0 if passed else 1)
