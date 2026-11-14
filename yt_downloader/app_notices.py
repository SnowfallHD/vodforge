"""Short messages published on getvodforge.com and shown once each in the app.

The notices are edited in the website repository (src/data/app-notices.json)
and deployed with the site, so a message can reach installed apps without an
app update. The request carries no installation ID or other identifier; the
list of notices already shown stays in the local settings.

The limits here match the website's validator. A notice the app doesn't
accept is skipped rather than shown in part.
"""

from __future__ import annotations

import json
import re
import sys
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .telemetry_transport import telemetry_urlopen

NOTICES_URL = "https://getvodforge.com/api/notices"
MAX_RESPONSE_BYTES = 64 * 1024
MAX_NOTICES = 10
MAX_SEEN = 100
TITLE_LIMIT = 80
BODY_LIMIT = 400
LABEL_LIMIT = 24
URL_LIMIT = 300
_ID = re.compile(r"[a-z0-9][a-z0-9-]{2,63}")
_VERSION = re.compile(r"(\d+)\.(\d+)\.(\d+)")
_FIELDS = frozenset(
    {
        "id",
        "title",
        "body",
        "link",
        "platforms",
        "below_version",
        "min_version",
        "starts_at",
        "ends_at",
    }
)


@dataclass(frozen=True)
class AppNotice:
    id: str
    title: str
    body: str
    link_label: str = ""
    link_url: str = ""
    platforms: tuple[str, ...] = ()
    below_version: tuple[int, int, int] | None = None
    min_version: tuple[int, int, int] | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None


def _text(value: Any, limit: int) -> str | None:
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        return None
    return value if value == value.strip() else None


def _version(value: Any) -> tuple[int, int, int] | None:
    if not isinstance(value, str):
        return None
    match = _VERSION.fullmatch(value)
    if match is None:
        return None
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def _time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.endswith("Z"):
        return None
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _link(value: Any) -> tuple[str, str] | None:
    if not isinstance(value, dict) or set(value) - {"label", "url"}:
        return None
    label = _text(value.get("label"), LABEL_LIMIT)
    url = value.get("url")
    if label is None or not isinstance(url, str) or len(url) > URL_LIMIT:
        return None
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username:
        return None
    return label, url


def parse_notice(value: Any) -> AppNotice | None:
    """One notice, or None when any part of it is invalid."""
    if not isinstance(value, dict) or set(value) - _FIELDS:
        return None
    notice_id = value.get("id")
    title = _text(value.get("title"), TITLE_LIMIT)
    body = _text(value.get("body"), BODY_LIMIT)
    if not isinstance(notice_id, str) or not _ID.fullmatch(notice_id):
        return None
    if title is None or body is None:
        return None
    link = ("", "")
    if "link" in value:
        parsed_link = _link(value["link"])
        if parsed_link is None:
            return None
        link = parsed_link
    platforms: tuple[str, ...] = ()
    if "platforms" in value:
        raw = value["platforms"]
        if (
            not isinstance(raw, list)
            or not raw
            or any(p not in {"windows", "macos"} for p in raw)
        ):
            return None
        platforms = tuple(raw)
    versions = {}
    for key in ("below_version", "min_version"):
        if key in value:
            versions[key] = _version(value[key])
            if versions[key] is None:
                return None
    times = {}
    for key in ("starts_at", "ends_at"):
        if key in value:
            times[key] = _time(value[key])
            if times[key] is None:
                return None
    starts, ends = times.get("starts_at"), times.get("ends_at")
    if starts is not None and ends is not None and starts >= ends:
        return None
    return AppNotice(
        id=notice_id,
        title=title,
        body=body,
        link_label=link[0],
        link_url=link[1],
        platforms=platforms,
        below_version=versions.get("below_version"),
        min_version=versions.get("min_version"),
        starts_at=starts,
        ends_at=ends,
    )


def parse_notices(payload: Any) -> list[AppNotice]:
    if not isinstance(payload, dict) or payload.get("version") != 1:
        return []
    raw = payload.get("notices")
    if not isinstance(raw, list):
        return []
    notices: list[AppNotice] = []
    for value in raw[:MAX_NOTICES]:
        notice = parse_notice(value)
        if notice is not None and all(n.id != notice.id for n in notices):
            notices.append(notice)
    return notices


def fetch_notices(
    *, opener: Callable[..., Any] = telemetry_urlopen, timeout: float = 10
) -> list[AppNotice]:
    """The published notices; an empty list when they can't be read."""
    request = urllib.request.Request(
        NOTICES_URL, headers={"Accept": "application/json"}
    )
    try:
        with opener(request, timeout=timeout) as response:
            status = int(getattr(response, "status", 200))
            raw = response.read(MAX_RESPONSE_BYTES + 1)
        if not 200 <= status < 300 or len(raw) > MAX_RESPONSE_BYTES:
            return []
        return parse_notices(json.loads(raw.decode("utf-8")))
    except (OSError, UnicodeError, ValueError):
        return []


def current_platform() -> str:
    return "macos" if sys.platform == "darwin" else "windows"


def next_notice(
    notices: Sequence[AppNotice],
    *,
    version: str,
    platform: str,
    seen: Iterable[str],
    now: datetime | None = None,
) -> AppNotice | None:
    """The first notice this app hasn't shown that applies to it now."""
    now = now or datetime.now(timezone.utc)
    shown = set(seen)
    app_version = _version(version.split("-", 1)[0])
    for notice in notices:
        if notice.id in shown:
            continue
        if notice.platforms and platform not in notice.platforms:
            continue
        if notice.starts_at is not None and now < notice.starts_at:
            continue
        if notice.ends_at is not None and now >= notice.ends_at:
            continue
        if notice.below_version is not None or notice.min_version is not None:
            if app_version is None:
                continue  # development builds without a version see none
            if notice.below_version is not None and app_version >= notice.below_version:
                continue
            if notice.min_version is not None and app_version < notice.min_version:
                continue
        return notice
    return None


def remember_seen(seen: Any, notice_id: str) -> list[str]:
    """The settings value after a notice was shown, newest last, bounded."""
    current: list[str] = []
    for value in seen if isinstance(seen, list) else []:
        if (
            isinstance(value, str)
            and _ID.fullmatch(value)
            and value != notice_id
            and value not in current
        ):
            current.append(value)
    return [*current, notice_id][-MAX_SEEN:]
