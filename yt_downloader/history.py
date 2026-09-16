from __future__ import annotations

import hashlib
import json
import math
import ntpath
import os
import re
import stat
import sys
import urllib.parse
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, cast

from .archive_paths import ArchivePath

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
RETRY_JOB_METADATA_KEY = "vodforge_retry_job"

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
    "chapters",
    "heatmap",
    "thumbnail",
    "best_thumbnail",
    "playlist_title",
    "playlist_id",
    "playlist_index",
    "vodforge_output_type",
    "vodforge_encoding_summary",
    "vodforge_output_path",
    "vodforge_attempt_signature",
    "vodforge_output_variant",
    "vodforge_output_profile",
    "vodforge_output_profile_details",
    "vodforge_run_id",
    "vodforge_run_activity",
    "vodforge_archive_id",
    "vodforge_archive_annotation_owner",
    "vodforge_relinked",
    RETRY_JOB_METADATA_KEY,
)

MAX_CHAPTERS = 500
MAX_HEATMAP_POINTS = 5000


def _finite_nonnegative(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) and number >= 0 else None


def sanitize_chapters(value: Any) -> list[dict[str, Any]]:
    """Retain bounded, display-only chapter timing from provider metadata."""

    if not isinstance(value, list):
        return []
    result: list[dict[str, Any]] = []
    for raw in value:
        if not isinstance(raw, dict):
            continue
        start = _finite_nonnegative(raw.get("start_time"))
        end = _finite_nonnegative(raw.get("end_time"))
        title = str(raw.get("title") or "").strip()[:300]
        if start is None or end is None or end < start:
            continue
        result.append({"start_time": start, "end_time": end, "title": title})
        if len(result) >= MAX_CHAPTERS:
            break
    return result


def sanitize_heatmap(value: Any) -> list[dict[str, float]]:
    """Retain bounded YouTube engagement samples without provider URLs."""

    if not isinstance(value, list):
        return []
    result: list[dict[str, float]] = []
    for raw in value:
        if not isinstance(raw, dict):
            continue
        start = _finite_nonnegative(raw.get("start_time"))
        end = _finite_nonnegative(raw.get("end_time"))
        raw_value = raw.get("value")
        if raw_value is None:
            continue
        try:
            value_number = float(raw_value)
        except (TypeError, ValueError, OverflowError):
            continue
        if (
            start is None
            or end is None
            or end < start
            or not math.isfinite(value_number)
        ):
            continue
        result.append(
            {
                "start_time": start,
                "end_time": end,
                "value": min(1.0, max(0.0, value_number)),
            }
        )
        if len(result) >= MAX_HEATMAP_POINTS:
            break
    return result


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
    from .telemetry_policy import preview_telemetry_allowed

    if preview_telemetry_allowed():
        return Path(os.environ["VODFORGE_QA_PROFILE"])
    platform_name = sys.platform if platform_name is None else platform_name
    home = Path.home() if home is None else home
    if platform_name.startswith("win"):
        base = (
            local_app_data
            if local_app_data is not None
            else os.environ.get("LOCALAPPDATA")
        )
        if base:
            return Path(base) / APP_NAME
        return home / "AppData" / "Local" / APP_NAME
    if platform_name == "darwin":
        return home / "Library" / "Application Support" / APP_NAME
    base = (
        xdg_data_home if xdg_data_home is not None else os.environ.get("XDG_DATA_HOME")
    )
    return (
        Path(base).expanduser() if base else home / ".local" / "share"
    ) / APP_NAME.lower()


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
    if (
        not text
        or len(text) > 128
        or any(
            character
            not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
            for character in text
        )
    ):
        return ""
    return text


def sanitize_durable_url(value: Any, *, preserve_youtube_context: bool) -> str | None:
    """Retain useful URL identity without credentials, fragments, or untrusted query data."""
    text = str(value or "").strip()
    if (
        not text
        or len(text) > 8192
        or any(ord(character) < 32 or ord(character) == 127 for character in text)
    ):
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
    if preserve_youtube_context and youtube_host in {
        "youtube.com",
        "m.youtube.com",
        "youtu.be",
    }:
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
            return "https://www.youtube.com/watch?" + urllib.parse.urlencode(
                canonical_query
            )
        if playlist_id:
            return "https://www.youtube.com/playlist?" + urllib.parse.urlencode(
                {"list": playlist_id}
            )

    safe_host = parsed.hostname
    if ":" in safe_host and not safe_host.startswith("["):
        safe_host = f"[{safe_host}]"
    default_port = (scheme == "http" and port == 80) or (
        scheme == "https" and port == 443
    )
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
        if (
            isinstance(metric, (int, float))
            and not isinstance(metric, bool)
            and metric >= 0
        ):
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


