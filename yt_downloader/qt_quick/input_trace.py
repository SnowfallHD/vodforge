"""Opt-in, bounded local input diagnostics for an isolated Qt candidate.

Nothing is installed at import time. Never serializes object names, labels, text,
URLs, paths, key text or media records. Geometric candidates are not proof of
Qt's dispatched target; action emission and grab observations are separate.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any, cast

from PySide6.QtCore import QEvent, QObject, QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QMouseEvent
from PySide6.QtQuick import QQuickItem, QQuickWindow
from shiboken6 import getCppPointer, isValid

_ACTIONS = frozenset(
    {
        "library_select",
        "library_filter",
        "library_import",
        "forge_options",
        "watch_more",
        "settings",
        "nav_forge",
        "nav_library",
        "nav_watch",
        "nav_activity",
        "fixture_action",
    }
)
_POPUPS = frozenset(
    {"library_filter", "forge_options", "watch_more", "settings", "fixture_popup"}
)
_EVENTS = {
    QEvent.Type.MouseButtonPress: "press",
    QEvent.Type.MouseButtonRelease: "release",
    QEvent.Type.MouseButtonDblClick: "double_press",
    QEvent.Type.MouseMove: "held_move",
    QEvent.Type.UngrabMouse: "ungrab",
    QEvent.Type.WindowActivate: "window_activate",
    QEvent.Type.WindowDeactivate: "window_deactivate",
    QEvent.Type.TouchCancel: "touch_cancel",
}


class InputTrace(QObject):
    """One-window observer. Caller owns explicit export and isolated-profile checks.

    Stop before engine/window teardown. Never returns true from eventFilter and
    never connects MouseArea.doubleClicked (doing so changes click behavior).
    """

    def __init__(self, window: QQuickWindow, *, max_records=256, seconds=60):
        super().__init__(window)
        if not 8 <= max_records <= 2048 or not 0 < seconds <= 300:
            raise ValueError("Input trace exceeds bounded diagnostic limits")
        self._window = window
        self._max_records = max_records
        self._deadline = time.monotonic() + seconds
        self._started = time.monotonic()
        self._records: list[dict[str, Any]] = []
        self._tokens: dict[int, str] = {}
        self._token_counter = 0
        self._actions: dict[int, str] = {}
        self._targets: dict[str, QQuickItem] = {}
        self._delivery_items: list[QQuickItem] = []
        self._popups: dict[str, QObject] = {}
        self._connections: list[tuple[QObject, Any, Callable]] = []
        self._position: QPointF | None = None
        self._gesture = 0
        self._event = 0
        self._last_move = 0.0
        self._stopped = False
        self._reason = "running"
        window.installEventFilter(self)
        self._connect(window, window.activeFocusItemChanged, self._focus_changed)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(lambda: self.stop("deadline"))
        self._timer.start(round(seconds * 1000))

    def _connect(self, owner, signal, callback):
        signal.connect(callback)
        self._connections.append((owner, signal, callback))

    def watch_action(self, item: QQuickItem, role: str) -> None:
        if (
            role not in _ACTIONS
            or self._stopped
            or role in self._targets
            or getCppPointer(item)[0] in self._actions
            or item.window() is not self._window
        ):
            raise ValueError("Unknown or inactive diagnostic action")
        self._actions[getCppPointer(item)[0]] = role
        self._targets[role] = item
        self._identity(item)
        self._connect(item, item.activated, lambda: self._record("action", action=role))
        pending = [item]
        visited = 0
        while pending and visited < 128:
            child = pending.pop()
            visited += 1
            if child.acceptedMouseButtons() != Qt.MouseButton.NoButton:
                child.installEventFilter(self)
                self._delivery_items.append(child)
            pending.extend(child.childItems())

    def watch_popup(self, popup: QObject, role: str) -> None:
        if role not in _POPUPS or self._stopped or role in self._popups:
            raise ValueError("Unknown or inactive diagnostic popup")
        self._popups[role] = popup
        self._connect(
            popup, cast(Any, popup).visibleChanged, lambda: self._record("popup_state")
        )

    def _identity(self, item: QQuickItem | None) -> dict[str, Any] | None:
        if item is None or not isValid(item):
            return None
        key = getCppPointer(item)[0]
        if key not in self._tokens:
            self._token_counter += 1
            self._tokens[key] = f"i{self._token_counter}"
            self._connect(item, item.destroyed, lambda: self._forget_item(key))
        token = self._tokens[key]
        owner = item
        action = None
        for _ in range(32):
            if owner is None:
                break
            action = self._actions.get(getCppPointer(owner)[0])
            if action is not None:
                break
            owner = owner.parentItem()
        return {
            "id": token,
            "action_owner": action,
            "mouse_area": item.inherits("QQuickMouseArea"),
            "filters_children": item.filtersChildMouseEvents(),
            "keep_grab": item.keepMouseGrab(),
            "enabled": item.isEnabled(),
            "visible": item.isVisible(),
            "opacity": round(item.opacity(), 3),
            "z": round(item.z(), 1),
        }

    def _forget_item(self, key):
        # A new delegate may reuse a retired native address. Never attach the
        # old token or action role to that unrelated object.
        self._tokens.pop(key, None)
        self._actions.pop(key, None)

    def _hit_candidates(self) -> tuple[list[dict[str, Any]], bool]:
        if self._position is None:
            return [], False
        hits: list[dict[str, Any]] = []
        visited = 0
        truncated = False

        def visit(item, depth=0):
            nonlocal visited, truncated
            visited += 1
            if visited > 2048 or depth > 48 or len(hits) >= 12:
                truncated = True
                return
            if not item.isVisible() or not item.isEnabled():
                return
            local = item.mapFromScene(self._position)
            inside = item.contains(local)
            if item.clip() and not inside:
                return
            children = list(enumerate(item.childItems()))
            children.sort(key=lambda pair: (pair[1].z(), pair[0]), reverse=True)
            # Positive/default-z children paint above their parent; negative
            # children below. This is a geometric ordering, not dispatch tracing.
            above = [child for _, child in children if child.z() >= 0]
            below = [child for _, child in children if child.z() < 0]
            for child in above:
                visit(child, depth + 1)
            accepts = item.acceptedMouseButtons() != Qt.MouseButton.NoButton
            if item.inherits("QQuickMouseArea") and not item.property("enabled"):
                accepts = False
            if inside and accepts:
                hit = self._identity(item)
                hit["local"] = [round(local.x(), 1), round(local.y(), 1)]
                hit["size"] = [round(item.width(), 1), round(item.height(), 1)]
                hits.append(hit)
            for child in below:
                visit(child, depth + 1)

        visit(self._window.contentItem())
        return hits[:12], truncated

    def _target_geometry(self):
        targets = {}
        for role, item in self._targets.items():
            if not isValid(item):
                targets[role] = {"destroyed": True}
                continue
            bounds = item.mapRectToScene(QRectF(0, 0, item.width(), item.height()))
            targets[role] = {
                "visible": item.isVisible(),
                "enabled": item.isEnabled(),
                "rect": [
                    round(value, 1)
                    for value in (
                        bounds.x(),
                        bounds.y(),
                        bounds.width(),
                        bounds.height(),
                    )
                ],
            }
        return targets

    def _record(self, kind: str, **fields) -> None:
        if self._stopped:
            return
        if time.monotonic() >= self._deadline:
            self.stop("deadline")
            return
        hits, truncated = self._hit_candidates()
        self._records.append(
            {
                "seq": len(self._records) + 1,
                "ms": round((time.monotonic() - self._started) * 1000, 1),
                "kind": kind,
                "gesture": self._gesture,
                "window_active": self._window.isActive(),
                "sample_position": (
                    [round(self._position.x(), 1), round(self._position.y(), 1)]
                    if self._position is not None
                    else None
                ),
                "focus": self._identity(self._window.activeFocusItem()),
                "grabber": self._identity(self._window.mouseGrabberItem()),
                "geometric_candidates": hits,
                "scan_truncated": truncated,
                "targets": self._target_geometry(),
                "popups": {
                    role: {
                        "visible": bool(popup.property("visible")),
                        "modal": bool(popup.property("modal")),
                        "opacity": float(popup.property("opacity")),
                    }
                    for role, popup in self._popups.items()
                    if isValid(popup)
                },
                **fields,
            }
        )
        if len(self._records) >= self._max_records:
            self.stop("record_limit")

    def _focus_changed(self):
        self._record("focus_changed")

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        kind = _EVENTS.get(event.type())
        if kind is not None and not self._stopped:
            if event.type() == QEvent.Type.MouseMove:
                now = time.monotonic()
                if (
                    watched is not self._window
                    or not isinstance(event, QMouseEvent)
                    or event.buttons() == Qt.MouseButton.NoButton
                    or now - self._last_move < 0.05
                ):
                    return False
                self._last_move = now
            if watched is not self._window:
                if isinstance(watched, QQuickItem):
                    self._record(
                        "target_delivery",
                        event=kind,
                        event_id=self._event,
                        target=self._identity(watched),
                    )
                return False
            self._event += 1
            event_id = self._event
            fields = {"event_id": event_id, "event": kind}
            if isinstance(event, QMouseEvent):
                self._position = QPointF(event.position())
                if event.type() == QEvent.Type.MouseButtonPress:
                    self._gesture += 1
                fields.update(
                    position=[
                        round(self._position.x(), 1),
                        round(self._position.y(), 1),
                    ],
                    buttons=event.buttons().value,
                    spontaneous=event.spontaneous(),
                )
            self._record("window_delivery", **fields)
            # A zero timer is an event-loop checkpoint, NOT synchronous after-
            # delivery proof. Preserve its source id when input is batched.
            QTimer.singleShot(
                0, self, lambda: self._record("settled", event_id=event_id)
            )
        return False

    def stop(self, reason="explicit"):
        if self._stopped:
            return
        self._stopped = True
        self._reason = (
            reason if reason in {"explicit", "deadline", "record_limit"} else "explicit"
        )
        self._timer.stop()
        if isValid(self._window):
            self._window.removeEventFilter(self)
        for item in self._delivery_items:
            if isValid(item):
                item.removeEventFilter(self)
        self._delivery_items.clear()
        for owner, signal, callback in self._connections:
            if not isValid(owner):
                continue
            try:
                signal.disconnect(callback)
            except (RuntimeError, TypeError):
                pass
        self._connections.clear()

    def snapshot(self) -> dict[str, Any]:
        return {"schema": 1, "status": self._reason, "records": list(self._records)}
