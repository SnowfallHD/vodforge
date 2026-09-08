"""Browser-independent, credential-scoped native telemetry delivery.

Credentials prove continuity, not official binary provenance. A legacy install
UUID is a compatibility link, not proof of ownership of an old installation.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import stat
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .analytics_consent import analytics_allowed
from .cloud_funnel import load_or_create_installation_state
from .private_files import write_private_bytes
from .safe_output import is_symlink_or_reparse
from .telemetry_policy import telemetry_collection_allowed
from .telemetry_transport import telemetry_urlopen
from .version import __version__

ENDPOINT = "https://getvodforge.com/api/telemetry/v2/"
SECRET_RE = re.compile(r"[A-Za-z0-9_-]{43}")


class RejectedTelemetryEvent(RuntimeError):
    """Server rejected this event permanently; never mark it delivered."""


def _read(path: Path) -> dict[str, Any]:
    before = path.lstat()
    if is_symlink_or_reparse(before) or not stat.S_ISREG(before.st_mode):
        raise OSError("Unsafe telemetry credential file")
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(fd, "rb") as stream:
        if not os.path.samestat(before, os.fstat(stream.fileno())):
            raise OSError("Telemetry credential changed")
        value = json.loads(stream.read(4097))
    if not isinstance(value, dict):
        raise TypeError("Invalid telemetry credential")
    return value


def _create_once(path: Path, value: dict[str, Any]) -> None:
    """Publish a complete private file atomically; concurrent creators cannot replace it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".telemetry-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(json.dumps(value).encode("utf-8"))
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(name, path)
        except FileExistsError:
            pass
    finally:
        os.unlink(name)


class TelemetryCredentialOwner:
    def __init__(
        self, directory: Path, *, opener: Callable[..., Any] = telemetry_urlopen
    ):
        self.path = directory / "telemetry-credential.json"
        self.receipt = directory / "telemetry-launch-receipt.json"
        self.backoff = directory / "telemetry-backoff.json"
        self.opener = opener

    def _credential(self) -> dict[str, Any]:
        if not self.path.exists():
            _create_once(
                self.path,
                {
                    "credential_id": str(uuid.uuid4()),
                    "secret": secrets.token_urlsafe(32),
                },
            )
        value = _read(self.path)
        if uuid.UUID(value["credential_id"]).version != 4 or not SECRET_RE.fullmatch(
            value["secret"]
        ):
            raise ValueError("Invalid telemetry credential")
        return value

    def launch_confirmed(self, app_version: str = __version__) -> bool:
        try:
            receipt = _read(self.receipt)
            return (
                receipt.get("credential_id") == _read(self.path).get("credential_id")
                and receipt.get("app_version") == app_version
                and receipt.get("install_id")
                == load_or_create_installation_state(
                    self.path.parent / "installation.json"
                ).install_id
            )
        except (OSError, ValueError, KeyError, TypeError):
            return False

    def _post(
        self, action: str, payload: dict[str, Any], credential: dict[str, Any]
    ) -> dict[str, Any] | None:
        if not telemetry_collection_allowed() or not analytics_allowed(
            self.path.parent
        ):
            return None
        try:
            previous = _read(self.backoff)
        except (OSError, ValueError, TypeError):
            previous = {}
        until = previous.get("until", 0)
        if (
            isinstance(until, (int, float))
            and time.time() < until <= time.time() + 172800
        ):
            return None
        request = urllib.request.Request(
            ENDPOINT + action,
            data=json.dumps(
                {**payload, "credential_id": credential["credential_id"]},
                separators=(",", ":"),
            ).encode(),
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Authorization": "Bearer " + credential["secret"],
            },
            method="POST",
        )
        try:
            with self.opener(request, timeout=4.0) as response:
                data = response.read(4097)
                if not 200 <= response.status < 300 or len(data) > 4096:
                    return None
            result = json.loads(data)
            if isinstance(result, dict) and result.get("ok") is True:
                write_private_bytes(self.backoff, b"{}")
            return (
                result
                if isinstance(result, dict) and result.get("ok") is True
                else None
            )
        except (OSError, ValueError) as exc:
            if (
                isinstance(exc, urllib.error.HTTPError)
                and action == "events"
                and exc.code in {400, 409}
            ):
                raise RejectedTelemetryEvent(
                    "server rejected telemetry shape or event identity"
                ) from None
            attempt = previous.get("attempt", 0)
            attempt = min(attempt + 1, 8) if type(attempt) is int else 1
            delay = min(30 * 2**attempt, 3600)
            if isinstance(exc, urllib.error.HTTPError):
                if exc.code in {401, 409}:
                    delay = 86400
                retry = exc.headers.get("Retry-After", "") if exc.headers else ""
                if retry.isdigit():
                    delay = max(delay, min(int(retry), 86400))
            try:
                write_private_bytes(
                    self.backoff,
                    json.dumps(
                        {
                            "attempt": attempt,
                            "until": time.time() + delay + secrets.randbelow(30),
                        }
                    ).encode(),
                )
            except OSError:
                pass
            return None

    def first_launch(self, app_version: str, platform: str) -> bool:
        if not telemetry_collection_allowed():
            return False
        try:
            credential = self._credential()
            if self.launch_confirmed(app_version):
                return True
            install_id = load_or_create_installation_state(
                self.path.parent / "installation.json"
            ).install_id
            enrolled = self._post(
                "enroll",
                {
                    "app_version": app_version,
                    "platform": platform,
                    "schema_version": 1,
                    "install_id": install_id,
                },
                credential,
            )
            if not enrolled or enrolled.get("enrolled") is not True:
                return False
            launched = self._post("launch", {"app_version": app_version}, credential)
            if (
                not launched
                or launched.get("launched") is not True
                or launched.get("credential_id") != credential["credential_id"]
                or launched.get("install_id") != install_id
                or launched.get("app_version") != app_version
            ):
                return False
            write_private_bytes(
                self.receipt,
                json.dumps(
                    {
                        "credential_id": credential["credential_id"],
                        "app_version": app_version,
                        "install_id": install_id,
                    }
                ).encode(),
            )
            return self.launch_confirmed(app_version)
        except (OSError, ValueError, KeyError, TypeError):
            return False

    def event(self, payload: dict[str, Any]) -> bool:
        if not telemetry_collection_allowed():
            return False
        if not self.first_launch(__version__, str(payload["platform"])):
            return False
        try:
            # Legacy UUID remains only in the local outbox/HeyCatch contract.
            event = {
                key: value for key, value in payload.items() if key != "install_id"
            }
            result = self._post("events", {"events": [event]}, self._credential())
            return bool(result and result.get("accepted") == 1)
        except (OSError, ValueError, KeyError, TypeError):
            return False

    def cloud_event(
        self, action: str, install_id: str, app_version: str, platform: str
    ) -> bool:
        if (
            action not in {"cloud_seen", "cloud_click"}
            or not telemetry_collection_allowed()
        ):
            return False
        if not self.first_launch(app_version, platform):
            return False
        try:
            local = load_or_create_installation_state(
                self.path.parent / "installation.json"
            )
            if local.install_id != install_id:
                return False
            result = self._post(action, {}, self._credential())
            return bool(result and result.get("recorded") is True)
        except (OSError, ValueError, KeyError, TypeError):
            return False
