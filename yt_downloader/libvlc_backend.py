from __future__ import annotations

import ctypes
import importlib
import os
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .playback_backend import (
    MediaPlayerError,
    NativeRenderSurface,
    PlaybackSnapshot,
    PlaybackStatus,
)

VLC_RUNTIME_VERSION = "3.0.23"


@dataclass(frozen=True, slots=True)
class LibVLCRuntime:
    """Resolved, self-contained libVLC runtime layout."""

    root: Path
    library: Path
    plugins: Path


_dll_directory_handles: list[Any] = []


def _runtime_from_root(root: Path) -> LibVLCRuntime | None:
    plugins = root / "plugins"
    if sys.platform == "darwin":
        library = root / "lib" / "libvlc.dylib"
        core = root / "lib" / "libvlccore.dylib"
        if not (library.is_file() and core.is_file() and plugins.is_dir()):
            return None
    elif sys.platform == "win32":
        library = root / "libvlc.dll"
        core = root / "libvlccore.dll"
        if not (library.is_file() and core.is_file() and plugins.is_dir()):
            return None
    else:
        return None
    return LibVLCRuntime(root=root, library=library, plugins=plugins)


def find_libvlc_runtime() -> LibVLCRuntime | None:
    """Find only an explicitly installed or VODForge-bundled libVLC runtime."""

    candidates: list[Path] = []
    override = os.environ.get("VODFORGE_VLC_RUNTIME", "").strip()
    if override:
        candidates.append(Path(override).expanduser())

    frozen_root = getattr(sys, "_MEIPASS", None)
    if frozen_root:
        candidates.extend(
            (
                Path(frozen_root) / "vlc",
                Path(sys.executable).resolve().parent / "vlc",
                Path(sys.executable).resolve().parent.parent / "Resources" / "vlc",
                Path(sys.executable).resolve().parent.parent / "Frameworks" / "vlc",
            )
        )
    repository_root = Path(__file__).resolve().parent.parent
    candidates.append(repository_root / "vendor" / "vlc")
    if sys.platform == "darwin":
        candidates.append(Path("/Applications/VLC.app/Contents/MacOS"))
    elif sys.platform == "win32":
        for environment_name in ("ProgramFiles", "ProgramFiles(x86)"):
            program_files = os.environ.get(environment_name)
            if program_files:
                candidates.append(Path(program_files) / "VideoLAN" / "VLC")

    seen: set[Path] = set()
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if resolved in seen:
            continue
        seen.add(resolved)
        runtime = _runtime_from_root(resolved)
        if runtime is not None:
            return runtime
    return None


def load_vlc_module(runtime: LibVLCRuntime) -> Any:
    """Load python-vlc against the exact resolved runtime, including plugins."""

    if sys.platform == "darwin":
        core = runtime.root / "lib" / "libvlccore.dylib"
        try:
            ctypes.CDLL(str(core), mode=ctypes.RTLD_GLOBAL)
        except OSError as exc:
            raise MediaPlayerError(
                "The bundled VODForge playback engine could not be loaded."
            ) from exc
    os.environ["PYTHON_VLC_LIB_PATH"] = str(runtime.library)
    os.environ["PYTHON_VLC_MODULE_PATH"] = str(runtime.plugins)
    os.environ["VLC_PLUGIN_PATH"] = str(runtime.plugins)
    if sys.platform == "win32" and hasattr(os, "add_dll_directory"):
        _dll_directory_handles.append(os.add_dll_directory(str(runtime.root)))
    try:
        return importlib.import_module("vlc")
    except (ImportError, OSError, SystemExit) as exc:
        raise MediaPlayerError(
            "The bundled VODForge playback engine could not be loaded."
        ) from exc


def probe_libvlc_runtime(runtime: LibVLCRuntime) -> str:
    """Initialize the exact runtime and return its provider version."""

    module = load_vlc_module(runtime)
    instance = None
    try:
        instance = module.Instance("--intf=dummy", "--quiet")
        if instance is None:
            raise RuntimeError("libVLC returned no instance")
        raw_version = module.libvlc_get_version()
        if isinstance(raw_version, bytes):
            version = raw_version.decode("utf-8", errors="replace")
        else:
            version = str(raw_version)
        if not version.strip():
            raise RuntimeError("libVLC returned no version")
        return version.strip()
    finally:
        if instance is not None:
            instance.release()


