from __future__ import annotations

import io
import json
import os
import subprocess
import threading
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from yt_downloader import app as app_module
from yt_downloader.history import upsert_history
from yt_downloader.library_state import LibraryProjectionOwner
from yt_downloader.local_audio_video import (
    LOCAL_VIDEO_HEIGHT,
    LOCAL_VIDEO_WIDTH,
    LocalAudioVideoCancelled,
    LocalAudioVideoConversionOwner,
    LocalAudioVideoError,
    LocalAudioVideoResult,
    LocalAudioVideoRuntime,
    LocalConversionRecoveryOwner,
    build_local_audio_video_command,
    local_video_filename,
    new_local_audio_video_request,
)
from yt_downloader.local_audio_video_ui import LocalAudioVideoDialog
from yt_downloader.models import OutputType


def _input_probe(*, title: str = "Quiet hours", artist: str = "Local artist"):
    return {
        "format": {
            "format_name": "mp3",
            "duration": "3.0",
            "tags": {"title": title, "artist": artist},
        },
        "streams": [
            {
                "codec_type": "audio",
                "codec_name": "mp3",
                "bit_rate": "192000",
                "sample_rate": "44100",
                "channels": 2,
            }
        ],
    }


def _output_probe():
    return {
        "format": {
            "format_name": "mov,mp4,m4a,3gp,3g2,mj2",
            "duration": "3.0",
            "size": "4096",
        },
        "streams": [
            {
                "codec_type": "video",
                "codec_name": "h264",
                "width": LOCAL_VIDEO_WIDTH,
                "height": LOCAL_VIDEO_HEIGHT,
                "avg_frame_rate": "30/1",
                "bit_rate": "25000",
                "pix_fmt": "yuv420p",
                "profile": "High",
            },
            {
                "codec_type": "audio",
                "codec_name": "aac",
                "bit_rate": "192000",
                "sample_rate": "48000",
                "channels": 2,
            },
        ],
    }


class FakeProcess:
    def __init__(self, command: list[str], *, blocking: bool = False) -> None:
        self.args = command
        self.pid = 43210
        self.returncode: int | None = None
        self._done = threading.Event()
        self.stdout: Any
        if blocking:
            self.stdout = _BlockingOutput(self._done)
        else:
            self.stdout = io.StringIO("out_time_us=1500000\nprogress=end\n")
            Path(command[-1]).write_bytes(b"fake validated mp4")

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        if (
            self.returncode is None
            and isinstance(self.stdout, _BlockingOutput)
            and not self._done.wait(timeout=timeout)
        ):
            raise subprocess.TimeoutExpired(self.args, timeout)
        if self.returncode is None:
            self.returncode = 0
        return self.returncode

    def terminate(self):
        self.returncode = -15
        self._done.set()

    def kill(self):
        self.returncode = -9
        self._done.set()


class _BlockingOutput:
    def __init__(self, done: threading.Event) -> None:
        self.done = done

    def __iter__(self):
        return self

    def __next__(self):
        self.done.wait(timeout=3)
        raise StopIteration


class _UnstoppableProcess:
    def __init__(self, command: list[str]) -> None:
        self.args = command
        self.pid = 43211
        self.returncode = None
        self.stdout = io.StringIO("progress=end\n")

    def poll(self):
        return None

    def wait(self, timeout=None):
        raise subprocess.TimeoutExpired(self.args, timeout)

    def terminate(self):
        return None

    def kill(self):
        return None


def _owner(
    tmp_path: Path,
    *,
    popen,
    probe_reader=None,
) -> LocalAudioVideoConversionOwner:
    state = tmp_path / "state" / "local-conversion-state.json"

    def default_probe(_ffprobe: str, path: Path):
        return _input_probe() if path.suffix.casefold() == ".mp3" else _output_probe()

    return LocalAudioVideoConversionOwner(
        ffmpeg="/trusted/ffmpeg",
        ffprobe="/trusted/ffprobe",
        recovery=LocalConversionRecoveryOwner(state),
        runtime=LocalAudioVideoRuntime(
            popen=popen,
            probe_reader=probe_reader or default_probe,
            image_normalizer=lambda _source, destination: destination.write_bytes(
                b"normalized image"
            ),
        ),
    )


