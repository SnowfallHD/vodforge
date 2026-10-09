"""Conservative split-stream refresh; never change access or selected quality."""

from pathlib import Path
from typing import Any


class TransferRefreshError(RuntimeError):
    """Fresh metadata could not safely resume the selected transfer."""


def _format(info: dict[str, Any], format_id: str) -> dict[str, Any] | None:
    matches = [
        item
        for item in info.get("formats") or []
        if isinstance(item, dict) and item.get("format_id") == format_id
    ]
    return matches[0] if len(matches) == 1 else None


def _signature(info: dict[str, Any]) -> tuple[Any, ...]:
    return tuple(
        info.get(key)
        for key in (
            "format_id",
            "ext",
            "vcodec",
            "acodec",
            "width",
            "height",
            "fps",
            "vbr",
            "tbr",
            "abr",
            "asr",
            "audio_channels",
            "language",
            "language_preference",
            "has_drm",
        )
    )


class SplitTransferRefresh:
    """One eligible audio403 following a completed, unchanged video stream."""

    def __init__(
        self, info: dict[str, Any], video_id: str, audio_id: str, staging: Path
    ) -> None:
        self.info = dict(info)
        self.video_id = video_id
        self.audio_id = audio_id
        self.staging = staging.resolve()
        video = _format(info, video_id)
        audio = _format(info, audio_id)
        self.video = dict(video) if video is not None else None
        self.audio = dict(audio) if audio is not None else None
        self.completed_video: Path | None = None
        self.completed_stat: tuple[int, int, int] | None = None
        self.audio_finished = False

    def observe(self, progress: dict[str, Any]) -> None:
        if progress.get("status") != "finished":
            return
        info = progress.get("info_dict") or {}
        if info.get("format_id") == self.audio_id:
            self.audio_finished = True
        if info.get("format_id") != self.video_id:
            return
        filename = progress.get("filename")
        if not isinstance(filename, str):
            return
        try:
            path = Path(filename)
            if path.is_symlink() or not path.is_file():
                return
            path = path.resolve()
            if not path.is_relative_to(self.staging):
                return
            stat = path.stat()
        except OSError:
            # Optional recovery observation must not break an ordinary transfer.
            return
        self.completed_video = path
        self.completed_stat = (stat.st_size, stat.st_mtime_ns, stat.st_ino)

    def eligible(self, status: int | None, errors: list[BaseException]) -> bool:
        if (
            status != 403
            or not isinstance(self.info.get("id"), str)
            or not self.info["id"]
            or self.completed_video is None
            or self.audio_finished
            or self.video is None
            or self.audio is None
            or self.info.get("availability") not in (None, "public", "unlisted")
            or self.video.get("has_drm")
            or self.audio.get("has_drm")
            or self.video.get("acodec") != "none"
            or self.audio.get("vcodec") != "none"
        ):
            return False
        audio_url = self.audio.get("url")
        if not isinstance(audio_url, str) or not audio_url:
            return False
        # Match the failed request in memory, never emit its signed URL.
        return any(
            value == audio_url
            for error in errors
            for value in (
                getattr(error, "url", None),
                getattr(getattr(error, "response", None), "url", None),
            )
        )

    def checked_refresh(self, fresh: dict[str, Any] | None) -> dict[str, Any]:
        if not isinstance(fresh, dict) or fresh.get("id") != self.info.get("id"):
            raise TransferRefreshError(
                "Source identity changed during transfer refresh; no output was committed."
            )
        if fresh.get("availability") not in (None, "public", "unlisted"):
            raise TransferRefreshError(
                "Source access is restricted; transfer refresh stopped without changing access settings."
            )
        if fresh.get("duration") != self.info.get("duration"):
            raise TransferRefreshError(
                "Source duration changed during transfer refresh; retry with a new run."
            )
        for old, format_id in (
            (self.video, self.video_id),
            (self.audio, self.audio_id),
        ):
            new = _format(fresh, format_id)
            if (
                old is None
                or new is None
                or _signature(old) != _signature(new)
                or new.get("has_drm")
            ):
                raise TransferRefreshError(
                    "Selected formats changed or are unavailable; refresh stopped without lowering quality. Choose formats in a new run."
                )
        audio = _format(fresh, self.audio_id)
        assert audio is not None and self.audio is not None
        if not audio.get("url") or audio.get("url") == self.audio.get("url"):
            raise TransferRefreshError(
                "The source returned the same rejected audio URL; refresh stopped. Check source access and retry later."
            )
        self.verify_video()
        return fresh

    def verify_video(self) -> None:
        path = self.completed_video
        if path is None or path.is_symlink() or not path.is_file():
            raise TransferRefreshError(
                "Completed video is unavailable; transfer refresh stopped."
            )
        stat = path.stat()
        if (stat.st_size, stat.st_mtime_ns, stat.st_ino) != self.completed_stat:
            raise TransferRefreshError(
                "Completed video changed; transfer refresh stopped."
            )
