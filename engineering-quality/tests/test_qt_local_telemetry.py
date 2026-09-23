"""Qt local conversion reports only the existing transaction's terminal outcome."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from yt_downloader.local_audio_video import (
    LOCAL_VIDEO_PROFILE_OPTIONS,
    LocalAudioVideoResult,
)
from yt_downloader.qt_quick import local_conversion


def test_qt_local_conversion_completion_waits_for_library_commit(
    tmp_path: Path, monkeypatch: Any
) -> None:
    class Owner:
        def __init__(self, **_kwargs: Any) -> None:
            pass

        def recover_interrupted(self) -> None:
            pass

        def convert(self, request: Any, *, on_progress: Any) -> LocalAudioVideoResult:
            del on_progress
            return LocalAudioVideoResult(
                output_path=tmp_path / "result.mp4",
                image_path=tmp_path / "private-cover.png",
                history_metadata={"vodforge_run_id": request.run_id},
                telemetry_dimensions={"encoder": "cpu"},
            )

        def cancel(self) -> None:
            pass

        def shutdown(self, *, timeout_seconds: float) -> bool:
            return True

    events: list[tuple[str, dict[str, Any]]] = []

    class Telemetry:
        def record(self, name: str, **fields: Any) -> bool:
            events.append((name, fields))
            return True

    monkeypatch.setattr(local_conversion, "LocalAudioVideoConversionOwner", Owner)
    monkeypatch.setattr(
        local_conversion, "local_conversion_state_path", lambda: tmp_path / "run.json"
    )
    monkeypatch.setattr(
        local_conversion.DownloadWorkerCore,
        "_find_ffmpeg",
        lambda: "ffmpeg",
    )
    monkeypatch.setattr(
        local_conversion.DownloadWorkerCore,
        "_find_ffprobe",
        lambda: "ffprobe",
    )
    runtime = local_conversion.LocalConversionRuntime()
    runtime.product_telemetry = Telemetry()
    runtime.start(
        tmp_path / "private.mp3",
        tmp_path / "private-cover.png",
        tmp_path,
        LOCAL_VIDEO_PROFILE_OPTIONS[0],
    )
    deadline = time.monotonic() + 2
    result: LocalAudioVideoResult | None = None
    while time.monotonic() < deadline:
        for kind, payload in runtime.poll():
            if kind == "done":
                assert isinstance(payload, LocalAudioVideoResult)
                result = payload
        if result is not None:
            break
        time.sleep(0.005)
    assert result is not None
    assert [name for name, _fields in events] == ["local_conversion_started"]
    runtime.observe_committed(result)
    assert [name for name, _fields in events] == [
        "local_conversion_started",
        "local_conversion_completed",
    ]
    assert "private" not in str(events)
    assert runtime.close()
