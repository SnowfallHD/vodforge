"""Native caption and resize ownership is shared by main and player frames."""

import pytest

from yt_downloader.qt_quick.windows_windowing import frame_hit_test


@pytest.mark.parametrize("scale", [1, 1.25, 1.5, 2])
@pytest.mark.parametrize("size", [(1100, 740), (780, 480)])
def test_frame_edges_controls_and_drag_region(scale, size):
    width, height = (round(v * scale) for v in size)
    border, header = round(8 * scale), round(32 * scale)
    points = [
        (0, 0, 13),
        (width - 1, 0, 14),
        (0, height - 1, 16),
        (width - 1, height - 1, 17),
        (width // 2, 0, 12),
        (width // 2, height - 1, 15),
        (0, height // 2, 10),
        (width - 1, height // 2, 11),
        (width // 2, header // 2, 2),
        (width - round(69 * scale), header // 2, 9),
        (width - round(23 * scale), header // 2, 1),
        (width - round(115 * scale), header // 2, 1),
        (width // 2, header + 5, 1),
    ]
    for x, y, expected in points:
        assert frame_hit_test(x, y, width, height, border, header, False) == expected
    assert frame_hit_test(0, height // 2, width, height, border, header, True) == 1
    assert frame_hit_test(width // 2, 0, width, height, border, header, True) == 2


def test_non_windows_owner_is_unchanged():
    import sys

    from yt_downloader.qt_quick.windows_windowing import integrate_windows_frames

    if sys.platform != "win32":
        assert integrate_windows_frames(None) is None


@pytest.mark.parametrize("foreign_handle", [0xABC, 0xDEF])
def test_native_dispatch_does_not_create_main_or_player_handles(foreign_handle):
    # Run the production callback's foreign-message path without a Windows UI.
    # A hidden window's winId getter is creation, not a harmless lookup.
    import ast
    import ctypes
    from ctypes import wintypes
    from pathlib import Path
    from types import CodeType, FunctionType, SimpleNamespace

    from yt_downloader.qt_quick import windows_windowing

    tree = ast.parse(Path(windows_windowing.__file__).read_text())
    method = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "nativeEventFilter"
    )
    method.decorator_list = []
    namespace = {"w": wintypes, "Any": object}
    compiled = compile(
        ast.Module(body=[method], type_ignores=[]), "production-native-dispatch", "exec"
    )
    method_code = next(
        value for value in compiled.co_consts if isinstance(value, CodeType)
    )
    dispatch = FunctionType(method_code, namespace)

    class HiddenOwner:
        def winId(self):
            raise AssertionError("Native dispatch attempted window creation")

    owner = SimpleNamespace(handles={}, windows=[HiddenOwner(), HiddenOwner()])
    msg = wintypes.MSG()
    msg.hWnd = foreign_handle
    msg.message = 0x0084
    assert dispatch(owner, b"windows_generic_MSG", ctypes.addressof(msg)) == (False, 0)


def test_native_maximize_gesture_queues_one_window_action():
    import ast
    import ctypes
    from ctypes import wintypes
    from pathlib import Path
    from types import CodeType, FunctionType, SimpleNamespace

    from yt_downloader.qt_quick import windows_windowing

    tree = ast.parse(Path(windows_windowing.__file__).read_text())
    method = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "nativeEventFilter"
    )
    compiled = compile(
        ast.Module(body=[method], type_ignores=[]), "production-native-dispatch", "exec"
    )
    code = next(value for value in compiled.co_consts if isinstance(value, CodeType))
    queued = []
    namespace = {
        "w": wintypes,
        "Any": object,
        "QWindow": SimpleNamespace(
            Visibility=SimpleNamespace(FullScreen=5, Maximized=4)
        ),
        "QTimer": SimpleNamespace(singleShot=lambda delay, call: queued.append(call)),
    }
    dispatch = FunctionType(code, namespace)
    states = [2]
    target = SimpleNamespace(
        visibility=lambda: states[-1],
        isVisible=lambda: True,
        showNormal=lambda: states.append(2),
        showMaximized=lambda: states.append(4),
    )
    owner = SimpleNamespace(handles={123: target}, max_pressed=None)
    msg = wintypes.MSG()
    msg.hWnd = 123
    msg.wParam = 9

    def send(kind):
        msg.message = kind
        return dispatch(owner, b"windows_generic_MSG", ctypes.addressof(msg))

    assert send(0x00A1) == (True, 0)
    assert send(0x00A2) == (True, 0)
    assert states == [2] and len(queued) == 1
    queued.pop()()
    assert states == [2, 4]
    # Release without a matching press is not another activation.
    send(0x00A2)
    assert not queued
    send(0x00A1)
    send(0x001F)
    send(0x00A2)
    assert not queued
    send(0x00A1)
    send(0x00A2)
    queued.pop()()
    assert states == [2, 4, 2]
