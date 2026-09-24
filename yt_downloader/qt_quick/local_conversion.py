"""Qt event handoff for the existing local audio-to-video transaction owner."""

from __future__ import annotations

import queue
import threading
from pathlib import Path
from typing import Any

from yt_downloader.app import DownloadWorkerCore, write_diagnostic
from yt_downloader.download_error_presentation import (
    download_error_message,
    technical_download_error,
)
from yt_downloader.failure_diagnostics import FailureDiagnostic, capture_failure
from yt_downloader.local_audio_video import (
    LocalAudioVideoCancelled,
    LocalAudioVideoConversionOwner,
    LocalAudioVideoError,
    LocalAudioVideoProgress,
    LocalAudioVideoResult,
    LocalConversionRecoveryOwner,
    LocalVideoProfile,
    local_conversion_state_path,
    new_local_audio_video_request,
)


class LocalConversionRuntime:
    def __init__(self) -> None:
        self.events: queue.Queue[tuple[str, Any]] = queue.Queue()
        self._owner = LocalAudioVideoConversionOwner(
            ffmpeg=DownloadWorkerCore._find_ffmpeg(),
            ffprobe=DownloadWorkerCore._find_ffprobe(),
            recovery=LocalConversionRecoveryOwner(local_conversion_state_path()),
        )
        self._owner.recover_interrupted()
        self._thread: threading.Thread | None = None
        self.product_telemetry: Any | None = None

    def _observe(
        self,
        event_name: str,
        run_id: str,
        *,
        dimensions: dict[str, str] | None = None,
        failure_detail: FailureDiagnostic | None = None,
    ) -> None:
        telemetry = self.product_telemetry
        if telemetry is None:
            return
        try:
            telemetry.record(
                event_name,
                dedupe_key=run_id,
                attempt_key=run_id,
                dimensions=dimensions,
                run_kind="local_audio_video",
                output_type="mp4",
                failure_reason=(failure_detail.reason if failure_detail else None),
                failure_detail=(failure_detail.payload() if failure_detail else None),
            )
        except (OSError, ValueError):
            pass

    @property
    def active(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(
        self,
        audio: Path,
        image: Path,
        output_dir: Path,
        profile: str,
    ) -> None:
        if self._thread is not None and self._thread.is_alive():
            raise LocalAudioVideoError("A local conversion is already running.")
        request = new_local_audio_video_request(
            audio, image, output_dir, profile=LocalVideoProfile(profile)
        )

        def run() -> None:
            try:
                result = self._owner.convert(
                    request,
                    on_progress=lambda progress: self.events.put(
                        ("progress", progress)
                    ),
                )
            except LocalAudioVideoCancelled as exc:
                self._observe("local_conversion_stopped", request.run_id)
                write_diagnostic(technical_download_error(exc))
                self.events.put(("error", "Conversion stopped."))
            except LocalAudioVideoError as exc:
                self._report_failure(request.run_id, exc)
            except Exception as exc:  # noqa: BLE001 - worker must report its terminal result
                self._report_failure(request.run_id, exc)
            else:
                self.events.put(("done", result))

        self._thread = threading.Thread(
            target=run, name="vodforge-qt-local-conversion", daemon=False
        )
        self._observe("local_conversion_started", request.run_id)
        self._thread.start()

    def _report_failure(self, run_id: str, error: Exception) -> None:
        detail = capture_failure(error, stage="processing")
        self._observe("local_conversion_failed", run_id, failure_detail=detail)
        write_diagnostic(technical_download_error(error))
        self.events.put(("error", download_error_message(error)))

    def observe_committed(self, result: LocalAudioVideoResult) -> None:
        run_id = str(result.history_metadata.get("vodforge_run_id") or "")
        if run_id:
            self._observe(
                "local_conversion_completed",
                run_id,
                dimensions=dict(result.telemetry_dimensions),
            )

    def observe_history_failed(self, result: LocalAudioVideoResult) -> None:
        run_id = str(result.history_metadata.get("vodforge_run_id") or "")
        if run_id:
            self._observe("local_conversion_failed", run_id)

    def cancel(self) -> None:
        self._owner.cancel()

    def poll(
        self,
    ) -> list[tuple[str, LocalAudioVideoProgress | LocalAudioVideoResult | str]]:
        result: list[
            tuple[str, LocalAudioVideoProgress | LocalAudioVideoResult | str]
        ] = []
        while True:
            try:
                result.append(self.events.get_nowait())
            except queue.Empty:
                return result

    def close(self) -> bool:
        self._owner.cancel()
        return self._owner.shutdown(timeout_seconds=10)
