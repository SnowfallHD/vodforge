"""Capture only the owned, foreground packaged consent window on the QA desktop."""

import ctypes
import json
import os
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path

from PIL import ImageGrab

exe, run = map(Path, sys.argv[1:3])
env = dict(os.environ)
env.pop("VODFORGE_DISABLE_TELEMETRY", None)
env.update(
    VODFORGE_QA_ACCESS_KEY=Path("E:/VODForgeQA/qa-access-key").read_text().strip(),
    VODFORGE_QA_PROFILE=str(run / "visual-profile"),
    VODFORGE_QA_COUNTRY="DE",
)
user32 = ctypes.windll.user32
user32.SetProcessDPIAware()
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetWindowThreadProcessId.argtypes = [
    wintypes.HWND,
    ctypes.POINTER(wintypes.DWORD),
]
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.SetWindowPos.argtypes = [
    wintypes.HWND,
    wintypes.HWND,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    wintypes.UINT,
]
raised = None
process = subprocess.Popen([str(exe), "--analytics-qa", "none", "0", "15"], env=env)
result = {"passed": False, "pid": process.pid}
try:
    time.sleep(4)
    hwnd = user32.GetForegroundWindow()
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    result["foreground_pid"] = pid.value
    title = ctypes.create_unicode_buffer(256)
    user32.GetWindowTextW(hwnd, title, len(title))
    result["foreground_title"] = title.value
    result["automatic_foreground"] = pid.value == process.pid
    if pid.value != process.pid:
        # Visual inspection is distinct from automatic foreground behavior.
        # Raise only this owned QA window; never change the production policy.
        owned = []
        callback_type = ctypes.WINFUNCTYPE(
            wintypes.BOOL, wintypes.HWND, wintypes.LPARAM
        )

        @callback_type
        def collect(candidate, _data):
            candidate_pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(candidate, ctypes.byref(candidate_pid))
            if candidate_pid.value == process.pid and user32.IsWindowVisible(candidate):
                owned.append(candidate)
            return True

        user32.IsWindowVisible.argtypes = [wintypes.HWND]
        user32.EnumWindows(collect, 0)
        if len(owned) != 1:
            raise RuntimeError("Could not unambiguously identify the owned QA window")
        hwnd = raised = owned[0]
        if not user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x13):
            raise RuntimeError("Could not raise owned QA window for visual inspection")
        result["explicit_qa_raise"] = True
        time.sleep(0.5)
    rect = wintypes.RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        raise RuntimeError("Could not resolve owned window bounds")
    ImageGrab.grab(bbox=(rect.left, rect.top, rect.right, rect.bottom)).save(
        run / "consent.png"
    )
    if raised:
        user32.SetWindowPos(raised, -2, 0, 0, 0, 0, 0x13)
        raised = None
    process.wait(timeout=25)
    if process.returncode != 0:
        raise RuntimeError("Packaged app did not close cleanly")
    result["passed"] = True
except Exception as error:
    result["error"] = str(error)
finally:
    if raised:
        user32.SetWindowPos(raised, -2, 0, 0, 0, 0, 0x13)
    if process.poll() is None:
        process.terminate()
        process.wait(timeout=10)
    (run / "visual.json").write_text(json.dumps(result))