def _stored_artifact_path(record: dict[str, Any]) -> ArchivePath | None:
    value = str(record.get("vodforge_output_path") or "").strip()
    if not value:
        summary = record.get("vodforge_encoding_summary")
        if isinstance(summary, dict):
            output = summary.get("output")
            if isinstance(output, dict):
                value = str(output.get("Output file path") or "").strip()
    try:
        candidate = ArchivePath.parse(value)
        directory = str(record.get("vodforge_output_dir") or "").strip()
        if directory and candidate.parent.key != ArchivePath.parse(directory).key:
            return None
        return candidate
    except ValueError:
        return None


def history_output_path(record: dict[str, Any]) -> Path | None:
    """Return a native exact path without filesystem access or foreign coercion."""
    candidate = _stored_artifact_path(record)
    if candidate is None or (candidate.style == "windows") != (os.name == "nt"):
        return None
    return Path(str(candidate))


def history_output_type(record: dict[str, Any]) -> str:
    raw = str(record.get("vodforge_output_type") or "").strip().upper()
    if raw == "ORIGINAL AUDIO":
        return "Original audio"
    if raw in {"MP4", "MP3"}:
        return raw
    summary = record.get("vodforge_encoding_summary")
    if not isinstance(summary, dict):
        summary = {}
    output = summary.get("output")
    if not isinstance(output, dict):
        output = {}
    output_path = str(output.get("Output file path") or "").strip().lower()
    container = str(output.get("Output container") or "").strip().lower()
    return "MP3" if output_path.endswith(".mp3") or container == "mp3" else "MP4"


def history_identity(record: dict[str, Any]) -> tuple[str, str, str]:
    video_id = str(record.get("id") or "").strip()
    location = _stored_artifact_path(record)
    if location is None:
        try:
            location = ArchivePath.parse(str(record.get("vodforge_output_dir") or ""))
        except ValueError:
            location = None
    normalized = str(location) if location else ""
    if location is not None and location.style == "windows":
        normalized = normalized.casefold()
    return (
        video_id or str(record.get("title") or "").strip(),
        normalized,
        history_output_type(record),
    )


def history_archive_owner(record: dict[str, Any]) -> str:
    archive_id = str(record.get("vodforge_archive_id") or "")
    if re.fullmatch(r"[0-9a-f]{64}", archive_id):
        return f"archive:{archive_id}"
    output_path = str(record.get("vodforge_output_path") or "").strip()
    if output_path:
        return f"history-path:{output_path}"
    digest = hashlib.sha256(
        "\0".join(history_identity(record)).encode("utf-8")
    ).hexdigest()[:24]
    return f"history:{digest}"


def history_activity_owner_keys(owners: set[str]) -> set[str]:
    """Exact accepted owners plus their existing stable relink lineage."""
    return owners | {
        "archive:" + hashlib.sha256(owner.encode("utf-8")).hexdigest()
        for owner in owners
    }


def history_annotation_owner(record: dict[str, Any]) -> str:
    preserved = str(record.get("vodforge_archive_annotation_owner") or "")
    if preserved:
        return preserved[:512]
    run_id = str(record.get("vodforge_run_id") or "").strip()
    return f"run:{run_id}" if run_id else history_archive_owner(record)


def history_media_identity(record: dict[str, Any]) -> tuple[str, str, str]:
    """Identify the provider item and playlist context independently of location."""
    video_id = str(record.get("id") or "").strip()
    source = video_id or str(record.get("title") or "").strip()
    playlist_id = str(record.get("playlist_id") or "").strip()
    return source, playlist_id, history_output_type(record)


