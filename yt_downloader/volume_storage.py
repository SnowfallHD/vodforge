"""Computer-volume capacity, independent of Library item counts and file size."""

from __future__ import annotations

import ctypes
import json
import os
import plistlib
import shutil
import subprocess  # nosec B404 - fixed system diskutil arguments
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from .archive_work import ArchiveWorkOwner
from .platform_services import hidden_window_subprocess_kwargs

_windows_ctypes: Any = ctypes


def format_storage_bytes(value: int) -> str:
    """Use one capacity label formatter in both native renderers."""
    size = float(value)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1000 or unit == "TB":
            return f"{size:.0f} {unit}" if size >= 100 else f"{size:.1f} {unit}"
        size /= 1000
    return str(value)


@dataclass(frozen=True, slots=True)
class StorageVolume:
    path: str
    label: str
    capacity_group: str = ""
    kind: Literal["local", "external", "network", "unknown"] = "unknown"


@dataclass(frozen=True, slots=True)
class VolumeCapacity:
    volume: StorageVolume
    total: int
    used: int
    free: int
    measured_at: float

    @property
    def fraction_used(self) -> float:
        return self.used / self.total if self.total else 0.0


@dataclass(frozen=True, slots=True)
class StorageSnapshot:
    selected: str
    status: Literal["loading", "ready", "unavailable"]
    choices: tuple[StorageVolume, ...] = ()
    capacity: VolumeCapacity | None = None


def default_volume(platform: str | None = None) -> str:
    return "C:\\" if (platform or sys.platform) == "win32" else "/"


def _disk_info(mount: str) -> dict:
    result = subprocess.run(  # nosec B603 B607 - fixed executable, path is one argv
        ["/usr/sbin/diskutil", "info", "-plist", mount],
        capture_output=True,
        timeout=3,
        check=False,
        **hidden_window_subprocess_kwargs(),
    )
    value = plistlib.loads(result.stdout) if result.returncode == 0 else {}
    return value if isinstance(value, dict) else {}


def distinct_capacity_volumes(
    volumes: tuple[StorageVolume, ...],
) -> tuple[StorageVolume, ...]:
    """An APFS container is one capacity pool, even with multiple mounted volumes."""
    groups: dict[str, StorageVolume] = {}
    for volume in sorted(volumes, key=lambda item: (item.path != "/", item.path)):
        key = volume.capacity_group or volume.path
        groups.setdefault(key, volume)
    return tuple(groups.values())


def _windows_fixed_drive_kinds() -> dict[
    str, Literal["local", "external", "network", "unknown"]
]:
    """Get actual bus facts in the existing worker; a fixed USB disk is external."""
    command = (
        "Get-Partition | Where-Object DriveLetter | ForEach-Object { "
        "$disk = $_ | Get-Disk; [pscustomobject]@{Drive=[string]$_.DriveLetter; "
        "Bus=[string]$disk.BusType} } | ConvertTo-Json -Compress"
    )
    try:
        powershell = (
            Path(os.environ.get("SystemRoot", r"C:\Windows"))
            / "System32"
            / "WindowsPowerShell"
            / "v1.0"
            / "powershell.exe"
        )
        # Only the fixed system PowerShell is invoked, with one fixed argv and no shell.
        result = subprocess.run(  # nosec B603
            [str(powershell), "-NoProfile", "-NonInteractive", "-Command", command],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
            **hidden_window_subprocess_kwargs(),
        )
        records = json.loads(result.stdout) if result.returncode == 0 else []
    except (OSError, subprocess.SubprocessError, ValueError):
        return {}
    records = [records] if isinstance(records, dict) else records
    kinds: dict[str, Literal["local", "external", "network", "unknown"]] = {}
    for record in records if isinstance(records, list) else []:
        if not isinstance(record, dict):
            continue
        drive, bus = (
            str(record.get("Drive", "")).upper(),
            str(record.get("Bus", "")).casefold(),
        )
        if len(drive) != 1 or drive not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            continue
        kinds[drive] = (
            "external"
            if bus in {"usb", "1394", "sd", "mmc"}
            else "local"
            if bus in {"nvme", "sata", "ata", "sas", "scsi", "raid", "scm"}
            else "unknown"
        )
    return kinds