def test_static_image_command_is_one_offline_mp4_encode(tmp_path: Path) -> None:
    audio = tmp_path / "source.mp3"
    image = tmp_path / "still.png"
    output = tmp_path / "result.mp4"

    command = build_local_audio_video_command(
        "/trusted/ffmpeg",
        audio_path=audio,
        image_path=image,
        output_path=output,
    )

    assert command[0] == "/trusted/ffmpeg"
    assert command.count("-i") == 2
    assert command[command.index("-loop") + 1] == "1"
    assert "scale=1920:1080" in command[command.index("-vf") + 1]
    assert command[command.index("-c:v") + 1] == "libx264"
    assert command[command.index("-c:a") + 1] == "aac"
    assert "-shortest" in command
    assert command[command.index("-movflags") + 1] == "+faststart"
    assert command[-1] == str(output)
    assert not any(value.startswith(("http://", "https://")) for value in command)


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("An evening: mix?.mp3", "An evening_ mix_.mp4"),
        ("CON.mp3", "CON_video.mp4"),
        ("  .mp3", "Audio video.mp4"),
    ],
)
def test_local_video_filename_is_cross_platform_safe(
    source: str, expected: str
) -> None:
    assert local_video_filename(Path(source)) == expected


def test_dialog_preserves_actionable_error_when_controls_return_idle() -> None:
    values: list[object] = []
    dialog = SimpleNamespace(
        audio_path=Path("audio.mp3"),
        image_path=Path("still.png"),
        create_button=SimpleNamespace(
            configure=lambda **options: values.append(("button", options))
        ),
        status_var=SimpleNamespace(set=lambda value: values.append(("status", value))),
    )

    LocalAudioVideoDialog._sync_ready_state(
        dialog,
        status="The selected audio is not a valid, playable MP3 file.",
    )

    assert ("button", {"state": "normal"}) in values
    assert (
        "status",
        "The selected audio is not a valid, playable MP3 file.",
    ) in values


def test_conversion_commits_directly_to_output_and_projects_into_mp4_library(
    tmp_path: Path,
) -> None:
    audio = tmp_path / "Quiet hours.mp3"
    image = tmp_path / "portrait.jpg"
    output_dir = tmp_path / "chosen destination"
    audio.write_bytes(b"mp3")
    image.write_bytes(b"jpg")
    processes: list[FakeProcess] = []

    def popen(command, **_kwargs):
        process = FakeProcess(command)
        processes.append(process)
        return process

    owner = _owner(tmp_path, popen=popen)
    request = new_local_audio_video_request(audio, image, output_dir)

    result = owner.convert(request, on_progress=lambda _progress: None)

    assert result.output_path == output_dir / "Quiet hours.mp4"
    assert result.output_path.is_file()
    assert result.output_path.parent == output_dir
    assert not (output_dir / ".vfstage").exists()
    assert owner.active is False
    assert processes[0].returncode == 0
    metadata = dict(result.history_metadata)
    assert metadata["vodforge_output_type"] == OutputType.MP4.value
    assert metadata["vodforge_run_id"] == request.run_id
    assert metadata["vodforge_output_path"] == str(result.output_path)
    assert metadata["title"] == "Quiet hours"
    assert metadata["uploader"] == "Local artist"
    serialized = json.dumps(metadata)
    assert str(audio) not in serialized
    assert str(image) not in serialized

    history = upsert_history([], metadata, output_dir)
    projection = LibraryProjectionOwner().reconcile(
        history_items=history,
        active_job=None,
        queued_jobs=[],
        terminal_jobs=[],
    )
    assert len(projection.rows) == 1
    assert projection.rows[0]["vodforge_run_id"] == request.run_id
    assert projection.rows[0]["vodforge_output_type"] == "MP4"
    assert projection.rows[0]["vodforge_output_path"] == str(result.output_path)


