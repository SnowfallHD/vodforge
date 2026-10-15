from __future__ import annotations

import sys
from pathlib import Path


def file_change_time_ns(descriptor: int) -> int:
    import ctypes
    import msvcrt
    from ctypes import wintypes

    class BasicInfo(ctypes.Structure):
        _fields_ = [
            ("creation", ctypes.c_longlong),
            ("access", ctypes.c_longlong),
            ("write", ctypes.c_longlong),
            ("change", ctypes.c_longlong),
            ("attributes", wintypes.DWORD),
        ]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)  # type: ignore[attr-defined]
    query = kernel.GetFileInformationByHandleEx
    query.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    query.restype = wintypes.BOOL
    info = BasicInfo()
    # FileBasicInfo=0. Borrow the caller's handle; never close or reopen it here.
    handle = msvcrt.get_osfhandle(descriptor)  # type: ignore[attr-defined]
    if not query(handle, 0, ctypes.byref(info), ctypes.sizeof(info)):
        raise ctypes.WinError(ctypes.get_last_error())  # type: ignore[attr-defined]
    return int(info.change) * 100 - 11_644_473_600_000_000_000


def system_trash_available() -> bool:
    from send2trash.win.modern import send2trash

    return callable(send2trash) and sys.getwindowsversion().major >= 10  # type: ignore[attr-defined]


def trash_file(path: Path) -> str:
    """Recycle through the existing native provider and require its receipt."""
    import pythoncom
    import pywintypes
    from send2trash.win.IFileOperationProgressSink import FileOperationProgressSink
    from win32com.server.exception import COMException
    from win32com.shell import shell, shellcon

    if not path.is_absolute():
        raise OSError("Select an absolute saved file location before using Trash.")
    size = path.stat().st_size

    class RecycleReceipt(FileOperationProgressSink):
        def PreDeleteItem(self, flags, item):
            if not flags & shellcon.TSF_DELETE_RECYCLE_IF_POSSIBLE:
                # A Python return value is not a failing COM HRESULT. Raising
                # the server exception aborts instead of authorizing a nuke.
                raise COMException(
                    desc="This file cannot be recycled; permanent deletion is not authorized.",
                    scode=-2147467259,  # E_FAIL
                )
            return 0

        def PostDeleteItem(self, flags, item, result, newly_created):
            # COPYENGINE_S_RECYCLE (0x00270008) is the native success value.
            # HRESULT failure is its high bit, not whether it is nonzero.
            if result & 0x80000000 or newly_created is None:
                return
            self.newItem = newly_created.GetDisplayName(shellcon.SIGDN_FILESYSPATH)

    pythoncom.CoInitialize()
    try:
        receipt = RecycleReceipt()
        sink = pythoncom.WrapObject(receipt, shell.IID_IFileOperationProgressSink)
        operation = pythoncom.CoCreateInstance(
            shell.CLSID_FileOperation,
            None,
            pythoncom.CLSCTX_ALL,
            shell.IID_IFileOperation,
        )
        operation.SetOperationFlags(
            shellcon.FOF_NOCONFIRMATION
            | shellcon.FOF_NOERRORUI
            | shellcon.FOF_SILENT
            | shellcon.FOFX_EARLYFAILURE
            | 0x20000000  # FOFX_ADDUNDORECORD (Windows 8+)
            | 0x00080000  # FOFX_RECYCLEONDELETE (Windows 8+)
        )
        item = shell.SHCreateItemFromParsingName(str(path), None, shell.IID_IShellItem)
        operation.DeleteItem(item, sink)
        result = operation.PerformOperations()
        if result or operation.GetAnyOperationsAborted() or not receipt.newItem:
            raise OSError("The system did not confirm a recoverable Recycle Bin item.")
        target = Path(receipt.newItem)
        if path.exists() or not target.is_file() or target.stat().st_size != size:
            raise OSError(
                "The system Trash result could not be verified. Review Library."
            )
        return str(target)
    except (pywintypes.com_error, COMException) as error:
        raise OSError(
            "The system could not recycle this file. No permanent deletion was authorized."
        ) from error
    finally:
        pythoncom.CoUninitialize()
