"""Launch/close/reopen the unmodified private executable in a fresh E: profile."""

import ctypes
import hashlib
import json
import os
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path

from PIL import ImageGrab


def main():
    exe, run = map(Path, sys.argv[1:3])
    profile = run / "profile"
    profile.mkdir()
    env = dict(os.environ, LOCALAPPDATA=str(profile), VODFORGE_DISABLE_TELEMETRY="1")
    user32 = ctypes.windll.user32
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.PostMessageW.argtypes = [
        wintypes.HWND,
        wintypes.UINT,
        wintypes.WPARAM,
        wintypes.LPARAM,
    ]
    result = {
        "passed": False,
        "executable_sha256": hashlib.sha256(exe.read_bytes()).hexdigest(),
        "launches": [],
    }
    process = None
    try:
        for launch in range(2):
            started = time.monotonic()
            process = subprocess.Popen([str(exe)], env=env)
            window = None
            while time.monotonic() - started < 30 and process.poll() is None:
                windows = []

                @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
                def collect(hwnd, _param, expected_pid=process.pid, owned=windows):
                    pid = wintypes.DWORD()
                    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                    title = ctypes.create_unicode_buffer(256)
                    user32.GetWindowTextW(hwnd, title, len(title))
                    if (
                        pid.value == expected_pid
                        and user32.IsWindowVisible(hwnd)
                        and title.value.startswith("VODForge")
                    ):
                        owned.append(hwnd)
                    return True

                user32.EnumWindows(collect, 0)
                if windows:
                    window = windows[0]
                    break
                time.sleep(0.1)
            if not window:
                raise RuntimeError("No visible owned VODForge window")
            visible_seconds = time.monotonic() - started
            time.sleep(4)
            rect = wintypes.RECT()
            user32.GetWindowRect(window, ctypes.byref(rect))
            user32.SetForegroundWindow(window)
            time.sleep(0.3)
            ImageGrab.grab(bbox=(rect.left, rect.top, rect.right, rect.bottom)).save(
                run / f"app-{launch}.png"
            )
            user32.PostMessageW(window, 0x0010, 0, 0)
            process.wait(timeout=15)
            if process.returncode != 0:
                raise RuntimeError(f"App exit {process.returncode}")
            result["launches"].append(
                {
                    "pid": process.pid,
                    "visible_seconds": round(visible_seconds, 3),
                    "exit_code": process.returncode,
                }
            )
        files = [p.name for p in (profile / "VODForge").glob("*.json")]
        result["profile_json_files"] = files
        forbidden = [
            name
            for name in files
            if any(token in name for token in ("credential", "outbox"))
        ]
        if forbidden:
            raise RuntimeError("Private app created telemetry delivery state")
        result["passed"] = True
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as error:
        result["error"] = str(error)
    finally:
        if process and process.poll() is None:
            process.kill()
            process.wait(timeout=10)
        (run / "app.json").write_text(json.dumps(result, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
