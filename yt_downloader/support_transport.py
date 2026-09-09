"""Explicit user submissions. No analytics enrollment, background delivery, or raw logs."""

from __future__ import annotations

import json
import re
import secrets
import threading
import time
import urllib.error
import urllib.request
import uuid
import webbrowser
from pathlib import Path
from typing import Any

from .private_json import create_private_json_once, read_private_json

ENDPOINT = "https://getvodforge.com/api/support/"
_LOCK = threading.Lock()


class SubmissionError(RuntimeError):
    pass


class VerificationRequired(SubmissionError):
    """A user-visible browser step, never a successful submission receipt."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self, req: Any, fp: Any, code: Any, msg: Any, headers: Any, newurl: Any
    ) -> None:
        return None


class SupportTransport:
    def __init__(self, directory: Path):
        self.path = directory / "support-credential.json"
        self.retry_after = 0.0

    def _credential(self) -> dict[str, Any]:
        with _LOCK:
            if not self.path.exists():
                create_private_json_once(
                    self.path,
                    {
                        "credential_id": str(uuid.uuid4()),
                        "secret": secrets.token_urlsafe(32),
                    },
                )
            value = read_private_json(self.path)
        try:
            valid = (
                uuid.UUID(value["credential_id"]).version == 4
                and re.fullmatch(r"[A-Za-z0-9_-]{43}", value["secret"]) is not None
            )
        except (KeyError, TypeError, ValueError, AttributeError):
            valid = False
        if not valid:
            raise SubmissionError("Support identity unavailable.")
        return value

    def _post(
        self, action: str, body: dict[str, Any], credential: dict[str, Any]
    ) -> dict[str, Any]:
        data = json.dumps(
            {"credential_id": credential["credential_id"], **body}
        ).encode()
        request = urllib.request.Request(
            ENDPOINT + action,
            data=data,
            headers={
                "User-Agent": "VODForge",
                "Content-Type": "application/json",
                "Authorization": "Bearer " + credential["secret"],
            },
            method="POST",
        )
        try:
            with urllib.request.build_opener(_NoRedirect()).open(
                request, timeout=12
            ) as response:
                result = json.loads(response.read(4097))
                if (
                    response.status != 200
                    or not isinstance(result, dict)
                    or result.get("ok") is not True
                ):
                    raise SubmissionError(
                        "The server did not confirm receipt. Your text is still here."
                    )
                return result
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                try:
                    delay = max(
                        1, min(86400, int(exc.headers.get("Retry-After", "60")))
                    )
                except ValueError:
                    delay = 60
                self.retry_after = time.monotonic() + delay
                raise SubmissionError(
                    "Too many requests. Please wait before trying again."
                ) from None
            raise SubmissionError(
                "Feedback is temporarily unavailable. Your text is still here."
            ) from None
        except (OSError, ValueError):
            raise SubmissionError(
                "Could not send. Check your connection and try again."
            ) from None

    def submit(self, kind: str, payload: dict[str, Any], request_id: str) -> str:
        if kind not in {"feedback", "review"}:
            raise SubmissionError("Unknown submission type.")
        if time.monotonic() < self.retry_after:
            raise SubmissionError("Please wait before trying again.")
        credential = self._credential()
        enrollment = self._post("enroll", {}, credential)
        verification_url = enrollment.get("verification_url")
        if verification_url:
            if not isinstance(verification_url, str) or not re.fullmatch(
                r"https://getvodforge\.com/support/verify/#[A-Za-z0-9_-]{43}",
                verification_url,
            ):
                raise SubmissionError("Untrusted verification destination.")
            try:
                if webbrowser.open(verification_url) is False:
                    raise SubmissionError(
                        "Could not open the browser check. Your text is preserved."
                    )
            except (webbrowser.Error, OSError):
                raise SubmissionError(
                    "Could not open the browser check. Your text is preserved."
                ) from None
            raise VerificationRequired(
                "Complete the browser check, then press Send again. Your text is preserved."
            )
        receipt = self._post(kind, {"request_id": request_id, **payload}, credential)
        if receipt.get("reference") != request_id:
            raise SubmissionError(
                "Receipt could not be verified. Your text is still here."
            )
        return request_id
