"""Native symbol reuse must never retain a replaced or destroyed window."""

import sys
from types import SimpleNamespace
from unittest.mock import Mock, call

import pytest

from yt_downloader.platforms.macos import windowing as window_chrome


@pytest.fixture(autouse=True)
def isolate_binding():
    resolver = getattr(window_chrome, "_native_root_control", None)
    if resolver is not None:
        resolver.cache_clear()
    yield
    if resolver is not None:
        resolver.cache_clear()


def test_symbol_is_reused_but_each_current_native_window_is_resolved(monkeypatch):
    function = Mock(side_effect=[101, 202, 0])
    library = Mock(return_value=SimpleNamespace(TkMacOSXGetRootControl=function))
    monkeypatch.setattr(window_chrome.ctypes, "CDLL", library)
    native = Mock(
        side_effect=lambda **kwargs: SimpleNamespace(window=lambda: kwargs["c_void_p"])
    )
    monkeypatch.setitem(sys.modules, "objc", SimpleNamespace(objc_object=native))
    widget = SimpleNamespace(winfo_id=Mock(side_effect=[11, 22, 33]))
    assert window_chrome._native_window(widget) == 101
    assert window_chrome._native_window(widget) == 202
    with pytest.raises(RuntimeError, match="unavailable"):
        window_chrome._native_window(widget)
    assert function.call_args_list == [call(11), call(22), call(33)]
    assert native.call_count == 2
    assert library.call_count == 1


def test_unavailable_symbol_is_not_cached_as_a_permanent_failure(monkeypatch):
    function = Mock(return_value=123)
    library = Mock(
        side_effect=[
            AttributeError("Tk not loaded"),
            SimpleNamespace(TkMacOSXGetRootControl=function),
        ]
    )
    monkeypatch.setattr(window_chrome.ctypes, "CDLL", library)
    monkeypatch.setitem(
        sys.modules,
        "objc",
        SimpleNamespace(
            objc_object=lambda **kwargs: SimpleNamespace(
                window=lambda: kwargs["c_void_p"]
            )
        ),
    )
    widget = SimpleNamespace(winfo_id=lambda: 10)
    with pytest.raises(AttributeError, match="Tk not loaded"):
        window_chrome._native_window(widget)
    assert window_chrome._native_window(widget) == 123
    assert library.call_count == 2
