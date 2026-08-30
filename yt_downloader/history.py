from __future__ import annotations

import json
import ntpath
import os
import re
import stat
import sys
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

APP_NAME = "VODForge"
HISTORY_SCHEMA_VERSION = 1
MAX_HISTORY_ITEMS = 5000
MAX_DESCRIPTION_CHARS = 20_000
MAX_HISTORY_FILE_BYTES = 128 * 1024 * 1024
MAX_RUN_ACTIVITY_LINES = 500
MAX_RUN_ACTIVITY_LINE_CHARS = 2_000
MAX_RUN_ACTIVITY_CHARS = 100_000
HISTORY_MEDIA_PRESENT = "present"
HISTORY_MEDIA_MISSING = "missing"
HISTORY_MEDIA_UNAVAILABLE = "unavailable"

HISTORY_METADATA_KEYS = (
    "id",
    "title",
    "webpage_url",
    "original_url",
    "description",
    "duration",
    "uploader",
    "channel",
    "tags",
    "extra_tags",
    "categories",
    "thumbnail",
    "best_thumbnail",
    "playlist_title",
    "playlist_id",
    "playlist_index",
    "vodforge_output_type",
    "vodforge_encoding_summary",
    "vodforge_run_id",
    "vodforge_run_activity",
)


class HistoryError(RuntimeError):
    """Raised when the local history ledger cannot be read or written safely."""


def application_data_dir(
    *,
    platform_name: str | None = None,
    home: Path | None = None,
    local_app_data: str | None = None,
    xdg_data_home: str | None = None,
) -> Path:
    """Return the conventional per-user application-data directory."""
    platform_name = sys.platform if platform_name is None else platform_name
    home = Path.home() if home is None else home
    if platform_name.startswith("win"):
        base = local_app_data if local_app_data is not None else os.environ.get("LOCALAPPDATA")
        if base:
            return Path(base) / APP_NAME
        return home / "AppData" / "Local" / APP_NAME
    if platform_name == "darwin":
        return home / "Library" / "Application Support" / APP_NAME
    base = xdg_data_home if xdg_data_home is not None else os.environ.get("XDG_DATA_HOME")
    return (Path(base).expanduser() if base else home / ".local" / "share") / APP_NAME.lower()


def history_file_path(**kwargs: Any) -> Path:
    return application_data_dir(**kwargs) / "download-history.json"


def _clean_string_list(value: Any, *, limit: int = 500) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    seen: set[str] = set()
    for item in value:
        text = str(item).strip()
        if not text or text in seen:
            continue
        result.append(text)
        seen.add(text)
        if len(result) >= limit:
            break
    return result


def _json_safe(value: Any) -> Any:
    try:
        encoded = json.dumps(value)
    except (TypeError, ValueError):
        return None
    if len(encoded.encode("utf-8")) > 200_000:
        return None
    return value


def _safe_url_identifier(value: Any) -> str:
    text = str(value or "").strip()
    if not text or len(text) > 128 or any(character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for character in text):
        return ""
    return text


