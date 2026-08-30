from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import statistics
import subprocess
import sys
import time
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tree_size(path: Path) -> int:
    if not path.exists():
        return 0
    if path.is_file():
        try:
            return path.stat().st_size
        except OSError:
            return 0
    total = 0
    for candidate in path.rglob("*"):
        try:
            if candidate.is_file() and not candidate.is_symlink():
                total += candidate.stat().st_size
        except OSError:
            continue
    return total


def percentile(values: Iterable[float], quantile: float) -> float | None:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        return None
    if len(ordered) == 1:
        return ordered[0]
    position = max(0.0, min(1.0, quantile)) * (len(ordered) - 1)
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def distribution(
    values: Iterable[float], *, digits: int = 4
) -> dict[str, float | int | None]:
    samples = [float(value) for value in values]
    if not samples:
        return {
            "count": 0,
            "min": None,
            "p50": None,
            "p95": None,
            "max": None,
            "mean": None,
        }
    rounded = lambda value: round(float(value), digits)
    return {
        "count": len(samples),
        "min": rounded(min(samples)),
        "p50": rounded(percentile(samples, 0.50)),
        "p95": rounded(percentile(samples, 0.95)),
        "max": rounded(max(samples)),
        "mean": rounded(statistics.fmean(samples)),
    }


@dataclass
class CommandResult:
    command: list[str]
    returncode: int | None
    duration_seconds: float
    stdout: str
    stderr: str
    timed_out: bool = False
    unavailable: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "command": self.command,
            "returncode": self.returncode,
            "duration_seconds": round(self.duration_seconds, 4),
            "stdout": self.stdout,
            "stderr": self.stderr,
            "timed_out": self.timed_out,
            "unavailable": self.unavailable,
        }


def run_command(
    command: list[str],
    *,
    cwd: Path,
    timeout: float = 300,
    env: dict[str, str] | None = None,
) -> CommandResult:
    started = time.monotonic()
    executable = (
        shutil.which(command[0]) if os.path.sep not in command[0] else command[0]
    )
    if not executable or not Path(executable).exists():
        return CommandResult(
            command, None, 0.0, "", f"tool unavailable: {command[0]}", unavailable=True
        )
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
        return CommandResult(
            command,
            completed.returncode,
            time.monotonic() - started,
            completed.stdout,
            completed.stderr,
        )
    except subprocess.TimeoutExpired as exc:
        return CommandResult(
            command,
            None,
            time.monotonic() - started,
            (exc.stdout or "") if isinstance(exc.stdout, str) else "",
            (exc.stderr or "") if isinstance(exc.stderr, str) else "",
            timed_out=True,
        )


def git_value(repo_root: Path, *args: str) -> str | None:
    result = run_command(["git", *args], cwd=repo_root, timeout=30)
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def machine_snapshot(repo_root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    memory_total: int | None = None
    cpu_name = platform.processor() or platform.machine()
    try:
        import psutil

        memory_total = int(psutil.virtual_memory().total)
        cpu_name = cpu_name or str(psutil.cpu_freq())
    except (ImportError, OSError):
        memory_total = None
    try:
        load_average = [round(value, 3) for value in os.getloadavg()]
    except (AttributeError, OSError):
        load_average = []
    disk = shutil.disk_usage(repo_root)
    machine = {
        "platform": platform.platform(),
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "processor": cpu_name,
        "python": sys.version.split()[0],
        "cpu_count_logical": os.cpu_count(),
        "memory_total_bytes": memory_total,
        "load_average_at_start": load_average,
        "disk_total_bytes": disk.total,
        "disk_free_bytes_at_start": disk.free,
        "timezone": time.tzname[0] if time.tzname else None,
    }
    tracked_files = git_value(repo_root, "ls-files")
    repository = {
        "root": str(repo_root),
        "commit": git_value(repo_root, "rev-parse", "HEAD"),
        "branch": git_value(repo_root, "branch", "--show-current"),
        "status_porcelain": (
            git_value(repo_root, "status", "--porcelain") or ""
        ).splitlines(),
        "tracked_file_count": len(tracked_files.splitlines()) if tracked_files else 0,
    }
    return machine, repository


def json_dump(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )


def scrub_path(value: str, roots: dict[Path, str]) -> str:
    output = value
    for root, replacement in sorted(
        roots.items(), key=lambda item: len(str(item[0])), reverse=True
    ):
        output = output.replace(str(root), replacement)
    return output
