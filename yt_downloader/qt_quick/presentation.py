"""Bounded Qt scene observations for the existing presentation telemetry owner.

QML inspects its own Image status because PySide cannot convert the private
QQuickImageBase status enum. Only counts and closed roles cross into Python.
"""

from __future__ import annotations

import time
from typing import Any

from PySide6.QtCore import QMetaObject, QObject, Qt, QTimer

from yt_downloader.library_search import LIBRARY_ALL_CATEGORIES
from yt_downloader.presentation_diagnostics import (
    PresentationObservations,
    count_bucket,
    delay_bucket,
)


def _count(value: Any) -> int:
    return min(100_000, max(0, int(value))) if type(value) is int else 0


def _audit_bucket(milliseconds: float) -> str:
    return (
        "under_2ms"
        if milliseconds < 2
        else "2_9ms"
        if milliseconds < 10
        else "10_49ms"
        if milliseconds < 50
        else "50ms_plus"
    )


def _scene_dimensions(
    bridge: Any,
    surface: str,
    snapshot: dict[str, Any],
    *,
    elapsed_ms: float,
    lag_ms: float,
) -> tuple[dict[str, str], bool]:
    expected = _count(snapshot.get("artworkExpected"))
    displayed = min(expected, _count(snapshot.get("artworkDisplayed")))
    unavailable = min(expected, _count(snapshot.get("artworkUnavailable")))
    pending = _count(snapshot.get("pending"))
    artwork_pending = _count(snapshot.get("artworkPending"))
    missing = _count(snapshot.get("missing"))
    roles = set(snapshot.get("missingRoles") or ()) & {"control", "surface", "artwork"}
    missing_role = (
        "none" if not missing else next(iter(roles)) if len(roles) == 1 else "mixed"
    )
    if expected == 0:
        artwork_state = "none"
    elif artwork_pending:
        artwork_state = "pending"
    elif displayed and unavailable:
        artwork_state = "mixed"
    elif unavailable and not displayed:
        artwork_state = "unavailable"
    elif displayed < expected:
        artwork_state = "decoded_awaiting_render"
    else:
        artwork_state = "ready"
    route = str(
        bridge._library_scene_route
        if surface == "library"
        else bridge._watch_scene_route
    )
    mode = (
        "folders"
        if surface == "library" and route == "folders"
        else "channels"
        if route == "channels"
        else "channel"
        if route == "channel"
        else "playlists"
        if route == "playlists"
        else "collections"
        if route == "collections"
        else "all"
    )
    search = bridge._library_search if surface == "library" else bridge._watch_search
    filtered = bool(search) or (
        surface == "library" and bridge._library_category != LIBRARY_ALL_CATEGORIES
    )
    eligible = _count(snapshot.get("eligible"))
    dimensions = {
        "mode_eligible_bucket": count_bucket(eligible),
        "query_state": "active" if search else "inactive",
        "filter_state": "active" if filtered else "inactive",
        "presentation_mode": mode,
        "mode_origin": "default" if route == "home" else "user",
        "presentation_population": (
            "library_projection" if surface == "library" else "saved_media"
        ),
        "eligible_bucket": count_bucket(eligible),
        "matching_bucket": count_bucket(_count(snapshot.get("matching"))),
        "rendered_bucket": count_bucket(_count(snapshot.get("rendered"))),
        "artwork_expected_bucket": count_bucket(expected),
        "artwork_displayed_bucket": count_bucket(displayed),
        "artwork_unavailable_bucket": count_bucket(unavailable),
        "artwork_state": artwork_state,
        "missing_image_bucket": count_bucket(missing),
        "missing_image_role": missing_role,
        "presentation_visibility": (
            "visible" if snapshot.get("visible") is True else "hidden"
        ),
        "presentation_scene": (
            "current" if snapshot.get("visible") is True else "retained"
        ),
        "presentation_audit": _audit_bucket(elapsed_ms),
        "lag_bucket": delay_bucket(lag_ms),
        "lag_measurement": "ui_pump_delay",
        "artwork_batch": "current",
    }
    return dimensions, bool(pending or artwork_state == "decoded_awaiting_render")


