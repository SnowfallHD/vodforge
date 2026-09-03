from __future__ import annotations

import subprocess
import threading
from pathlib import Path

from yt_downloader.media_preview import MediaPreviewOwner


class FakeProcess:
    def __init__(self, *, output: bytes = b"") -> None:
        self._output = output
        self.returncode: int | None = None
        self._finished = threading.Event()

    def poll(self):
        return self.returncode

    def communicate(self, timeout):
        assert timeout == 12
        self.returncode = 0
        self._finished.set()
        return self._output, b""

    def terminate(self):
        self.returncode = 0
        self._finished.set()

    def kill(self):
        self.returncode = -9
        self._finished.set()

    def wait(self, timeout=None):
        if self.returncode is None:
            self._finished.wait(timeout=timeout or 2)
        if self.returncode is None:
            raise subprocess.TimeoutExpired("preview", timeout or 2)
        return self.returncode


def test_preview_generation_is_separate_from_live_playback(tmp_path: Path) -> None:
    media = tmp_path / "video.mp4"
    media.write_bytes(b"video")
    process = FakeProcess(output=b"png-data")
    commands: list[list[str]] = []

    def popen(command, **_kwargs):
        commands.append(command)
        return process

    owner = MediaPreviewOwner(ffmpeg="/trusted/ffmpeg", popen=popen)
    owner.load(media)

    assert owner.preview_png(7.5) == b"png-data"
    assert commands[0][0] == "/trusted/ffmpeg"
    assert commands[0][commands[0].index("-ss") + 1] == "7.500"
    assert owner._registry.processes == set()
