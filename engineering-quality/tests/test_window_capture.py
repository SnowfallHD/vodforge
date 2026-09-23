"""The Windows resize recorder must sample only the attested window."""

from __future__ import annotations

import ctypes
from types import SimpleNamespace

import pytest
from PIL import Image, ImageGrab
from quality_harness.window_capture import _windows_capture


@pytest.mark.parametrize("actual_pid", [422, 423])
def test_windows_capture_requires_same_live_window_owner(monkeypatch, actual_pid):
    calls = []

    class User32:
        def IsWindow(self, hwnd):
            calls.append(("window", hwnd.value))
            return 1

        def IsWindowVisible(self, hwnd):
            calls.append(("visible", hwnd.value))
            return 1

        def GetWindowThreadProcessId(self, hwnd, pointer):
            calls.append(("owner", hwnd.value))
            pointer._obj.value = actual_pid
            return 1

        def GetWindowRect(self, hwnd, pointer):
            calls.append(("bounds", hwnd.value))
            pointer._obj.left, pointer._obj.top = 10, 20
            pointer._obj.right, pointer._obj.bottom = 110, 70
            return 1

    class NativeFunction:
        def __init__(self, callback):
            self.callback = callback
            self.argtypes = None

        def __call__(self, *args):
            return self.callback(*args)

    user32 = User32()
    for name in (
        "IsWindow",
        "IsWindowVisible",
        "GetWindowThreadProcessId",
        "GetWindowRect",
    ):
        setattr(user32, name, NativeFunction(getattr(user32, name)))
    monkeypatch.setattr(ctypes, "windll", SimpleNamespace(user32=user32), raising=False)
    monkeypatch.setattr(
        ImageGrab,
        "grab",
        lambda **kwargs: (
            calls.append(("pixels", kwargs)) or Image.new("RGB", (100, 50))
        ),
    )
    if actual_pid != 422:
        with pytest.raises(RuntimeError, match="changed owner"):
            _windows_capture(75, 422)
        assert not any(name == "pixels" for name, _value in calls)
    else:
        bitmap, bounds = _windows_capture(75, 422)
        assert bitmap.size == (100, 50)
        assert bounds == [10, 20, 110, 70]
        assert calls[-1] == ("pixels", {"window": 75})
