"""Qt handoff for the existing metadata-only provider preview operation."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from yt_downloader.app import (
    ProviderNetworkCoordinator,
    QueueLogger,
    fetch_metadata_preview,
    format_ytdlp_user_error,
    iter_video_infos,
    single_video_url_requires_video_id_error,
)
from yt_downloader.archive_work import ArchiveWorkOwner
from yt_downloader.cookie_inputs import cookie_inputs_for_source
from yt_downloader.failure_diagnostics import FailureDiagnostic, capture_failure
from yt_downloader.library_diagnostics import begin_library_action
from yt_downloader.models import CookieSource, OutputType


class QtMetadataPreview:
    """One current request; metadata is transient until a run is admitted."""

    def __init__(self, coordinator: ProviderNetworkCoordinator) -> None:
        self._coordinator = coordinator
        self._work = ArchiveWorkOwner()
        self.phase = "idle"
        self.message = ""
        self.info: dict[str, Any] | None = None
        self.product_telemetry: Any | None = None
        self._observation: Any | None = None

    def begin(
        self,
        url: str,
        output_type: OutputType,
        *,
        ignore_playlists: bool,
        cookie_source: CookieSource,
        cookie_file: Path | None,
        cookie_browser: str | None,
        ffmpeg: str | None,
        deno: str | None,
    ) -> bool:
        source = url.strip()
        parsed = urlparse(source)
        if self._work.busy:
            self.message = "A metadata preview is already running."
            return False
        observation = begin_library_action(
            self.product_telemetry, "preview_start", "preview"
        )
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            self.message = "Paste a complete video URL first."
            observation.emit("rejected", "validation")
            return False
        if ignore_playlists:
            error = single_video_url_requires_video_id_error(source)
            if error:
                self.message = error
                observation.emit("rejected", "validation")
                return False
        try:
            cookies = cookie_inputs_for_source(
                cookie_source, cookie_file, cookie_browser
            )
        except (OSError, RuntimeError, ValueError) as exc:
            self.message = str(exc)
            observation.emit(
                "rejected",
                "validation",
                failure_detail=capture_failure(exc, stage="preparation"),
            )
            return False

        def work(cancelled: Any) -> dict[str, Any]:
            try:
                info = fetch_metadata_preview(
                    source,
                    output_type,
                    ignore_playlists=ignore_playlists,
                    cookie_inputs=cookies,
                    ffmpeg=ffmpeg,
                    deno=deno,
                    logger=QueueLogger(None),
                    coordinator=self._coordinator,
                    should_abort=cancelled.is_set,
                )
            except Exception as exc:  # noqa: BLE001 - provider errors become user-facing state
                return {
                    "error": format_ytdlp_user_error(exc),
                    "failure": capture_failure(exc, stage="analysis"),
                }
            return {"info": info}

        if self._work.submit("metadata_preview", work) is None:
            self.message = "A metadata preview is already running."
            observation.emit("rejected", "launch")
            return False
        self._observation = observation
        observation.emit("admitted", "launch")
        self.phase = "loading"
        self.message = "Fetching title, creator, and thumbnail…"
        self.info = None
        return True

    def poll(self) -> bool:
        result = self._work.poll()
        if result is None:
            return False
        payload = result.value if isinstance(result.value, dict) else {}
        info = payload.get("info")
        observation, self._observation = self._observation, None
        if isinstance(info, dict) and info and iter_video_infos(info):
            self.phase = "complete"
            self.message = "Preview complete — no media has been downloaded."
            self.info = info
            if observation is not None:
                observation.emit("completed", "completed")
        else:
            self.phase = "failed"
            self.message = str(
                payload.get("error") or "Metadata preview returned no usable item."
            )
            self.info = None
            if observation is not None:
                detail = payload.get("failure")
                observation.emit(
                    "rejected",
                    "launch",
                    failure_detail=detail
                    if isinstance(detail, FailureDiagnostic)
                    else FailureDiagnostic(stage="analysis"),
                )
        return True

    def close(self) -> None:
        if self._observation is not None:
            self._observation.emit("cancelled", "confirmation")
            self._observation = None
        self._work.close()