def available_volumes(cancelled: threading.Event) -> tuple[StorageVolume, ...]:
    if os.name == "nt":
        kernel = _windows_ctypes.windll.kernel32
        mask = kernel.GetLogicalDrives()
        result = []
        fixed_kinds = _windows_fixed_drive_kinds()
        for bit in range(26):
            if cancelled.is_set():
                break
            mount = f"{chr(65 + bit)}:\\\\"
            drive_type = kernel.GetDriveTypeW(mount)
            if not mask & (1 << bit) or drive_type not in {2, 3, 4}:
                continue
            label = ctypes.create_unicode_buffer(261)
            try:
                named = kernel.GetVolumeInformationW(
                    mount, label, len(label), None, None, None, None, 0
                )
            except OSError:
                named = False
            result.append(
                StorageVolume(
                    mount,
                    label.value if named and label.value else f"Drive {chr(65 + bit)}:",
                    kind="external"
                    if drive_type == 2
                    else "network"
                    if drive_type == 4
                    else fixed_kinds.get(chr(65 + bit), "unknown"),
                )
            )
        return tuple(result)
    if sys.platform != "darwin":
        return (StorageVolume("/", "This computer"),)
    import psutil

    partitions = psutil.disk_partitions(all=False)
    network_types = {"smbfs", "nfs", "webdav", "afpfs", "cifs"}
    network_mounts = {
        part.mountpoint for part in partitions if part.fstype.lower() in network_types
    }
    candidates = [
        "/",
        *(
            part.mountpoint
            for part in partitions
            if part.mountpoint.startswith("/Volumes/")
            or part.mountpoint in network_mounts
        ),
    ]
    result = []
    for mount in dict.fromkeys(candidates):
        if cancelled.is_set():
            break
        try:
            info = _disk_info(mount)
        except (
            OSError,
            subprocess.SubprocessError,
            ValueError,
            plistlib.InvalidFileException,
        ):
            info = {}
        result.append(
            StorageVolume(
                mount,
                str(
                    info.get("VolumeName")
                    or ("This computer" if mount == "/" else Path(mount).name)
                ),
                str(info.get("APFSContainerReference") or ""),
                "network"
                if mount in network_mounts
                else "local"
                if info.get("Internal") is True
                else "external"
                if info.get("Internal") is False
                else "unknown",
            )
        )
    return distinct_capacity_volumes(tuple(result))


def read_volume_capacity(
    selected: str,
    cancelled: threading.Event,
) -> tuple[tuple[StorageVolume, ...], VolumeCapacity | None]:
    choices = available_volumes(cancelled)
    if cancelled.is_set():
        return choices, None
    volume = next((item for item in choices if item.path == selected), None)
    if volume is None:
        # Never reinterpret an unmounted path as its parent/system volume.
        return choices, None
    try:
        usage = shutil.disk_usage(volume.path)
    except OSError:
        return choices, None
    if cancelled.is_set() or usage.total <= 0:
        return choices, None
    return choices, VolumeCapacity(
        volume,
        usage.total,
        max(0, usage.total - usage.free),
        usage.free,
        time.time(),
    )


class StorageCapacityOwner:
    """One bounded asynchronous lane; a blocked drive cannot create more workers."""

    def __init__(
        self,
        selected: str = "",
        *,
        reader: Callable = read_volume_capacity,
        worker: ArchiveWorkOwner | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._reader, self._clock = reader, clock
        self._worker = worker or ArchiveWorkOwner()
        self._selected = selected or default_volume()
        self._snapshot = StorageSnapshot(self._selected, "loading")
        self._due = 0.0
        self._submitted = ""
        self._closed = False

    @property
    def snapshot(self) -> StorageSnapshot:
        return self._snapshot

    def select(self, path: str) -> None:
        if self._closed or not path or path == self._selected:
            return
        self._worker.cancel()
        self._selected = path
        self._snapshot = StorageSnapshot(path, "loading", self._snapshot.choices)
        self._due = 0.0

    def refresh(self) -> None:
        self._due = 0.0

    def poll(self) -> StorageSnapshot:
        if self._closed:
            return self._snapshot
        result = self._worker.poll()
        if result is not None and self._submitted == self._selected:
            choices, capacity = (
                result.value if not result.error and result.value else ((), None)
            )
            self._snapshot = StorageSnapshot(
                self._selected,
                "ready" if capacity is not None else "unavailable",
                tuple(choices),
                capacity,
            )
            self._due = self._clock() + 30
        if not self._worker.busy and self._clock() >= self._due:
            selected = self._selected
            if (
                self._worker.submit(
                    "volume_capacity",
                    lambda cancelled: self._reader(selected, cancelled),
                )
                is not None
            ):
                self._submitted = selected
        return self._snapshot

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            self._worker.close()