def test_existing_filename_is_preserved_and_new_output_gets_suffix(
    tmp_path: Path,
) -> None:
    audio = tmp_path / "Song.mp3"
    image = tmp_path / "still.png"
    output_dir = tmp_path / "exports"
    audio.write_bytes(b"mp3")
    image.write_bytes(b"png")
    output_dir.mkdir()
    original = output_dir / "Song.mp4"
    original.write_bytes(b"existing media")

    owner = _owner(
        tmp_path,
        popen=lambda command, **_kwargs: FakeProcess(command),
    )
    result = owner.convert(
        new_local_audio_video_request(audio, image, output_dir),
        on_progress=lambda _progress: None,
    )

    assert original.read_bytes() == b"existing media"
    assert result.output_path == output_dir / "Song (1).mp4"


def test_app_coordinates_completed_output_through_canonical_history(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    output = tmp_path / "selected" / "Song.mp4"
    image = tmp_path / "still.png"
    metadata = {
        "id": "local_run",
        "title": "Song",
        "vodforge_run_id": "run",
        "vodforge_output_type": "MP4",
        "vodforge_output_path": str(output),
    }
    events: list[object] = []
    app = SimpleNamespace(
        download_history=[],
        last_output_dirs=[],
        status_var=SimpleNamespace(set=lambda value: events.append(("status", value))),
        _append_log=lambda value: events.append(("log", value)),
        _select_focus_view=lambda value: events.append(("view", value)),
    )

    def record(info, destination):
        events.append(("history", info, destination))
        app.download_history = [dict(info)]

    app._record_download_history = record
    monkeypatch.setattr(
        app_module,
        "save_custom_cached_thumbnail_image",
        lambda info, source: events.append(("thumbnail", info, source)),
    )
    result = LocalAudioVideoResult(
        output_path=output,
        image_path=image,
        history_metadata=metadata,
    )

    app_module.DownloaderApp._complete_local_audio_video(app, result)

    assert ("history", metadata, output.parent) in events
    assert ("view", "library") in events
    assert output.parent in app.last_output_dirs
    assert not hasattr(app, "metadata_items")


def test_fast_cancel_reaps_child_and_removes_private_stage(tmp_path: Path) -> None:
    audio = tmp_path / "Song.mp3"
    image = tmp_path / "still.png"
    output_dir = tmp_path / "exports"
    audio.write_bytes(b"mp3")
    image.write_bytes(b"png")
    started = threading.Event()

    def popen(command, **_kwargs):
        started.set()
        return FakeProcess(command, blocking=True)

    owner = _owner(tmp_path, popen=popen)
    errors: list[BaseException] = []

    def convert() -> None:
        try:
            owner.convert(
                new_local_audio_video_request(audio, image, output_dir),
                on_progress=lambda _progress: None,
            )
        except BaseException as exc:  # noqa: BLE001 - test captures worker failure
            errors.append(exc)

    worker = threading.Thread(target=convert)
    worker.start()
    assert started.wait(timeout=2)
    owner.cancel()
    worker.join(timeout=5)

    assert not worker.is_alive()
    assert len(errors) == 1
    assert isinstance(errors[0], LocalAudioVideoCancelled)
    assert owner.active is False
    assert not (output_dir / ".vfstage").exists()
    assert not (tmp_path / "state" / "local-conversion-state.json").exists()


def test_unconfirmed_child_retains_stage_and_recovery_ownership(
    tmp_path: Path,
) -> None:
    audio = tmp_path / "Song.mp3"
    image = tmp_path / "still.png"
    output_dir = tmp_path / "exports"
    audio.write_bytes(b"mp3")
    image.write_bytes(b"png")
    owner = _owner(
        tmp_path,
        popen=lambda command, **_kwargs: _UnstoppableProcess(command),
    )

    with pytest.raises(LocalAudioVideoError, match="did not finish cleanly"):
        owner.convert(
            new_local_audio_video_request(audio, image, output_dir),
            on_progress=lambda _progress: None,
        )

    state_path = tmp_path / "state" / "local-conversion-state.json"
    payload = json.loads(state_path.read_text(encoding="utf-8"))
    assert payload["children"][0]["pid"] == 43211
    assert Path(payload["staging_dir"]).is_dir()


def test_shutdown_before_worker_start_prevents_late_child_spawn(tmp_path: Path) -> None:
    audio = tmp_path / "Song.mp3"
    image = tmp_path / "still.png"
    audio.write_bytes(b"mp3")
    image.write_bytes(b"png")
    calls: list[list[str]] = []
    owner = _owner(
        tmp_path,
        popen=lambda command, **_kwargs: calls.append(command),
    )

    assert owner.shutdown() is True
    with pytest.raises(LocalAudioVideoCancelled, match="closing"):
        owner.convert(
            new_local_audio_video_request(audio, image, tmp_path / "exports"),
            on_progress=lambda _progress: None,
        )

    assert calls == []


def test_restart_recovers_only_recorded_abandoned_stage(tmp_path: Path) -> None:
    output_root = tmp_path / "exports"
    staging = output_root / ".vfstage" / "owned-transaction"
    staging.mkdir(parents=True)
    (staging / "partial.mp4").write_bytes(b"partial")
    state = tmp_path / "local-conversion-state.json"
    state.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "state": "active",
                "owner_pid": os.getpid() + 100_000,
                "run_id": "interrupted-run",
                "output_root": str(output_root),
                "staging_dir": str(staging),
                "children": [],
            }
        ),
        encoding="utf-8",
    )
    owner = LocalConversionRecoveryOwner(
        state,
        owner_command_reader=lambda _pid: None,
    )

    assert owner.recover_interrupted() is True
    assert not staging.exists()
    assert not (output_root / ".vfstage").exists()
    assert not state.exists()


