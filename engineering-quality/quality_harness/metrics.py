from __future__ import annotations

import gc
import json
import os
import threading
import time
import tracemalloc
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .util import tree_size

_OBJECT_MODULE_PREFIXES = (
    "yt_downloader",
    "yt_dlp",
    "PIL",
    "tkinter",
    "quality_harness",
)
_SELECTED_OBJECT_TYPES = {
    "_io.BufferedReader",
    "_io.BufferedWriter",
    "_io.FileIO",
    "_io.TextIOWrapper",
    "PIL.Image.Image",
    "PIL.ImageTk.PhotoImage",
    "subprocess.Popen",
    "threading.Thread",
    "yt_downloader.models.DownloadJob",
    "yt_dlp.YoutubeDL.YoutubeDL",
}


def _qualified_type_name(object_type: type[Any]) -> str:
    module = getattr(object_type, "__module__", "")
    qualname = getattr(object_type, "__qualname__", "")
    safe_module = module if isinstance(module, str) and module else "<unknown>"
    safe_qualname = (
        qualname
        if isinstance(qualname, str) and qualname
        else type(object_type).__name__
    )
    return f"{safe_module}.{safe_qualname}"


def _gc_tracked_object_counts(*, top_types: int = 20) -> dict[str, Any]:
    """Count GC-tracked objects without claiming to count every Python allocation."""
    objects = gc.get_objects()
    counts = Counter(type(item) for item in objects)
    module_totals: dict[str, int] = {prefix: 0 for prefix in _OBJECT_MODULE_PREFIXES}
    selected = {name: 0 for name in sorted(_SELECTED_OBJECT_TYPES)}
    named_counts: list[tuple[str, int]] = []
    for object_type, count in counts.items():
        name = _qualified_type_name(object_type)
        named_counts.append((name, count))
        raw_module = getattr(object_type, "__module__", "")
        module = raw_module if isinstance(raw_module, str) else ""
        for prefix in _OBJECT_MODULE_PREFIXES:
            if module == prefix or module.startswith(f"{prefix}."):
                module_totals[prefix] += count
        if name in selected:
            selected[name] = count
    named_counts.sort(key=lambda item: (-item[1], item[0]))
    result = {
        "available": True,
        "scope": "gc_tracked_objects_only",
        "total": len(objects),
        "module_prefix_counts": module_totals,
        "selected_type_counts": selected,
        "top_type_counts": [
            {"type": name, "count": count}
            for name, count in named_counts[: max(0, top_types)]
        ],
    }
    del objects
    del counts
    return result


def _linear_slope(values: list[int]) -> float | None:
    if len(values) < 2:
        return None
    midpoint = (len(values) - 1) / 2
    mean = sum(values) / len(values)
    denominator = sum((index - midpoint) ** 2 for index in range(len(values)))
    if denominator == 0:
        return None
    numerator = sum(
        (index - midpoint) * (value - mean) for index, value in enumerate(values)
    )
    return round(numerator / denominator, 3)


def lifecycle_growth_summary(
    values: list[int], *, warmup_jobs: int = 10
) -> dict[str, Any]:
    """Describe a series without turning a machine-specific delta into a verdict."""
    if not values:
        return {
            "sample_count": 0,
            "first": None,
            "last": None,
            "delta": None,
            "linear_slope_per_job": None,
            "post_warmup_sample_count": 0,
            "post_warmup_delta": None,
            "post_warmup_linear_slope_per_job": None,
            "new_high_count": 0,
        }
    tail = values[min(max(0, warmup_jobs), len(values)) :]
    new_highs = 0
    high = values[0]
    for value in values[1:]:
        if value > high:
            high = value
            new_highs += 1
    return {
        "sample_count": len(values),
        "first": values[0],
        "last": values[-1],
        "delta": values[-1] - values[0],
        "linear_slope_per_job": _linear_slope(values),
        "post_warmup_sample_count": len(tail),
        "post_warmup_delta": tail[-1] - tail[0] if len(tail) >= 2 else None,
        "post_warmup_linear_slope_per_job": _linear_slope(tail),
        "new_high_count": new_highs,
    }