def sanitize_durable_url(value: Any, *, preserve_youtube_context: bool) -> str | None:
    """Retain useful URL identity without credentials, fragments, or untrusted query data."""
    text = str(value or "").strip()
    if not text or len(text) > 8192 or any(ord(character) < 32 or ord(character) == 127 for character in text):
        return None
    try:
        parsed = urllib.parse.urlsplit(text)
        port = parsed.port
    except ValueError:
        return None
    scheme = parsed.scheme.casefold()
    if scheme not in {"http", "https"} or not parsed.hostname:
        return None

    hostname = parsed.hostname.casefold()
    youtube_host = hostname.removeprefix("www.")
    if preserve_youtube_context and youtube_host in {"youtube.com", "m.youtube.com", "youtu.be"}:
        query = urllib.parse.parse_qs(parsed.query)
        video_id = ""
        if youtube_host == "youtu.be":
            video_id = _safe_url_identifier(parsed.path.strip("/").split("/", 1)[0])
        else:
            video_id = _safe_url_identifier((query.get("v") or [""])[0])
        playlist_id = _safe_url_identifier((query.get("list") or [""])[0])
        if video_id:
            canonical_query = {"v": video_id}
            if playlist_id:
                canonical_query["list"] = playlist_id
            return "https://www.youtube.com/watch?" + urllib.parse.urlencode(canonical_query)
        if playlist_id:
            return "https://www.youtube.com/playlist?" + urllib.parse.urlencode({"list": playlist_id})

    safe_host = parsed.hostname
    if ":" in safe_host and not safe_host.startswith("["):
        safe_host = f"[{safe_host}]"
    default_port = (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
    netloc = safe_host if port is None or default_port else f"{safe_host}:{port}"
    return urllib.parse.urlunsplit((parsed.scheme, netloc, parsed.path or "/", "", ""))


_DURABLE_URL_PATTERN = re.compile(r"https?://[^\s<>'\"]+", re.IGNORECASE)
_TRAILING_URL_PUNCTUATION = ".,;:!?)]}"


def sanitize_durable_text(value: Any) -> str:
    """Sanitize every embedded HTTP(S) URL while preserving surrounding diagnostic text."""
    text = str(value or "")

    def replace_url(match: re.Match[str]) -> str:
        candidate = match.group(0)
        trailing = ""
        while candidate and candidate[-1] in _TRAILING_URL_PUNCTUATION:
            trailing = candidate[-1] + trailing
            candidate = candidate[:-1]
        safe = sanitize_durable_url(candidate, preserve_youtube_context=True)
        return (safe or "[redacted invalid URL]") + trailing

    return _DURABLE_URL_PATTERN.sub(replace_url, text)


def sanitize_durable_thumbnail_record(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    url = sanitize_durable_url(value.get("url"), preserve_youtube_context=False)
    if not url:
        return None
    result: dict[str, Any] = {"url": url}
    for key in ("width", "height", "filesize", "filesize_approx"):
        metric = value.get(key)
        if isinstance(metric, (int, float)) and not isinstance(metric, bool) and metric >= 0:
            result[key] = metric
    return result


def sanitize_run_activity(value: Any) -> list[str]:
    """Bound app-owned, user-visible run activity before durable storage."""
    if not isinstance(value, list):
        return []
    result: list[str] = []
    total_chars = 0
    for item in value:
        line = str(item).replace("\x00", "").replace("\r", "").rstrip()
        if not line:
            continue
        line = sanitize_durable_text(line)
        line = line[:MAX_RUN_ACTIVITY_LINE_CHARS]
        remaining = MAX_RUN_ACTIVITY_CHARS - total_chars
        if remaining <= 0:
            break
        line = line[:remaining]
        if not line:
            break
        result.append(line)
        total_chars += len(line)
        if len(result) >= MAX_RUN_ACTIVITY_LINES:
            break
    return result


def history_output_dir(record: dict[str, Any]) -> Path | None:
    value = str(record.get("vodforge_output_dir") or "").strip()
    return Path(value).expanduser() if value else None


def history_output_type(record: dict[str, Any]) -> str:
    raw = str(record.get("vodforge_output_type") or "").strip().upper()
    if raw in {"MP4", "MP3"}:
        return raw
    summary = record.get("vodforge_encoding_summary") if isinstance(record.get("vodforge_encoding_summary"), dict) else {}
    output = summary.get("output") if isinstance(summary.get("output"), dict) else {}
    output_path = str(output.get("Output file path") or "").strip().lower()
    container = str(output.get("Output container") or "").strip().lower()
    return "MP3" if output_path.endswith(".mp3") or container == "mp3" else "MP4"


def history_identity(record: dict[str, Any]) -> tuple[str, str, str]:
    video_id = str(record.get("id") or "").strip()
    output_dir = history_output_dir(record)
    normalized_dir = os.path.normcase(os.path.abspath(str(output_dir))) if output_dir else ""
    if video_id:
        return video_id, normalized_dir, history_output_type(record)
    return str(record.get("title") or "").strip(), normalized_dir, history_output_type(record)


def history_media_identity(record: dict[str, Any]) -> tuple[str, str, str]:
    """Identify the provider item and playlist context independently of location."""
    video_id = str(record.get("id") or "").strip()
    source = video_id or str(record.get("title") or "").strip()
    playlist_id = str(record.get("playlist_id") or "").strip()
    return source, playlist_id, history_output_type(record)


def _external_storage_root(path: Path, *, platform_name: str | None = None) -> str | None:
    """Return a removable/network storage root whose absence is inconclusive."""
    platform_name = sys.platform if platform_name is None else platform_name
    raw_path = str(path)
    if platform_name.startswith("win"):
        windows_path = PureWindowsPath(raw_path)
        drive, _tail = ntpath.splitdrive(raw_path)
        if drive:
            return windows_path.anchor or f"{drive}\\"
        return None

    parts = PurePosixPath(raw_path).parts
    if platform_name == "darwin" and len(parts) >= 3 and parts[:2] == ("/", "Volumes"):
        return str(PurePosixPath(*parts[:3]))
    if platform_name.startswith("linux"):
        if len(parts) >= 3 and parts[:2] in {("/", "mnt"), ("/", "media")}:
            return str(PurePosixPath(*parts[:3]))
        if len(parts) >= 4 and parts[:3] == ("/", "run", "media"):
            return str(PurePosixPath(*parts[:4]))
    return None


def history_media_file_state(record: dict[str, Any]) -> str:
    """Return present, missing, or unavailable for a recorded media artifact."""
    output_dir = history_output_dir(record)
    if output_dir is None:
        return HISTORY_MEDIA_MISSING
    extension = ".mp3" if history_output_type(record) == "MP3" else ".mp4"
    try:
        directory_stat = output_dir.stat()
    except FileNotFoundError:
        storage_root = _external_storage_root(output_dir)
        if storage_root and not Path(storage_root).exists():
            return HISTORY_MEDIA_UNAVAILABLE
        return HISTORY_MEDIA_MISSING
    except OSError:
        return HISTORY_MEDIA_UNAVAILABLE
    if not stat.S_ISDIR(directory_stat.st_mode):
        return HISTORY_MEDIA_MISSING

    try:
        for path in output_dir.iterdir():
            if path.suffix.casefold() != extension:
                continue
            try:
                if path.is_file() and path.stat().st_size > 0:
                    return HISTORY_MEDIA_PRESENT
            except FileNotFoundError:
                continue
            except OSError:
                return HISTORY_MEDIA_UNAVAILABLE
    except OSError:
        return HISTORY_MEDIA_UNAVAILABLE
    return HISTORY_MEDIA_MISSING


def history_media_file_exists(record: dict[str, Any]) -> bool:
    """Return whether a recorded item folder still contains its media artifact."""
    return history_media_file_state(record) == HISTORY_MEDIA_PRESENT


def sanitize_history_record(
    info: dict[str, Any],
    output_dir: Path | str,
    *,
    recorded_at: str | None = None,
) -> dict[str, Any]:
    """Keep only metadata needed by the browser and the exact saved location."""
    record: dict[str, Any] = {}
    for key in HISTORY_METADATA_KEYS:
        value = info.get(key)
        if key in {"tags", "extra_tags", "categories"}:
            value = _clean_string_list(value)
        elif key == "description":
            value = str(value or "")[:MAX_DESCRIPTION_CHARS]
        elif key == "vodforge_run_activity":
            value = sanitize_run_activity(value)
        elif key == "vodforge_run_id":
            value = str(value or "").strip()[:128]
        elif key in {"webpage_url", "original_url"}:
            value = sanitize_durable_url(value, preserve_youtube_context=True)
        elif key == "thumbnail":
            value = sanitize_durable_url(value, preserve_youtube_context=False)
        elif key == "best_thumbnail":
            value = sanitize_durable_thumbnail_record(value)
        else:
            value = _json_safe(value)
        if value not in (None, "", [], {}):
            record[key] = value

    path = Path(output_dir).expanduser()
    try:
        path = path.resolve(strict=False)
    except OSError:
        path = Path(os.path.abspath(str(path)))
    record["vodforge_output_dir"] = str(path)
    record["vodforge_output_type"] = history_output_type(record or info)
    record["vodforge_recorded_at"] = recorded_at or datetime.now(timezone.utc).isoformat()
    return record


def upsert_history(
    existing: list[dict[str, Any]],
    info: dict[str, Any],
    output_dir: Path | str,
    *,
    recorded_at: str | None = None,
    replace_missing_media: bool = False,
) -> list[dict[str, Any]]:
    record = sanitize_history_record(info, output_dir, recorded_at=recorded_at)
    identity = history_identity(record)
    media_identity = history_media_identity(record)
    remaining = [
        item
        for item in existing
        if history_identity(item) != identity
        and not (
            replace_missing_media
            and history_media_identity(item) == media_identity
            and history_media_file_state(item) == HISTORY_MEDIA_MISSING
        )
    ]
    return [record, *remaining][:MAX_HISTORY_ITEMS]


def save_history(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": HISTORY_SCHEMA_VERSION,
        "items": records[:MAX_HISTORY_ITEMS],
    }
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if os.name != "nt":
            temporary.chmod(0o600)
        temporary.replace(path)
    except (OSError, TypeError, ValueError) as exc:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise HistoryError(f"VODForge could not save download history: {exc}") from exc


def load_history(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        if path.stat().st_size > MAX_HISTORY_FILE_BYTES:
            raise HistoryError("VODForge found an unexpectedly large download-history file.")
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HistoryError(f"VODForge could not read download history: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != HISTORY_SCHEMA_VERSION:
        raise HistoryError("VODForge found an unsupported download-history file.")
    raw_items = payload.get("items")
    if not isinstance(raw_items, list):
        raise HistoryError("VODForge found an invalid download-history file.")

    records: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        output_dir = history_output_dir(item)
        if output_dir is None:
            continue
        record = sanitize_history_record(
            item,
            output_dir,
            recorded_at=str(item.get("vodforge_recorded_at") or "").strip() or None,
        )
        identity = history_identity(record)
        if identity in seen:
            continue
        records.append(record)
        seen.add(identity)
        if len(records) >= MAX_HISTORY_ITEMS:
            break
    return records
