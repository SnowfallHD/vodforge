from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from typing import Any

from .util import tree_size


class ResourceSampler:
    """Sample this harness process, its children, and run-local disk use."""

    def __init__(self, disk_root: Path, interval_seconds: float = 0.05) -> None:
        self.disk_root = disk_root
        self.interval_seconds = interval_seconds
        self.samples: list[dict[str, Any]] = []
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._started = 0.0
        self._baseline_fds = self._fd_count()
        self._baseline_threads = threading.active_count()
        self._psutil = None
        try:
            import psutil

            self._psutil = psutil
            self._root_process = psutil.Process(os.getpid())
            self._prime_cpu(self._root_process)
        except Exception:  # noqa: BLE001 - optional metrics must survive psutil/platform failures
            self._root_process = None

    @staticmethod
    def _prime_cpu(process: Any) -> None:
        try:
            process.cpu_percent(None)
        except Exception:  # noqa: BLE001 - process may disappear between samples
            return

    def _fd_count(self) -> int | None:
        try:
            import psutil

            process = psutil.Process(os.getpid())
            method = getattr(process, "num_fds", None) or getattr(
                process, "num_handles", None
            )
            return int(method()) if callable(method) else None
        except Exception:  # noqa: BLE001 - optional FD metric is platform/process dependent
            return None

    def start(self) -> ResourceSampler:
        self._started = time.monotonic()
        self._thread = threading.Thread(
            target=self._run, name="vodforge-quality-resource-sampler", daemon=True
        )
        self._thread.start()
        return self

    def _process_tree(self) -> list[Any]:
        if self._root_process is None:
            return []
        try:
            return [self._root_process, *self._root_process.children(recursive=True)]
        except Exception:  # noqa: BLE001 - child tree can change while psutil walks it
            return [self._root_process]

    def _run(self) -> None:
        primed: set[int] = set()
        while not self._stop.is_set():
            processes = self._process_tree()
            rss = 0
            cpu = 0.0
            children = 0
            zombies = 0
            for process in processes:
                try:
                    if process.pid not in primed:
                        self._prime_cpu(process)
                        primed.add(process.pid)
                    rss += int(process.memory_info().rss)
                    cpu += float(process.cpu_percent(None))
                    if (
                        self._root_process is not None
                        and process.pid != self._root_process.pid
                    ):
                        children += 1
                    if (
                        self._psutil is not None
                        and process.status() == self._psutil.STATUS_ZOMBIE
                    ):
                        zombies += 1
                except Exception:  # noqa: BLE001,S112 - a sampled process may exit mid-read
                    continue
            self.samples.append(
                {
                    "elapsed_seconds": round(time.monotonic() - self._started, 4),
                    "rss_bytes": rss or None,
                    "cpu_percent": round(cpu, 3),
                    "child_processes": children,
                    "zombies": zombies,
                    "disk_bytes": tree_size(self.disk_root),
                    "threads": threading.active_count(),
                    "fds": self._fd_count(),
                }
            )
            self._stop.wait(self.interval_seconds)

    def stop(self) -> dict[str, Any]:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=max(1.0, self.interval_seconds * 4))
        if not self.samples:
            self._run_once()
        rss_values = [
            sample["rss_bytes"]
            for sample in self.samples
            if sample.get("rss_bytes") is not None
        ]
        cpu_values = [float(sample["cpu_percent"]) for sample in self.samples]
        disk_values = [int(sample["disk_bytes"]) for sample in self.samples]
        child_values = [int(sample["child_processes"]) for sample in self.samples]
        zombie_values = [int(sample["zombies"]) for sample in self.samples]
        final_fds = self._fd_count()
        return {
            "sample_count": len(self.samples),
            "peak_rss_bytes": max(rss_values, default=None),
            "mean_cpu_percent": round(sum(cpu_values) / len(cpu_values), 3)
            if cpu_values
            else None,
            "peak_cpu_percent": max(cpu_values, default=None),
            "peak_disk_bytes": max(disk_values, default=0),
            "peak_child_processes": max(child_values, default=0),
            "peak_zombie_processes": max(zombie_values, default=0),
            "fd_count_before": self._baseline_fds,
            "fd_count_after": final_fds,
            "fd_delta": (final_fds - self._baseline_fds)
            if final_fds is not None and self._baseline_fds is not None
            else None,
            "thread_count_before": self._baseline_threads,
            "thread_count_after": threading.active_count(),
            "thread_delta": threading.active_count() - self._baseline_threads,
            "samples": self.samples,
        }

    def _run_once(self) -> None:
        self.samples.append(
            {
                "elapsed_seconds": 0.0,
                "rss_bytes": None,
                "cpu_percent": 0.0,
                "child_processes": 0,
                "zombies": 0,
                "disk_bytes": tree_size(self.disk_root),
                "threads": threading.active_count(),
                "fds": self._fd_count(),
            }
        )
