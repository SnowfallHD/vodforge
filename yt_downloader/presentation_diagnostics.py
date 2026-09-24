"""Bounded scene observations, independent of rendering and media ownership.

Only closed enums/count buckets reach ProductTelemetryOwner. Canvas identifiers
are inspected locally, never retained in observations or transported.
"""

from __future__ import annotations

import time
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


class PresentationProbe:
    """Coalesced owner boundaries; no pointer/animation-frame observations."""

    def __init__(self, widget: Any, telemetry: Any, surface: str):
        # Only the Tk adapter needs Tcl. Qt imports the shared bounded owner
        # without pulling Tcl/Tk into its frozen runtime.
        from tkinter import TclError

        self.widget = widget
        self._tcl_error = TclError
        self.observations = PresentationObservations(telemetry, surface)
        self.surface = surface
        self.after: str | None = None
        self.deadline = 0.0
        self.last_size = (0, 0)
        self.closed = False
        self.retired_batch = False

    def change(self, trigger: str) -> None:
        if self.closed:
            return
        observation = self.observations
        # Coalesce a resize burst while its unsettled operation is pending.
        # Artwork completion belongs to the operation that requested it.
        if observation.bound is None or (
            trigger not in {"artwork", "resize"}
            or (
                trigger == "resize"
                and observation.trigger != "resize"
                and observation.last
            )
        ):
            if self.after is not None:
                try:
                    self.widget.after_cancel(self.after)
                except self._tcl_error:
                    self.close()
                    return
                self.after = None
            observation.begin(trigger)
            self.retired_batch = False
        if trigger in {"hide", "artwork"}:
            self.schedule()

    def schedule(self) -> None:
        if self.closed or self.observations.bound is None or self.after is not None:
            return
        # Preserve the first pending audit's due time. Repeated geometry updates
        # must not hide time spent waiting for the UI event loop.
        delay = 0 if not self.observations.last else 120
        self.deadline = time.monotonic() + delay / 1000
        self.after = self.widget.after(delay, self.sample)

    def sample(self) -> None:
        self.after = None
        if self.closed or not self.observations.permitted():
            return
        started = time.monotonic()
        try:
            dimensions, pending = self.widget._presentation_snapshot()
            elapsed = (time.monotonic() - started) * 1000
            dimensions.update(
                {
                    "presentation_audit": "under_2ms"
                    if elapsed < 2
                    else "2_9ms"
                    if elapsed < 10
                    else "10_49ms"
                    if elapsed < 50
                    else "50ms_plus",
                    "lag_bucket": delay_bucket(
                        max(0, (started - self.deadline) * 1000)
                    ),
                    "lag_measurement": "ui_pump_delay",
                    "artwork_batch": "superseded" if self.retired_batch else "current",
                }
            )
            self.observations.observe(dimensions, pending=pending)
        except (self._tcl_error, AttributeError):
            self.close()

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        if self.after is not None:
            try:
                self.widget.after_cancel(self.after)
            except self._tcl_error:
                pass
            self.after = None
        if self.observations.last:
            self.observations.last["presentation_scene"] = "retired"
        self.observations.finish("retired")


def canvas_snapshot(
    widget: Any, dimensions: dict[str, str]
) -> tuple[dict[str, str], bool]:
    """Audit actual Tcl canvas ownership once at a settled owner boundary."""
    canvas = widget.canvas
    live = set(canvas.tk.splitlist(canvas.tk.call("image", "names")))
    missing = []
    displayed_artwork = set()
    for surface in (canvas, *widget.__dict__.get("_presentation_extra_canvases", ())):
        for item in surface.find_all():
            if surface.type(item) != "image":
                continue
            name = surface.itemcget(item, "image")
            tags = surface.gettags(item)
            role = next(
                (
                    value
                    for value in ("control", "artwork", "surface")
                    if "presentation-" + value in tags
                ),
                "unknown",
            )
            if name not in live:
                missing.append(role)
            elif role == "artwork":
                displayed_artwork.add(name)
    wanted = set(widget._artwork_wanted)
    unavailable = wanted & widget._artwork_unavailable
    decoded = {key for key in wanted if key in widget._artwork_images}
    pending = wanted - decoded - unavailable
    awaiting = any(
        str(widget._artwork_images[key]) not in displayed_artwork for key in decoded
    )
    state = (
        "none"
        if not wanted
        else "pending"
        if pending
        else "decoded_awaiting_render"
        if awaiting
        else "unavailable"
        if len(unavailable) == len(wanted)
        else "mixed"
        if unavailable
        else "ready"
    )
    dimensions.update(
        {
            "artwork_expected_bucket": count_bucket(len(wanted)),
            "artwork_displayed_bucket": count_bucket(len(displayed_artwork)),
            "artwork_unavailable_bucket": count_bucket(len(unavailable)),
            "artwork_state": state,
            "missing_image_bucket": count_bucket(len(missing)),
            "missing_image_role": "none"
            if not missing
            else next(iter(set(missing)))
            if len(set(missing)) == 1
            else "mixed",
            "presentation_visibility": "visible"
            if widget.winfo_ismapped()
            else "hidden",
            "presentation_scene": "current"
            if widget.winfo_ismapped()
            else "retained"
            if canvas.find_all()
            else "awaiting",
        }
    )
    return dimensions, bool(pending or awaiting)