def _external_storage_root(
    path: Path, *, platform_name: str | None = None
) -> str | None:
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
    try:
        lexical = ArchivePath.parse(str(output_dir))
    except ValueError:
        return HISTORY_MEDIA_UNAVAILABLE
    if (lexical.style == "windows") != (os.name == "nt"):
        return HISTORY_MEDIA_UNAVAILABLE
    output_path = history_output_path(record)
    if output_path is not None:
        try:
            output_stat = output_path.stat()
        except FileNotFoundError:
            storage_root = _external_storage_root(output_path)
            if storage_root and not Path(storage_root).exists():
                return HISTORY_MEDIA_UNAVAILABLE
            return HISTORY_MEDIA_MISSING
        except OSError:
            return HISTORY_MEDIA_UNAVAILABLE
        return (
            HISTORY_MEDIA_PRESENT
            if stat.S_ISREG(output_stat.st_mode) and output_stat.st_size > 0
            else HISTORY_MEDIA_MISSING
        )
    if history_output_type(record) == "Original audio":
        return HISTORY_MEDIA_MISSING  # New audio records require their exact committed path.
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
        elif key == "chapters":
            value = sanitize_chapters(value)
        elif key == "heatmap":
            value = sanitize_heatmap(value)
        elif key == "description":
            value = str(value or "")[:MAX_DESCRIPTION_CHARS]
        elif key == "vodforge_run_activity":
            value = sanitize_run_activity(value)
        elif key == "vodforge_run_id":
            value = str(value or "").strip()[:128]
        elif key == RETRY_JOB_METADATA_KEY:
            value = _json_safe(dict(value)) if isinstance(value, dict) else None
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

    raw_directory = str(output_dir)
    try:
        directory = ArchivePath.parse(raw_directory)
    except ValueError:
        directory = ArchivePath.parse(
            os.path.abspath(os.path.expanduser(raw_directory))
        )
    record["vodforge_output_dir"] = str(directory)
    record["vodforge_output_type"] = history_output_type(record or info)
    exact_output = _stored_artifact_path(record)
    if exact_output is not None:
        record["vodforge_output_path"] = str(exact_output)
    else:
        record.pop("vodforge_output_path", None)
    record["vodforge_recorded_at"] = (
        recorded_at or datetime.now(timezone.utc).isoformat()
    )
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
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        if os.name != "nt":
            temporary.chmod(0o600)
        temporary.replace(path)
    except (OSError, TypeError, ValueError) as exc:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise HistoryError(f"VODForge could not save download history: {exc}") from exc


def _load_history_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        if path.stat().st_size > MAX_HISTORY_FILE_BYTES:
            raise HistoryError(
                "VODForge found an unexpectedly large download-history file."
            )
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HistoryError(f"VODForge could not read download history: {exc}") from exc
    if (
        not isinstance(payload, dict)
        or payload.get("schema_version") != HISTORY_SCHEMA_VERSION
    ):
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


_NAMESPACE_SCAN_LIMIT = 128
_NAMESPACE_PEER_LIMIT = 32
_OBSERVED_MEDIA_SUFFIXES = frozenset(
    {".mp4", ".mp3", ".m4a", ".opus", ".ogg", ".webm", ".mkv", ".mov", ".wav", ".flac"}
)


def _observed_namespace_files(output_path: Path) -> dict[str, str]:
    """Count recognized regular media in one directory, with an explicit cap."""
    count = 0
    state = "complete"
    try:
        if not output_path.is_file():
            return {"namespace_scan_state": "missing"}
        with os.scandir(output_path.parent) as entries:
            for index, entry in enumerate(entries):
                if index == _NAMESPACE_SCAN_LIMIT:
                    state = "capped"
                    break
                if Path(entry.name).suffix.lower() in _OBSERVED_MEDIA_SUFFIXES:
                    if entry.is_symlink():
                        state = "unknown"
                    elif entry.is_file(follow_symlinks=False):
                        count += 1
    except FileNotFoundError:
        return {"namespace_scan_state": "missing"}
    except OSError:
        return {"namespace_scan_state": "unreadable"}
    return {"namespace_scan_state": state, "namespace_media_file_count": str(count)}


def _namespace_source(info: Any) -> tuple[str, str, str] | None:
    if not isinstance(info, dict):
        return None
    signature, identifier = info.get("vodforge_attempt_signature"), info.get("id")
    raw_url = info.get("webpage_url")
    if not all(
        isinstance(value, str) and value for value in (signature, identifier, raw_url)
    ):
        return None
    signature, identifier, raw_url = cast(
        tuple[str, str, str], (signature, identifier, raw_url)
    )
    if not re.fullmatch(r"[0-9a-f]{64}", signature):
        return None
    url = sanitize_durable_url(raw_url, preserve_youtube_context=True)
    return (identifier, url, signature) if url else None


def _namespace_peer_eligibility(record: Any, source: tuple[str, str, str]) -> str:
    if not isinstance(record, dict):
        return "unknown"
    identifier, url, signature = source
    if record.get("id") != identifier:
        return "skip"
    peer_source = _namespace_source(record)
    if peer_source is None:
        return "unknown"
    if peer_source[1] != url or peer_source[2] == signature:
        return "skip"
    return "candidate"


