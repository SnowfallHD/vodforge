from __future__ import annotations

import json
import subprocess
import threading
import time
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest

from yt_downloader.media_player import (
    MediaPlaybackOwner,
    MediaPlayerError,
    probe_media_duration,
    resolve_library_media_path,
)


class FakeProcess:
    def __init__(self, *, output: bytes = b"") -> None:
        self.stdout = BytesIO()
        self._output = output
        self.returncode: int | None = None
        self.terminated = False
        self._finished = threading.Event()

    def poll(self):
        return self.returncode

    def communicate(self, timeout):
        assert timeout == 12
        self.returncode = 0
        self._finished.set()
        return self._output, b""

    def terminate(self):
        self.terminated = True
        self.returncode = 0
        self._finished.set()

    def kill(self):
        self.returncode = -9
        self._finished.set()

    def wait(self, timeout=None):
        if self.returncode is None:
            if timeout is None:
                self._finished.wait(timeout=2)
            else:
                self._finished.wait(timeout=timeout)
            if self.returncode is None:
                raise subprocess.TimeoutExpired("player", timeout or 2)
        return self.returncode


class ImmediateFailureProcess(FakeProcess):
    def wait(self, timeout=None):
        self.returncode = 1
        self._finished.set()
        return self.returncode


def test_resolve_library_media_path_prefers_exact_committed_file(
    tmp_path: Path,
) -> None:
    media = tmp_path / "video.mp4"
    media.write_bytes(b"valid")

    assert (
        resolve_library_media_path(
            {
                "vodforge_output_dir": str(tmp_path),
                "vodforge_output_path": str(media),
                "vodforge_output_type": "MP4",
            }
        )
        == media
    )


def test_resolve_library_media_path_falls_back_only_when_unambiguous(
    tmp_path: Path,
) -> None:
    first = tmp_path / "first.mp3"
    first.write_bytes(b"audio")
    record = {"vodforge_output_dir": str(tmp_path), "vodforge_output_type": "MP3"}
    assert resolve_library_media_path(record) == first

    (tmp_path / "second.mp3").write_bytes(b"audio")
    assert resolve_library_media_path(record) is None


def test_probe_duration_uses_fixed_json_contract(tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def runner(command, **_kwargs):
        calls.append(command)
        return SimpleNamespace(stdout=json.dumps({"format": {"duration": "42.5"}}))

    assert (
        probe_media_duration("/trusted/ffprobe", tmp_path / "video.mp4", runner=runner)
        == 42.5
    )
    assert calls[0][0] == "/trusted/ffprobe"
    assert calls[0][-1].endswith("video.mp4")


def test_probe_duration_rejects_malformed_or_unbounded_values(tmp_path: Path) -> None:
    def runner(*_args, **_kwargs):
        return SimpleNamespace(stdout='{"format":{"duration":"nan"}}')

    with pytest.raises(MediaPlayerError):
        probe_media_duration("ffprobe", tmp_path / "bad.mp4", runner=runner)


def test_audio_playback_pause_and_close_are_owned_and_reaped(tmp_path: Path) -> None:
    media = tmp_path / "audio.mp3"
    media.write_bytes(b"audio")
    now = [10.0]
    commands: list[list[str]] = []
    processes: list[FakeProcess] = []

    def popen(command, **_kwargs):
        commands.append(command)
        process = FakeProcess()
        processes.append(process)
        return process

    owner = MediaPlaybackOwner(
        ffmpeg="/trusted/ffmpeg",
        ffprobe="/trusted/ffprobe",
        ffplay="/trusted/ffplay",
        popen=popen,
        clock=lambda: now[0],
    )
    owner.load(media, duration=30, audio_only=True)
    owner.play()
    now[0] = 15.0

    paused = owner.pause()

    assert paused.status == "Paused"
    assert paused.position == 5.0
    assert commands[0][0] == "/trusted/ffplay"
    assert processes[0].terminated is True
    assert owner._playback_registry.processes == set()
    owner.close()
    assert owner.snapshot.status == "Closed"


def test_ended_playback_restarts_from_beginning(tmp_path: Path) -> None:
    media = tmp_path / "audio.mp3"
    media.write_bytes(b"audio")
    now = [0.0]
    commands: list[list[str]] = []

    def popen(command, **_kwargs):
        commands.append(command)
        return FakeProcess()

    owner = MediaPlaybackOwner(
        ffmpeg="ffmpeg",
        ffprobe="ffprobe",
        ffplay="ffplay",
        popen=popen,
        clock=lambda: now[0],
    )
    owner.load(media, duration=10, audio_only=True)
    owner.play()
    now[0] = 11.0
    assert owner.snapshot.status == "Ended"

    owner.play()

    second_seek = commands[1].index("-ss")
    assert commands[1][second_seek + 1] == "0.000"
    assert owner.snapshot.status == "Playing"


def test_preview_generation_uses_player_registry_and_releases_child(
    tmp_path: Path,
) -> None:
    media = tmp_path / "video.mp4"
    media.write_bytes(b"video")
    process = FakeProcess(output=b"png-data")
    commands: list[list[str]] = []

    def popen(command, **_kwargs):
        commands.append(command)
        return process

    owner = MediaPlaybackOwner(
        ffmpeg="/trusted/ffmpeg",
        ffprobe="ffprobe",
        ffplay="ffplay",
        popen=popen,
    )
    owner.load(media, duration=20, audio_only=False)

    assert owner.preview_png(7.5) == b"png-data"
    assert commands[0][0] == "/trusted/ffmpeg"
    assert commands[0][commands[0].index("-ss") + 1] == "7.500"
    assert owner._preview_registry.processes == set()


def test_audio_engine_failure_terminalizes_current_playback(tmp_path: Path) -> None:
    media = tmp_path / "audio.mp3"
    media.write_bytes(b"audio")
    owner = MediaPlaybackOwner(
        ffmpeg="ffmpeg",
        ffprobe="ffprobe",
        ffplay="ffplay",
        popen=lambda *_args, **_kwargs: ImmediateFailureProcess(),
    )
    owner.load(media, duration=30, audio_only=True)

    owner.play()

    deadline = time.monotonic() + 1
    while owner.snapshot.status == "Playing" and time.monotonic() < deadline:
        time.sleep(0.01)
    assert owner.snapshot.status == "Failed"
    assert owner.snapshot.error == "The local playback engine stopped unexpectedly."
