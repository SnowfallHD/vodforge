from __future__ import annotations

import io
import subprocess
import threading
from pathlib import Path
from unittest.mock import Mock

import pytest
from PIL import Image

from yt_downloader import library_artwork_source as module
from yt_downloader.library_artwork_source import LibraryArtworkSource


def bitmap(size=(1920, 1080), color="blue"):
    output = io.BytesIO()
    Image.new("RGB", size, color).save(output, format="JPEG")
    return output.getvalue()


def setup(tmp_path, monkeypatch, *, data=None):
    media = tmp_path / "actual.mp4"
    media.write_bytes(b"local fixture")
    row = {
        "vodforge_output_dir": str(tmp_path),
        "vodforge_output_path": str(media),
        "vodforge_output_type": "MP4",
        "duration": 100,
    }
    processes = []

    class Process:
        def __init__(self, command, **_options):
            self.command = command
            self.returncode = None
            self.killed = False
            processes.append(self)

        def communicate(self, **_options):
            self.returncode = 0
            return data if data is not None else bitmap(), b""

        def poll(self):
            return self.returncode

        def kill(self):
            self.killed = True
            self.returncode = -9

    monkeypatch.setattr(
        module, "find_runtime_executable", lambda _name: "/controlled/ffmpeg"
    )
    monkeypatch.setattr(module.subprocess, "Popen", Process)
    owner = LibraryArtworkSource(
        tmp_path / "cache",
        thumbnail_path=lambda _row: None,
        media_path=lambda _row: media,
    )
    return owner, row, processes, Process


def test_hero_selects_original_resolution_instead_of_first_small_preview(tmp_path):
    small = tmp_path / "preview.jpg"
    small.write_bytes(bitmap((320, 180), "red"))
    original = tmp_path / "thumbnail.jpg"
    original.write_bytes(bitmap((1920, 1080), "blue"))
    owner = LibraryArtworkSource(
        tmp_path / "cache",
        thumbnail_path=lambda _r: small,
        media_path=Mock(
            side_effect=AssertionError("Adequate original must not extract")
        ),
    )
    assert (
        owner.resolve(
            {"vodforge_output_dir": str(tmp_path)},
            (1380, 350),
            "media",
            threading.Event(),
        )
        == original
    )


def test_imported_video_extracts_once_and_shares_usable_frame_across_roles(
    tmp_path, monkeypatch
):
    owner, row, processes, _ = setup(tmp_path, monkeypatch)
    path = owner.resolve(row, (1380, 350), "media", threading.Event())
    assert path and Image.open(path).size == (1920, 1080)
    assert owner.resolve(row, (240, 135), "media", threading.Event()) == path
    assert owner.resolve(row, (112, 112), "avatar", threading.Event()) == path
    assert len(processes) == 1
    command = processes[0].command
    assert command[command.index("-map") + 1] == "0:V:0"
    assert command[command.index("-protocol_whitelist") + 1] == "file,pipe"


@pytest.mark.parametrize(
    "role,field", [("avatar", "channel_avatar_path"), ("banner", "channel_banner_path")]
)
def test_channel_profile_roles_do_not_swap_avatar_and_banner(tmp_path, role, field):
    avatar = tmp_path / "avatar.png"
    avatar.write_bytes(bitmap((900, 900), "green"))
    banner = tmp_path / "banner.png"
    banner.write_bytes(bitmap((2560, 400), "blue"))
    owner = LibraryArtworkSource(
        tmp_path / "cache",
        thumbnail_path=Mock(side_effect=AssertionError("Role already available")),
        media_path=lambda _r: None,
    )
    record = {"channel_avatar_path": str(avatar), "channel_banner_path": str(banner)}
    assert owner.resolve(record, (112, 112), role, threading.Event()) == Path(
        record[field]
    )


def test_cover_art_audio_uses_attached_image_without_a_time_seek(tmp_path, monkeypatch):
    owner, row, processes, _ = setup(tmp_path, monkeypatch, data=bitmap((700, 700)))
    row["vodforge_output_type"] = "MP3"
    result = owner.resolve(row, (240, 135), "media", threading.Event())
    assert result and Image.open(result).size == (700, 700)
    assert "-ss" not in processes[0].command
    assert (
        owner.resolve_asset(row, (240, 135), "media", threading.Event()).kind
        == "embedded_art"
    )
    assert processes[0].command[processes[0].command.index("-map") + 1] == "0:v:0"


