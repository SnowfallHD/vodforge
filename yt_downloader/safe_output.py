from __future__ import annotations

import errno
import os
import shutil
import stat
import uuid
from collections.abc import Callable, Sequence
from pathlib import Path


class UnsafeOutputPathError(RuntimeError):
    """Raised when a final output path can escape its selected root."""


def is_symlink_or_reparse(stat_result: os.stat_result) -> bool:
    if stat.S_ISLNK(stat_result.st_mode):
        return True
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return bool(getattr(stat_result, "st_file_attributes", 0) & reparse_flag)


def _same_file(first: os.stat_result, second: os.stat_result) -> bool:
    return (first.st_dev, first.st_ino) == (second.st_dev, second.st_ino)


def _resolved_beneath(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _lexical_destination_parts(
    root: Path, destination: Path
) -> tuple[Path, Path, tuple[str, ...], str]:
    root_absolute = Path(os.path.abspath(os.fspath(root)))
    destination_absolute = Path(os.path.abspath(os.fspath(destination)))
    try:
        relative = destination_absolute.relative_to(root_absolute)
    except ValueError as exc:
        raise UnsafeOutputPathError(
            "The final output path is outside the selected destination."
        ) from exc
    if not relative.parts or relative.name in {"", ".", ".."}:
        raise UnsafeOutputPathError("The final output filename is invalid.")
    parent_parts = tuple(relative.parts[:-1])
    if any(part in {"", ".", ".."} for part in parent_parts):
        raise UnsafeOutputPathError(
            "The final output path contains an unsafe directory component."
        )
    return root_absolute, destination_absolute, parent_parts, relative.name


def _directory_open_flags() -> int:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    flags |= getattr(os, "O_CLOEXEC", 0)
    return flags


def _open_directory_at(
    parent_fd: int, name: str, *, purpose: str = "final output"
) -> int:
    try:
        descriptor = os.open(name, _directory_open_flags(), dir_fd=parent_fd)
    except OSError as exc:
        raise UnsafeOutputPathError(
            f"The {purpose} directory component {name!r} is not a safe directory."
        ) from exc
    try:
        path_stat = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        descriptor_stat = os.fstat(descriptor)
        if (
            is_symlink_or_reparse(path_stat)
            or not stat.S_ISDIR(path_stat.st_mode)
            or not _same_file(path_stat, descriptor_stat)
        ):
            raise UnsafeOutputPathError(
                f"The {purpose} directory component {name!r} changed or redirects elsewhere."
            )
        return descriptor
    except Exception:
        os.close(descriptor)
        raise


def _walk_directory_fds(root_fd: int, parts: Sequence[str], *, create: bool) -> int:
    current_fd = os.dup(root_fd)
    try:
        for part in parts:
            if create:
                try:
                    os.mkdir(part, mode=0o777, dir_fd=current_fd)
                except FileExistsError:
                    pass
                except OSError as exc:
                    if exc.errno != errno.EEXIST:
                        raise
            next_fd = _open_directory_at(current_fd, part)
            os.close(current_fd)
            current_fd = next_fd
        return current_fd
    except Exception:
        os.close(current_fd)
        raise


def _restrict_private_directory_fd(descriptor: int, label: str) -> None:
    descriptor_stat = os.fstat(descriptor)
    if not stat.S_ISDIR(descriptor_stat.st_mode):
        raise UnsafeOutputPathError(f"The {label} is not a directory.")
    os.fchmod(descriptor, 0o700)
    if stat.S_IMODE(os.fstat(descriptor).st_mode) != 0o700:
        raise PermissionError(
            f"The {label} permissions could not be restricted to 0700."
        )


def _create_private_staging_posix(root_real: Path, *, attempts: int) -> Path:
    try:
        root_fd = os.open(root_real, _directory_open_flags())
    except OSError as exc:
        raise UnsafeOutputPathError(
            "The selected output root could not be opened safely for staging."
        ) from exc
    try:
        try:
            os.mkdir(".vfstage", mode=0o700, dir_fd=root_fd)
        except FileExistsError:
            pass
        staging_root_fd = _open_directory_at(
            root_fd, ".vfstage", purpose="VODForge staging"
        )
        try:
            _restrict_private_directory_fd(staging_root_fd, "VODForge staging root")
            for _attempt in range(attempts):
                token = uuid.uuid4().hex[:8]
                try:
                    os.mkdir(token, mode=0o700, dir_fd=staging_root_fd)
                except FileExistsError:
                    continue
                child_fd: int | None = None
                try:
                    child_fd = _open_directory_at(
                        staging_root_fd,
                        token,
                        purpose="VODForge staging",
                    )
                    _restrict_private_directory_fd(
                        child_fd, "VODForge run staging directory"
                    )
                    return root_real / ".vfstage" / token
                except Exception:
                    try:
                        os.rmdir(token, dir_fd=staging_root_fd)
                    except OSError:
                        pass
                    raise
                finally:
                    if child_fd is not None:
                        os.close(child_fd)
        finally:
            os.close(staging_root_fd)
    finally:
        os.close(root_fd)
    raise RuntimeError("VODForge could not allocate a unique staging directory.")


def _create_private_staging_portable(root_real: Path, *, attempts: int) -> Path:
    staging_root = root_real / ".vfstage"
    try:
        staging_root.mkdir(mode=0o700)
    except FileExistsError:
        pass
    root_stat = staging_root.lstat()
    if is_symlink_or_reparse(root_stat) or not stat.S_ISDIR(root_stat.st_mode):
        raise UnsafeOutputPathError(
            "The VODForge staging root redirects or is not a directory."
        )
    if os.name != "nt":
        staging_root.chmod(0o700)
        if stat.S_IMODE(staging_root.stat().st_mode) != 0o700:
            raise PermissionError(
                "The VODForge staging root permissions could not be restricted to 0700."
            )
    for _attempt in range(attempts):
        staging = staging_root / uuid.uuid4().hex[:8]
        try:
            staging.mkdir(mode=0o700)
        except FileExistsError:
            continue
        staging_stat = staging.lstat()
        if is_symlink_or_reparse(staging_stat) or not stat.S_ISDIR(
            staging_stat.st_mode
        ):
            raise UnsafeOutputPathError(
                "The VODForge run staging directory redirects or is not a directory."
            )
        if os.name != "nt":
            staging.chmod(0o700)
            if stat.S_IMODE(staging.stat().st_mode) != 0o700:
                raise PermissionError(
                    "The VODForge run staging permissions could not be restricted to 0700."
                )
        return staging
    raise RuntimeError("VODForge could not allocate a unique staging directory.")


def create_private_staging_directory(output_root: Path, *, attempts: int = 16) -> Path:
    """Create private same-volume staging without following descendants."""
    root_absolute = Path(os.path.abspath(os.fspath(output_root)))
    root_absolute.mkdir(parents=True, exist_ok=True)
    try:
        root_real = root_absolute.resolve(strict=True)
    except OSError as exc:
        raise UnsafeOutputPathError(
            "The selected output root could not be resolved for staging."
        ) from exc
    if not root_real.is_dir():
        raise UnsafeOutputPathError("The selected output root is not a directory.")
    supports_secure_dir_fds = (
        os.name != "nt"
        and hasattr(os, "O_NOFOLLOW")
        and os.open in os.supports_dir_fd
        and os.mkdir in os.supports_dir_fd
        and os.stat in os.supports_dir_fd
    )
    if supports_secure_dir_fds:
        return _create_private_staging_posix(root_real, attempts=attempts)
    return _create_private_staging_portable(root_real, attempts=attempts)


def _remove_idle_staging_root(staging_root: Path) -> bool:
    """Remove an idle VODForge root, tolerating Finder's private metadata only."""

    if staging_root.name != ".vfstage":
        return False
    try:
        root_stat = staging_root.lstat()
    except FileNotFoundError:
        return True
    if is_symlink_or_reparse(root_stat) or not stat.S_ISDIR(root_stat.st_mode):
        return False

    supports_secure_dir_fds = (
        os.name != "nt"
        and hasattr(os, "O_NOFOLLOW")
        and os.open in os.supports_dir_fd
        and os.stat in os.supports_dir_fd
        and os.unlink in os.supports_dir_fd
    )
    if supports_secure_dir_fds:
        try:
            root_fd = os.open(staging_root, _directory_open_flags())
        except OSError:
            return False
        try:
            entries = os.listdir(root_fd)
            if entries == [".DS_Store"]:
                finder_stat = os.stat(
                    ".DS_Store", dir_fd=root_fd, follow_symlinks=False
                )
                if is_symlink_or_reparse(finder_stat) or not stat.S_ISREG(
                    finder_stat.st_mode
                ):
                    return False
                os.unlink(".DS_Store", dir_fd=root_fd)
            elif entries:
                return False
        except OSError:
            return False
        finally:
            os.close(root_fd)
    else:
        try:
            portable_entries = list(staging_root.iterdir())
        except OSError:
            return False
        if len(portable_entries) == 1 and portable_entries[0].name == ".DS_Store":
            try:
                finder_stat = portable_entries[0].lstat()
                if is_symlink_or_reparse(finder_stat) or not stat.S_ISREG(
                    finder_stat.st_mode
                ):
                    return False
                portable_entries[0].unlink()
            except OSError:
                return False
        elif portable_entries:
            return False

    try:
        staging_root.rmdir()
    except OSError:
        return False
    return True


def cleanup_private_staging_directory(staging_dir: Path) -> bool:
    """Remove one transaction and its idle root without touching unknown entries."""

    staging = Path(staging_dir)
    staging_root = staging.parent
    if staging_root.name != ".vfstage" or staging.name in {"", ".", ".."}:
        return False
    try:
        staging_stat = staging.lstat()
    except FileNotFoundError:
        return _remove_idle_staging_root(staging_root)
    if is_symlink_or_reparse(staging_stat) or not stat.S_ISDIR(staging_stat.st_mode):
        return False
    shutil.rmtree(staging, ignore_errors=True)
    if os.path.lexists(staging):
        return False
    return _remove_idle_staging_root(staging_root)


def _reject_unsafe_leaf_at(parent_fd: int, name: str) -> None:
    try:
        leaf_stat = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        return
    if is_symlink_or_reparse(leaf_stat) or not stat.S_ISREG(leaf_stat.st_mode):
        raise UnsafeOutputPathError(
            "The final output filename already redirects or is not a regular file."
        )


def _commit_posix(
    source: Path,
    root_real: Path,
    destination_absolute: Path,
    parent_parts: Sequence[str],
    leaf_name: str,
    control_check: Callable[[], None] | None,
) -> None:
    try:
        root_fd = os.open(root_real, _directory_open_flags())
    except OSError as exc:
        raise UnsafeOutputPathError(
            "The selected output root could not be opened safely."
        ) from exc
    try:
        root_path_stat = os.stat(root_real, follow_symlinks=False)
        root_descriptor_stat = os.fstat(root_fd)
        if (
            is_symlink_or_reparse(root_path_stat)
            or not stat.S_ISDIR(root_path_stat.st_mode)
            or not _same_file(root_path_stat, root_descriptor_stat)
        ):
            raise UnsafeOutputPathError(
                "The selected output root changed while it was being opened."
            )

        created_parent_fd = _walk_directory_fds(root_fd, parent_parts, create=True)
        os.close(created_parent_fd)
        if control_check is not None:
            control_check()

        parent_fd = _walk_directory_fds(root_fd, parent_parts, create=False)
        try:
            # Re-resolve the user-visible path immediately before commit and
            # prove it still names the exact directory opened through root_fd.
            resolved_parent = destination_absolute.parent.resolve(strict=True)
            if not _resolved_beneath(resolved_parent, root_real):
                raise UnsafeOutputPathError(
                    "The final output directory resolves outside the selected destination."
                )
            resolved_stat = os.stat(resolved_parent, follow_symlinks=False)
            parent_stat = os.fstat(parent_fd)
            if is_symlink_or_reparse(resolved_stat) or not _same_file(
                resolved_stat, parent_stat
            ):
                raise UnsafeOutputPathError(
                    "The final output directory changed before commit."
                )
            _reject_unsafe_leaf_at(parent_fd, leaf_name)
            os.replace(source, leaf_name, dst_dir_fd=parent_fd)
        finally:
            os.close(parent_fd)
    finally:
        os.close(root_fd)


def _verify_windows_directory_chain(
    root_absolute: Path,
    root_real: Path,
    parent_parts: Sequence[str],
    *,
    create: bool,
) -> Path:
    current = root_absolute
    for part in parent_parts:
        current /= part
        if create:
            try:
                current.mkdir()
            except FileExistsError:
                pass
        try:
            current_stat = current.lstat()
        except OSError as exc:
            raise UnsafeOutputPathError(
                f"The final output directory component {part!r} could not be verified."
            ) from exc
        if is_symlink_or_reparse(current_stat) or not stat.S_ISDIR(
            current_stat.st_mode
        ):
            raise UnsafeOutputPathError(
                f"The final output directory component {part!r} redirects or is not a directory."
            )
        try:
            resolved = current.resolve(strict=True)
        except OSError as exc:
            raise UnsafeOutputPathError(
                f"The final output directory component {part!r} could not be resolved."
            ) from exc
        if not _resolved_beneath(resolved, root_real):
            raise UnsafeOutputPathError(
                "The final output directory resolves outside the selected destination."
            )
    return current


def _commit_windows(
    source: Path,
    root_absolute: Path,
    root_real: Path,
    destination_absolute: Path,
    parent_parts: Sequence[str],
    leaf_name: str,
    control_check: Callable[[], None] | None,
) -> None:
    _verify_windows_directory_chain(root_absolute, root_real, parent_parts, create=True)
    if control_check is not None:
        control_check()
    parent = _verify_windows_directory_chain(
        root_absolute, root_real, parent_parts, create=False
    )
    resolved_parent = parent.resolve(strict=True)
    if not _resolved_beneath(resolved_parent, root_real):
        raise UnsafeOutputPathError(
            "The final output directory resolves outside the selected destination."
        )
    leaf = parent / leaf_name
    try:
        leaf_stat = leaf.lstat()
    except FileNotFoundError:
        pass
    else:
        if is_symlink_or_reparse(leaf_stat) or not stat.S_ISREG(leaf_stat.st_mode):
            raise UnsafeOutputPathError(
                "The final output filename already redirects or is not a regular file."
            )
    # Windows does not expose an os.replace directory-handle variant. The
    # immediately preceding reparse and resolved-containment checks are the
    # strongest portable boundary available here.
    os.replace(source, destination_absolute)


def commit_file_beneath(
    source: Path,
    root: Path,
    destination: Path,
    *,
    control_check: Callable[[], None] | None = None,
) -> Path:
    """Atomically replace a regular file beneath ``root`` without following children.

    The selected root itself may be a symlink chosen by the user. Every
    descendant component is created and verified without following symlinks or
    Windows reparse points, then checked again immediately before commit.
    """
    root_absolute, destination_absolute, parent_parts, leaf_name = (
        _lexical_destination_parts(
            root,
            destination,
        )
    )
    root_absolute.mkdir(parents=True, exist_ok=True)
    try:
        root_real = root_absolute.resolve(strict=True)
    except OSError as exc:
        raise UnsafeOutputPathError(
            "The selected output root could not be resolved."
        ) from exc
    try:
        root_stat = root_real.stat()
    except OSError as exc:
        raise UnsafeOutputPathError(
            "The selected output root could not be inspected."
        ) from exc
    if not stat.S_ISDIR(root_stat.st_mode):
        raise UnsafeOutputPathError("The selected output root is not a directory.")

    supports_secure_dir_fds = (
        os.name != "nt"
        and hasattr(os, "O_NOFOLLOW")
        and os.open in os.supports_dir_fd
        and os.mkdir in os.supports_dir_fd
        and os.stat in os.supports_dir_fd
    )
    if supports_secure_dir_fds:
        _commit_posix(
            source,
            root_real,
            destination_absolute,
            parent_parts,
            leaf_name,
            control_check,
        )
    else:
        _commit_windows(
            source,
            root_absolute,
            root_real,
            destination_absolute,
            parent_parts,
            leaf_name,
            control_check,
        )
    return destination_absolute
