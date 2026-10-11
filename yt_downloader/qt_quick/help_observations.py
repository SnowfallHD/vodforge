"""Observe the actual Qt Help menu and panel lifecycles without owning UI state."""

from __future__ import annotations

import uuid
from typing import Any

from yt_downloader.archive_observations import bind_operation, operation
from yt_downloader.failure_diagnostics import capture_failure


class QtHelpObservations:
    def __init__(self) -> None:
        self._telemetry: Any = None
        self._menu: Any = None
        self._selected: tuple[str, Any] | None = None
        self._panel: tuple[str, Any] | None = None
        self._shown = False

    def _record(self, action: str, bound: Any, target: str, **kwargs: Any) -> None:
        operation(
            self._telemetry,
            "help_operation",
            action,
            bound,
            {"help_target": target},
            **kwargs,
        )

    def menu_shown(self, telemetry: Any) -> None:
        self.menu_closed()
        self._telemetry = telemetry
        self._menu = bind_operation(
            telemetry, "help_operation", operation_key=str(uuid.uuid4())
        )
        self._record("requested", self._menu, "menu")
        self._record("shown", self._menu, "menu")

    def menu_closed(self) -> None:
        self._record("closed", self._menu, "menu")
        self._menu = None

    def select(self, target: str) -> None:
        if target not in {"feedback", "review", "welcome", "menu"}:
            return
        self._record("selected", self._menu, target)
        # None is deliberately retained: a denied menu cannot be adopted on regrant.
        self._selected = (target, self._menu)
        self._menu = None

    def begin(self, telemetry: Any, target: str) -> Any:
        self._telemetry = telemetry
        selected, self._selected = self._selected, None
        if selected is not None and selected[0] == target:
            bound = selected[1]
        else:
            bound = bind_operation(
                telemetry, "help_operation", operation_key=str(uuid.uuid4())
            )
            self._record("requested", bound, target)
        self._record("dispatched", bound, target)
        return bound

    def ready(self, bound: Any, target: str) -> None:
        if self._panel is not None:
            self._record("replaced", self._panel[1], self._panel[0])
            self.panel_closed()
        self._panel = (target, bound)
        self._shown = False

    def panel_shown(self, target: str) -> None:
        if self._panel is not None and self._panel[0] == target and not self._shown:
            self._record("shown", self._panel[1], target)
            self._shown = True

    def panel_closed(self) -> None:
        if self._panel is not None:
            self._record("closed", self._panel[1], self._panel[0])
        self._panel = None
        self._shown = False

    def blocked(self, bound: Any, target: str) -> None:
        operation(
            self._telemetry,
            "help_operation",
            "blocked",
            bound,
            {"help_target": target, "ui_blocker": "panel"},
        )
        self._record("closed", bound, target)

    def failed(self, bound: Any, target: str, error: Exception) -> None:
        self._record(
            "failed",
            bound,
            target,
            failure_detail=capture_failure(error, stage="dispatch", inspect_text=False),
        )
        self._record("closed", bound, target)

    def close(self) -> None:
        self.menu_closed()
        self.panel_closed()
        self._selected = None