class QtPresentationProbe(QObject):
    """Sample actual QML image status at scene changes and bounded idle cadence."""

    def __init__(self, bridge: Any, window: Any, telemetry: Any):
        super().__init__(bridge)
        self._bridge = bridge
        self._window = window
        self._observations = {
            surface: PresentationObservations(telemetry, surface)
            for surface in ("watch", "library")
        }
        self._surface = ""
        self._last_signature: tuple[Any, ...] | None = None
        self._trigger = "entry"
        self._due = time.monotonic()
        self._closed = False
        self._settle = QTimer(self)
        self._settle.setSingleShot(True)
        self._settle.timeout.connect(self.sample)
        self._periodic = QTimer(self)
        self._periodic.setInterval(500)
        self._periodic.timeout.connect(self.sample)
        self._periodic.start()
        bridge.selectionChanged.connect(lambda: self.change("navigation"))
        bridge.librarySceneChanged.connect(lambda: self.change("data"))
        bridge.watchSceneChanged.connect(lambda: self.change("data"))
        bridge.themeRevisionChanged.connect(lambda: self.change("theme"))
        window.widthChanged.connect(lambda: self.change("resize"))
        window.heightChanged.connect(lambda: self.change("resize"))
        self.change("entry")

    def change(self, trigger: str) -> None:
        if self._closed:
            return
        self._trigger = trigger
        if not self._settle.isActive():
            self._due = time.monotonic() + 0.05
            self._settle.start(50)

    def sample(self) -> None:
        if self._closed:
            return
        surface = str(self._bridge.selection).lower()
        if surface not in self._observations:
            self._retire()
            return
        observation = self._observations[surface]
        # No QML tree traversal is done until the existing consent owner permits
        # this closed diagnostic operation.
        try:
            if not observation.telemetry.permitted():
                return
        except (AttributeError, RuntimeError):
            return
        started = time.monotonic()
        try:
            if not QMetaObject.invokeMethod(
                self._window,
                "refreshPresentationDiagnosticSnapshot",
                Qt.ConnectionType.DirectConnection,
            ):
                return
            value = self._window.property("presentationDiagnosticSnapshot")
            snapshot = value.toVariant() if hasattr(value, "toVariant") else value
            if not isinstance(snapshot, dict):
                return
        except (RuntimeError, TypeError, ValueError):
            return
        elapsed_ms = (time.monotonic() - started) * 1000
        signature = (
            surface,
            *(
                snapshot.get(key)
                for key in (
                    "artworkExpected",
                    "artworkDisplayed",
                    "artworkUnavailable",
                    "pending",
                    "artworkPending",
                    "missing",
                    "rendered",
                    "matching",
                    "visible",
                )
            ),
            tuple(snapshot.get("missingRoles") or ()),
        )
        if surface != self._surface:
            self._retire()
            self._surface = surface
            observation.begin("entry")
        elif (
            self._trigger
            and observation.last
            and not (
                observation.fault and self._trigger in {"data", "artwork", "resize"}
            )
        ):
            observation.begin(self._trigger)
        elif signature != self._last_signature and observation.bound is None:
            observation.begin("artwork")
        if (
            signature == self._last_signature
            and not self._trigger
            and not observation.bound
        ):
            return
        if observation.bound is None:
            observation.begin(self._trigger if self._trigger else "entry")
        dimensions, pending = _scene_dimensions(
            self._bridge,
            surface,
            snapshot,
            elapsed_ms=elapsed_ms,
            lag_ms=max(0.0, (started - self._due) * 1000) if self._trigger else 0.0,
        )
        observation.observe(dimensions, pending=pending)
        self._last_signature = signature
        self._trigger = ""

    def _retire(self) -> None:
        if self._surface:
            observation = self._observations[self._surface]
            if observation.last:
                observation.last["presentation_scene"] = "retired"
            observation.finish("retired")
            self._surface = ""
            self._last_signature = None

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._periodic.stop()
        self._settle.stop()
        self._retire()
