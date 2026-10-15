"""Content-free semantic sessions, exception categories and exit observations.

This is an event timeline, not session replay. It never inspects UI text, media,
exception values, tracebacks, local variables, screenshots or OS crash reports.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any

import psutil

from .analytics_consent import AnalyticsConsentOwner
from .private_files import write_private_bytes
from .product_telemetry import ProductTelemetryOwner
from .telemetry_features import time_bucket


def exception_kind(kind: type[BaseException]) -> str:
    for base, label in (
        (MemoryError, "memory_error"),
        (TypeError, "type_error"),
        (ValueError, "value_error"),
        (OSError, "os_error"),
        (RuntimeError, "runtime_error"),
    ):
        if issubclass(kind, base):
            return label
    return "other"


class ApplicationLifecycle:
    def __init__(self, telemetry: ProductTelemetryOwner, directory: Path) -> None:
        self.telemetry = telemetry
        self.directory = directory
        self.started = time.monotonic()
        self._next_heartbeat = self.started + 300
        self._active = False
        self._ready = False
        self._ready_sent = False
        self._closed = False
        self._foreground: bool | None = None
        self._view = "forge"
        self._view_sent: str | None = None
        self._marker: Path | None = None
        self._sys_hook: Any = None
        self._thread_hook: Any = None
        self._prior_sys: Any = None
        self._prior_thread: Any = None
        self._exception_seen: set[tuple[str, str]] = set()

    def record(self, action: str, **dimensions: str) -> bool:
        if self._closed:
            return False
        try:
            return self.telemetry.record(
                "feature_used",
                feature="application_lifecycle",
                action=action,
                dimensions=dimensions,
            )
        except (OSError, ValueError, RuntimeError):
            return False  # Analytics must not break normal launch/exit/control.

    def _clear_marker(self) -> None:
        marker, self._marker = self._marker, None
        if marker is not None:
            try:
                if not marker.is_symlink():
                    marker.unlink(missing_ok=True)
            except OSError:
                pass

    def _begin_marker(self) -> None:
        root = self.directory / "analytics-sessions"
        try:
            if root.is_symlink():
                return
            root.mkdir(mode=0o700, exist_ok=True)
            owner = AnalyticsConsentOwner(self.directory)
            state = owner.snapshot()
            epoch = {
                "collection": state.get("collection_epoch"),
                "provider": state.get("posthog_epoch")
                if owner.posthog_allowed
                else None,
            }
            # Bounded process metadata only. An unreadable/live owner is not a
            # crash. A confirmed dead marker means unclean exit, not its cause.
            markers = list(root.glob("*.json"))[:32]
            for path in markers:
                if path.is_symlink() or path.stat().st_size > 1024:
                    continue
                try:
                    uuid.UUID(path.stem)
                    value = json.loads(path.read_text())
                    if set(value) != {"pid", "created", "epoch"}:
                        continue
                    if type(value["pid"]) is not int or value["pid"] <= 0:
                        continue
                    try:
                        process = psutil.Process(value["pid"])
                        dead = process.create_time() != value["created"]
                    except psutil.NoSuchProcess:
                        dead = True
                    except (psutil.AccessDenied, OSError):
                        continue
                    if dead:
                        if value["epoch"] == epoch:
                            self.record("unclean_previous_exit")
                        path.unlink()
                except (OSError, ValueError, TypeError):
                    continue
            if len(list(root.glob("*.json"))) >= 32:
                return
            marker = root / (str(uuid.uuid4()) + ".json")
            write_private_bytes(
                marker,
                json.dumps(
                    {
                        "pid": os.getpid(),
                        "created": psutil.Process().create_time(),
                        "epoch": epoch,
                    }
                ).encode(),
            )
            self._marker = marker
        except (OSError, ValueError, psutil.Error):
            pass

    def tick(self) -> None:
        if self._closed:
            return
        if not self.telemetry.permitted():
            self._clear_marker()
            self._active = False
            self._ready_sent = False
            self._view_sent = None
            return
        if not self._active:
            if not self.record("session_started"):
                return
            self._active = True
            self._begin_marker()
            if self._foreground is not None:
                self.record("foreground" if self._foreground else "background")
        if self._ready and not self._ready_sent:
            self._ready_sent = self.record(
                "startup_ready",
                duration_bucket=time_bucket(time.monotonic() - self.started),
            )
        if (
            self._ready
            and self._view_sent != self._view
            and self.record("screen_viewed", view=self._view)
        ):
            self._view_sent = self._view
        now = time.monotonic()
        if now >= self._next_heartbeat:
            self._next_heartbeat = now + 300
            self.record("heartbeat", duration_bucket=time_bucket(now - self.started))

    def ready(self) -> None:
        self._ready = True

    def foreground(self, active: bool) -> None:
        if self._foreground != active:
            self._foreground = active
            if self._active:
                self.record("foreground" if active else "background")

    def viewed(self, view: str) -> None:
        if view in {"forge", "library", "watch", "activity"}:
            self._view = view
            if self._active:
                self.tick()

    def report_exception(self, kind: type[BaseException], origin: str) -> None:
        if issubclass(kind, (SystemExit, KeyboardInterrupt)):
            return
        category = exception_kind(kind)
        key = (category, origin)
        if key not in self._exception_seen and self.record(
            "unhandled_exception", exception_kind=category, exception_origin=origin
        ):
            self._exception_seen.add(key)

    def install_exception_hooks(self) -> None:
        if self._sys_hook is not None:
            return
        self._prior_sys, self._prior_thread = sys.excepthook, threading.excepthook

        def main_hook(kind: Any, value: Any, traceback: Any) -> None:
            try:
                self.report_exception(kind, "main_thread")
            finally:
                self._prior_sys(kind, value, traceback)

        def thread_hook(args: Any) -> None:
            try:
                self.report_exception(args.exc_type, "worker_thread")
            finally:
                self._prior_thread(args)

        self._sys_hook, self._thread_hook = main_hook, thread_hook
        sys.excepthook, threading.excepthook = main_hook, thread_hook

    def close(self) -> None:
        if self._closed:
            return
        if self._active:
            self.record(
                "session_ended",
                duration_bucket=time_bucket(time.monotonic() - self.started),
            )
        self._closed = True
        self._clear_marker()
        if self._sys_hook is not None and sys.excepthook is self._sys_hook:
            sys.excepthook = self._prior_sys
        if self._thread_hook is not None and threading.excepthook is self._thread_hook:
            threading.excepthook = self._prior_thread
