"""Opt-in source-native queue proof using separate files and actual libVLC Ended."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.focus_ui_preview import isolated_preview_services
from tests.test_archive_actual_playback import until
from tests.test_archive_models import saved
from yt_downloader import app as app_module
from yt_downloader.analytics_startup import AnalyticsStartup
from yt_downloader.engagement_ui import EngagementUI
from yt_downloader.platform_services import find_runtime_executable
from yt_downloader.watch_library import watch_channels, watch_rails

pytestmark = pytest.mark.skipif(
    os.environ.get("VODFORGE_ACTUAL_PLAYBACK_TESTS") != "1",
    reason="explicit real-provider native queue run required",
)


@pytest.mark.parametrize(
    "kind,shuffled,mode,volume,count,scenario",
    [
        ("playlist", False, "embedded", 50, 3, "complete"),
        ("channel", True, "floating", 0, 3, "complete"),
        ("playlist", False, "fullscreen", 100, 2, "complete"),
        ("playlist", False, "embedded", 0, 1, "complete"),
        ("playlist", False, "fullscreen", 50, 2, "constructor"),
        ("playlist", False, "fullscreen", 50, 3, "audio"),
    ],
)
def test_actual_files_advance_release_and_preserve_user_controls(
    tmp_path, monkeypatch, kind, shuffled, mode, volume, count, scenario
):
    runtime = app_module.find_libvlc_runtime()
    ffmpeg = find_runtime_executable("ffmpeg")
    assert runtime is not None and ffmpeg
    rows, originals, commands = [], {}, []
    from PIL import Image

    for index in range(count):
        folder = tmp_path / str(index)
        folder.mkdir()
        audio = scenario == "audio" and index == 1
        media = folder / ("episode.m4a" if audio else "episode.mp4")
        command = [
            ffmpeg,
            "-nostdin",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"testsrc2=size=640x360:rate=24, hue=h={index * 80}",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency={220 + index * 110}:sample_rate=48000",
            "-t",
            "7",
            "-af",
            "volume=0.005",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            str(media),
        ]
        if audio:
            command = [
                ffmpeg,
                "-nostdin",
                "-v",
                "error",
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=330:sample_rate=48000",
                "-t",
                "7",
                "-af",
                "volume=0.005",
                "-c:a",
                "aac",
                str(media),
            ]
        result = subprocess.run(
            command, check=False, capture_output=True, text=True, timeout=30
        )
        assert result.returncode == 0, result.stderr
        commands.append(command)
        originals[str(media)] = hashlib.sha256(media.read_bytes()).hexdigest()
        Image.new("RGB", (640, 360), ("#1c4272", "#634171", "#417153")[index]).save(
            folder / "thumbnail.jpeg"
        )
        rows.append(
            dict(
                saved(
                    media,
                    video=f"queue-{index}",
                    playlist="Queue fixture",
                    channel="Synthetic creator",
                    kind="Original audio" if audio else "MP4",
                ),
                playlist_index=index + 1,
                duration=7,
                vodforge_run_id=f"queue-native-{index}",
            )
        )
    evidence = {
        "kind": kind,
        "shuffle": shuffled,
        "presentation": mode,
        "volume": volume,
        "count": count,
        "scenario": scenario,
        "physical_input": False,
        "actual_provider_ended": True,
        "callback_errors": [],
        "players": [],
        "events": [],
        "commands": commands,
    }
    app = None
    monkeypatch.setattr(AnalyticsStartup, "start", lambda self: None)
    monkeypatch.setattr(EngagementUI, "start", lambda self: None)
    try:
        with (
            isolated_preview_services(),
            patch.object(app_module, "find_libvlc_runtime", return_value=runtime),
        ):
            app = app_module.DownloaderApp()
            app.report_callback_exception = lambda *args: evidence[
                "callback_errors"
            ].append(repr(args))
            app.geometry("1280x850")
            app.deiconify()
            app.download_history = rows
            app._reconcile_library_projection()
            app._select_focus_view("watch")
            until(app, lambda: app.focus_watch._render_after is None)
            app.watch_queue._observe = lambda action, operation, dimensions, **extra: (
                evidence["events"].append(
                    {
                        "action": action,
                        "operation": operation,
                        "dimensions": dimensions,
                        "failure_detail": extra["failure_detail"].payload()
                        if extra.get("failure_detail")
                        else None,
                    }
                )
            )
            # Deterministic shuffle still goes through the real shuffle route.
            app.watch_queue._shuffle = lambda keys: keys.reverse()
            videos = (
                watch_channels(app.metadata_items)[0].videos
                if kind == "channel"
                else watch_rails(app.metadata_items)[0].videos
            )
            original_player = app_module.MediaPlayerWindow
            constructed = []

            def construct(*args, **kwargs):
                if scenario == "constructor" and constructed:
                    raise RuntimeError("Synthetic player construction refusal")
                player = original_player(*args, **kwargs)
                constructed.append(player)
                return player

            monkeypatch.setattr(app_module, "MediaPlayerWindow", construct)
            app.focus_watch._scene_start_queue(videos, kind, shuffled)
            seen = []
            previous = None
            presentation_window = None
            expected = list(originals)
            if shuffled:
                expected.reverse()
            for index in range(count):
                if scenario == "constructor" and index == 1:
                    until(
                        app,
                        lambda: (
                            app.watch_queue.token is None
                            and app.status_var.get() == "Playback needs attention"
                        ),
                        timeout=20,
                    )
                    assert not presentation_window.winfo_exists()
                    assert "_archive_queue_presentation" not in app.__dict__
                    assert app._media_player_window is None
                    evidence["failed_host_closed"] = True
                    break
                audio = scenario == "audio" and index == 1
                expected_mode = (
                    "embedded" if scenario == "audio" and index >= 1 else mode
                )
                until(
                    app,
                    lambda old=previous: (
                        app._media_player_window is not None
                        and app._media_player_window is not old
                        and app._media_player_window.playback.snapshot.status
                        == "Playing"
                    ),
                    timeout=20,
                )
                player = app._media_player_window
                backend = player.playback
                if index == 0:
                    player._unmuted_volume = 67
                    backend.set_volume(volume)
                    if mode != "embedded":
                        player._open_presentation(mode)
                until(
                    app,
                    lambda backend=backend: (
                        backend.snapshot.volume == volume
                        and backend._player.audio_get_volume() == volume
                    ),
                )
                assert player._presentation_mode == expected_mode
                assert not app.playback_engine.retiring
                if expected_mode != "embedded":
                    if presentation_window is not None:
                        assert player._presentation_window is presentation_window
                    presentation_window = player._presentation_window
                assert player._unmuted_volume == 67
                until(
                    app,
                    lambda backend=backend: (
                        backend.snapshot.position > 0.6
                        and backend.snapshot.duration > 6
                    ),
                )
                stats = backend._vlc.MediaStats()
                assert backend._media.get_stats(stats)
                counters = {
                    name: getattr(stats, name)
                    for name in (
                        "decoded_video",
                        "displayed_pictures",
                        "decoded_audio",
                        "played_abuffers",
                    )
                }
                if not audio:
                    assert (
                        counters["decoded_video"] > 0
                        and counters["displayed_pictures"] > 0
                    )
                else:
                    assert not presentation_window.winfo_exists()
                    assert player._surface_owner is None
                    assert (
                        player._control_notice
                        == "This audio item plays in the main window."
                    )
                    evidence["audio_host_closed"] = True
                assert counters["decoded_audio"] > 0
                if expected_mode == "fullscreen":
                    evidence.setdefault("fullscreen_geometry_before_wait", []).append(
                        {
                            "index": index,
                            "width": player._presentation_window.winfo_width(),
                            "height": player._presentation_window.winfo_height(),
                            "screen_width": app.winfo_screenwidth(),
                            "screen_height": app.winfo_screenheight(),
                            "attribute": bool(
                                player._presentation_window.attributes("-fullscreen")
                            ),
                            "native_window_id": int(
                                player._surface_owner._view.window().windowNumber()
                            ),
                            "native_frame": str(
                                player._surface_owner._view.window().frame()
                            ),
                        }
                    )
                    until(
                        app,
                        lambda player=player: (
                            player._presentation_window.winfo_width()
                            >= app.winfo_screenwidth() - 2
                            and player._presentation_window.winfo_height()
                            >= app.winfo_screenheight() - 2
                        ),
                    )
                elif expected_mode == "floating":
                    assert player._presentation_window.winfo_viewable()
                    assert player._presentation_window.attributes("-topmost")
                    assert 480 <= player._presentation_window.winfo_width() <= 1000
                if previous is not None:
                    assert previous.closed and previous.playback._closed
                    assert (
                        previous._surface_owner is None
                        or previous._surface_owner._view is None
                    )
                path = str(backend.snapshot.path)
                seen.append(path)
                assert path == expected[index]
                evidence["players"].append(
                    {
                        "path": Path(path).parent.name,
                        "provider_volume": backend._player.audio_get_volume(),
                        "presentation": player._presentation_mode,
                        "position": backend.snapshot.position,
                        "provider_counters": counters,
                        "remaining_count": len(app.watch_queue.remaining_keys or ()),
                    }
                )
                # Capture the exact NSWindow hosting this player's video, not
                # an arbitrary first window returned by the compositor.
                import sys

                output = os.environ.get("VODFORGE_NATIVE_EVIDENCE_DIR")
                if sys.platform == "darwin" and output and not audio:
                    window = player._surface_owner._view.window()
                    rect = window.frame()
                    window_id = int(window.windowNumber())
                    label = f"queue-{kind}-{mode}-{count}-{scenario}-{index}"
                    destination = Path(output) / (label + ".png")
                    argv = [
                        "/usr/sbin/screencapture",
                        "-x",
                        "-o",
                        "-l",
                        str(window_id),
                        str(destination),
                    ]
                    import Quartz

                    listed = (
                        Quartz.CGWindowListCopyWindowInfo(
                            Quartz.kCGWindowListOptionIncludingWindow, window_id
                        )
                        or []
                    )
                    own = next(
                        (
                            item
                            for item in listed
                            if int(item.get("kCGWindowNumber", -1)) == window_id
                        ),
                        {},
                    )
                    evidence.setdefault("capture_visibility", []).append(
                        {
                            "index": index,
                            "native_visible": bool(window.isVisible()),
                            "native_miniaturized": bool(window.isMiniaturized()),
                            "native_occlusion": int(window.occlusionState()),
                            "compositor_on_screen": bool(
                                own.get("kCGWindowIsOnscreen", False)
                            ),
                            "tk_state": player._presentation_window.state()
                            if player._presentation_window is not None
                            else app.state(),
                        }
                    )
                    result = subprocess.run(
                        argv, check=False, capture_output=True, text=True, timeout=10
                    )
                    evidence["capture_visibility"][-1]["capture_error"] = result.stderr
                    assert result.returncode == 0 and destination.exists()
                    evidence.setdefault("captures", []).append(
                        {
                            "label": label,
                            "window_id": window_id,
                            "argv": argv,
                            "native_frame": [
                                rect.origin.x,
                                rect.origin.y,
                                rect.size.width,
                                rect.size.height,
                            ],
                        }
                    )
                previous = player
            until(app, lambda: app.watch_queue.token is None, timeout=15)
            assert previous.playback.snapshot.status == (
                "Closed" if scenario == "constructor" else "Ended"
            )
            assert seen == (expected[:1] if scenario == "constructor" else expected)
            assert [e["action"] for e in evidence["events"]] == (
                ["requested", "started", "advanced", "failed"]
                if scenario == "constructor"
                else ["requested", "started", "advanced", "completed"]
                if count > 1
                else ["requested", "started", "completed"]
            )
            if scenario == "constructor":
                assert (
                    evidence["events"][-1]["dimensions"]["queue_failure_boundary"]
                    == "constructor"
                )
            assert not evidence["callback_errors"]
            app._archive_cancel_playback()
            until(app, lambda: not app.playback_engine._retirement_threads)
            assert previous.closed and previous.playback._closed
            assert {
                p: hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in originals
            } == originals
            app._request_application_close()
            until(app, lambda: not app.tk.call("info", "commands", "."), timeout=10)
            evidence["passed"] = True
    finally:
        if app is not None and app.tk.call("info", "commands", "."):
            app._request_application_close()
            until(app, lambda: not app.tk.call("info", "commands", "."), timeout=10)
        output = os.environ.get("VODFORGE_NATIVE_EVIDENCE_DIR")
        if output:
            Path(output).mkdir(parents=True, exist_ok=True)
            (Path(output) / f"queue-{kind}-{mode}-{count}-{scenario}.json").write_text(
                json.dumps(evidence, indent=2)
            )
