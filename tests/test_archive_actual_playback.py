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


def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)


def tab(player, label):
    key = next(
        key
        for key in player._info_notebook.tabs()
        if player._info_notebook.tab(key, "text") == label
    )
    player._info_notebook.select(key)
    return player._info_notebook.nametowidget(key)


def capture(app, label, evidence):
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
    window_id = int(owned[0]["kCGWindowNumber"])
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
                watch.search.set("fixture")
                until(app, lambda: watch._render_after is None and bool(watch._offsets))
                watch._move_rail(next(iter(watch._offsets)), 1)
                until(app, lambda: watch._render_after is None)
                watch.canvas.yview_moveto(0.35)
                app.update()
                assert any(watch._offsets.values()) and watch.canvas.yview()[0] > 0
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
            assert player.play_button.winfo_ismapped()
            assert (
                player.timeline.winfo_rooty() + player.timeline.winfo_height()
                <= app.winfo_rooty() + app.winfo_height()
            )
            player._toggle()
            until(app, lambda: backend.snapshot.status == "Paused")
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
