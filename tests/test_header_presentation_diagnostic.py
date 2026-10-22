import ctypes
from types import SimpleNamespace

from yt_downloader.platforms.macos.header_host import HeaderHost


class Getter:
    def __init__(self, success=1):
        self.success = success

    def __call__(self, handle, values, count):
        assert handle.value == 123 and count == 52
        for i in range(count):
            values[i] = i / 100
        values[3] = float("nan")
        values[8] = float("inf")
        return self.success


def host(getter=None, closed=False):
    h = HeaderHost.__new__(HeaderHost)
    h._handle = ctypes.c_void_p(None if closed else 123)
    h._library = SimpleNamespace()
    if getter is not None:
        h._library.vf_header_host_qa_presentation = getter
    return h


def test_optional_old_library_and_closed_owner_are_unavailable():
    assert host().qa_presentation() is None
    assert host(Getter(), closed=True).qa_presentation() is None


def test_fixed_numeric_schema_sanitizes_unknowns():
    values = host(Getter()).qa_presentation()
    assert len(values) == 52
    assert values[3] is None and values[8] is None
    assert values[51] == 0.51


def test_native_refusal_is_not_a_runtime_failure():
    assert host(Getter(0)).qa_presentation() is None


def test_trace_exports_only_fixed_numeric_rows_and_requires_current_fit():
    from yt_downloader.qt_quick.mac_header import header_timeline_sample

    calls = []
    geometry = [0.0] * 98
    native = SimpleNamespace(
        snapshot=lambda: (1, 1793, geometry),
        qa_presentation=lambda: calls.append(1) or [None] * 52,
    )
    window = SimpleNamespace(
        property=lambda name: {} if name == "nativeRowPacket" else False,
        devicePixelRatio=lambda: 2,
        _native_window_controls=SimpleNamespace(retired=False, _host=native),
    )
    header = SimpleNamespace(property=lambda name: 0, x=lambda: 0)
    result = header_timeline_sample(window, header)
    assert result["native_presentation"] == {"schema": 1, "rows": [[None] * 13] * 4}
    assert calls == [1]
    native.snapshot = lambda: (1, 1, geometry)
    assert header_timeline_sample(window, header)["native_presentation"] is None
    assert calls == [1]
