"""Opt-in real libVLC source-native journey, using only generated local fixtures.

Executed by native_surface_contract. Provider decode/output counters, actual
FFmpeg previews and independent annotation/file-handle outcomes are required.
This is not packaged, Windows, audible-output or physical-input certification.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import tkinter as tk
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.focus_ui_preview import isolated_preview_services
from tests.test_archive_models import saved
from yt_downloader import app as app_module
from yt_downloader.analytics_startup import AnalyticsStartup
from yt_downloader.engagement_ui import EngagementUI
from yt_downloader.library_annotations import load_library_annotations
from yt_downloader.platform_services import find_runtime_executable

pytestmark = pytest.mark.skipif(
    os.environ.get("VODFORGE_ACTUAL_PLAYBACK_TESTS") != "1",
    reason="explicit real-provider native run required",
)


def until(app, predicate, timeout=12):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.update()
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("Native condition did not become true before its deadline")


def assert_native_overlay_roles(app, overlay, evidence):
    """Observe actual AppKit glyphs/rails after normal presentation polling."""
    from AppKit import NSColorSpace

    from yt_downloader.platforms.macos.surfaces import _bitmap_rep_image
    from yt_downloader.ui_theme import THEME

    def rgb(color):
        value = color.colorUsingColorSpace_(NSColorSpace.sRGBColorSpace())
        return tuple(
            round(channel * 255)
            for channel in (
                value.redComponent(),
                value.greenComponent(),
                value.blueComponent(),
            )
        )

    def expected(role):
        return tuple(int(THEME[role][i : i + 2], 16) for i in (1, 3, 5))

    def capture_view(view):
        bounds = view.bounds()
        rep = view.bitmapImageRepForCachingDisplayInRect_(bounds)
        view.cacheDisplayInRect_toBitmapImageRep_(bounds, rep)
        # Native backing may use the display's P3 profile. Compare semantic
        # sRGB tokens only after an explicit native color-space conversion.
        rep = rep.bitmapImageRepByConvertingToColorSpace_renderingIntent_(
            NSColorSpace.sRGBColorSpace(), 0
        )
        assert rep is not None
        return _bitmap_rep_image(rep).convert("RGB")

    def matching(image, target):
        return sum(
            max(abs(a - b) for a, b in zip(pixel, target)) <= 8
            for y in range(image.height)
            for x in range(image.width)
            for pixel in (image.getpixel((x, y)),)
        )

    original = {key: THEME[key] for key in ("icon", "progress", "text", "focus")}
    try:
        for label, colors in (
            ("approved", original),
            (
                "changed",
                {
                    "icon": "#66ddcc",
                    "progress": "#ccaaff",
                    "text": "#e5e5e5",
                    "focus": "#ffdd99",
                },
            ),
            ("restored", original),
        ):
            THEME.update(colors)
            deadline = time.monotonic() + 0.2
            while time.monotonic() < deadline:
                app.update()
                time.sleep(0.01)
            assert all(
                rgb(button.contentTintColor()) == expected("icon")
                for button in overlay.buttons
            ), "Native action glyph roles are stale"
            assert rgb(overlay.time.textColor()) == expected("text")
            # Real rendered controls, not merely requested tint metadata.
            glyph = capture_view(overlay.buttons[0])
            timeline = capture_view(overlay.timeline)
            volume = capture_view(overlay.volume)
            destination = Path(os.environ["VODFORGE_NATIVE_EVIDENCE_DIR"])
            for name, image in (
                ("glyph", glyph),
                ("timeline", timeline),
                ("volume", volume),
            ):
                image.save(destination / f"native-player-{label}-{name}.png")
            assert matching(glyph, expected("icon")) > 5, (
                "Action tint did not reach native pixels"
            )
            assert matching(timeline, expected("progress")) > 5, (
                "Timeline progress role missing"
            )
            assert matching(volume, expected("progress")) > 5, (
                "Volume progress role missing"
            )
            evidence.setdefault("native_role_pixels", []).append(
                {"state": label, "colors": dict(colors)}
            )
    finally:
        THEME.update(original)


def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)


def tab(player, label):
    target = {
        "Chapters": "chapters",
        "About": "info",
        "Source": "source",
        "File": "output",
        "Notes": "notes",
        "Moments": "moments",
    }[label]
    key = next(key for key, value in player._detail_targets.items() if value == target)
    player._select_information_panel(key)
    return player._information_sections[key]


def capture(app, label, evidence, *, window_id=None):
    if sys.platform != "darwin" or not os.environ.get("VODFORGE_NATIVE_EVIDENCE_DIR"):
        return
    import Quartz

    destination = Path(os.environ["VODFORGE_NATIVE_EVIDENCE_DIR"]) / (label + ".png")
    windows = Quartz.CGWindowListCopyWindowInfo(
        Quartz.kCGWindowListOptionOnScreenOnly, 0
    )
    owned = [
        window
        for window in windows
        if window.get("kCGWindowOwnerPID") == os.getpid()
        and window.get("kCGWindowLayer") == 0
    ]
    assert owned
    if window_id is None:
        window_id = int(owned[0]["kCGWindowNumber"])
    else:
        assert any(int(window["kCGWindowNumber"]) == window_id for window in owned)
    argv = [
        "/usr/sbin/screencapture",
        "-x",
        "-o",
        "-l",
        str(window_id),
        str(destination),
    ]
    result = subprocess.run(
        argv, check=False, capture_output=True, text=True, timeout=10
    )
    evidence.setdefault("captures", []).append(
        {
            "label": label,
            "window_id": window_id,
            "argv": argv,
            "returncode": result.returncode,
            "stderr": result.stderr,
        }
    )
    assert result.returncode == 0 and destination.exists()


@pytest.mark.parametrize(
    "format_name,origin",
    [("MP4", "watch"), ("MP3", "library"), ("Original audio", "library")],
)
def test_real_embedded_media_annotation_transport_preview_and_release(
    tmp_path, monkeypatch, format_name, origin
):
    runtime = app_module.find_libvlc_runtime()
    ffmpeg = find_runtime_executable("ffmpeg")
    assert runtime is not None and ffmpeg, "Required source-native runtime unavailable"
    suffix = {"MP4": "mp4", "MP3": "mp3", "Original audio": "m4a"}[format_name]
    media = tmp_path / ("fixture." + suffix)
    argv = [ffmpeg, "-nostdin", "-v", "error"]
    if format_name == "MP4":
        argv += ["-f", "lavfi", "-i", "testsrc2=size=640x360:rate=24"]
    argv += [
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=440:sample_rate=48000",
        "-t",
        "12",
        "-af",
        "volume=0.01",
    ]
    if format_name == "MP4":
        argv += [
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
        ]
    else:
        argv += ["-c:a", "libmp3lame" if format_name == "MP3" else "aac"]
    result = subprocess.run(
        [*argv, str(media)], check=False, capture_output=True, text=True, timeout=30
    )
    assert result.returncode == 0, result.stderr
    original_bytes = media.read_bytes()
    from PIL import Image

    Image.new("RGB", (640, 360), "#162d56").save(tmp_path / "thumbnail.jpeg")
    evidence = {
        "kind": "actual libVLC source-native synthetic journey",
        "pid": os.getpid(),
        "format": format_name,
        "origin": origin,
        "ffmpeg_argv": argv,
        "physical_input": False,
        "audibility_observed": False,
        "callback_errors": [],
        "provider_counters": {},
        "outcomes": [],
    }
    monkeypatch.setattr(AnalyticsStartup, "start", lambda self: None)
    monkeypatch.setattr(EngagementUI, "start", lambda self: None)
    app = None
    try:
        with (
            isolated_preview_services(),
            patch.object(app_module, "find_libvlc_runtime", return_value=runtime),
        ):
            app = app_module.DownloaderApp()
            app.report_callback_exception = lambda *args: evidence[
                "callback_errors"
            ].append(repr(args))
            app.tk.eval(
                "set ::archive_background_errors {}; proc bgerror {message} {lappend ::archive_background_errors $message}"
            )
            app.geometry("1100x600")
            app.deiconify()
            record = {
                **saved(
                    media,
                    video="actual-fixture",
                    playlist="Fixture Playlist 0",
                    channel="Synthetic creator",
                ),
                "vodforge_output_type": format_name,
                "vodforge_run_id": "actual-fixture-" + suffix,
                "duration": 0,
                "playlist_index": 3,
                "tags": ["source-tag"],
                "description": "Synthetic source description",
                "chapters": [
                    {"start_time": 0, "end_time": 4, "title": "Beginning"},
                    {"start_time": 4, "end_time": 8, "title": "Middle"},
                    {"start_time": 8, "end_time": 12, "title": "Ending"},
                ],
                "heatmap": [{"start_time": 0, "end_time": 12, "value": 0.8}],
            }
            app.download_history = [record]
            if origin == "watch":
                app.download_history.extend(
                    {
                        **saved(
                            tmp_path / f"other-{index}.mp4",
                            video=f"fixture-extra-{index}",
                            playlist=f"Fixture Playlist {index // 8}",
                            channel="Synthetic creator",
                        ),
                        "playlist_index": index % 8 + 1,
                    }
                    for index in range(24)
                )
            app._reconcile_library_projection()
            app.library_output_type_var.set("All")
            app._select_focus_view("library")
            app.video_tree.model.reveal(0)
            app.video_tree.selection_set("0")
            app._display_selected_metadata(0)
            dialogs = []
            original_dialog = app_module.LibraryAnnotationDialog

            def observe_dialog(*args, **kwargs):
                dialog = original_dialog(*args, **kwargs)
                dialogs.append(dialog)
                return dialog

            with patch.object(
                app_module, "LibraryAnnotationDialog", side_effect=observe_dialog
            ):
                app._show_library_annotation_editor()
                dialog = dialogs[-1]
                app.update()
                dialog.category_var.set("Fixture collection")
                dialog.tags_var.set("Personal, personal, Saved")
                note = "Preserved personal note " * 50
                dialog.note.delete("1.0", "end")
                dialog.note.insert("1.0", note)
                next(
                    w
                    for w in descendants(dialog.popup)
                    if isinstance(w, app_module.ttk.Button)
                    and w.cget("text") == "Save details"
                ).invoke()
            persisted = load_library_annotations(app.library_annotations.path)
            annotation = next(iter(persisted.values()))
            assert annotation.category == "Fixture collection"
            assert annotation.tags == ("Personal", "Saved")
            assert annotation.note == note.strip()
            assert app.metadata_items[0]["tags"] == ["source-tag"]
            evidence["outcomes"].append(
                "real annotation dialog saved through canonical ledger"
            )
            operations = []
            original_operation = app.product_telemetry.record_operation

            def observe_operation(feature, action, **kwargs):
                operations.append((feature, action, kwargs.get("dimensions", {})))
                return original_operation(feature, action, **kwargs)

            monkeypatch.setattr(
                app.product_telemetry, "record_operation", observe_operation
            )
            app._select_focus_view(origin)

            def browser_state():
                if origin == "watch":
                    watch = app.focus_watch
                    return {
                        "mode": watch._mode,
                        "channel": watch._channel,
                        "query": watch.search.get(),
                        "page": watch._page,
                        "rail_offsets": dict(watch._offsets),
                        "scroll": watch.canvas.yview(),
                    }
                return {
                    "path": str(app.video_tree.model.path),
                    "owner": app.video_tree.model.selected_owner,
                    "page": app.video_tree.model.page,
                    "scroll": app.video_tree.canvas.yview(),
                    "query": app.library_search_var.get(),
                    "category": app.library_category_var.get(),
                }

            if origin == "watch":
                watch = app.focus_watch
                watch._navigate("channels", "Synthetic creator")
                # Exercise the current channel page and vertical scroll restoration.
                # Horizontal rail pagination has its separate scene contract.
                watch.search.set("")
                until(
                    app,
                    lambda: (
                        watch._render_after is None
                        and watch.canvas.bbox("all") is not None
                    ),
                )
                watch.canvas.yview_moveto(0.35)
                app.update()
                assert (
                    watch._channel == "Synthetic creator"
                    and watch.canvas.yview()[0] > 0
                )
            state = browser_state()
            evidence["browser_before"] = state
            app._play_selected_library_item(app.metadata_items[0])
            until(app, lambda: app.__dict__.get("_media_player_window") is not None)
            player = app._media_player_window
            backend = player.playback
            until(app, lambda: backend.snapshot.status == "Playing")
            assert player.popup.winfo_toplevel() is app and player.embedded
            assert not any(isinstance(w, tk.Toplevel) for w in app.winfo_children())
            player.volume_var.set(0)
            player._schedule_volume("0")
            until(app, lambda: backend._player.audio_get_volume() == 0)
            player.volume_var.set(37)
            player._schedule_volume("37")
            until(app, lambda: backend._player.audio_get_volume() == 37)
            until(
                app,
                lambda: (
                    backend.snapshot.position > 0.5 and backend.snapshot.duration > 11
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
            evidence["provider_counters"] = counters
            assert (
                counters["decoded_audio"] > 0
                and backend._player.audio_get_track_count() > 0
            )
            if format_name == "MP4":
                assert (
                    counters["decoded_video"] > 0 and counters["displayed_pictures"] > 0
                )
            if player._native_overlay is not None:
                assert not player.transport.winfo_ismapped()
                assert (
                    player.stage.winfo_rooty() + player.stage.winfo_height()
                    <= app.winfo_rooty() + app.winfo_height()
                )
            else:
                assert player.play_button.winfo_ismapped()
                assert (
                    player.timeline.winfo_rooty() + player.timeline.winfo_height()
                    <= app.winfo_rooty() + app.winfo_height()
                )
            if format_name == "MP4" and sys.platform == "darwin":
                from threading import Thread

                import Quartz
                from AppKit import NSApplication

                NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
                app.lift()
                app.update()
                center = (
                    player.stage.winfo_rootx() + player.stage.winfo_width() // 2,
                    player.stage.winfo_rooty() + player.stage.winfo_height() // 2,
                )
                Quartz.CGEventPost(
                    Quartz.kCGHIDEventTap,
                    Quartz.CGEventCreateMouseEvent(
                        None,
                        Quartz.kCGEventMouseMoved,
                        center,
                        Quartz.kCGMouseButtonLeft,
                    ),
                )
                overlay = player._native_overlay
                assert overlay is not None
                assert_native_overlay_roles(app, overlay, evidence)
                capture(app, "actual-mp4-before-click", evidence)
                evidence["click_geometry"] = {
                    "tk_center": center,
                    "native_frame": str(overlay.video_click.frame()),
                    "native_screen": str(
                        overlay.video_click.window().convertPointToScreen_(
                            overlay.video_click.convertPoint_toView_(
                                (
                                    overlay.video_click.bounds().size.width / 2,
                                    overlay.video_click.bounds().size.height / 2,
                                ),
                                None,
                            )
                        )
                    ),
                }
                until(app, lambda: overlay.view.isHidden(), timeout=6)
                toggles = []
                evidence["body_click_toggles"] = toggles
                window_point = overlay.video_click.convertPoint_toView_(
                    (
                        overlay.video_click.bounds().size.width / 2,
                        overlay.video_click.bounds().size.height / 2,
                    ),
                    None,
                )
                evidence["body_hit_view"] = str(
                    overlay.video_click.window().contentView().hitTest_(window_point)
                )
                evidence["native_key_window"] = bool(
                    overlay.video_click.window().isKeyWindow()
                )
                original_toggle = backend.toggle

                def observed_toggle():
                    toggles.append(backend.snapshot.status)
                    return original_toggle()

                monkeypatch.setattr(backend, "toggle", observed_toggle)
                for expected in ("Paused", "Playing"):

                    def click():
                        for kind in (
                            Quartz.kCGEventLeftMouseDown,
                            Quartz.kCGEventLeftMouseUp,
                        ):
                            event = Quartz.CGEventCreateMouseEvent(
                                None, kind, center, Quartz.kCGMouseButtonLeft
                            )
                            Quartz.CGEventSetFlags(event, 0)
                            Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)
                            time.sleep(0.06)

                    driver = Thread(target=click, daemon=True)
                    driver.start()
                    until(
                        app,
                        lambda expected=expected: backend.snapshot.status == expected,
                    )
                    # Keep pumping after the expected transition to catch duplicate dispatch.
                    deadline = time.monotonic() + 0.35
                    while time.monotonic() < deadline:
                        app.update()
                        time.sleep(0.01)
                    driver.join(1)
                    assert not driver.is_alive()
                    assert backend.snapshot.status == expected
                    if expected == "Paused":
                        assert not overlay.view.isHidden()
                assert toggles == ["Playing", "Paused"]
                evidence["outcomes"].append(
                    "OS video-body clicks toggle exactly once with native controls hidden and visible"
                )
                capture(app, "actual-mp4-player", evidence)
            elif sys.platform == "darwin":
                from threading import Thread

                import Quartz
                from AppKit import NSApplication

                assert player._native_overlay is None
                NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
                app.lift()
                app.update()
                point = (
                    player.stage.winfo_rootx() + player.stage.winfo_width() // 4,
                    player.stage.winfo_rooty() + player.stage.winfo_height() // 3,
                )
                audio_toggles = []
                original_audio_toggle = backend.toggle

                def observed_audio_toggle():
                    audio_toggles.append(backend.snapshot.status)
                    return original_audio_toggle()

                monkeypatch.setattr(backend, "toggle", observed_audio_toggle)
                for expected in ("Paused", "Playing"):

                    def click_audio():
                        for kind in (
                            Quartz.kCGEventLeftMouseDown,
                            Quartz.kCGEventLeftMouseUp,
                        ):
                            event = Quartz.CGEventCreateMouseEvent(
                                None, kind, point, Quartz.kCGMouseButtonLeft
                            )
                            Quartz.CGEventSetFlags(event, 0)
                            Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)
                            time.sleep(0.06)

                    driver = Thread(target=click_audio, daemon=True)
                    driver.start()
                    until(
                        app,
                        lambda expected=expected: backend.snapshot.status == expected,
                    )
                    deadline = time.monotonic() + 0.35
                    while time.monotonic() < deadline:
                        app.update()
                        time.sleep(0.01)
                    driver.join(1)
                    assert not driver.is_alive() and backend.snapshot.status == expected
                assert audio_toggles == ["Playing", "Paused"]
                evidence["outcomes"].append(
                    "OS audio-artwork clicks toggle exactly once with usable fallback controls"
                )
            player._toggle()
            until(app, lambda: backend.snapshot.status == "Paused")
            if format_name == "MP4" and sys.platform == "darwin":
                # Native transport targets must consume input without a body toggle.
                def control_click(view, fraction=0.5, dismiss_menu=False):
                    local = (
                        view.bounds().size.width * fraction,
                        view.bounds().size.height / 2,
                    )
                    screen = view.window().convertPointToScreen_(
                        view.convertPoint_toView_(local, None)
                    )
                    screen_height = Quartz.CGDisplayBounds(
                        Quartz.CGMainDisplayID()
                    ).size.height
                    point = (screen.x, screen_height - screen.y)
                    move = Quartz.CGEventCreateMouseEvent(
                        None,
                        Quartz.kCGEventMouseMoved,
                        point,
                        Quartz.kCGMouseButtonLeft,
                    )
                    Quartz.CGEventSetFlags(move, 0)
                    Quartz.CGEventPost(Quartz.kCGHIDEventTap, move)
                    deadline = time.monotonic() + 0.15
                    while time.monotonic() < deadline:
                        app.update()
                        time.sleep(0.01)
                    if view is overlay.volume or view in overlay.buttons:
                        expected_control = (
                            len(overlay.buttons)
                            if view is overlay.volume
                            else overlay.buttons.index(view)
                        )
                        until(
                            app,
                            lambda: any(
                                item[0] == expected_control
                                for item in overlay._control_highlights
                            ),
                            timeout=2,
                        )
                        evidence.setdefault("native_control_hover", []).append(
                            expected_control
                        )
                        if view is overlay.volume:
                            capture(app, "actual-mp4-volume-hover", evidence)
                    local = (
                        view.bounds().size.width * fraction,
                        view.bounds().size.height / 2,
                    )
                    window_point = view.convertPoint_toView_(local, None)
                    screen = view.window().convertPointToScreen_(window_point)
                    point = (screen.x, screen_height - screen.y)
                    evidence.setdefault("control_clicks", []).append(
                        {
                            "target": str(view),
                            "point": point,
                            "hidden": bool(view.isHidden()),
                            "hit_view": str(
                                view.window().contentView().hitTest_(window_point)
                            ),
                            "frame": str(view.frame()),
                            "window": int(view.window().windowNumber()),
                            "before_volume": backend.snapshot.volume,
                        }
                    )

                    def send():
                        for kind in (
                            Quartz.kCGEventLeftMouseDown,
                            Quartz.kCGEventLeftMouseUp,
                        ):
                            event = Quartz.CGEventCreateMouseEvent(
                                None, kind, point, Quartz.kCGMouseButtonLeft
                            )
                            Quartz.CGEventSetFlags(event, 0)
                            Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)
                            time.sleep(0.06)
                        if dismiss_menu:
                            time.sleep(0.2)
                            for down in (True, False):
                                event = Quartz.CGEventCreateKeyboardEvent(
                                    None, 53, down
                                )
                                Quartz.CGEventSetFlags(event, 0)
                                Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)

                    driver = Thread(target=send, daemon=True)
                    driver.start()
                    deadline = time.monotonic() + 0.65
                    while time.monotonic() < deadline:
                        app.update()
                        time.sleep(0.01)
                    driver.join(1)
                    assert not driver.is_alive()

                toggle_count = len(toggles)
                control_click(overlay.timeline, 0.25)
                until(app, lambda: abs(backend.snapshot.position - 3) < 0.8)
                control_click(overlay.volume, 0.6)
                until(app, lambda: backend.snapshot.volume != 37)
                control_click(overlay.buttons[4], dismiss_menu=True)
                assert (
                    backend.snapshot.status == "Paused" and len(toggles) == toggle_count
                )
                evidence["outcomes"].append(
                    "OS native seek volume and options-menu clicks do not bubble into body playback toggle"
                )
                player._open_presentation("fullscreen")
                until(
                    app,
                    lambda: (
                        player._presentation_mode == "fullscreen"
                        and player._presentation_window.winfo_ismapped()
                    ),
                )
                assert (
                    player.playback is backend and backend.snapshot.status == "Paused"
                )
                assert not player.transport.winfo_ismapped()
                assert (
                    player._native_overlay.video_click.window()
                    == player._native_overlay.view.window()
                )
                player._return_presentation()
                until(
                    app,
                    lambda: (
                        player._presentation_window is None
                        and player.stage.winfo_ismapped()
                    ),
                )
                assert (
                    player.playback is backend and backend.snapshot.status == "Paused"
                )
                assert not player.transport.winfo_ismapped()
                evidence["outcomes"].append(
                    "fullscreen round trip retains paused backend and one native control surface"
                )
                # Floating mode is a separate native host contract from fullscreen.
                overlay = player._native_overlay
                assert overlay is not None
                floating_actions = []
                original_action = overlay._on_action

                def observe_floating_action(action, value):
                    floating_actions.append({"action": action, "value": value})
                    original_action(action, value)

                monkeypatch.setattr(overlay, "_on_action", observe_floating_action)
                key_window = NSApplication.sharedApplication().keyWindow()
                evidence["floating_before"] = {
                    "native_window": int(overlay.view.window().windowNumber()),
                    "key_window": int(key_window.windowNumber())
                    if key_window
                    else None,
                    "window_is_key": bool(overlay.view.window().isKeyWindow()),
                    "button_enabled": bool(overlay.buttons[7].isEnabled()),
                    "closed": overlay._closed,
                    "actions": floating_actions,
                    "main_geometry": app.geometry(),
                    "stage_size": [
                        player.stage.winfo_width(),
                        player.stage.winfo_height(),
                    ],
                    "provider_media": str(backend.snapshot.path),
                    "provider_position": backend.snapshot.position,
                }
                control_click(overlay.buttons[7])
                evidence["floating_after_click"] = {
                    "mode": player._presentation_mode,
                    "pending": list(player._overlay_actions),
                    "notice": player._control_notice,
                }
                until(
                    app,
                    lambda: (
                        player._presentation_mode == "floating"
                        and player._presentation_window.winfo_ismapped()
                    ),
                )
                floating = player._presentation_window
                overlay = player._native_overlay
                assert overlay is not None
                floating_id = int(overlay.view.window().windowNumber())
                assert bool(floating.attributes("-topmost"))
                assert (
                    player.playback is backend and backend.snapshot.status == "Paused"
                )
                assert overlay.video_click.window() == overlay.view.window()
                assert not player.transport.winfo_ismapped()
                capture(app, "actual-mp4-floating", evidence, window_id=floating_id)
                evidence["floating_window"] = {
                    "window_id": floating_id,
                    "title": floating.title(),
                    "topmost": True,
                    "provider_preserved": True,
                    "paused": True,
                }
                control_click(overlay.buttons[7])
                until(
                    app,
                    lambda: (
                        player._presentation_window is None
                        and player.stage.winfo_ismapped()
                    ),
                )
                assert not floating.winfo_exists()
                assert (
                    player.playback is backend and backend.snapshot.status == "Paused"
                )
                assert (
                    str(backend.snapshot.path)
                    == evidence["floating_before"]["provider_media"]
                )
                assert app.geometry() == evidence["floating_before"]["main_geometry"]
                assert [
                    player.stage.winfo_width(),
                    player.stage.winfo_height(),
                ] == evidence["floating_before"]["stage_size"]
                evidence["floating_restored"] = {
                    "host_destroyed": True,
                    "main_geometry": app.geometry(),
                    "provider_media": str(backend.snapshot.path),
                    "provider_position": backend.snapshot.position,
                    "same_provider": True,
                }
                assert not player.transport.winfo_ismapped()
                evidence["outcomes"].append(
                    "OS floating-window button round trip retires the owned host and preserves paused provider"
                )

            poll_token = player._poll_after_id
            for _ in range(3):
                app._play_selected_library_item(app.metadata_items[0])
                player.show()
            assert player._poll_after_id == poll_token
            until(app, lambda: player.status_var.get() == "Paused")
            assert (
                app._media_player_window is player
                and backend.snapshot.status == "Paused"
            )
            evidence["outcomes"].append("same media refocus retained paused provider")
            tab(player, "Notes")
            app.update()
            notes = [
                w.get("1.0", "end")
                for w in descendants(player.popup)
                if isinstance(w, tk.Text)
            ]
            assert any(
                "Fixture collection" in text
                and note.strip() in text
                and "Personal, Saved" in text
                for text in notes
            )
            note_widget = next(
                w
                for w in descendants(player.popup)
                if isinstance(w, tk.Text)
                and "Fixture collection" in w.get("1.0", "end")
            )
            note_widget.yview_moveto(1)
            app.update()
            assert note_widget.yview()[1] == 1.0
            assert (
                note_widget.winfo_rooty() + note_widget.winfo_height()
                <= app.winfo_rooty() + app.winfo_height()
            )
            capture(app, "actual-" + suffix + "-notes", evidence)
            tab(player, "Chapters")
            player.chapter_list.selection_clear(0, "end")
            player.chapter_list.selection_set(1)
            player.chapter_list.event_generate("<<ListboxSelect>>")
            until(app, lambda: abs(backend.snapshot.position - 4) < 1)
            player.timeline.event_generate(
                "<Button-1>",
                x=10 + int((player.timeline.winfo_width() - 20) * 0.5),
                y=12,
            )
            until(app, lambda: abs(backend.snapshot.position - 6) < 1)
            if format_name == "MP4":
                until(
                    app,
                    lambda: (
                        len(player._preview_images) == 5
                        and all(image is not None for image in player._preview_images)
                    ),
                    timeout=20,
                )
                captions = [str(w.cget("text")) for w in player._preview_captions]
                assert len(captions) == 5 and all(
                    caption != "—" for caption in captions
                )
                evidence["preview_captions"] = captions
                tab(player, "Moments")
                app.update()
                capture(app, "actual-" + suffix + "-moments", evidence)
                player.preview_labels[2].event_generate("<Button-1>")
                until(
                    app,
                    lambda: (
                        abs(backend.snapshot.position - backend.snapshot.duration * 0.5)
                        < 1
                    ),
                )
                evidence["outcomes"].append(
                    "five actual FFmpeg frames including late duration and preview seek"
                )
            else:
                assert not player.preview_labels
            player._seek_to(10.5)
            player._toggle()
            until(app, lambda: backend.snapshot.status == "Ended", timeout=8)
            player._toggle()
            until(
                app,
                lambda: (
                    backend.snapshot.status == "Playing"
                    and backend.snapshot.position < 4
                ),
            )
            capture(app, "actual-" + suffix + "-replay", evidence)
            surface = player._surface_owner
            app._archive_cancel_playback()
            until(app, lambda: not app.playback_engine._retirement_threads)
            assert backend._closed and player.closed
            assert surface is None or surface._view is None
            assert app.winfo_exists()
            until(app, lambda: app.focus_watch._render_after is None)
            evidence["browser_after"] = browser_state()
            assert state == evidence["browser_after"]
            assert not any(
                w for w in app.winfo_children() if isinstance(w, tk.Toplevel)
            )
            if sys.platform == "darwin":
                handles = subprocess.run(
                    ["/usr/sbin/lsof", "-p", str(os.getpid()), "-Fn"],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                evidence["file_handle_probe"] = {
                    "returncode": handles.returncode,
                    "stdout": handles.stdout,
                    "stderr": handles.stderr,
                }
                assert handles.returncode == 0
                assert "p" + str(os.getpid()) in handles.stdout.splitlines()
                assert not any(
                    line.startswith("n" + str(tmp_path))
                    for line in handles.stdout.splitlines()
                )
                evidence["outcomes"].append(
                    "no remaining candidate process handles to synthetic fixture"
                )
            assert media.read_bytes() == original_bytes
            assert {
                "requested",
                "ready",
                "started",
                "completed",
                "focused",
                "closed",
            }.issubset(
                {
                    action
                    for feature, action, dims in operations
                    if feature == "playback_operation"
                }
            )
            assert all(
                dims.get("playback_origin") == origin
                and dims.get("player_surface") == "embedded"
                for feature, action, dims in operations
                if feature == "playback_operation"
            )
            evidence["operations"] = operations
            app._request_application_close()
            until(app, lambda: not app.tk.call("info", "commands", "."), timeout=8)
            deadline = time.monotonic() + 0.3
            while time.monotonic() < deadline:
                app.tk.call("update")
                time.sleep(0.01)
            evidence["tcl_background_errors"] = list(
                app.tk.call("set", "::archive_background_errors")
            )
            assert (
                not evidence["callback_errors"]
                and not evidence["tcl_background_errors"]
            )
            evidence["root_destroyed"] = True
    finally:
        if app is not None and app.tk.call("info", "commands", "."):
            app._request_application_close()
            until(app, lambda: not app.tk.call("info", "commands", "."), timeout=8)
        evidence["completed"] = evidence.get("root_destroyed", False)
        output = os.environ.get("VODFORGE_NATIVE_EVIDENCE_DIR")
        if output:
            Path(output).mkdir(parents=True, exist_ok=True)
            (Path(output) / ("actual-" + suffix + "-receipt.json")).write_text(
                json.dumps(evidence, indent=2)
            )