def _compare_namespace_peer(output_path: Path, record: dict[str, Any]) -> str:
    try:
        peer = history_output_path(record)
        if peer is None:
            return "unknown"
        if not peer.is_file() or not output_path.is_file():
            return "missing"
        if output_path.parent.samefile(peer.parent):
            return "shared_directory"
        if output_path.samefile(peer):
            return "shared_artifact"
    except FileNotFoundError:
        return "missing"
    except OSError:
        return "unreadable"
    return "distinct"


def _observed_namespace_peers(
    output_path: Path, info: Any, history: Any
) -> dict[str, str]:
    """Compare only retained same-source other intents; races are not excluded."""
    if info is None:
        return {"peer_namespace_state": "not_applicable"}
    source = _namespace_source(info)
    if source is None or not isinstance(history, (list, tuple)):
        return {"peer_namespace_state": "unknown", "peer_comparison_count": "0"}
    return _observe_retained_peers(output_path, source, history)


def _observe_retained_peers(
    output_path: Path, source: tuple[str, str, str], history: list | tuple
) -> dict[str, str]:
    compared = 0
    candidates = 0
    uncertain: str | None = "capped" if len(history) > MAX_HISTORY_ITEMS else None
    state = "no_comparable"
    for record in history[:MAX_HISTORY_ITEMS]:
        eligibility = _namespace_peer_eligibility(record, source)
        if eligibility != "candidate":
            if eligibility == "unknown":
                uncertain = uncertain or "unknown"
            continue
        candidates += 1
        if candidates > _NAMESPACE_PEER_LIMIT:
            uncertain = "capped"
            break
        result = _compare_namespace_peer(output_path, record)
        if result not in {"distinct", "shared_directory", "shared_artifact"}:
            uncertain = uncertain or result
            continue
        compared += 1
        state = result
        if result != "distinct":
            # A positively observed shared identity remains useful even if some
            # other rows were unavailable or the history scan was capped.
            uncertain = None
            break
    return {
        "peer_namespace_state": uncertain or state,
        "peer_comparison_count": str(compared),
    }


def observed_output_namespace(
    output_path: Path, info: Any = None, history: Any = None
) -> dict[str, str]:
    """Observation only: a malformed row or filesystem race never owns an export."""
    facts = {"namespace_scan_state": "unknown", "peer_namespace_state": "unknown"}
    try:
        facts.update(_observed_namespace_files(output_path))
    except Exception:  # noqa: BLE001, S110  # nosec B110 - optional observation must not control committed media
        pass
    try:
        facts.update(_observed_namespace_peers(output_path, info, history))
    except Exception:  # noqa: BLE001, S110  # nosec B110 - legacy/mutating history cannot break an export
        pass
    return facts


def pending_history_path(path: Path) -> Path:
    """Private recovery journal owned by the same history persistence boundary."""
    return path.with_name(f".{path.name}.pending")


def _read_pending_history(path: Path) -> list[dict[str, Any]]:
    journal = pending_history_path(path)
    try:
        try:
            size = journal.stat().st_size
        except FileNotFoundError:
            return []
        if size > MAX_HISTORY_FILE_BYTES:
            raise HistoryError("Pending history exceeds the supported size.")
        payload = json.loads(journal.read_text(encoding="utf-8"))
        operations = payload["operations"]
        if payload.get("schema_version") != 1 or not isinstance(operations, list):
            raise ValueError("Invalid pending history schema")
        if len(operations) > MAX_HISTORY_ITEMS:
            raise ValueError("Too many pending history operations")
        for operation in operations:
            if not isinstance(operation, dict) or operation.get("kind") not in {
                "record",
                "activity",
            }:
                raise ValueError("Invalid pending history operation")
            if operation["kind"] == "record":
                record = operation.get("record")
                if not isinstance(record, dict) or history_output_dir(record) is None:
                    raise ValueError("Invalid pending history record")
            elif (
                not isinstance(operation.get("owners"), list)
                or len(operation["owners"]) > MAX_HISTORY_ITEMS
                or not all(
                    isinstance(owner, str) and len(owner) <= 16384
                    for owner in operation["owners"]
                )
                or not isinstance(operation.get("activity"), list)
                or not isinstance(operation.get("run_id", ""), str)
                or len(operation.get("run_id", "")) > 512
            ):
                raise ValueError("Invalid pending activity update")
        return operations
    except (OSError, UnicodeError, ValueError, KeyError, TypeError) as exc:
        raise HistoryError(
            "VODForge could not recover pending history updates."
        ) from exc


def _pending_operation_key(operation: dict[str, Any]) -> tuple[Any, ...]:
    if operation["kind"] == "record":
        return ("record", *history_identity(operation["record"]))
    return ("activity", operation.get("run_id", ""), *operation["owners"])


