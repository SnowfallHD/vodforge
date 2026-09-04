from __future__ import annotations

import json
import os
import sys
import time
import tkinter as tk
from pathlib import Path
from typing import Any

from .libvlc_backend import (
    LibVLCEngineOwner,
    LibVLCPlaybackBackend,
    find_libvlc_runtime,
)
from .playback_backend import MediaPlayerError
from .playback_surface import TkPlaybackSurfaceOwner
from .private_files import write_private_bytes


def _wait_for(
    root: tk.Tk,
    predicate: Any,
    *,
    timeout_seconds: float = 5.0,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        root.update()
        if predicate():
            return
        time.sleep(0.02)
    raise MediaPlayerError("The packaged playback engine did not become ready in time.")


def _sample_engine_clock(
    root: tk.Tk,
    backend: LibVLCPlaybackBackend,
    *,
    sample_seconds: float = 2.0,
) -> dict[str, float | int | bool]:
    """Confirm the engine clock advances smoothly without a Python frame clock."""

    backend.pause()
    seek_started = time.perf_counter()
    backend.seek(0.25)
    _wait_for(root, lambda: 0.15 <= backend.snapshot.position <= 0.75)
    seek_settle_ms = (time.perf_counter() - seek_started) * 1000
    backend.play()
    _wait_for(
        root,
        lambda: backend.snapshot.status == "Playing",
    )
    warmup_position = backend.snapshot.position
    warmup_started = time.perf_counter()
    _wait_for(root, lambda: backend.snapshot.position >= warmup_position + 0.35)
    warmup_ms = (time.perf_counter() - warmup_started) * 1000
    engine_start = backend.snapshot.position
    wall_start = time.perf_counter()
    previous = engine_start
    regressions = 0
    while time.perf_counter() - wall_start < sample_seconds:
        root.update()
        current = backend.snapshot.position
        if current + 0.08 < previous:
            regressions += 1
        previous = current
        time.sleep(0.02)
    wall_elapsed = time.perf_counter() - wall_start
    engine_elapsed = backend.snapshot.position - engine_start
    delta = engine_elapsed - wall_elapsed
    return {
        "wall_seconds": round(wall_elapsed, 3),
        "engine_seconds": round(engine_elapsed, 3),
        "delta_ms": round(delta * 1000, 1),
        "regressions": regressions,
        "seek_settle_ms": round(seek_settle_ms, 2),
        "resume_warmup_ms": round(warmup_ms, 2),
        "within_tolerance": not regressions and abs(delta) <= 0.35,
    }


def run_packaged_playback_probe(paths: tuple[Path, ...]) -> int:
    """Exercise the packaged native backend without constructing DownloaderApp."""

    receipt_path = os.environ.get("VODFORGE_PLAYBACK_SMOKE_RECEIPT", "").strip()
    receipt: dict[str, Any] = {
        "schema": 1,
        "platform": sys.platform,
        "backend": "libvlc",
        "one_engine_clock": True,
        "external_player_processes": 0,
        "steps": [],
        "success": False,
    }
    root: tk.Tk | None = None
    backend: LibVLCPlaybackBackend | None = None
    engine: LibVLCEngineOwner | None = None
    surface: TkPlaybackSurfaceOwner | None = None

    def checkpoint(phase: str) -> None:
        receipt["phase"] = phase
        if receipt_path:
            write_private_bytes(
                Path(receipt_path),
                json.dumps(receipt, sort_keys=True, indent=2).encode("utf-8"),
            )

    try:
        checkpoint("initialize")
        if not paths:
            raise MediaPlayerError("The packaged playback probe needs local media.")
        runtime = find_libvlc_runtime()
        if runtime is None:
            raise MediaPlayerError("The packaged libVLC runtime is missing.")
        root = tk.Tk()
        root.title("VODForge internal playback verification")
        root.geometry("720x480")
        stage = tk.Frame(root, bg="#000000")
        stage.pack(fill="both", expand=True)
        root.update_idletasks()

        engine = LibVLCEngineOwner(runtime=runtime)
        engine_started = time.perf_counter()
        engine.start()
        _wait_for(root, lambda: engine.ready or engine.failed, timeout_seconds=10.0)
        if not engine.ready:
            raise MediaPlayerError("The packaged playback engine could not warm.")
        receipt["steps"].append(
            {
                "action": "engine_warm",
                "elapsed_ms": round((time.perf_counter() - engine_started) * 1000, 2),
            }
        )
        surface = TkPlaybackSurfaceOwner(root, stage)
        backend = engine.create_backend()
        backend.attach_render_surface(surface.surface)

        for index, path in enumerate(paths):
            checkpoint(f"load:{index}:{path.suffix.casefold()}")
            backend.load(path)
            started = time.perf_counter()
            backend.play()
            _wait_for(root, lambda: backend.snapshot.status == "Playing")
            startup_ms = (time.perf_counter() - started) * 1000
            receipt["steps"].append(
                {
                    "action": "open_play" if index == 0 else "switch_file",
                    "extension": path.suffix.casefold(),
                    "startup_ms": round(startup_ms, 2),
                }
            )
            checkpoint(f"playing:{index}:{path.suffix.casefold()}")
            if index > 0:
                continue

            backend.pause()
            _wait_for(root, lambda: backend.snapshot.status == "Paused")
            backend.play()
            _wait_for(root, lambda: backend.snapshot.status == "Playing")
            duration = backend.snapshot.duration
            targets = (
                0.15,
                min(max(0.25, duration * 0.55), max(0.25, duration - 0.25)),
                min(max(0.25, duration - 0.35), max(0.25, duration)),
                0.05,
            )
            seek_latencies: list[float] = []
            for target in targets:
                started = time.perf_counter()
                backend.seek(target)
                seek_latencies.append((time.perf_counter() - started) * 1000)
                root.update()
            receipt["steps"].append(
                {
                    "action": "pause_resume_rapid_seek",
                    "seek_call_ms_max": round(max(seek_latencies), 2),
                    "count": len(targets),
                }
            )
            checkpoint("rapid_seek_complete")
            backend.set_volume(0)
            backend.set_volume(40)
            backend.set_volume(0)
            receipt["steps"].append({"action": "volume", "final": 0})
            checkpoint("volume_complete")
            clock_sample = _sample_engine_clock(root, backend)
            receipt["steps"].append({"action": "engine_clock", **clock_sample})
            checkpoint("clock_complete")
            if not clock_sample["within_tolerance"]:
                raise MediaPlayerError(
                    "The packaged playback clock did not advance smoothly enough."
                )
            root.geometry("940x620")
            root.update_idletasks()
            surface.refresh()
            receipt["steps"].append(
                {
                    "action": "resize",
                    "width": stage.winfo_width(),
                    "height": stage.winfo_height(),
                }
            )
            checkpoint("resize_complete")

        checkpoint("shutdown_before_reopen")
        backend.detach_render_surface()
        surface.close()
        close_started = time.perf_counter()
        backend.shutdown()
        close_return_ms = (time.perf_counter() - close_started) * 1000
        receipt["steps"].append(
            {
                "action": "close_return",
                "elapsed_ms": round(close_return_ms, 2),
            }
        )
        if close_return_ms > 500:
            raise MediaPlayerError("The player session blocked the UI while closing.")
        backend = engine.create_backend()
        surface = TkPlaybackSurfaceOwner(root, stage)
        backend.attach_render_surface(surface.surface)
        backend.load(paths[0])
        backend.set_volume(0)
        backend.play()
        _wait_for(root, lambda: backend.snapshot.status == "Playing")
        receipt["steps"].append({"action": "close_reopen", "status": "Playing"})
        receipt["success"] = True
        checkpoint("complete")
    except Exception as exc:  # noqa: BLE001 - probe must receipt every native failure
        receipt["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        if backend is not None:
            backend.detach_render_surface()
            backend.shutdown()
        if surface is not None:
            surface.close()
        if engine is not None:
            engine.shutdown(timeout_seconds=8.0)
        if root is not None:
            try:
                root.destroy()
            except tk.TclError:
                pass
        encoded = json.dumps(receipt, sort_keys=True, indent=2).encode("utf-8")
        if receipt_path:
            write_private_bytes(Path(receipt_path), encoded)
        else:
            print(encoded.decode("utf-8"))
    return 0 if receipt["success"] else 1
