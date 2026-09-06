"""Item-scoped artwork ownership, independent of surface rendering."""

from collections.abc import Mapping
from typing import Any

from .models import DownloadJob


def thumbnail_item_identity(info: Mapping[str, Any] | None) -> str:
    info = info or {}
    return str(info.get("id") or info.get("webpage_url") or "")


def advance_thumbnail_item(job: DownloadJob, info: Mapping[str, Any]) -> bool:
    """Retire decoded artwork before replacing metadata for another item."""
    changed = thumbnail_item_identity(job.preview_info) != thumbnail_item_identity(info)
    if changed:
        job.preview_thumbnail_image = None
    return changed


def matching_thumbnail_image(job: DownloadJob, info: Mapping[str, Any]) -> Any:
    """A playlist parent's last decoded image cannot represent every child."""
    if thumbnail_item_identity(job.preview_info) != thumbnail_item_identity(info):
        return None
    return job.preview_thumbnail_image