def _stage_history_mutation(path: Path, mutation: dict[str, Any]) -> None:
    """Durably accept a bounded delta before delaying its in-memory callback.

    Only the UI history coordinator writes this journal. The relink worker writes
    the main history file, so the two cannot overwrite one another's snapshots.
    """
    if mutation.get("kind") == "record":
        raw = mutation["record"]
        clean = {
            "kind": "record",
            "record": sanitize_history_record(
                raw,
                raw["vodforge_output_dir"],
                recorded_at=str(raw.get("vodforge_recorded_at") or "") or None,
            ),
        }
    elif mutation.get("kind") == "activity":
        owners = tuple(dict.fromkeys(mutation["owners"]))
        if len(owners) > MAX_HISTORY_ITEMS or not all(
            isinstance(owner, str) and len(owner) <= 16384 for owner in owners
        ):
            raise HistoryError("Pending history owner scope exceeds its limit.")
        clean = {
            "kind": "activity",
            "owners": list(owners),
            "activity": sanitize_run_activity(mutation["activity"]),
            "run_id": str(mutation.get("run_id") or "")[:512],
        }
    else:
        raise HistoryError("Unsupported pending history operation.")
    existing = _read_pending_history(path)
    key = _pending_operation_key(clean)
    operations = [item for item in existing if _pending_operation_key(item) != key]
    operations.append(clean)
    if len(operations) > MAX_HISTORY_ITEMS:
        raise HistoryError("Pending history exceeds its supported operation count.")
    payload = json.dumps(
        {"schema_version": 1, "operations": operations}, ensure_ascii=False
    )
    if len(payload.encode("utf-8")) > MAX_HISTORY_FILE_BYTES:
        raise HistoryError("Pending history exceeds its supported size.")
    journal = pending_history_path(path)
    temporary = journal.with_name(journal.name + ".tmp")
    try:
        journal.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_text(payload, encoding="utf-8")
        if os.name != "nt":
            temporary.chmod(0o600)
        temporary.replace(journal)
    except OSError as exc:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise HistoryError("VODForge could not save pending history updates.") from exc


def recover_pending_history(
    path: Path, current: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], int]:
    """Merge durable deltas with actual history, never an old whole-file snapshot.

    Replay is idempotent across a crash after save but before journal retirement.
    Activity deltas follow a relink's recorded lineage without replacing its path.
    No media filesystem observations or media writes occur here.
    """
    operations = _read_pending_history(path)
    if not operations:
        return current, 0
    result = [dict(record) for record in current]
    for operation in operations:
        if operation["kind"] == "record":
            record = operation["record"]
            result = upsert_history(
                result,
                record,
                record["vodforge_output_dir"],
                recorded_at=record.get("vodforge_recorded_at"),
                replace_missing_media=False,
            )
        else:
            owners = set(operation["owners"])
            run_id = operation.get("run_id", "")
            # Include only records durably accepted in this same journal. A
            # matching run alone cannot claim unrelated existing export variants.
            if run_id:
                owners.update(
                    history_archive_owner(pending["record"])
                    for pending in operations
                    if pending["kind"] == "record"
                    and pending["record"].get("vodforge_run_id") == run_id
                )
            owner_keys = history_activity_owner_keys(owners)
            result = [
                {
                    **record,
                    "vodforge_run_activity": sanitize_run_activity(
                        operation["activity"]
                    ),
                }
                if (
                    history_archive_owner(record) in owner_keys
                    and (
                        not run_id
                        or not record.get("vodforge_run_id")
                        or record.get("vodforge_run_id") == run_id
                    )
                )
                else record
                for record in result
            ]
    save_history(path, result)
    try:
        pending_history_path(path).unlink()
    except OSError as exc:
        # Fail closed before accepting further history edits. Retaining this
        # idempotent journal permits a retry without losing either update.
        raise HistoryError(
            "Pending history was saved but recovery cleanup failed."
        ) from exc
    return result, len(operations)


def load_history(
    path: Path, *, on_recovered: Callable[[int], None] | None = None
) -> list[dict[str, Any]]:
    records, count = recover_pending_history(path, _load_history_records(path))
    if count and on_recovered is not None:
        try:
            on_recovered(count)
        except Exception:  # noqa: BLE001, S110 - optional observation cannot prevent durable recovery
            pass
    return records


def stage_history_mutation(path: Path, mutation: dict[str, Any]) -> None:
    try:
        _stage_history_mutation(path, mutation)
    except (OSError, TypeError, ValueError, KeyError) as exc:
        raise HistoryError("VODForge could not save pending history updates.") from exc
