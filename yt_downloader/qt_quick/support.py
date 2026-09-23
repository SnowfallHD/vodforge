"""Qt session adapter for explicit feedback and public-review submissions."""

from __future__ import annotations

import json
import queue
import threading
import uuid
from pathlib import Path
from typing import Any

from yt_downloader.support_diagnostics import FailureContext
from yt_downloader.support_payload import feedback_payload, review_payload
from yt_downloader.support_transport import (
    SubmissionError,
    SupportTransport,
    VerificationRequired,
)


class QtSupportSession:
    def __init__(self, directory: Path, *, transport: SupportTransport | None = None):
        self.transport = transport or SupportTransport(directory)
        self.kind = ""
        self.context: FailureContext | None = None
        self.status = ""
        self.busy = False
        self.sent = False
        self._request_id = str(uuid.uuid4())
        self._last_payload = ""
        self._receipts: queue.Queue[tuple[bool, str]] = queue.Queue(maxsize=1)

    def open(self, kind: str, context: FailureContext | None = None) -> bool:
        if kind not in {"feedback", "review"} or self.busy:
            return False
        self.kind = kind
        self.context = context if kind == "feedback" else None
        self.status = (
            "No logs, cookies, or credentials are sent automatically."
            if kind == "feedback"
            else "Public reviews are reviewed before publication."
        )
        self.sent = False
        self._last_payload = ""
        self._request_id = str(uuid.uuid4())
        return True

    def submit(self, values: dict[str, Any]) -> bool:
        if self.busy or self.sent or self.kind not in {"feedback", "review"}:
            return False
        try:
            if self.kind == "feedback":
                payload = feedback_payload(
                    reason=str(values.get("reason") or ""),
                    message=str(values.get("message") or ""),
                    reply=values.get("reply") is True,
                    email=str(values.get("email") or ""),
                    include_diagnostics=values.get("diagnostics") is True,
                    include_video_url=values.get("videoUrl") is True,
                    context=self.context,
                )
            else:
                stars = values.get("stars")
                payload = review_payload(
                    stars=stars
                    if isinstance(stars, int) and not isinstance(stars, bool)
                    else 0,
                    comment=str(values.get("message") or ""),
                    display_name=str(values.get("name") or ""),
                )
        except ValueError as error:
            self.status = str(error)
            return False
        encoded = json.dumps(payload, sort_keys=True)
        if self._last_payload and encoded != self._last_payload:
            self._request_id = str(uuid.uuid4())
        self._last_payload = encoded
        request_id = self._request_id
        kind = self.kind
        self.busy = True
        self.status = "Sending…"

        def deliver() -> None:
            try:
                receipt = self.transport.submit(kind, payload, request_id)
            except VerificationRequired as error:
                result = (False, str(error))
            except (SubmissionError, OSError, ValueError, TypeError, KeyError):
                result = (
                    False,
                    "Could not confirm delivery. Your text is preserved; please try again later.",
                )
            else:
                result = (True, receipt)
            self._receipts.put(result)

        threading.Thread(
            target=deliver, daemon=True, name="vodforge-qt-user-submission"
        ).start()
        return True

    def poll(self) -> bool:
        try:
            ok, result = self._receipts.get_nowait()
        except queue.Empty:
            return False
        self.busy = False
        if ok:
            self.sent = True
            self.status = f"Thank you. Received as {result}."
        else:
            self.status = result
        return True

    def close(self) -> bool:
        if self.busy:
            return False
        self.kind = ""
        self.context = None
        return True
