from __future__ import annotations

import json
import subprocess  # nosec B404 - fixed argv to trusted local media tools
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO

from .history import history_output_dir, history_output_path, history_output_type
from .platform_services import hidden_window_subprocess_kwargs
from .process_lifecycle import ActiveChildProcessRegistry

PLAYER_WIDTH = 768
PLAYER_HEIGHT = 432
PLAYER_FPS = 20
PLAYER_FRAME_BYTES = PLAYER_WIDTH * PLAYER_HEIGHT * 3


class MediaPlayerError(RuntimeError):
    """Raised when a local media item cannot be played safely."""


@dataclass(frozen=True, slots=True)
class PlaybackSnapshot:
    path: Path | None
    status: str
    position: float
    duration: float
    volume: int
    frame_sequence: int
    error: str = ""


def resolve_library_media_path(record: dict[str, Any]) -> Path | None:
    """Resolve one committed Library artifact without treating its row as authority."""

    exact = history_output_path(record)
    if exact is not None:
        try:
            if exact.is_file() and exact.stat().st_size > 0:
                return exact
        except OSError:
            return None
    output_dir = history_output_dir(record)
    if output_dir is None:
        return None
    extension = ".mp3" if history_output_type(record) == "MP3" else ".mp4"
    try:
        candidates = sorted(
            (
                child
                for child in output_dir.iterdir()
                if child.suffix.casefold() == extension
                and child.is_file()
                and child.stat().st_size > 0
            ),
            key=lambda path: path.name.casefold(),
        )
    except OSError:
        return None
    return candidates[0] if len(candidates) == 1 else None


