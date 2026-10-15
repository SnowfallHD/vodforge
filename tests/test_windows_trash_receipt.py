"""Native provider boundary: never accept a missing recycling receipt."""

import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform != "win32", reason="Windows native bindings"
)


@pytest.mark.parametrize(
    "outcome",
    [
        "success",
        "recycled_success",
        "nonrecyclable",
        "missing_receipt",
        "aborted",
        "native_error",
    ],
)
def test_windows_trash_requires_native_recycling_receipt(
    tmp_path, monkeypatch, outcome
):
    import pythoncom
    from send2trash.win import modern
    from win32com.shell import shell, shellcon

    from yt_downloader.platforms.windows import filesystem

    source = tmp_path / "owned.txt"
    source.write_bytes(b"owned disposable bytes")
    target = tmp_path / "recoverable-owned.txt"
    initialized = []
    monkeypatch.setattr(pythoncom, "CoInitialize", lambda: initialized.append("init"))
    monkeypatch.setattr(pythoncom, "CoUninitialize", lambda: initialized.append("end"))
    monkeypatch.setattr(pythoncom, "WrapObject", lambda obj, interface: obj)
    monkeypatch.setattr(shell, "SHCreateItemFromParsingName", lambda *args: source)
    # Prior adapter is a no-op negative control, never a real deletion here.
    monkeypatch.setattr(modern, "send2trash", lambda path: None)

    class Target:
        def GetDisplayName(self, kind):
            assert kind == shellcon.SIGDN_FILESYSPATH
            return str(target)

    class Operation:
        def SetOperationFlags(self, flags):
            assert flags & 0x00080000

        def DeleteItem(self, item, sink):
            self.sink = sink

        def PerformOperations(self):
            flags = (
                0
                if outcome == "nonrecyclable"
                else shellcon.TSF_DELETE_RECYCLE_IF_POSSIBLE
            )
            self.sink.PreDeleteItem(flags, source)
            if outcome in {"success", "recycled_success"}:
                source.rename(target)
                # Actual Windows recycling returns COPYENGINE_S_RECYCLE,
                # a successful nonzero HRESULT, not S_OK.
                result = 0x00270008 if outcome == "recycled_success" else 0
                self.sink.PostDeleteItem(flags, source, result, Target())
            elif outcome == "native_error":
                self.sink.PostDeleteItem(flags, source, -2147467259, None)
            return 0

        def GetAnyOperationsAborted(self):
            return outcome == "aborted"

    monkeypatch.setattr(pythoncom, "CoCreateInstance", lambda *args: Operation())
    if outcome in {"success", "recycled_success"}:
        assert Path(filesystem.trash_file(source)) == target
        assert target.read_bytes() == b"owned disposable bytes"
        assert not source.exists()
    else:
        with pytest.raises(OSError):
            filesystem.trash_file(source)
        assert source.read_bytes() == b"owned disposable bytes"
        assert not target.exists()
    assert initialized == ["init", "end"]
