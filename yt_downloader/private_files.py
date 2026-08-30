from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import BinaryIO, TextIO

from .safe_output import is_symlink_or_reparse


def open_private_file_descriptor(
    path: Path,
    *,
    append: bool,
    truncate: bool = False,
) -> int:
    """Open one private regular file without following an existing redirect."""
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | getattr(os, "O_CLOEXEC", 0)
    if append:
        flags |= os.O_APPEND
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags | os.O_CREAT | os.O_EXCL | nofollow, 0o600)
    except FileExistsError:
        existing = path.lstat()
        if is_symlink_or_reparse(existing) or not stat.S_ISREG(existing.st_mode):
            raise OSError(f"Refusing to open non-regular private file: {path}")
        descriptor = os.open(path, flags | nofollow)
    try:
        descriptor_stat = os.fstat(descriptor)
        current = path.lstat()
        if (
            is_symlink_or_reparse(current)
            or not stat.S_ISREG(descriptor_stat.st_mode)
            or not os.path.samestat(current, descriptor_stat)
        ):
            raise OSError(f"Private file changed or redirects elsewhere: {path}")
        if os.name != "nt":
            os.fchmod(descriptor, 0o600)
            if stat.S_IMODE(os.fstat(descriptor).st_mode) != 0o600:
                raise PermissionError(
                    f"Private file permissions could not be restricted: {path}"
                )
        if truncate:
            os.ftruncate(descriptor, 0)
        return descriptor
    except Exception:
        os.close(descriptor)
        raise


def open_private_text_file(path: Path, *, truncate: bool = False) -> TextIO:
    descriptor = open_private_file_descriptor(
        path,
        append=not truncate,
        truncate=truncate,
    )
    try:
        return os.fdopen(
            descriptor,
            "a" if not truncate else "w",
            encoding="utf-8",
            buffering=1,
        )
    except Exception:
        os.close(descriptor)
        raise


def open_private_binary_file(path: Path, *, truncate: bool = False) -> BinaryIO:
    descriptor = open_private_file_descriptor(
        path,
        append=not truncate,
        truncate=truncate,
    )
    try:
        return os.fdopen(descriptor, "ab" if not truncate else "wb")
    except Exception:
        os.close(descriptor)
        raise


def write_private_bytes(path: Path, payload: bytes) -> None:
    with open_private_binary_file(path, truncate=True) as destination:
        destination.write(payload)
