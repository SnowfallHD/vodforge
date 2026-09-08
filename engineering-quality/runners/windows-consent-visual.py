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
    if pid.value != process.pid:
        raise RuntimeError(
            "Packaged VODForge did not own foreground; refusing unrelated capture"
        )
    rect = wintypes.RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        raise RuntimeError("Could not resolve owned window bounds")
    ImageGrab.grab(bbox=(rect.left, rect.top, rect.right, rect.bottom)).save(
        run / "consent.png"
    )
    process.wait(timeout=25)
    if process.returncode != 0:
        raise RuntimeError("Packaged app did not close cleanly")
    result["passed"] = True
except Exception as error:
    result["error"] = str(error)
finally:
    if process.poll() is None:
        process.terminate()
        process.wait(timeout=10)
    (run / "visual.json").write_text(json.dumps(result))
