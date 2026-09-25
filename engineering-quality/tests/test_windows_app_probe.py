"""The packaged Windows app probe must accept pointer-sized native handles."""

from __future__ import annotations

import ctypes
import importlib.util
import sys
from ctypes import wintypes
from pathlib import Path

import pytest


@pytest.mark.skipif(sys.platform != "win32", reason="Win32 window API")
def test_packaged_app_probe_accepts_64_bit_window_handle():
    script = Path(__file__).resolve().parents[1] / "runners" / "windows-app-probe.py"
    spec = importlib.util.spec_from_file_location("windows_app_probe", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    module.configure_window_api(user32)
    large_handle = 0x1_0000_0000
    pid = wintypes.DWORD()
    title = ctypes.create_unicode_buffer(32)

    assert user32.GetWindowThreadProcessId(large_handle, ctypes.byref(pid)) == 0
    assert user32.GetWindowTextW(large_handle, title, len(title)) == 0
    assert not user32.IsWindowVisible(large_handle)
