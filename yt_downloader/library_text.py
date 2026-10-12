"""Canonical Library text values, independent of presentation widgets."""

from typing import Any

from .download_service import best_thumbnail

COPY_ACTIONS = {
    "description": "source_description_copied",
    "source_description": "source_description_copied",
    "source_tags": "source_tags_copied",
    "tags": "personal_tags_copied",
    "note": "personal_note_copied",
    "thumbnail_url": "thumbnail_url_copied",
}


def library_tag_values(row: dict[str, Any], field: str = "tags") -> list[str]:
    keys = (
        ("tags",)
        if field == "source_tags"
        else ("vodforge_user_tags",)
        if field == "user_tags"
        else ("tags", "vodforge_user_tags")
    )
    result: list[str] = []
    seen: set[str] = set()
    for key in keys:
        values = row.get(key) or ()
        if not isinstance(values, (list, tuple)):
            continue
        for value in values:
            tag = str(value).strip()
            if tag and tag.casefold() not in seen:
                result.append(tag)
                seen.add(tag.casefold())
    return result


def library_copy_text(
    row: dict[str, Any], field: str, displayed_note: str | None = None
) -> str:
    if field == "description":
        return str(row.get("vodforge_user_description", row.get("description")) or "")
    if field == "source_description":
        return str(row.get("description") or "")
    if field in {"source_tags", "tags"}:
        return ", ".join(library_tag_values(row, field))
    if field == "note":
        return (
            displayed_note
            if displayed_note is not None
            else str(row.get("vodforge_user_note") or "")
        )
    if field == "thumbnail_url":
        thumbnail = best_thumbnail(row)
        return str(thumbnail.get("url") or "") if thumbnail else ""
    return ""