def probe_media_duration(
    ffprobe: str,
    path: Path,
    *,
    runner: Callable[..., Any] = subprocess.run,
) -> float:
    """Read duration through a fixed ffprobe query and reject malformed output."""

    try:
        result = runner(  # nosec B603 - executable is resolved by platform service
            [
                ffprobe,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "json",
                str(path),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
            **hidden_window_subprocess_kwargs(),
        )
        value = float(json.loads(result.stdout)["format"]["duration"])
    except (
        OSError,
        subprocess.SubprocessError,
        ValueError,
        KeyError,
        TypeError,
    ) as exc:
        raise MediaPlayerError("VODForge could not read this media duration.") from exc
    if not 0 < value < 60 * 60 * 48:
        raise MediaPlayerError("This media item reports an invalid duration.")
    return value


class MediaPlaybackOwner:
    """Own local playback state and child processes independently of download runs."""

    def __init__(
        self,
        *,
        ffmpeg: str,
        ffprobe: str,
        ffplay: str,
        diagnostic: Callable[[str], None] | None = None,
        popen: Callable[..., Any] = subprocess.Popen,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.ffmpeg = ffmpeg
        self.ffprobe = ffprobe
        self.ffplay = ffplay
        self._diagnostic = diagnostic or (lambda _message: None)
        self._popen = popen
        self._clock = clock
        self._playback_registry = ActiveChildProcessRegistry(
            diagnostic=self._diagnostic
        )
        self._preview_registry = ActiveChildProcessRegistry(diagnostic=self._diagnostic)
        self._lock = threading.RLock()
        self._path: Path | None = None
        self._audio_only = False
        self._status = "Idle"
        self._position = 0.0
        self._duration = 0.0
        self._volume = 80
        self._started_at = 0.0
        self._generation = 0
        self._frame_sequence = 0
        self._latest_frame: bytes | None = None
        self._error = ""

    @property
    def snapshot(self) -> PlaybackSnapshot:
        with self._lock:
            position = self._position
            status = self._status
            if status == "Playing":
                position = min(
                    self._duration,
                    self._position + max(0.0, self._clock() - self._started_at),
                )
                if position >= self._duration:
                    status = "Ended"
            return PlaybackSnapshot(
                path=self._path,
                status=status,
                position=position,
                duration=self._duration,
                volume=self._volume,
                frame_sequence=self._frame_sequence,
                error=self._error,
            )

    def latest_frame(self, sequence: int) -> tuple[int, bytes | None]:
        with self._lock:
            if sequence == self._frame_sequence:
                return sequence, None
            return self._frame_sequence, self._latest_frame

    def load(
        self,
        path: Path,
        *,
        duration: float | None = None,
        audio_only: bool | None = None,
    ) -> PlaybackSnapshot:
        self.stop(reset=True)
        try:
            media_path = path.expanduser().resolve(strict=True)
            if not media_path.is_file() or media_path.stat().st_size <= 0:
                raise MediaPlayerError("The saved media file is missing or empty.")
        except OSError as exc:
            raise MediaPlayerError("The saved media file is unavailable.") from exc
        media_duration = float(duration or 0)
        if media_duration <= 0:
            media_duration = probe_media_duration(self.ffprobe, media_path)
        with self._lock:
            self._path = media_path
            self._duration = media_duration
            self._position = 0.0
            self._audio_only = (
                media_path.suffix.casefold() == ".mp3"
                if audio_only is None
                else audio_only
            )
            self._status = "Ready"
            self._error = ""
            self._latest_frame = None
            self._frame_sequence += 1
        return self.snapshot

    def play(self) -> PlaybackSnapshot:
        if self.snapshot.status == "Ended":
            self.stop(reset=True)
        with self._lock:
            if self._path is None:
                raise MediaPlayerError("Choose a saved Library item first.")
            if self._status == "Playing":
                return self.snapshot
            self._generation += 1
            generation = self._generation
            path = self._path
            offset = self._position
            volume = self._volume
            audio_only = self._audio_only
            self._status = "Playing"
            self._started_at = self._clock()
            self._error = ""
        try:
            self._spawn_audio(path, offset, volume, generation)
            if not audio_only:
                self._spawn_video(path, offset, generation)
        except (OSError, subprocess.SubprocessError) as exc:
            self._playback_registry.terminate_all(timeout_seconds=1.0)
            with self._lock:
                self._status = "Failed"
                self._error = "The local playback engine could not start."
            raise MediaPlayerError(self._error) from exc
        return self.snapshot

    def preview_png(self, position: float) -> bytes:
        """Generate one bounded preview under the player's process owner."""

        with self._lock:
            path = self._path
        if path is None:
            raise MediaPlayerError("Choose a saved Library item first.")
        try:
            process = self._popen(  # nosec B603 - fixed argv to resolved ffmpeg
                [
                    self.ffmpeg,
                    "-nostdin",
                    "-v",
                    "error",
                    "-ss",
                    f"{max(0.0, position):.3f}",
                    "-i",
                    str(path),
                    "-frames:v",
                    "1",
                    "-vf",
                    "scale=192:108:force_original_aspect_ratio=decrease,pad=192:108:(ow-iw)/2:(oh-ih)/2",
                    "-f",
                    "image2pipe",
                    "-vcodec",
                    "png",
                    "pipe:1",
                ],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                **hidden_window_subprocess_kwargs(),
            )
            self._preview_registry.register(process, timeout_seconds=1.0)
            output, _stderr = process.communicate(timeout=12)
        except (OSError, subprocess.SubprocessError) as exc:
            raise MediaPlayerError(
                "A preview thumbnail could not be generated."
            ) from exc
        finally:
            if "process" in locals():
                self._preview_registry.finalize(
                    process,
                    timeout_seconds=1.0,
                    confirmed_exited=process.poll() is not None,
                )
        with self._lock:
            if path != self._path or self._status == "Closed":
                raise MediaPlayerError("Preview generation was cancelled.")
        if not output or len(output) > 5 * 1024 * 1024:
            raise MediaPlayerError("A preview thumbnail was invalid.")
        return bytes(output)

    def pause(self) -> PlaybackSnapshot:
        with self._lock:
            if self._status != "Playing":
                return self.snapshot
            self._position = min(
                self._duration,
                self._position + max(0.0, self._clock() - self._started_at),
            )
            self._status = "Paused"
            self._generation += 1
        self._playback_registry.terminate_all(timeout_seconds=1.0)
        return self.snapshot

    def toggle(self) -> PlaybackSnapshot:
        return self.pause() if self.snapshot.status == "Playing" else self.play()

    def seek(self, position: float) -> PlaybackSnapshot:
        with self._lock:
            target = min(self._duration, max(0.0, float(position)))
            playing = self._status == "Playing"
            self._position = target
            self._status = "Paused"
            self._started_at = self._clock()
            self._generation += 1
        self._playback_registry.terminate_all(timeout_seconds=1.0)
        return self.play() if playing else self.snapshot

    def set_volume(self, value: int) -> PlaybackSnapshot:
        with self._lock:
            volume = min(100, max(0, int(value)))
            if volume == self._volume:
                return self.snapshot
            playing = self._status == "Playing"
            current = self.snapshot.position
            self._volume = volume
            if playing:
                self._position = current
                self._started_at = self._clock()
                self._generation += 1
                self._status = "Paused"
        if playing:
            self._playback_registry.terminate_all(timeout_seconds=1.0)
            return self.play()
        return self.snapshot

    def stop(self, *, reset: bool = False) -> PlaybackSnapshot:
        with self._lock:
            if self._status == "Playing":
                self._position = min(
                    self._duration,
                    self._position + max(0.0, self._clock() - self._started_at),
                )
            self._generation += 1
            self._status = "Ready" if reset and self._path is not None else "Stopped"
            if reset:
                self._position = 0.0
        self._playback_registry.terminate_all(timeout_seconds=1.0)
        return self.snapshot

    def close(self) -> None:
        with self._lock:
            self._generation += 1
            self._status = "Closed"
        self._playback_registry.terminate_all(timeout_seconds=1.5)
        self._preview_registry.terminate_all(timeout_seconds=1.5)

    def _spawn_audio(
        self, path: Path, offset: float, volume: int, generation: int
    ) -> None:
        process = self._popen(  # nosec B603 - fixed argv to resolved ffplay
            [
                self.ffplay,
                "-nodisp",
                "-autoexit",
                "-loglevel",
                "error",
                "-ss",
                f"{offset:.3f}",
                "-volume",
                str(volume),
                str(path),
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            **hidden_window_subprocess_kwargs(),
        )
        self._playback_registry.register(process, timeout_seconds=1.0)
        threading.Thread(
            target=self._reap_audio_process,
            args=(process, generation),
            daemon=True,
            name="vodforge-player-audio",
        ).start()

    def _spawn_video(self, path: Path, offset: float, generation: int) -> None:
        process = self._popen(  # nosec B603 - fixed argv to resolved ffmpeg
            [
                self.ffmpeg,
                "-nostdin",
                "-v",
                "error",
                "-re",
                "-ss",
                f"{offset:.3f}",
                "-i",
                str(path),
                "-an",
                "-vf",
                (
                    f"fps={PLAYER_FPS},scale={PLAYER_WIDTH}:{PLAYER_HEIGHT}:"
                    "force_original_aspect_ratio=decrease,"
                    f"pad={PLAYER_WIDTH}:{PLAYER_HEIGHT}:(ow-iw)/2:(oh-ih)/2"
                ),
                "-pix_fmt",
                "rgb24",
                "-f",
                "rawvideo",
                "pipe:1",
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            bufsize=PLAYER_FRAME_BYTES * 2,
            **hidden_window_subprocess_kwargs(),
        )
        self._playback_registry.register(process, timeout_seconds=1.0)
        threading.Thread(
            target=self._read_frames,
            args=(process, generation),
            daemon=True,
            name="vodforge-player-video",
        ).start()

    def _read_frames(self, process: Any, generation: int) -> None:
        stream: BinaryIO | None = process.stdout
        if stream is None:
            return
        try:
            while True:
                frame = stream.read(PLAYER_FRAME_BYTES)
                if len(frame) != PLAYER_FRAME_BYTES:
                    break
                with self._lock:
                    if generation != self._generation or self._status != "Playing":
                        break
                    self._latest_frame = frame
                    self._frame_sequence += 1
        except (OSError, ValueError) as exc:
            self._diagnostic(f"media player frame reader stopped: {type(exc).__name__}")
        finally:
            self._playback_registry.finalize(
                process,
                timeout_seconds=1.0,
                confirmed_exited=process.poll() is not None,
            )

    def _reap_audio_process(self, process: Any, generation: int) -> None:
        return_code: int | None = None
        failed = False
        try:
            return_code = process.wait()
        except (OSError, subprocess.SubprocessError) as exc:
            self._diagnostic(
                f"media player audio process stopped: {type(exc).__name__}"
            )
            failed = True
        finally:
            self._playback_registry.finalize(
                process,
                timeout_seconds=1.0,
                confirmed_exited=process.poll() is not None,
            )
        if return_code not in (None, 0):
            failed = True
        if not failed:
            return
        with self._lock:
            if generation != self._generation or self._status != "Playing":
                return
            self._generation += 1
            self._status = "Failed"
            self._error = "The local playback engine stopped unexpectedly."
        self._playback_registry.terminate_all(timeout_seconds=1.0)
