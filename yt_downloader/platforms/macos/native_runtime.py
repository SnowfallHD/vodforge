"""Typed calls to existing Objective-C functions, without Python native callbacks.

The function prototypes wrap libobjc's existing executable addresses. They never
wrap a Python callable or allocate a libffi executable closure (unlike PyObjC's
AppKit struct registration). No entitlement or process security change is needed.
"""

from __future__ import annotations

import ctypes
from functools import lru_cache
from typing import Any


@lru_cache(maxsize=1)
def _runtime():
    ctypes.CDLL("/System/Library/Frameworks/AppKit.framework/AppKit")
    runtime = ctypes.CDLL("/usr/lib/libobjc.A.dylib")
    runtime.objc_getClass.argtypes = [ctypes.c_char_p]
    runtime.objc_getClass.restype = ctypes.c_void_p
    runtime.sel_registerName.argtypes = [ctypes.c_char_p]
    runtime.sel_registerName.restype = ctypes.c_void_p
    return runtime


def class_pointer(name: bytes) -> int:
    pointer = int(_runtime().objc_getClass(name) or 0)
    if not pointer:
        raise RuntimeError("Required Objective-C class is unavailable")
    return pointer


def selector_pointer(name: bytes) -> int:
    pointer = int(_runtime().sel_registerName(name) or 0)
    if not pointer:
        raise RuntimeError("Required Objective-C selector is unavailable")
    return pointer


@lru_cache(maxsize=64)
def _message(restype: Any, argtypes: tuple):
    address = ctypes.cast(_runtime().objc_msgSend, ctypes.c_void_p).value
    if not address:
        raise RuntimeError("Objective-C message dispatch is unavailable")
    return ctypes.CFUNCTYPE(restype, ctypes.c_void_p, ctypes.c_void_p, *argtypes)(
        address
    )


def send(receiver: int, selector: bytes, restype: Any, argtypes: tuple = (), *args):
    """Call a scalar/pointer-returning public selector with its exact signature.

    Struct returns are deliberately excluded: x86_64 requires a different ABI
    for some structures, and the window owner needs only scalar/pointer calls.
    """
    if isinstance(restype, type) and issubclass(restype, ctypes.Structure):
        raise TypeError("Struct-returning Objective-C messages are not supported")
    target = selector_pointer(selector)
    return _message(restype, tuple(argtypes))(receiver, target, *args)
