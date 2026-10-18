"""Optional-file repair for an already committed, validated single MP4.

No extractor, media worker, encoder or history writer belongs to this route.
Legacy admission intentionally accepts only the complete canonical outcome message.
"""

from __future__ import annotations

import copy
import json
import re
import stat
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from threading import Event
from typing import Any

from yt_downloader import download_service as service
from yt_downloader.archive_relink import record_fingerprint
from yt_downloader.models import OutputType
from yt_downloader.safe_output import write_file_beneath

_OPTIONAL_ONLY = re.compile(
    r"MP4 completed with issues — 1 valid output\(s\), 0 failed, 0 skipped, "
    r"[1-9][0-9]* optional sidecar failure\(s\)\. Keep the valid files\. "
    r"Review Technical details for each issue and its next step\."
)


@dataclass(frozen=True)
class SidecarTarget:
    job: Any
    info: dict[str, Any]
    fingerprint: Any
    media: Path
    media_stat: tuple[int, ...]
    root: Path
    metadata: bool
    thumbnail: bool
    source_key: tuple[Any, ...]

    @property
    def label(self) -> str:
        return "Retry files" if self.metadata else "Retry artwork"


def file_identity(path: Path) -> tuple[int, ...]:
    value = path.lstat()
    if not stat.S_ISREG(value.st_mode):
        raise ValueError("Expected an unchanged regular saved file.")
    return (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns)


def source_key(job: Any) -> tuple[Any, ...]:
    return (
        job.run_id,
        job.url,
        job.output_type,
        job.batch_mode,
        job.single_video_only,
        str(job.output_dir),
        tuple(job.urls),
        tuple(job.tags),
        job.write_thumbnail,
        job.write_info_json,
        job.terminal_status,
        job.terminal_message,
    )


def optional_outcome(job: Any) -> bool:
    return bool(
        job.terminal_status == "Partial"
        and job.output_type == OutputType.MP4
        and not job.batch_mode
        and job.single_video_only
        and len(job.urls) <= 1
        and _OPTIONAL_ONLY.fullmatch(job.terminal_message or "")
    )


def optional_target(job: Any, history: list[dict[str, Any]]) -> SidecarTarget | None:
    if not optional_outcome(job):
        return None
    rows = [row for row in history if row.get("vodforge_run_id") == job.run_id]
    if len(rows) != 1:
        return None
    info = rows[0]
    summary = info.get("vodforge_encoding_summary")
    output = summary.get("output") if isinstance(summary, dict) else None
    validation = output.get("Validation status") if isinstance(output, dict) else None
    if validation not in {"Validated", "Validated existing output"}:
        return None
    try:
        media = Path(info["vodforge_output_path"])
        root = Path(job.output_dir).resolve(strict=True)
        # Reject symlink aliases, moved output and escaped destinations.
        if not media.is_absolute() or media.resolve(strict=True) != media:
            return None
        media.relative_to(root)
        identity = file_identity(media)
        if not identity[2] or media.suffix.lower() != ".mp4":
            return None
        metadata_path = media.parent / "metadata.json"
        metadata_missing = job.write_info_json and not metadata_path.exists()
        if job.write_info_json and not metadata_missing:
            file_identity(metadata_path)
            if metadata_path.stat().st_size > 2_000_000:
                return None
        thumbnail = media.parent / "thumbnail.jpeg"
        if thumbnail.exists():
            file_identity(thumbnail)
            if thumbnail.stat().st_size > service.THUMBNAIL_MAX_BYTES:
                return None
        return SidecarTarget(
            job,
            copy.deepcopy(info),
            record_fingerprint(info),
            media,
            identity,
            root,
            metadata_missing,
            job.write_thumbnail,
            source_key(job),
        )
    except (KeyError, OSError, ValueError, TypeError, RuntimeError):
        return None


def target_current(target: SidecarTarget, history: list[dict[str, Any]]) -> bool:
    rows = [row for row in history if row.get("vodforge_run_id") == target.job.run_id]
    try:
        return (
            source_key(target.job) == target.source_key
            and len(rows) == 1
            and record_fingerprint(rows[0]) == target.fingerprint
            and file_identity(target.media) == target.media_stat
            and target.media.resolve(strict=True) == target.media
        )
    except (OSError, ValueError):
        return False


