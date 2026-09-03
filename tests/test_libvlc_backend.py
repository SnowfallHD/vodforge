from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from yt_downloader.libvlc_backend import LibVLCPlaybackBackend, LibVLCRuntime
from yt_downloader.playback_backend import MediaPlayerError, NativeRenderSurface


class FakeMedia:
    def __init__(self, path: str) -> None:
        self.path = path
        self.released = False

    def release(self) -> None:
        self.released = True


class FakePlayer:
    def __init__(self, states: SimpleNamespace) -> None:
        self.states = states
        self.state = states.NothingSpecial
        self.time = 0
        self.length = -1
        self.volume = 80
        self.media: FakeMedia | None = None
        self.surface_calls: list[tuple[str, int]] = []
        self.seek_calls: list[int] = []
        self.stop_calls = 0
        self.release_calls = 0
        self.actions: list[str] = []

    def audio_set_volume(self, value: int) -> int:
        self.volume = value
        return 0

    def get_state(self):
        return self.state

    def get_time(self):
        return self.time

    def get_length(self):
        return self.length

    def set_hwnd(self, handle: int) -> None:
        self.actions.append(f"hwnd:{handle}")
        self.surface_calls.append(("hwnd", handle))

    def set_nsobject(self, handle: int) -> None:
        self.actions.append(f"nsview:{handle}")
        self.surface_calls.append(("nsview", handle))

    def set_media(self, media: FakeMedia) -> None:
        self.media = media
        self.state = self.states.NothingSpecial
        self.time = 0

    def play(self) -> int:
        self.state = self.states.Playing
        return 0

    def set_pause(self, value: int) -> None:
        self.state = self.states.Paused if value else self.states.Playing

    def set_time(self, value: int) -> None:
        self.time = value
        self.seek_calls.append(value)

    def stop(self) -> None:
        self.actions.append("stop")
        self.stop_calls += 1
        self.state = self.states.Stopped
        self.time = 0

    def release(self) -> None:
        self.release_calls += 1


class FakeInstance:
    def __init__(self, player: FakePlayer) -> None:
        self.player = player
        self.media: list[FakeMedia] = []
        self.released = False

    def media_player_new(self) -> FakePlayer:
        return self.player

    def media_new_path(self, path: str) -> FakeMedia:
        media = FakeMedia(path)
        self.media.append(media)
        return media

    def release(self) -> None:
        self.released = True


class FakeVLC:
    State = SimpleNamespace(
        NothingSpecial=0,
        Opening=1,
        Buffering=2,
        Playing=3,
        Paused=4,
        Stopped=5,
        Ended=6,
        Error=7,
    )

    def __init__(self) -> None:
        self.player = FakePlayer(self.State)
        self.instance = FakeInstance(self.player)
        self.arguments: tuple[str, ...] = ()

    def Instance(self, *arguments: str) -> FakeInstance:
        self.arguments = arguments
        return self.instance


def make_backend() -> tuple[LibVLCPlaybackBackend, FakeVLC]:
    module = FakeVLC()
    backend = LibVLCPlaybackBackend(
        runtime=LibVLCRuntime(Path("/vlc"), Path("/vlc/libvlc"), Path("/vlc/plugins")),
        vlc_module=module,
    )
    return backend, module


def test_single_engine_owns_play_pause_seek_volume_and_time(tmp_path: Path) -> None:
    media = tmp_path / "video.mp4"
    media.write_bytes(b"video")
    backend, module = make_backend()
    backend.attach_render_surface(NativeRenderSurface("nsview", 4123))
    backend.load(media, duration=30)

    assert backend.play().status == "Playing"
    module.player.time = 4_250
    assert backend.snapshot.position == 4.25
    assert backend.pause().status == "Paused"
    assert backend.seek(11.5).position == 11.5
    assert backend.set_volume(37).volume == 37
    assert module.player.surface_calls == [("nsview", 4123)]
    assert module.player.seek_calls == [11_500]
    assert module.player.stop_calls == 1  # load only; controls never restart the engine
    assert "--avcodec-hw=any" in module.arguments
    assert "--no-metadata-network-access" in module.arguments


def test_load_switches_media_in_place_and_releases_previous(tmp_path: Path) -> None:
    first = tmp_path / "first.mp4"
    second = tmp_path / "second.mp3"
    first.write_bytes(b"first")
    second.write_bytes(b"second")
    backend, module = make_backend()
    backend.attach_render_surface(NativeRenderSurface("hwnd", 88))

    backend.load(first, duration=10)
    first_media = module.instance.media[0]
    backend.load(second, duration=20, audio_only=True)

    assert backend.snapshot.path == second
    assert first_media.released is True
    assert module.player.stop_calls == 2
    assert module.player.actions[-3:] == ["hwnd:0", "stop", "hwnd:88"]


def test_stop_detaches_and_restores_drawable_around_provider_stop(
    tmp_path: Path,
) -> None:
    media = tmp_path / "video.mp4"
    media.write_bytes(b"video")
    backend, module = make_backend()
    backend.attach_render_surface(NativeRenderSurface("nsview", 47))
    backend.load(media, duration=10)
    module.player.actions.clear()

    backend.stop()

    assert module.player.actions == ["nsview:0", "stop", "nsview:47"]


def test_shutdown_is_idempotent_and_releases_native_owners(tmp_path: Path) -> None:
    media = tmp_path / "video.mp4"
    media.write_bytes(b"video")
    backend, module = make_backend()
    backend.attach_render_surface(NativeRenderSurface("hwnd", 99))
    backend.load(media, duration=10)

    backend.shutdown()
    backend.shutdown()

    assert backend.snapshot.status == "Closed"
    assert module.player.surface_calls[-1] == ("hwnd", 0)
    assert module.player.actions[-2:] == ["hwnd:0", "stop"]
    assert module.player.release_calls == 1
    assert module.instance.released is True
    assert module.instance.media[0].released is True


def test_missing_file_fails_without_touching_engine(tmp_path: Path) -> None:
    backend, module = make_backend()

    with pytest.raises(MediaPlayerError, match="unavailable"):
        backend.load(tmp_path / "missing.mp4")

    assert module.player.stop_calls == 0


def test_provider_state_failure_becomes_an_immutable_failed_snapshot(
    tmp_path: Path,
) -> None:
    media = tmp_path / "video.mp4"
    media.write_bytes(b"video")
    backend, module = make_backend()
    backend.load(media, duration=12)

    def fail_state():
        raise RuntimeError("native provider unavailable")

    module.player.get_state = fail_state

    assert backend.snapshot.status == "Failed"
    assert backend.snapshot.error == "The local playback engine stopped responding."