class LifecycleCheckpointRecorder:
    """Write bounded, post-GC lifecycle observations without retaining job results."""

    def __init__(self, run_root: Path, *, jobs: int, detailed: bool) -> None:
        self.run_root = run_root
        self.jobs = jobs
        self.detailed = detailed
        self._started = time.monotonic()
        self.observation_dir = run_root / "cases" / "lifecycle-soak-observability"
        self.observation_dir.mkdir(parents=True, exist_ok=True)
        self.samples_path = self.observation_dir / "per-job-samples.jsonl"
        self.samples_path.write_text("", encoding="utf-8")
        self.trace_baseline_path = self.observation_dir / "baseline.tracemalloc"
        self.trace_final_path = self.observation_dir / "final.tracemalloc"
        self._tracing_started_here = False
        self._process: Any | None = None
        try:
            import psutil  # type: ignore[import-untyped]

            self._process = psutil.Process(os.getpid())
        # Optional metrics explicitly degrade to an unavailable receipt.
        except Exception:  # noqa: BLE001,S110  # nosec B110
            pass

    @property
    def artifacts(self) -> list[str]:
        paths = [self.samples_path]
        if self.trace_baseline_path.is_file():
            paths.append(self.trace_baseline_path)
        if self.trace_final_path.is_file():
            paths.append(self.trace_final_path)
        return [str(path) for path in paths]

    def start(self) -> dict[str, Any]:
        if self.detailed:
            if not tracemalloc.is_tracing():
                tracemalloc.start(5)
                self._tracing_started_here = True
            # Warm the observer itself before establishing the resource baseline.
            _gc_tracked_object_counts(top_types=1)
            gc.collect()
            baseline = tracemalloc.take_snapshot()
            baseline.dump(str(self.trace_baseline_path))
            del baseline
            gc.collect()
        return self._record(phase="baseline", job_index=None, extra=None)

    def before_job(self, job_index: int) -> dict[str, Any]:
        return self._record(phase="before_job", job_index=job_index, extra=None)

    def after_job(self, job_index: int, *, extra: dict[str, Any]) -> dict[str, Any]:
        trace_checkpoint = self.detailed and job_index in {
            10,
            25,
            50,
            75,
            100,
            self.jobs,
        }
        return self._record(
            phase="after_job",
            job_index=job_index,
            extra=extra,
            trace_checkpoint=trace_checkpoint,
            final=job_index == self.jobs,
        )

    def finish(self) -> None:
        if self._tracing_started_here and tracemalloc.is_tracing():
            tracemalloc.stop()

    def _record(
        self,
        *,
        phase: str,
        job_index: int | None,
        extra: dict[str, Any] | None,
        trace_checkpoint: bool = False,
        final: bool = False,
    ) -> dict[str, Any]:
        collected = gc.collect()
        sample: dict[str, Any] = {
            "phase": phase,
            "job_index": job_index,
            "elapsed_seconds": round(time.monotonic() - self._started, 4),
            "gc": {
                "collected_by_forced_full_gc": collected,
                "generation_counts_after": list(gc.get_count()),
                "generation_stats": gc.get_stats(),
                "uncollectable_garbage_count": len(gc.garbage),
            },
            "process": self._process_state(),
            "python_threads": {
                "count": threading.active_count(),
                "names": sorted(thread.name for thread in threading.enumerate()),
            },
            "storage": self._storage_state(),
            "headless_visibility": {
                "tk_interpreter": "unavailable_headless_no_tk_initialization",
                "tk_image_count": None,
                "in_memory_history_count": None,
                "in_memory_completed_job_count": None,
                "reason": "worker adapter does not construct Tk or pump UI history events",
            },
        }
        sample["gc_tracked_objects"] = (
            _gc_tracked_object_counts()
            if self.detailed
            else {
                "available": False,
                "scope": "disabled_in_normal_profile",
            }
        )
        sample["tracemalloc"] = self._trace_state(
            checkpoint=trace_checkpoint, final=final
        )
        if extra:
            sample["job"] = extra
        self._append(sample)
        if self.detailed and tracemalloc.is_tracing():
            tracemalloc.reset_peak()
        return sample

    def _process_state(self) -> dict[str, Any]:
        if self._process is None:
            return {
                "available": False,
                "rss_bytes": None,
                "uss_bytes": None,
                "vms_bytes": None,
                "fd_or_handle_count": None,
                "os_thread_count": None,
                "child_processes": None,
            }
        try:
            memory = self._process.memory_info()
            full_memory_method = getattr(self._process, "memory_full_info", None)
            full_memory = full_memory_method() if callable(full_memory_method) else None
            fd_method = getattr(self._process, "num_fds", None) or getattr(
                self._process, "num_handles", None
            )
            thread_method = getattr(self._process, "num_threads", None)
            children: list[dict[str, Any]] = []
            for child in self._process.children(recursive=True):
                try:
                    children.append(
                        {
                            "pid": int(child.pid),
                            "status": str(child.status()),
                        }
                    )
                # A child may exit between process-tree enumeration and inspection.
                except Exception:  # noqa: BLE001,S112  # nosec B112
                    continue
            return {
                "available": True,
                "rss_bytes": int(memory.rss),
                "uss_bytes": int(getattr(full_memory, "uss", 0))
                if getattr(full_memory, "uss", None) is not None
                else None,
                "vms_bytes": int(memory.vms),
                "fd_or_handle_count": int(fd_method()) if callable(fd_method) else None,
                "os_thread_count": int(thread_method())
                if callable(thread_method)
                else None,
                "child_processes": children,
            }
        except Exception:  # noqa: BLE001 - optional process metrics are best effort
            return {
                "available": False,
                "rss_bytes": None,
                "uss_bytes": None,
                "vms_bytes": None,
                "fd_or_handle_count": None,
                "os_thread_count": None,
                "child_processes": None,
            }

    @staticmethod
    def _directory_receipt(path: Path, pattern: str = "*") -> dict[str, Any]:
        try:
            files = [item for item in path.glob(pattern) if item.is_file()]
            return {
                "available": True,
                "file_count": len(files),
                "bytes": sum(item.stat().st_size for item in files),
            }
        except OSError:
            return {"available": False, "file_count": None, "bytes": None}

    def _storage_state(self) -> dict[str, Any]:
        from yt_downloader.history import application_data_dir, history_file_path

        data_dir = application_data_dir()
        history_path = history_file_path()
        history_exists = False
        history_bytes: int | None = None
        history_count: int | None = None
        history_error: str | None = None
        try:
            history_exists = history_path.is_file()
            if history_exists:
                history_bytes = history_path.stat().st_size
                payload = json.loads(history_path.read_text(encoding="utf-8"))
                items = payload.get("items") if isinstance(payload, dict) else None
                history_count = len(items) if isinstance(items, list) else None
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            history_error = type(exc).__name__
        staging_paths: list[str] = []
        try:
            staging_paths = [
                str(path)
                for path in self.run_root.rglob("*")
                if ".vfstage" in path.parts
            ]
        except OSError:
            pass
        isolated_tmp = self.run_root / "tmp"
        return {
            "thumbnail_cache": self._directory_receipt(
                data_dir / "thumbnail-cache", "*.jpeg"
            ),
            "history_file": {
                "exists": history_exists,
                "bytes": history_bytes,
                "record_count": history_count,
                "error_type": history_error,
                "visibility": "on_disk_only_ui_event_queue_not_pumped",
            },
            "staging_residue_count": len(staging_paths),
            "staging_residue_paths": staging_paths,
            "isolated_tmp": self._directory_receipt(isolated_tmp),
        }

    def _trace_state(self, *, checkpoint: bool, final: bool) -> dict[str, Any]:
        if not self.detailed or not tracemalloc.is_tracing():
            return {
                "available": False,
                "scope": "disabled_in_normal_profile",
                "current_bytes": None,
                "peak_bytes": None,
                "baseline_delta": None,
            }
        current, peak = tracemalloc.get_traced_memory()
        result: dict[str, Any] = {
            "available": True,
            "scope": "python_allocations_visible_to_tracemalloc",
            "current_bytes": current,
            "peak_bytes": peak,
            "baseline_delta": None,
        }
        if not checkpoint or not self.trace_baseline_path.is_file():
            return result
        current_snapshot = tracemalloc.take_snapshot()
        if final:
            current_snapshot.dump(str(self.trace_final_path))
        baseline_snapshot = tracemalloc.Snapshot.load(str(self.trace_baseline_path))
        differences = current_snapshot.compare_to(baseline_snapshot, "lineno")
        bucket_size: defaultdict[str, int] = defaultdict(int)
        bucket_count: defaultdict[str, int] = defaultdict(int)
        positive: list[dict[str, Any]] = []
        for difference in differences:
            frame = difference.traceback[0]
            filename = str(frame.filename)
            bucket = self._trace_bucket(filename)
            bucket_size[bucket] += int(difference.size_diff)
            bucket_count[bucket] += int(difference.count_diff)
            if difference.size_diff > 0 and len(positive) < 20:
                positive.append(
                    {
                        "file": filename,
                        "line": int(frame.lineno),
                        "size_diff_bytes": int(difference.size_diff),
                        "count_diff": int(difference.count_diff),
                    }
                )
        result["baseline_delta"] = {
            "size_diff_bytes_by_owner": dict(sorted(bucket_size.items())),
            "count_diff_by_owner": dict(sorted(bucket_count.items())),
            "top_positive_locations": positive,
        }
        del differences
        del baseline_snapshot
        del current_snapshot
        return result

    @staticmethod
    def _trace_bucket(filename: str) -> str:
        normalized = filename.replace("\\", "/")
        if "/yt_downloader/" in normalized:
            return "production"
        if "/quality_harness/" in normalized:
            return "harness"
        if "/yt_dlp/" in normalized:
            return "yt_dlp"
        if "/PIL/" in normalized:
            return "pillow"
        if "/lib/python" in normalized:
            return "stdlib"
        return "other"

    def _append(self, sample: dict[str, Any]) -> None:
        with self.samples_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(sample, ensure_ascii=False, sort_keys=True) + "\n")


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
                # A sampled process may exit between enumeration and inspection.
                except Exception:  # noqa: BLE001,S112  # nosec B112
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
