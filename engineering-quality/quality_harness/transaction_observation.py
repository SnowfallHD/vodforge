"""Read-only filesystem observations for controlled lifecycle transactions."""

from pathlib import Path

from .util import sha256_file


def file_observation(path):
    path = Path(path)
    if path.is_symlink():
        return {"path": str(path), "exists": True, "symlink": True}
    if not path.exists():
        return {"path": str(path), "exists": False}
    state = {
        "path": str(path),
        "exists": True,
        "symlink": False,
        "mode": path.stat().st_mode & 0o777,
    }
    if path.is_file():
        state.update(size_bytes=path.stat().st_size, sha256=sha256_file(path))
    return state
