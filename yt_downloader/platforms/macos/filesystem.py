"""Use the existing system Trash service through typed public native calls."""

from __future__ import annotations

import ctypes
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from yt_downloader.platforms.macos import native_runtime as native

_TRASH_SELECTOR = b"trashItemAtURL:resultingItemURL:error:"


@contextmanager
def _autorelease_pool() -> Iterator[None]:
    pool_class = native.class_pointer(b"NSAutoreleasePool")
    if not pool_class:
        raise OSError("System Trash is unavailable for this file.")
    pool = native.send(pool_class, b"new", ctypes.c_void_p)
    if not pool:
        raise OSError("System Trash is unavailable for this file.")
    try:
        yield
    finally:
        native.send(pool, b"drain", None)


def _file_manager() -> int:
    manager_class = native.class_pointer(b"NSFileManager")
    if not manager_class:
        raise OSError("System Trash is unavailable for this file.")
    manager = native.send(manager_class, b"defaultManager", ctypes.c_void_p)
    if not manager:
        raise OSError("System Trash is unavailable for this file.")
    return int(manager)


def system_trash_available() -> bool:
    with _autorelease_pool():
        manager = _file_manager()
        return bool(
            native.send(
                manager,
                b"respondsToSelector:",
                ctypes.c_bool,
                (ctypes.c_void_p,),
                native.selector_pointer(_TRASH_SELECTOR),
            )
        )


def trash_file(path: Path) -> str | None:
    # Foundation strings preserve Unicode, including non-ASCII source names.
    encoded = str(path).encode("utf-8")
    if b"\0" in encoded:
        raise OSError("The system could not move this file to Trash.")
    with _autorelease_pool():
        manager = _file_manager()
        string_class = native.class_pointer(b"NSString")
        url_class = native.class_pointer(b"NSURL")
        if not string_class or not url_class:
            raise OSError("System Trash is unavailable for this file.")
        string = native.send(
            string_class,
            b"stringWithUTF8String:",
            ctypes.c_void_p,
            (ctypes.c_char_p,),
            encoded,
        )
        url = (
            native.send(
                url_class,
                b"fileURLWithPath:",
                ctypes.c_void_p,
                (ctypes.c_void_p,),
                string,
            )
            if string
            else 0
        )
        if not url:
            raise OSError("The system could not move this file to Trash.")
        resulting_url = ctypes.c_void_p()
        error = ctypes.c_void_p()
        succeeded = native.send(
            manager,
            _TRASH_SELECTOR,
            ctypes.c_bool,
            (
                ctypes.c_void_p,
                ctypes.POINTER(ctypes.c_void_p),
                ctypes.POINTER(ctypes.c_void_p),
            ),
            url,
            ctypes.byref(resulting_url),
            ctypes.byref(error),
        )
        if not succeeded:
            raise OSError("The system could not move this file to Trash.")
        if not resulting_url.value:
            return None
        result_path = native.send(resulting_url.value, b"path", ctypes.c_void_p)
        result_bytes = (
            native.send(result_path, b"UTF8String", ctypes.c_char_p)
            if result_path
            else None
        )
        if not isinstance(result_bytes, bytes):
            raise OSError("The system did not return a readable Trash location.")
        return result_bytes.decode("utf-8")
