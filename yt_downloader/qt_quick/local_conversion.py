"""Qt event handoff for the existing local audio-to-video transaction owner."""

from __future__ import annotations

import queue
import threading
from pathlib import Path
from typing import Any

from yt_downloader.app import DownloadWorkerCore
from yt_downloader.local_audio_video import (
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
            except LocalAudioVideoError as exc:
                self.events.put(("error", str(exc)))
            except Exception as exc:  # noqa: BLE001 - worker must report its terminal result
                self.events.put(
                    ("error", f"Local conversion failed: {type(exc).__name__}")
                )
            else:
                self.events.put(("done", result))

        self._thread = threading.Thread(
            target=run, name="vodforge-qt-local-conversion", daemon=False
        )
        self._thread.start()

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