@dataclass(frozen=True)
class SidecarReceipt:
    artifacts: tuple[tuple[Path, tuple[int, ...]], ...]

    def unchanged(self) -> bool:
        try:
            return all(
                file_identity(path) == identity for path, identity in self.artifacts
            )
        except (OSError, ValueError):
            return False


def repair_sidecars(
    target: SidecarTarget,
    data_dir: Path,
    cancelled: Event,
    *,
    current: Callable[[], bool] = lambda: True,
) -> SidecarReceipt:
    """One explicit bounded attempt. Preserve all existing media/sidecar bytes."""

    def check() -> None:
        if (
            cancelled.is_set()
            or not current()
            or source_key(target.job) != target.source_key
            or file_identity(target.media) != target.media_stat
        ):
            raise RuntimeError("Artwork recovery owner changed or closed.")
        if (
            target.root.resolve(strict=True) != target.root
            or target.media.resolve(strict=True) != target.media
        ):
            raise RuntimeError("Saved media location changed.")

    check()
    info = target.info
    metadata = target.media.parent / "metadata.json"

    def verify_metadata() -> None:
        file_identity(metadata)
        if metadata.stat().st_size > 2_000_000:
            raise ValueError("Metadata exceeds the recovery bound.")
        if json.loads(metadata.read_text(encoding="utf-8")).get("id") != info.get("id"):
            raise ValueError("Metadata owner changed.")

    if target.job.write_info_json and metadata.exists():
        verify_metadata()
    cache = service.cached_thumbnail_path(info, data_dir=data_dir)
    if cache is None:
        raise ValueError("No saved artwork identity.")
    if cache.parent.resolve() != cache.parent.absolute():
        raise ValueError("Artwork cache location changed.")
    thumbnail = target.media.parent / "thumbnail.jpeg"
    # Cache/sidecar validation is bounded; unknown existing bytes are never replaced.
    existing = cache if cache.exists() else thumbnail if thumbnail.exists() else None
    if existing is not None:
        file_identity(existing)
        if existing.stat().st_size > service.THUMBNAIL_MAX_BYTES:
            raise ValueError("Existing artwork is not bounded.")
        data = existing.read_bytes()
    else:
        thumb = service.best_thumbnail_for_download(info)
        url = str((thumb or {}).get("url") or "")
        if not url:
            raise ValueError("No saved artwork address.")
        data = service.download_bounded_url_bytes(url, source_url=target.job.url)
    service.decode_bounded_thumbnail(data).close()
    check()  # A delayed fetch must not write after cancellation/media replacement.
    if not cache.exists():
        service.save_cached_thumbnail_bytes(info, data, data_dir=data_dir)
    check()
    if target.thumbnail and not thumbnail.exists():
        data = cache.read_bytes()
        write_file_beneath(
            target.root, thumbnail, lambda staged: staged.write_bytes(data)
        )
    check()
    metadata = target.media.parent / "metadata.json"
    if target.metadata and not metadata.exists():
        service.write_compact_video_metadata(
            target.media.parent, info, target.job.tags, output_root=target.root
        )
    check()
    file_identity(cache)
    if cache.stat().st_size > service.THUMBNAIL_MAX_BYTES:
        raise ValueError("Cached artwork exceeds the recovery bound.")
    service.decode_bounded_thumbnail(cache.read_bytes()).close()
    if target.thumbnail:
        file_identity(thumbnail)
        if thumbnail.stat().st_size > service.THUMBNAIL_MAX_BYTES:
            raise ValueError("Artwork exceeds the recovery bound.")
        service.decode_bounded_thumbnail(thumbnail.read_bytes()).close()
    if target.job.write_info_json:
        verify_metadata()
    artifacts = [cache]
    if target.thumbnail:
        artifacts.append(thumbnail)
    if target.job.write_info_json:
        artifacts.append(metadata)
    return SidecarReceipt(tuple((path, file_identity(path)) for path in artifacts))
