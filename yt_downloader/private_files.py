from __future__ import annotations

import os
import stat
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import BinaryIO, TextIO, TypeVar

from .safe_output import is_symlink_or_reparse

T = TypeVar("T")

# How long to keep retrying a Windows file that another handle has open.
BUSY_FILE_RETRY_SECONDS = 1.0
_ON_WINDOWS = os.name == "nt"


def retry_while_file_is_busy(operation: Callable[[], T]) -> T:
    """Retry briefly when Windows refuses a file because it is open elsewhere.

    Windows can't replace a file, or open one being replaced, while another
    handle has it open: a reader thread in this app, an antivirus scanner or the
    search indexer. Both raise PermissionError for a moment (in a test, over a
    third of saves failed while another thread read the same file). macOS and
    Linux allow it, so they don't retry, and a lasting denial still fails after
    about a second.
    """
    if not _ON_WINDOWS:
        return operation()
    deadline = time.monotonic() + BUSY_FILE_RETRY_SECONDS
    delay = 0.002
    while True:
        try:
            return operation()
        except PermissionError:
            if time.monotonic() >= deadline:
                raise
        time.sleep(delay)
        delay = min(delay * 2, 0.05)


def replace_file(source: Path, destination: Path) -> None:
    """os.replace that tolerates a destination briefly open on Windows."""
    retry_while_file_is_busy(lambda: os.replace(source, destination))


def read_text(path: Path) -> str:
    """UTF-8 text of a file another thread may be replacing at this moment."""
    return retry_while_file_is_busy(lambda: path.read_text(encoding="utf-8"))


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
    """Replace a complete private document; precommit failure keeps old bytes.

    Append streams deliberately retain their separate non-replacement semantics.
    POSIX directory fsync makes the rename durable; Windows exposes file fsync
    and atomic replace here, without a power-loss guarantee for the directory.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    expected = None
    try:
        existing = path.lstat()
    except FileNotFoundError:
        pass
    else:
        if is_symlink_or_reparse(existing) or not stat.S_ISREG(existing.st_mode):
            raise OSError(f"Refusing to replace non-regular private file: {path}")
        descriptor = open_private_file_descriptor(path, append=False)
        try:
            expected = os.fstat(descriptor)
            if not os.path.samestat(existing, expected):
                raise OSError(f"Private file changed before replacement: {path}")
        finally:
            os.close(descriptor)
    temporary = path.with_name(f".vf-private-{uuid.uuid4().hex}.tmp")
    staged = None
    try:
        with open_private_binary_file(temporary, truncate=True) as destination:
            staged = os.fstat(destination.fileno())
            if destination.write(payload) != len(payload):
                raise OSError("Incomplete private document write")
            destination.flush()
            os.fsync(destination.fileno())
        current_stage = temporary.lstat()
        if is_symlink_or_reparse(current_stage) or not os.path.samestat(
            staged, current_stage
        ):
            raise OSError("Private staging document changed before replacement")
        try:
            current = path.lstat()
        except FileNotFoundError:
            if expected is not None:
                raise OSError(
                    "Private destination disappeared before replacement"
                ) from None
        else:
            if (
                expected is None
                or is_symlink_or_reparse(current)
                or not os.path.samestat(expected, current)
            ):
                raise OSError("Private destination changed before replacement")
        replace_file(temporary, path)
        if os.name != "nt":
            directory = os.open(
                path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
            )
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
    finally:
        # Never unlink a substituted file, and never mask the write failure.
        try:
            current = temporary.lstat()
            if (
                staged is not None
                and os.path.samestat(staged, current)
                and not is_symlink_or_reparse(current)
            ):
                temporary.unlink()
        except OSError:
            pass
