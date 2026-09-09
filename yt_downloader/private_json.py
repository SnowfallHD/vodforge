"""Small private JSON credentials: safe reads and exclusive atomic first publication."""

from __future__ import annotations

import json
import os
import stat
import tempfile
from pathlib import Path
from typing import Any

from .safe_output import is_symlink_or_reparse


def read_private_json(path: Path) -> dict[str, Any]:
    before = path.lstat()
    if is_symlink_or_reparse(before) or not stat.S_ISREG(before.st_mode):
        raise OSError("Unsafe credential file")
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(fd, "rb") as stream:
        if not os.path.samestat(before, os.fstat(stream.fileno())):
            raise OSError("Credential file changed")
        value = json.loads(stream.read(4097))
    if not isinstance(value, dict):
        raise TypeError("Invalid credential file")
    return value


def create_private_json_once(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".credential-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(json.dumps(value).encode("utf-8"))
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(name, path)
        except FileExistsError:
            pass
    finally:
        os.unlink(name)