def test_recovery_child_receipt_does_not_persist_source_paths(tmp_path: Path) -> None:
    output_root = tmp_path / "exports"
    staging = output_root / ".vfstage" / "owned-transaction"
    staging.mkdir(parents=True)
    state = tmp_path / "local-conversion-state.json"
    owner = LocalConversionRecoveryOwner(state)
    owner.begin(output_root=output_root, staging_dir=staging, run_id="private-run")

    owner.child_started(
        SimpleNamespace(
            pid=54321,
            args=[
                "/trusted/ffmpeg",
                "-i",
                str(tmp_path / "private song.mp3"),
                str(staging / "rendered.mp4"),
            ],
        )
    )

    payload = json.loads(state.read_text(encoding="utf-8"))
    assert payload["children"] == [{"pid": 54321, "argv": ["/trusted/ffmpeg"]}]
    serialized = json.dumps(payload)
    assert "private song.mp3" not in serialized


def test_restart_fails_closed_when_prior_owner_is_still_live(tmp_path: Path) -> None:
    output_root = tmp_path / "exports"
    staging = output_root / ".vfstage" / "owned-transaction"
    staging.mkdir(parents=True)
    state = tmp_path / "local-conversion-state.json"
    state.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "state": "active",
                "owner_pid": os.getpid() + 100_000,
                "run_id": "live-run",
                "output_root": str(output_root),
                "staging_dir": str(staging),
                "children": [],
            }
        ),
        encoding="utf-8",
    )
    owner = LocalConversionRecoveryOwner(
        state,
        owner_command_reader=lambda _pid: "/trusted/ffmpeg rendered.mp4",
    )

    assert owner.recover_interrupted() is False
    assert staging.exists()
    assert state.exists()
