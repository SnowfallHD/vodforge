from __future__ import annotations

import json
import os
import sys
import time
import urllib.parse
import urllib.request
import uuid
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from .history import application_data_dir

CLOUD_ORIGIN = "https://getvodforge.com"
CLOUD_PAGE_URL = f"{CLOUD_ORIGIN}/cloud"
CLOUD_LAUNCH_ENDPOINT = f"{CLOUD_ORIGIN}/api/funnel/launch"
CLOUD_SEEN_ENDPOINT = f"{CLOUD_ORIGIN}/api/funnel/seen"
CLOUD_CLICK_ENDPOINT = f"{CLOUD_ORIGIN}/api/funnel/click"
INSTALLATION_STATE_SCHEMA_VERSION = 1
INSTALLATION_STATE_FILENAME = "installation.json"
MAX_STATE_FILE_BYTES = 4096
NETWORK_TIMEOUT_SECONDS = 4.0


class InstallationIdentityError(RuntimeError):
    """Raised when the anonymous local installation state cannot be used safely."""


@dataclass(frozen=True)
class InstallationState:
    install_id: str
    first_launch_confirmed: bool = False
    cloud_seen_confirmed: bool = False


def installation_state_path(*, data_dir: Path | None = None, **kwargs: Any) -> Path:
    return (
        data_dir if data_dir is not None else application_data_dir(**kwargs)
    ) / INSTALLATION_STATE_FILENAME


def _parse_install_id(value: Any) -> str:
    try:
        parsed = uuid.UUID(str(value).strip())
    except (AttributeError, TypeError, ValueError) as exc:
        raise InstallationIdentityError("installation ID is not a valid UUID") from exc
    if parsed.version != 4:
        raise InstallationIdentityError("installation ID must be a random UUID4")
    return str(parsed)


def _read_state(path: Path) -> InstallationState:
    try:
        if path.stat().st_size > MAX_STATE_FILE_BYTES:
            raise InstallationIdentityError("installation state is unexpectedly large")
        payload = json.loads(path.read_text(encoding="utf-8"))
    except InstallationIdentityError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise InstallationIdentityError(
            f"could not read installation state: {exc}"
        ) from exc
    if (
        not isinstance(payload, dict)
        or payload.get("schema_version") != INSTALLATION_STATE_SCHEMA_VERSION
    ):
        raise InstallationIdentityError("installation state has an unsupported schema")
    return InstallationState(
        install_id=_parse_install_id(payload.get("install_id")),
        first_launch_confirmed=payload.get("first_launch_confirmed") is True,
        cloud_seen_confirmed=payload.get("cloud_seen_confirmed") is True,
    )


def _encoded_state(state: InstallationState) -> bytes:
    return (
        json.dumps(
            {
                "schema_version": INSTALLATION_STATE_SCHEMA_VERSION,
                "install_id": state.install_id,
                "first_launch_confirmed": state.first_launch_confirmed,
                "cloud_seen_confirmed": state.cloud_seen_confirmed,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def _create_state_exclusively(path: Path, state: InstallationState) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return False
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(_encoded_state(state))
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    return True


def _replace_state(path: Path, state: InstallationState) -> None:
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(_encoded_state(state))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


def load_or_create_installation_state(path: Path | None = None) -> InstallationState:
    destination = path if path is not None else installation_state_path()
    if destination.exists():
        return _read_state(destination)

    candidate = InstallationState(install_id=str(uuid.uuid4()))
    if _create_state_exclusively(destination, candidate):
        return candidate

    # A second app process may still be finishing its exclusive first write.
    last_error: InstallationIdentityError | None = None
    for _attempt in range(5):
        try:
            return _read_state(destination)
        except InstallationIdentityError as exc:
            last_error = exc
            time.sleep(0.02)
    raise last_error or InstallationIdentityError("could not load installation state")


def mark_cloud_seen_confirmed(path: Path, install_id: str) -> InstallationState:
    state = _read_state(path)
    normalized = _parse_install_id(install_id)
    if state.install_id != normalized:
        raise InstallationIdentityError(
            "installation ID changed while recording Cloud state"
        )
    if state.cloud_seen_confirmed:
        return state
    updated = replace(state, cloud_seen_confirmed=True)
    _replace_state(path, updated)
    return updated


def mark_first_launch_confirmed(path: Path, install_id: str) -> InstallationState:
    state = _read_state(path)
    normalized = _parse_install_id(install_id)
    if state.install_id != normalized:
        raise InstallationIdentityError(
            "installation ID changed while recording first launch"
        )
    if state.first_launch_confirmed:
        return state
    updated = replace(state, first_launch_confirmed=True)
    _replace_state(path, updated)
    return updated


def installation_platform(platform_name: str | None = None) -> str:
    value = sys.platform if platform_name is None else platform_name
    if value == "darwin":
        return "macos"
    if value.startswith("win"):
        return "windows"
    if value.startswith("linux"):
        return "linux"
    return "unknown"


def cloud_page_url(install_id: str | None) -> str:
    if not install_id:
        return CLOUD_PAGE_URL
    return f"{CLOUD_PAGE_URL}?{urllib.parse.urlencode({'iid': _parse_install_id(install_id)})}"


def _post_json(
    url: str,
    payload: dict[str, str],
    *,
    opener: Callable[..., Any] = urllib.request.urlopen,
    timeout_seconds: float = NETWORK_TIMEOUT_SECONDS,
) -> bool:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "VODForge-Cloud-Funnel/1",
        },
        method="POST",
    )
    try:
        with opener(request, timeout=timeout_seconds) as response:
            status = int(getattr(response, "status", 200))
            body = response.read(4097)
        if status < 200 or status >= 300 or len(body) > 4096:
            return False
        result = json.loads(body.decode("utf-8"))
        return isinstance(result, dict) and result.get("ok") is True
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError):
        return False


def record_cloud_seen(
    state: InstallationState,
    *,
    app_version: str,
    platform_name: str | None = None,
    opener: Callable[..., Any] = urllib.request.urlopen,
) -> bool:
    return _post_json(
        CLOUD_SEEN_ENDPOINT,
        {
            "install_id": state.install_id,
            "platform": installation_platform(platform_name),
            "app_version": str(app_version),
        },
        opener=opener,
    )


def record_first_launch(
    state: InstallationState,
    *,
    app_version: str,
    platform_name: str | None = None,
    opener: Callable[..., Any] = urllib.request.urlopen,
) -> bool:
    return _post_json(
        CLOUD_LAUNCH_ENDPOINT,
        {
            "install_id": state.install_id,
            "platform": installation_platform(platform_name),
            "app_version": str(app_version),
        },
        opener=opener,
    )


def record_cloud_click(
    state: InstallationState,
    *,
    opener: Callable[..., Any] = urllib.request.urlopen,
) -> bool:
    return _post_json(
        CLOUD_CLICK_ENDPOINT,
        {"install_id": state.install_id},
        opener=opener,
    )