class LibVLCPlaybackBackend:
    """Own one libVLC player and expose only engine-authoritative playback state."""

    def __init__(
        self,
        *,
        runtime: LibVLCRuntime,
        diagnostic: Callable[[str], None] | None = None,
        vlc_module: Any | None = None,
    ) -> None:
        self.runtime = runtime
        self._diagnostic = diagnostic or (lambda _message: None)
        self._vlc = vlc_module or load_vlc_module(runtime)
        self._lock = threading.RLock()
        self._path: Path | None = None
        self._duration_hint = 0.0
        self._volume = 80
        self._error = ""
        self._closed = False
        self._surface: NativeRenderSurface | None = None
        self._media: Any | None = None
        try:
            self._instance = self._vlc.Instance(
                "--intf=dummy",
                "--no-video-title-show",
                "--no-osd",
                "--no-metadata-network-access",
                "--quiet",
                "--avcodec-hw=any",
                "--file-caching=120",
            )
            if self._instance is None:
                raise RuntimeError("libVLC returned no instance")
            self._player = self._instance.media_player_new()
            if self._player is None:
                raise RuntimeError("libVLC returned no player")
            self._player.audio_set_volume(self._volume)
            self._attach_provider_events()
        except Exception as exc:
            self._diagnostic(f"libVLC initialization failed: {type(exc).__name__}")
            raise MediaPlayerError(
                "The bundled VODForge playback engine could not initialize."
            ) from exc

    @property
    def snapshot(self) -> PlaybackSnapshot:
        with self._lock:
            if self._closed:
                return PlaybackSnapshot(
                    path=self._path,
                    status="Closed",
                    position=0.0,
                    duration=self._duration_hint,
                    volume=self._volume,
                )
            path = self._path
            error = self._error
            if path is None:
                status: PlaybackStatus = "Idle"
                position_ms = 0.0
                duration_ms = 0.0
            else:
                try:
                    status = self._translate_state(self._player.get_state())
                    position_ms = self._safe_nonnegative(self._player.get_time())
                    duration_ms = self._safe_nonnegative(self._player.get_length())
                except Exception as exc:  # noqa: BLE001 - provider state is isolated
                    self._diagnostic(f"libVLC state read failed: {type(exc).__name__}")
                    status = "Failed"
                    position_ms = 0.0
                    duration_ms = 0.0
                    error = "The local playback engine stopped responding."
                if status == "Failed" and not error:
                    error = "The local media file could not be played."
            duration = duration_ms / 1000 if duration_ms > 0 else self._duration_hint
            position = position_ms / 1000
            if duration > 0:
                position = min(position, duration)
            return PlaybackSnapshot(
                path=path,
                status=status,
                position=position,
                duration=duration,
                volume=self._volume,
                error=error,
            )

    def attach_render_surface(self, surface: NativeRenderSurface) -> None:
        with self._lock:
            self._ensure_open()
            try:
                self._bind_provider_surface(surface)
            except Exception as exc:
                raise MediaPlayerError(
                    "VODForge could not attach its internal playback surface."
                ) from exc
            self._surface = surface

    def detach_render_surface(self) -> None:
        with self._lock:
            if self._closed or self._surface is None:
                return
            try:
                self._bind_provider_surface(None)
            except Exception as exc:  # noqa: BLE001 - teardown remains best effort
                self._diagnostic(f"libVLC surface detach failed: {type(exc).__name__}")
            finally:
                self._surface = None

    def load(
        self,
        path: Path,
        *,
        duration: float | None = None,
        audio_only: bool | None = None,
    ) -> PlaybackSnapshot:
        del audio_only  # libVLC discovers the media tracks itself.
        try:
            media_path = path.expanduser().resolve(strict=True)
            if not media_path.is_file() or media_path.stat().st_size <= 0:
                raise MediaPlayerError("The saved media file is missing or empty.")
        except OSError as exc:
            raise MediaPlayerError("The saved media file is unavailable.") from exc
        with self._lock:
            self._ensure_open()
            previous = self._media
            surface = self._surface if previous is not None else None
            try:
                if surface is not None:
                    self._bind_provider_surface(None)
                self._stop_provider()
                media = self._instance.media_new_path(str(media_path))
                self._player.set_media(media)
                self._player.audio_set_volume(self._volume)
            except Exception as exc:
                raise MediaPlayerError(
                    "VODForge could not load this media file."
                ) from exc
            finally:
                if surface is not None:
                    self._bind_provider_surface(surface)
            self._media = media
            self._path = media_path
            self._duration_hint = self._bounded_duration(duration)
            self._error = ""
            if previous is not None:
                try:
                    previous.release()
                except Exception as exc:  # noqa: BLE001 - provider cleanup is best effort
                    self._diagnostic(
                        f"libVLC previous media release failed: {type(exc).__name__}"
                    )
        return self.snapshot

    def play(self) -> PlaybackSnapshot:
        with self._lock:
            self._ensure_loaded()
            if self.snapshot.status == "Ended":
                self._player.set_time(0)
            try:
                result = self._player.play()
            except Exception as exc:  # noqa: BLE001 - native provider failures are translated
                return self._fail("The local playback engine could not start.", exc)
            if result == -1:
                return self._fail("The local playback engine could not start.")
            self._error = ""
        return self.snapshot

    def pause(self) -> PlaybackSnapshot:
        with self._lock:
            self._ensure_loaded()
            try:
                self._player.set_pause(1)
            except Exception as exc:  # noqa: BLE001 - native provider failures are translated
                return self._fail("The local playback engine could not pause.", exc)
        return self.snapshot

    def toggle(self) -> PlaybackSnapshot:
        return (
            self.pause()
            if self.snapshot.status in {"Playing", "Starting"}
            else self.play()
        )

    def seek(self, position: float) -> PlaybackSnapshot:
        with self._lock:
            self._ensure_loaded()
            duration = self.snapshot.duration
            target = max(0.0, float(position))
            if duration > 0:
                target = min(duration, target)
            try:
                self._player.set_time(round(target * 1000))
            except Exception as exc:  # noqa: BLE001 - native provider failures are translated
                return self._fail("The local playback engine could not seek.", exc)
        return self.snapshot

    def set_volume(self, value: int) -> PlaybackSnapshot:
        volume = min(100, max(0, int(value)))
        with self._lock:
            self._ensure_open()
            try:
                result = self._player.audio_set_volume(volume)
            except Exception as exc:  # noqa: BLE001 - native provider failures are translated
                return self._fail(
                    "The local playback engine could not change volume.", exc
                )
            if result == -1:
                state = self._translate_state(self._player.get_state())
                if state in {"Playing", "Paused"}:
                    return self._fail(
                        "The local playback engine could not change volume."
                    )
            self._volume = volume
        return self.snapshot

    def stop(self) -> PlaybackSnapshot:
        with self._lock:
            self._ensure_open()
            surface = self._surface
            try:
                if surface is not None:
                    self._bind_provider_surface(None)
                self._stop_provider()
            except Exception as exc:  # noqa: BLE001 - native provider failures are translated
                return self._fail("The local playback engine could not stop.", exc)
            finally:
                if surface is not None:
                    self._bind_provider_surface(surface)
        return self.snapshot

    def shutdown(self) -> None:
        with self._lock:
            if self._closed:
                return
            # Detach the platform drawable before stopping. On macOS, stopping
            # a just-started video while its CAOpenGLLayer is still attached can
            # synchronously wait on the Tk/AppKit main thread and deadlock app
            # shutdown. LibVLC owns playback; the surface owner remains alive
            # until this method returns, so this ordering is deterministic.
            self.detach_render_surface()
            try:
                self._stop_provider()
            except Exception as exc:  # noqa: BLE001 - provider cleanup is best effort
                self._diagnostic(
                    f"libVLC stop during shutdown failed: {type(exc).__name__}"
                )
            media = self._media
            self._media = None
            self._closed = True
            for owner in (self._player, media, self._instance):
                if owner is None:
                    continue
                try:
                    owner.release()
                except Exception as exc:  # noqa: BLE001 - provider cleanup is best effort
                    self._diagnostic(
                        f"libVLC release during shutdown failed: {type(exc).__name__}"
                    )

    def _translate_state(self, state: Any) -> PlaybackStatus:
        mapping: dict[Any, PlaybackStatus] = {
            self._vlc.State.NothingSpecial: "Ready",
            self._vlc.State.Opening: "Starting",
            self._vlc.State.Buffering: "Starting",
            self._vlc.State.Playing: "Playing",
            self._vlc.State.Paused: "Paused",
            self._vlc.State.Stopped: "Stopped",
            self._vlc.State.Ended: "Ended",
            self._vlc.State.Error: "Failed",
        }
        return mapping.get(state, "Ready")

    def _bind_provider_surface(
        self,
        surface: NativeRenderSurface | None,
    ) -> None:
        """Bind or clear the native drawable without changing surface ownership."""

        current = surface or self._surface
        if current is None:
            return
        handle = surface.handle if surface is not None else 0
        if current.kind == "hwnd":
            self._player.set_hwnd(handle)
        elif current.kind == "nsview":
            self._player.set_nsobject(handle)
        else:  # pragma: no cover - closed by the value type
            raise MediaPlayerError("Unsupported native playback surface.")

    def _stop_provider(self) -> None:
        """Stop libVLC while servicing native drawable teardown messages."""

        if threading.current_thread() is not threading.main_thread():
            self._player.stop()
            return

        if sys.platform == "darwin":
            # VLC 3's CAOpenGLLayer output synchronously dispatches part of
            # teardown to Cocoa's main queue. Tk must keep that queue moving.
            try:
                from Foundation import (  # type: ignore[import-untyped]
                    NSDate,
                    NSDefaultRunLoopMode,
                    NSRunLoop,
                )
            except ImportError as exc:  # pragma: no cover - packaging contract
                raise MediaPlayerError(
                    "The macOS playback bridge could not stop cleanly."
                ) from exc

            run_loop = NSRunLoop.currentRunLoop()

            def service_native_events() -> None:
                run_loop.runMode_beforeDate_(
                    NSDefaultRunLoopMode,
                    NSDate.dateWithTimeIntervalSinceNow_(0.01),
                )

        elif sys.platform == "win32":
            # Windows video outputs can synchronously message the host HWND
            # during teardown. Keep that owning thread responsive too.
            service_native_events = self._service_windows_messages
        else:
            self._player.stop()
            return

        self._run_provider_stop_with_pump(service_native_events)

    def _run_provider_stop_with_pump(self, pump_events: Callable[[], None]) -> None:
        """Run blocking provider teardown off-thread and pump the host surface."""

        finished = threading.Event()
        provider_error: list[Exception] = []

        def stop_player() -> None:
            try:
                self._player.stop()
            except Exception as exc:  # noqa: BLE001 - translated on the owner thread
                provider_error.append(exc)
            finally:
                finished.set()

        worker = threading.Thread(
            target=stop_player,
            name="vodforge-libvlc-stop",
            daemon=True,
        )
        worker.start()
        deadline = time.monotonic() + 5.0
        while not finished.is_set():
            if time.monotonic() >= deadline:
                raise MediaPlayerError(
                    "The local playback engine did not stop cleanly."
                )
            pump_events()
            finished.wait(0.005)
        worker.join()
        if provider_error:
            raise provider_error[0]

    @staticmethod
    def _service_windows_messages() -> None:
        """Dispatch pending messages for the Tk-owned native video HWND."""

        class Point(ctypes.Structure):
            _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

        class Message(ctypes.Structure):
            _fields_ = [
                ("hwnd", ctypes.c_void_p),
                ("message", ctypes.c_uint),
                ("w_param", ctypes.c_size_t),
                ("l_param", ctypes.c_ssize_t),
                ("time", ctypes.c_ulong),
                ("point", Point),
                ("private", ctypes.c_ulong),
            ]

        user32 = ctypes.windll.user32  # type: ignore[attr-defined]
        message = Message()
        while user32.PeekMessageW(ctypes.byref(message), None, 0, 0, 1):
            user32.TranslateMessage(ctypes.byref(message))
            user32.DispatchMessageW(ctypes.byref(message))

    def _attach_provider_events(self) -> None:
        """Use libVLC's event edge only to apply settings when output exists."""

        try:
            event_manager = self._player.event_manager()
            event_manager.event_attach(
                self._vlc.EventType.MediaPlayerPlaying,
                self._playback_started,
            )
            self._event_manager = event_manager
        except (AttributeError, TypeError):
            self._event_manager = None

    def _playback_started(self, _event: Any) -> None:
        with self._lock:
            if self._closed:
                return
            try:
                self._player.audio_set_volume(self._volume)
            except Exception as exc:  # noqa: BLE001 - provider callback remains isolated
                self._diagnostic(
                    f"libVLC deferred volume application failed: {type(exc).__name__}"
                )

    def _fail(self, message: str, exc: Exception | None = None) -> PlaybackSnapshot:
        if exc is not None:
            self._diagnostic(f"libVLC playback failure: {type(exc).__name__}")
        self._error = message
        raise MediaPlayerError(message) from exc

    def _ensure_open(self) -> None:
        if self._closed:
            raise MediaPlayerError("This VODForge player has already closed.")

    def _ensure_loaded(self) -> None:
        self._ensure_open()
        if self._path is None:
            raise MediaPlayerError("Choose a saved Library item first.")

    @staticmethod
    def _safe_nonnegative(value: Any) -> float:
        try:
            return max(0.0, float(value))
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _bounded_duration(value: float | None) -> float:
        try:
            duration = float(value or 0)
        except (TypeError, ValueError):
            return 0.0
        return duration if 0 < duration < 60 * 60 * 48 else 0.0
