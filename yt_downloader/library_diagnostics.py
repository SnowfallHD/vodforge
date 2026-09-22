"""Admission/removal facts at canonical boundaries, without user content."""

from __future__ import annotations

import uuid
from typing import Any

from .failure_diagnostics import capture_failure
from .product_telemetry import BoundProductOperation


class LibraryActionObservation:
    def __init__(self, bound: BoundProductOperation | None, intent: str, subject: str):
        self.bound = bound
        self.intent = intent
        self.subject = subject
        self.closed = False
        self.attempts = 0

    def emit(
        self, action: str, boundary: str, *, error: BaseException | None = None
    ) -> bool:
        if self.closed:
            return False
        if action in {"completed", "rejected", "duplicate_focused", "cancelled"}:
            self.closed = True
        self.attempts += 1
        if self.attempts > 4 or self.bound is None:
            return False
        try:
            return self.bound.record(
                action,
                {
                    "library_intent": self.intent,
                    "library_subject": self.subject,
                    "library_boundary": boundary,
                },
                **(
                    {
                        "failure_detail": capture_failure(
                            error,
                            stage="history"
                            if boundary in {"history", "annotation"}
                            else "dispatch",
                            inspect_text=False,
                        )
                    }
                    if error is not None
                    else {}
                ),
            )
        except Exception:  # noqa: BLE001 - optional evidence cannot change admission
            return False


def begin_library_action(
    telemetry: Any, intent: str, subject: str, boundary: str = "validation"
) -> LibraryActionObservation:
    bound = None
    try:
        bound = telemetry.bind_operation(
            "library_action_operation", operation_key=str(uuid.uuid4())
        )
    except Exception:  # noqa: BLE001 - unavailable consent/transport fails closed
        bound = None
    # Even a denied operation keeps its original no-consent context. A later
    # queue/launch boundary cannot silently rebind it after consent is granted.
    observation = LibraryActionObservation(bound, intent, subject)
    observation.emit("requested", boundary)
    return observation


def observe_library_action(
    observation: Any, action: str, boundary: str, *, error: BaseException | None = None
) -> None:
    if isinstance(observation, LibraryActionObservation):
        observation.emit(action, boundary, error=error)