def test_modified_media_gets_a_new_frame_identity(tmp_path, monkeypatch):
    owner, row, processes, _ = setup(tmp_path, monkeypatch)
    first = owner.resolve(row, (1380, 350), "media", threading.Event())
    Path(row["vodforge_output_path"]).write_bytes(b"changed source fixture")
    second = owner.resolve(row, (1380, 350), "media", threading.Event())
    assert first != second
    assert len(processes) == 2


def test_media_changed_during_extraction_cannot_publish_stale_frame(
    tmp_path, monkeypatch
):
    owner, row, _processes, process = setup(tmp_path, monkeypatch)
    original = process.communicate

    def changed(self, **kwargs):
        Path(row["vodforge_output_path"]).write_bytes(b"changed during process")
        return original(self, **kwargs)

    monkeypatch.setattr(process, "communicate", changed)
    assert owner.resolve(row, (1380, 350), "media", threading.Event()) is None
    assert not list((tmp_path / "cache").glob("*"))


@pytest.mark.parametrize("cancel_kind", ["request", "owner"])
def test_cancellation_kills_owned_frame_process_and_publishes_nothing(
    tmp_path, monkeypatch, cancel_kind
):
    owner, row, processes, process = setup(tmp_path, monkeypatch)
    cancelled = threading.Event()
    original = process.communicate

    def delayed(self, **kwargs):
        if self.killed:
            return original(self, **kwargs)
        cancelled.set() if cancel_kind == "request" else owner.close()
        raise subprocess.TimeoutExpired(self.command, 0.1)

    monkeypatch.setattr(process, "communicate", delayed)
    assert owner.resolve(row, (1380, 350), "media", cancelled) is None
    assert processes[0].killed
    assert not list((tmp_path / "cache").glob("*"))


def test_failed_or_coverless_media_is_negatively_cached(tmp_path, monkeypatch):
    owner, row, processes, _ = setup(tmp_path, monkeypatch, data=b"not an image")
    for _ in range(8):
        assert owner.resolve(row, (1380, 350), "media", threading.Event()) is None
    assert len(processes) == 1
    assert not list((tmp_path / "cache").glob("*"))


def test_frame_timeout_kills_process_without_publishing(tmp_path, monkeypatch):
    owner, row, processes, process = setup(tmp_path, monkeypatch)
    clock = [1]
    monkeypatch.setattr(module.time, "monotonic", lambda: clock[0])
    original = process.communicate

    def delayed(self, **kwargs):
        if self.killed:
            return original(self, **kwargs)
        clock[0] += 5
        raise subprocess.TimeoutExpired(self.command, 0.1)

    monkeypatch.setattr(process, "communicate", delayed)
    assert owner.resolve(row, (1380, 350), "media", threading.Event()) is None
    assert processes[0].killed


def test_low_resolution_thumbnail_is_replaced_by_better_actual_frame(
    tmp_path, monkeypatch
):
    owner, row, processes, _ = setup(tmp_path, monkeypatch)
    small = tmp_path / "thumbnail.jpg"
    small.write_bytes(bitmap((320, 180), "red"))
    result = owner.resolve(row, (1380, 350), "media", threading.Event())
    assert result != small
    assert Image.open(result).size == (1920, 1080)
    assert len(processes) == 1


def test_same_owner_cancel_then_retry_launches_fresh_extraction(tmp_path, monkeypatch):
    owner, row, processes, process = setup(tmp_path, monkeypatch)
    cancelled = threading.Event()
    original = process.communicate

    def abandoned(self, **kwargs):
        if self.killed:
            return original(self, **kwargs)
        cancelled.set()
        raise subprocess.TimeoutExpired(self.command, 0.1)

    monkeypatch.setattr(process, "communicate", abandoned)
    assert owner.resolve(row, (1380, 350), "media", cancelled) is None
    assert processes[0].killed
    assert not owner._negative
    cancelled.clear()
    monkeypatch.setattr(process, "communicate", original)
    result = owner.resolve(row, (1380, 350), "media", cancelled)
    assert result and Image.open(result).size == (1920, 1080)
    assert len(processes) == 2
