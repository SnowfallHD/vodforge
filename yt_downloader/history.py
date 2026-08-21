from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


APP_NAME = "VODForge"
HISTORY_SCHEMA_VERSION = 1
MAX_HISTORY_ITEMS = 5000
MAX_DESCRIPTION_CHARS = 20_000
MAX_HISTORY_FILE_BYTES = 128 * 1024 * 1024

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
    "vodforge_encoding_summary",
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


def history_output_dir(record: dict[str, Any]) -> Path | None:
    value = str(record.get("vodforge_output_dir") or "").strip()
    return Path(value).expanduser() if value else None


def history_identity(record: dict[str, Any]) -> tuple[str, str]:
    video_id = str(record.get("id") or "").strip()
    output_dir = history_output_dir(record)
    normalized_dir = os.path.normcase(os.path.abspath(str(output_dir))) if output_dir else ""
    if video_id:
        return video_id, normalized_dir
    return str(record.get("title") or "").strip(), normalized_dir


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
    record["vodforge_recorded_at"] = recorded_at or datetime.now(timezone.utc).isoformat()
    return record


def upsert_history(
    existing: list[dict[str, Any]],
    info: dict[str, Any],
    output_dir: Path | str,
    *,
    recorded_at: str | None = None,
) -> list[dict[str, Any]]:
    record = sanitize_history_record(info, output_dir, recorded_at=recorded_at)
    identity = history_identity(record)
    remaining = [item for item in existing if history_identity(item) != identity]
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
    seen: set[tuple[str, str]] = set()
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
