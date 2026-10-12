"""Bounded scene observations, independent of rendering and media ownership.

Only closed enums/count buckets reach ProductTelemetryOwner. Canvas identifiers
are inspected locally, never retained in observations or transported.
"""

from __future__ import annotations

import uuid
import weakref
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .product_telemetry import BoundProductOperation


def count_bucket(count: int) -> str:
    return (
        "0"
        if count <= 0
        else "1"
        if count == 1
        else "2_5"
        if count <= 5
        else "6_20"
        if count <= 20
        else "21_100"
        if count <= 100
        else "101_plus"
    )


def delay_bucket(milliseconds: float) -> str:
    return (
        "under_50ms"
        if milliseconds < 50
        else "50_99ms"
        if milliseconds < 100
        else "100_249ms"
        if milliseconds < 250
        else "250_999ms"
        if milliseconds < 1000
        else "1000ms_plus"
    )


@dataclass
class PresentationBudget:
    ordinary: int = 0
    incidents: int = 0
    critical: int = 0
    summaries: int = 0
    attempts: int = 0


_BUDGETS: weakref.WeakKeyDictionary[Any, dict[str, PresentationBudget]] = (
    weakref.WeakKeyDictionary()
)


def session_budget(telemetry: Any, surface: str) -> PresentationBudget:
    try:
        return _BUDGETS.setdefault(telemetry, {}).setdefault(
            surface, PresentationBudget()
        )
    except TypeError:
        # A missing/non-owner test adapter cannot produce telemetry anyway.
        return PresentationBudget()


class PresentationObservations:
    """At most64attempts/surface/session, including reserved fault/closure slots.

    Twelve ordinary operations get initial+settled observations. Four later
    fault-only operations remain admissible after healthy sampling starts.
    Critical events have22reserved slots, terminal events16, summaries2:
    24+22+16+2=64. Failed writes consume budget; there is no hot retry loop.
    """

    def __init__(self, telemetry: Any, surface: str):
        self.telemetry = telemetry
        self.surface = surface
        self.budget = session_budget(telemetry, surface)
        self.bound: BoundProductOperation | None = None
        self.admitted = False
        self.ordinary_admitted = False
        self.normal_count = 0
        self.critical_count = 0
        self.fault = False
        self.trigger = "entry"
        self.last: dict[str, str] = {}
        self.sampling = "full"

    @property
    def attempts(self) -> int:
        return self.budget.attempts

    def begin(self, trigger: str) -> None:
        self.finish("superseded", replacement=trigger)
        self.trigger = trigger
        self.normal_count = self.critical_count = 0
        self.fault = False
        self.last = {}
        self.admitted = False
        self.ordinary_admitted = False
        self.bound = None
        try:
            self.bound = self.telemetry.bind_operation(
                "presentation_operation", operation_key=str(uuid.uuid4())
            )
        except Exception:  # noqa: BLE001 - optional diagnostics cannot own UI
            self.bound = None

    def permitted(self) -> bool:
        try:
            return self.bound is not None and self.bound.permitted()
        except Exception:  # noqa: BLE001 - denied/failed consent fails closed
            return False

    def _emit(self, action: str, dimensions: Mapping[str, str]) -> None:
        if self.bound is None:
            return
        self.budget.attempts += 1
        try:
            self.bound.record(
                action,
                {
                    **dimensions,
                    "presentation_surface": self.surface,
                    "presentation_trigger": self.trigger,
                    "presentation_sampling": self.sampling,
                },
            )
        except Exception:  # noqa: BLE001 - bounded failed attempts are never retried here
            return

    def _sampled(self) -> None:
        if self.admitted and self.budget.summaries < 2:
            self.budget.summaries += 1
            self._emit("sampled", self.last)

    def observe(self, dimensions: Mapping[str, str], *, pending: bool) -> None:
        if not self.permitted():
            return
        previous = self.last
        self.last = dict(dimensions)
        fault = dimensions.get("missing_image_role", "none") != "none"
        if not self.admitted:
            if self.budget.ordinary < 12:
                self.budget.ordinary += 1
                self.admitted = True
                self.ordinary_admitted = True
            elif fault and self.budget.incidents < 4:
                self.budget.incidents += 1
                self.admitted = True
            else:
                return
        if fault != self.fault:
            if self.budget.critical < 22 and self.critical_count < 2:
                self.budget.critical += 1
                self.critical_count += 1
                self._emit("fault" if fault else "recovered", self.last)
            else:
                self.sampling = (
                    "transition_limited" if self.critical_count >= 2 else "exhausted"
                )
                self._sampled()
            self.fault = fault
        elif not fault and self.normal_count < 2 and self.ordinary_admitted:
            if self.normal_count == 0 or (not pending and previous != self.last):
                self.normal_count += 1
                self._emit("observed", self.last)
        if not pending and not fault:
            self.finish("settled")

    def finish(self, action: str, *, replacement: str = "none") -> None:
        if self.admitted:
            if self.budget.ordinary >= 12 and self.sampling == "full":
                self.sampling = "healthy_sampled"
                self._sampled()
            if self.budget.incidents >= 4 and self.sampling != "exhausted":
                self.sampling = "exhausted"
                self._sampled()
            self._emit(action, {**self.last, "presentation_replacement": replacement})
        self.bound = None
        self.admitted = False
        self.ordinary_admitted = False
