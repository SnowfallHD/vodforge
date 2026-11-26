"""Capture the README screens of the Windows app with the sample library.

Run in the logged-in desktop session (for example from a scheduled task with
/IT), after scripts/seed_public_design_profile.py has made the sample profile:

    python windows_capture.py [width height]

It drives the app by clicking (UI Automation invoke doesn't switch views),
saves one PNG per screen to OUT, and quits the app. Telemetry is off. APP,
HOME and OUT are the QA test PC's folders; change them for another machine.
"""

import ctypes
import ctypes.wintypes as wt
import os
import subprocess
import sys
import time
from pathlib import Path

from PIL import ImageGrab
from pywinauto import Application, Desktop, mouse

APP = Path(r"E:\VODForgeQA\artifacts\cand-030\portable\VODForge\VODForge.exe")
HOME = Path(r"E:\VODForgeQA\readme-home")
OUT = Path(r"E:\VODForgeQA\readme-shots")
OUT.mkdir(exist_ok=True)
LOG = OUT / "capture.log"


def log(*a):
    with LOG.open("a", encoding="utf-8") as f:
        f.write(" ".join(map(str, a)) + "\n")


env = dict(os.environ, LOCALAPPDATA=str(HOME), VODFORGE_DISABLE_TELEMETRY="1")
proc = subprocess.Popen([str(APP)], env=env)
app = Application(backend="uia")
for _ in range(60):
    try:
        app.connect(process=proc.pid, timeout=1)
        break
    except Exception:  # noqa: BLE001 - window not there yet
        time.sleep(1)
time.sleep(6)


def win():
    ws = Desktop(backend="uia").windows(process=proc.pid)
    return max(ws, key=lambda w: w.rectangle().width()) if ws else None


w = win()
hwnd = w.handle
user32 = ctypes.windll.user32
user32.ShowWindow(hwnd, 9)
user32.MoveWindow(
    hwnd,
    60,
    40,
    int(sys.argv[1]) if len(sys.argv) > 1 else 1280,
    int(sys.argv[2]) if len(sys.argv) > 2 else 820,
    True,
)
user32.SetForegroundWindow(hwnd)
time.sleep(1.5)


def buttons():
    return [b for b in win().descendants(control_type="Button")]


def visible(b):
    r = b.rectangle()
    wr = win().rectangle()
    return r.top >= wr.top + 30 and r.bottom <= wr.bottom - 4 and r.width() > 0


def press(name, startswith=False, wait=1.8):
    for attempt in range(12):
        for b in buttons():
            t = b.window_text()
            if (t.startswith(name) if startswith else t == name) and b.is_enabled():
                if visible(b):
                    b.click_input()
                    time.sleep(wait)
                    log("clicked", t)
                    return True
                # Scroll the page under the window's middle toward the control.
                wr = win().rectangle()
                r = b.rectangle()
                mouse.scroll(
                    coords=((wr.left + wr.right) // 2, (wr.top + wr.bottom) // 2),
                    wheel_dist=-3 if r.top > wr.bottom else 3,
                )
                time.sleep(0.6)
                break
        else:
            break
    log("MISSING", name, [b.window_text() for b in buttons()][:80])
    return False


def hover_video():
    wr = win().rectangle()
    for dx in (0, 8, 16):
        mouse.move(coords=(wr.left + 400 + dx, wr.top + 420))
        time.sleep(0.15)


def shot(name, focus=True):
    if focus:
        user32.SetForegroundWindow(hwnd)
        time.sleep(0.8)
    rect = wt.RECT()
    ctypes.windll.dwmapi.DwmGetWindowAttribute(
        hwnd, 9, ctypes.byref(rect), ctypes.sizeof(rect)
    )
    img = ImageGrab.grab(
        bbox=(rect.left, rect.top, rect.right, rect.bottom), all_screens=True
    )
    img.save(OUT / f"{name}.png")
    log("shot", name, img.size)


for n in ("Not now", "Later", "No thanks"):
    press(n, wait=0.8)
press("Forge")
shot("forge")
press("Library")
shot("library")
press("Storage for", startswith=True)
shot("my-files")
press("Issues & Recovery")
press("Coastal Trail at Low Tide", startswith=True)
shot("recovery")
press("← Library")
press("Videos", startswith=True)
# The card is below the visible grid; searching brings it to the top.
box = win().descendants(control_type="Edit")[0]
box.click_input()
time.sleep(0.4)
box.type_keys("Canopy")
time.sleep(2)
press("Details for Under the Canopy", wait=2.5)
shot("library-detail")
press("Watch", wait=2.5)
shot("watch")
press("Play", wait=4)
hover_video()
time.sleep(0.4)
shot("player", focus=False)
press("Library")
press("Library")
log("dpi", user32.GetDpiForWindow(hwnd))
w.close()
time.sleep(3)
try:
    proc.wait(15)
except subprocess.TimeoutExpired:
    proc.kill()
log("done")
