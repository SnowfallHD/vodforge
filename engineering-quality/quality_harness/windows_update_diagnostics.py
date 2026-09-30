"""Read-only evidence for a failed isolated Windows upgrade; never an oracle."""

from __future__ import annotations

import argparse
import ctypes
import json
from ctypes import wintypes
from pathlib import Path

import psutil

from quality_harness.e2e_provenance import _verify_windows_window_identity


def process_snapshot(target_pid: int) -> tuple[list[dict], set[int]]:
    """Keep inaccessible owners explicit instead of reporting them as absent."""
    owners = {target_pid}
    rows = []
    try:
        root = psutil.Process(target_pid)
        processes = [root]
        try:
            processes.extend(root.children(recursive=True))
        except psutil.Error as exc:
            rows.append({"pid": target_pid, "children_error": type(exc).__name__})
        for process in processes:
            owners.add(process.pid)
            row = {"pid": process.pid}
            for field in ("ppid", "name", "exe", "status", "create_time"):
                try:
                    row[field] = getattr(process, field)()
                except psutil.Error as exc:
                    row[field + "_error"] = type(exc).__name__
            rows.append(row)
    except psutil.Error as exc:
        rows.append({"pid": target_pid, "inspection_error": type(exc).__name__})
    return rows, owners


def window_snapshot(owners: set[int]) -> list[dict]:
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
    user32.EnumWindows.restype = wintypes.BOOL
    user32.GetWindowThreadProcessId.argtypes = [
        wintypes.HWND,
        ctypes.POINTER(wintypes.DWORD),
    ]
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    rows = []
    errors = []

    @callback_type
    def visit(handle, _):
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(handle, ctypes.byref(owner))
        if owner.value in owners:
            title = ctypes.create_unicode_buffer(4096)
            user32.GetWindowTextW(handle, title, len(title))
            try:
                rows.append(
                    _verify_windows_window_identity(
                        int(handle), owner.value, title.value
                    )
                )
            except (OSError, ValueError, RuntimeError) as exc:
                errors.append(type(exc).__name__)
        return True

    if not user32.EnumWindows(visit, 0):
        raise ctypes.WinError(ctypes.get_last_error())
    if errors:
        raise RuntimeError("Native window inspection failed: " + ",".join(errors))
    return rows


def copy_isolated_logs(run: Path, output: Path, limit: int = 1024 * 1024) -> list[dict]:
    """Only two app logs in this QA profile; no settings, keys or cookie files."""
    rows = []
    run = run.resolve()
    for name in ("latest.log", "activity.log"):
        source = run / "profile" / "VODForge" / "logs" / name
        if not source.exists():
            continue
        if not source.resolve().is_relative_to(run):
            rows.append({"name": name, "error": "outside_isolated_run"})
            continue
        size = source.stat().st_size
        with source.open("rb") as stream:
            stream.seek(max(0, size - limit))
            data = stream.read(limit)
        (output / name).write_bytes(data)
        rows.append({"name": name, "original_bytes": size, "copied_bytes": len(data)})
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--run", type=Path, required=True)
    args = parser.parse_args()
    output = args.run / "failure-diagnostics"
    output.mkdir(exist_ok=True)
    result = {"target_pid": args.pid, "evidence_tier": "read-only-failure-diagnostics"}
    processes, owners = process_snapshot(args.pid)
    result["processes"] = processes
    for name, capture in (
        ("windows", lambda: window_snapshot(owners)),
        ("logs", lambda: copy_isolated_logs(args.run, output)),
    ):
        try:
            result[name] = capture()
        except (OSError, ValueError, RuntimeError) as exc:
            result[name + "_error"] = type(exc).__name__
    (output / "snapshot.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
