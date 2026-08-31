"""Cross-surface state authority contracts for the VODForge desktop UI.

These tests intentionally guard ownership boundaries rather than individual
widget arrangements. A Forge run owns Forge identity and progress; Library
selection owns Library inspection; worker events may enrich only their run ID;
and each thumbnail surface owns its own asynchronous request generation.
"""

import inspect
import queue
import re
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import yt_downloader.app as app_module
from yt_downloader.app import (
    DownloaderApp,
    DownloadJob,
    ExportMode,
    ManualAudioCodec,
    ManualExportSettings,
    Mp3ExportSettings,
    OutputType,
    RoundedIconButton,
    focus_view_shortcut_bindings,
)
from yt_downloader.focus_settings import FocusSettingsDialog
from yt_downloader.history import HistoryError, history_identity, upsert_history


class Value:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class TextBuffer:
    def __init__(self):
        self.value = ""

    def config(self, **_kwargs):
        return None

    def insert(self, _index, value):
        self.value += str(value)

    def delete(self, _start, _end):
        self.value = ""

    def get(self, _start, _end):
        return self.value

    def see(self, _index):
        return None


class ScrollAwareTextBuffer(TextBuffer):
    def __init__(self, *, last: float):
        super().__init__()
        self.last = last
        self.seen: list[str] = []
        self.moved_to: list[float] = []

    def yview(self):
        return (0.0, self.last)

    def see(self, index):
        self.seen.append(str(index))

    def yview_moveto(self, fraction):
        self.moved_to.append(float(fraction))


class LiveWorker:
    def is_alive(self):
        return True


class Control:
    def __init__(self):
        self.raised = False
        self.configured: list[dict[str, object]] = []

    def config(self, **kwargs):
        self.configured.append(dict(kwargs))

    configure = config

    def tkraise(self):
        self.raised = True


class IdleTextBuffer(ScrollAwareTextBuffer):
    def after_idle(self, callback):
        callback()


class SelectedTree:
    def __init__(self, index: int = 0):
        self.index = index

    def selection(self):
        return (str(self.index),)


def make_job(tmp_path: Path, *, video_id: str = "authority-id") -> DownloadJob:
    return DownloadJob(
        url=f"https://www.youtube.com/watch?v={video_id}",
        output_dir=tmp_path,
        output_type=OutputType.MP4,
        quality_label="1080p Full HD",
        export_mode=ExportMode.AUTO_CBR,
        manual_settings=ManualExportSettings(),
        mp3_settings=Mp3ExportSettings(),
        single_video_only=True,
        use_nvenc=False,
        embed_thumbnail=False,
        write_thumbnail=False,
        embed_metadata=False,
        write_info_json=False,
        tags=[],
    )


def make_queued_snapshot_app() -> DownloaderApp:
    app = DownloaderApp.__new__(DownloaderApp)
    app.focus_active_title_var = Value("")
    app.focus_active_detail_var = Value("")
    app.focus_active_duration_var = Value("")
    app.focus_active_profile_var = Value("")
    app.focus_display_progress_var = Value(0)
    app.focus_percent_var = Value("")
    app.focus_display_status_var = Value("")
    app.focus_transfer_var = Value("")
    app.focus_summary_text = TextBuffer()
    app._set_focus_preview_start_action = lambda _info: None
    app._set_focus_progress_color = lambda: None
    app._focus_profile_text = lambda *_args, **_kwargs: "Queued MP3"
    app._set_text = lambda widget, value, **_kwargs: setattr(widget, "value", value)
    app._render_focus_run_activity = lambda *_args: None
    app._display_focus_record_thumbnail = lambda *_args: None
    return app


def test_worker_copy_with_same_run_id_resolves_to_active_authority(tmp_path: Path):
    active_job = make_job(tmp_path)
    worker_copy = replace(active_job, url="https://youtu.be/authority-id")
    stale_job = replace(active_job, run_id="different-run")
    app = DownloaderApp.__new__(DownloaderApp)
    app.active_job = active_job

    assert worker_copy is not active_job
    assert app._active_run_for_metadata_event(worker_copy) is active_job
    assert app._active_run_for_metadata_event(stale_job) is None
    app.active_job = None
    assert app._active_run_for_metadata_event(worker_copy) is None


def test_queued_run_selection_resolves_only_the_matching_pending_job(tmp_path: Path):
    active_job = make_job(tmp_path, video_id="active")
    queued_job = make_job(tmp_path, video_id="queued")
    other_job = make_job(tmp_path, video_id="other")
    app = DownloaderApp.__new__(DownloaderApp)
    app.active_job = active_job
    app.pending_jobs = [other_job, queued_job]
    app.metadata_items = []
    displayed: list[tuple[dict, DownloadJob]] = []
    app._display_focus_queued_job_snapshot = lambda record, job: displayed.append(
        (record, job)
    )
    app._display_focus_job_snapshot = lambda _job: (_ for _ in ()).throw(
        AssertionError("active run leaked")
    )

    record = {"kind": "queued", "run_id": queued_job.run_id}
    app._focus_select_run_record(record)

    assert app._focus_selected_run_id == queued_job.run_id
    assert displayed == [(record, queued_job)]


def test_queued_mp3_snapshot_renders_default_bitrate_without_crashing(tmp_path: Path):
    app = make_queued_snapshot_app()
    job = make_job(tmp_path, video_id="queued-mp3-default")
    job.output_type = OutputType.MP3
    job.mp3_settings = Mp3ExportSettings(bitrate_kbps=320)

    app._display_focus_queued_job_snapshot({"run_id": job.run_id}, job)

    assert "Audio quality   320 kbps" in app.focus_summary_text.value
    assert "Sample rate     Preserve source" in app.focus_summary_text.value


def test_queued_mp3_snapshot_formats_explicit_string_sample_rate(tmp_path: Path):
    app = make_queued_snapshot_app()
    job = make_job(tmp_path, video_id="queued-mp3-explicit")
    job.output_type = OutputType.MP3
    job.mp3_settings = Mp3ExportSettings(
        bitrate_kbps=192,
        sample_rate="48000",
        channels="2",
    )

    app._display_focus_queued_job_snapshot({"run_id": job.run_id}, job)

    assert "Audio quality   192 kbps" in app.focus_summary_text.value
    assert "Sample rate     48 kHz" in app.focus_summary_text.value
    assert "Channels        2" in app.focus_summary_text.value


def test_rounded_icon_button_preserves_tk_configuration_query_contract(monkeypatch):
    configure_calls: list[tuple[object, dict[str, object]]] = []
    content_updates: list[tuple[object, dict[str, object]]] = []
    invoked: list[bool] = []

    def fake_canvas_configure(_self, cnf=None, **kwargs):
        configure_calls.append((cnf, dict(kwargs)))
        if isinstance(cnf, str):
            return (cnf, cnf, cnf.title(), "base-default", "base-current")
        if cnf is None and not kwargs:
            return {
                "cursor": ("cursor", "cursor", "Cursor", "", "hand2"),
                "state": ("state", "state", "State", "normal", "normal"),
            }
        return None

    monkeypatch.setattr(app_module.tk.Canvas, "configure", fake_canvas_configure)
    monkeypatch.setattr(
        app_module.tk.Canvas,
        "cget",
        lambda _self, key: f"base:{key}",
    )

    button = RoundedIconButton.__new__(RoundedIconButton)
    button._button_image = None
    button._button_text = "Run"
    button._content_item = "content"
    button._state = "normal"
    button._hovered = True
    button._pressed = True
    button._command = lambda: invoked.append(True)
    button._redraw = lambda: None
    button.itemconfigure = lambda item, **kwargs: content_updates.append(
        (item, dict(kwargs))
    )

    button.configure(state="disabled")

    assert button.cget("state") == "disabled"
    assert button._hovered is False
    assert button._pressed is False
    assert button["state"] == "disabled"
    assert button.configure("state")[-1] == "disabled"
    assert button.configure("text")[-1] == "Run"
    assert button.configure("width")[-1] == "base-current"
    assert button.cget("width") == "base:width"
    all_options = button.configure()
    assert all_options["state"][-1] == "disabled"
    assert all_options["text"][-1] == "Run"
    configure_call_count = len(configure_calls)
    assert button.configure({}) is None
    assert len(configure_calls) == configure_call_count
    button._invoke()
    assert invoked == []

    button.config({"state": "normal", "text": "Forge"}, width=88)

    assert button.cget("state") == "normal"
    assert button.cget("text") == "Forge"
    assert content_updates == [("content", {"text": "Forge"})]
    assert (None, {"cursor": "arrow"}) in configure_calls
    assert (None, {"cursor": "hand2"}) in configure_calls
    assert (None, {"width": 88}) in configure_calls
    button._invoke()
    assert invoked == [True]


def test_library_selection_cannot_mutate_forge_identity_or_thumbnail(tmp_path: Path):
    info = {
        "id": "library-only-id",
        "title": "Library selection",
        "uploader": "Library creator",
        "duration": 42,
        "description": "Library description",
        "tags": ["library"],
        "vodforge_output_type": "MP4",
        "thumbnails": [{"url": "https://i.ytimg.com/vi/library-only-id/hqdefault.jpg"}],
    }
    app = DownloaderApp.__new__(DownloaderApp)
    app.metadata_items = [info]
    app.selected_title_var = Value("")
    app.selected_meta_var = Value("")
    app.selected_location_var = Value("")
    app.focus_active_title_var = Value("Forge-owned title")
    app.focus_active_detail_var = Value("Forge-owned creator")
    app.focus_active_duration_var = Value("9:59")
    app.focus_active_profile_var = Value("Forge-owned profile")
    app.status_var = Value("Ready")
    app.pulled_tags_text = object()
    app.description_text = object()
    app.source_summary_text = object()
    app.output_summary_text = object()
    app.focus_summary_text = None
    app._set_text = lambda *_args, **_kwargs: None
    app._set_encoding_summary_text = lambda *_args, **_kwargs: None
    thumbnail_requests: list[tuple[str, str]] = []
    app._load_thumbnail_preview = lambda url, *, target="both", **_kwargs: (
        thumbnail_requests.append((url, target))
    )

    app._display_selected_metadata(0)

    assert app.focus_active_title_var.get() == "Forge-owned title"
    assert app.focus_active_detail_var.get() == "Forge-owned creator"
    assert app.focus_active_duration_var.get() == "9:59"
    assert app.focus_active_profile_var.get() == "Forge-owned profile"
    assert app.status_var.get() == "Ready"
    assert thumbnail_requests == [
        ("https://i.ytimg.com/vi/library-only-id/hqdefault.jpg", "library")
    ]
    assert app.selected_title_var.get() == "Library selection"
    assert "MP4 • Library creator" in app.selected_meta_var.get()
    assert app.selected_location_var.get() == "Not downloaded in this history"

    library_source = inspect.getsource(DownloaderApp._build_focus_library_view)
    assert "thumbnail_wrap.pack_propagate(False)" in library_source
    assert "thumbnail_wrap.grid_propagate(False)" not in library_source


def test_next_run_output_toggle_cannot_rewrite_a_selected_forge_run():
    app = DownloaderApp.__new__(DownloaderApp)
    app.output_type_var = Value("MP3")
    app.quality_var = Value("1080p Full HD")
    app.export_mode_var = Value("Auto CBR")
    app.mp3_quality_var = Value("Maximum — 320 kbps CBR")
    app.mp3_sample_rate_var = Value("Preserve source")
    app.mp3_channels_var = Value("Preserve source")
    app.mp3_embed_metadata_var = Value(True)
    app.mp3_cover_art_mode_var = Value("No Art")
    app.mp3_custom_cover_art_path = None
    app.batch_urls = []
    app.worker = None
    app._focus_active_override = False
    app._focus_selected_run_id = "completed-run"
    app.focus_command_hint_var = Value("")
    app.focus_active_profile_var = Value("MP4  •  Auto CBR")
    app.focus_active_detail_var = Value("Selected creator")
    app.focus_transfer_var = Value("Complete  /  Ready to open in Library")
    app.focus_summary_text = TextBuffer()
    app.focus_summary_text.insert(
        "1.0", "Container/ext: mp4\nSave to       /completed/run.mp4"
    )
    app.output_var = Value("/next/run")
    app.focus_output_display_var = Value("")
    app._focus_layout = "wide"
    refreshed: list[bool] = []
    app._refresh_output_specific_settings = lambda: refreshed.append(True)

    app._on_output_type_changed()

    assert "MP3 audio" in app.focus_command_hint_var.get()
    assert refreshed == [True]
    assert app.focus_active_profile_var.get() == "MP4  •  Auto CBR"
    assert app.focus_transfer_var.get() == "Complete  /  Ready to open in Library"
    assert (
        app.focus_summary_text.value
        == "Container/ext: mp4\nSave to       /completed/run.mp4"
    )

    app._sync_focus_destination()

    assert app.focus_output_display_var.get() == "/next/run"
    assert (
        app.focus_summary_text.value
        == "Container/ext: mp4\nSave to       /completed/run.mp4"
    )

    app.focus_run_deck = object()
    app._focus_run_records = list
    app._set_focus_preview_start_action = lambda *_args: None
    app._set_focus_progress_color = lambda *_args: None
    app.focus_active_title_var = Value("Selected title")
    app.focus_active_duration_var = Value("4:16")
    app.focus_display_progress_var = Value(100)
    app.focus_percent_var = Value("100%")
    app.focus_display_status_var = Value("Showing completed run")
    app._render_focus_run_activity = lambda *_args: None
    app._reset_active_thumbnail = lambda: None
    app._refresh_focus_run_deck = lambda: None

    app._reconcile_focus_after_library_removal({"completed-run"})

    assert app._focus_selected_run_id is None
    assert app.focus_active_profile_var.get() == "MP3  •  320 kbps  •  Source rate"
    assert (
        app.focus_transfer_var.get() == "Audio-only MP3  /  best YouTube audio source"
    )
    assert app.focus_summary_text.value == (
        "Format        MP3\n"
        "Audio         Best YouTube source\n"
        "Output mode   Maximum — 320 kbps CBR\n"
        "Sample rate   Preserve source\n"
        "Save to       /next/run"
    )


def test_next_run_destination_cannot_rewrite_the_selected_active_run():
    app = DownloaderApp.__new__(DownloaderApp)
    app._focus_selected_run_id = "active-run"
    app.active_job = SimpleNamespace(run_id="active-run")
    app.worker = LiveWorker()
    app.output_var = Value("/next/run")
    app.focus_output_display_var = Value("")
    app.focus_summary_text = TextBuffer()
    app.focus_summary_text.insert(
        "1.0", "Container/ext: mp4\nSave to       /active/run.mp4"
    )
    app._focus_layout = "wide"

    app._sync_focus_destination()

    assert app.focus_output_display_var.get() == "/next/run"
    assert (
        app.focus_summary_text.value
        == "Container/ext: mp4\nSave to       /active/run.mp4"
    )


def test_library_suppressed_active_run_cannot_reclaim_the_neutral_forge_hero(
    tmp_path: Path,
):
    active = make_job(tmp_path, video_id="removed-active")
    app = DownloaderApp.__new__(DownloaderApp)
    app.active_job = active
    app.worker = LiveWorker()
    app._library_suppressed_run_ids = {active.run_id}
    app._focus_selected_run_id = None
    app._focus_active_override = False
    app.output_type_var = Value("MP3")
    app.quality_var = Value("1080p Full HD")
    app.export_mode_var = Value("Auto CBR")
    app.mp3_quality_var = Value("Maximum — 320 kbps CBR")
    app.mp3_sample_rate_var = Value("Preserve source")
    app.mp3_channels_var = Value("Preserve source")
    app.mp3_embed_metadata_var = Value(True)
    app.mp3_cover_art_mode_var = Value("No Art")
    app.mp3_custom_cover_art_path = None
    app.batch_urls = []
    app.output_var = Value("/next/run")
    app.focus_command_hint_var = Value("")
    app.focus_active_profile_var = Value("MP4  •  Active")
    app.focus_active_detail_var = Value("Ready")
    app.focus_transfer_var = Value("Active MP4 run")
    app.focus_summary_text = TextBuffer()
    app.focus_summary_text.insert(
        "1.0", "Container/ext: mp4\nSave to       /removed/run.mp4"
    )

    app._sync_focus_settings_summary()

    neutral_transfer = "Audio-only MP3  /  best YouTube audio source"
    neutral_summary = app.focus_summary_text.value
    assert app._focus_shows_next_run_defaults() is True
    assert app._focus_follows_active_run() is False
    assert app.focus_active_profile_var.get() == "MP3  •  320 kbps  •  Source rate"
    assert app.focus_transfer_var.get() == neutral_transfer
    assert "Format        MP3" in neutral_summary

    app._append_log = lambda *_args: None
    app._terminal_jobs = []
    app._completed_jobs = []
    app.progress_var = Value(58)
    app.status_var = Value("Removed run is stopping")
    app.download_button = Control()
    app.cancel_button = Control()
    app.skip_video_button = Control()
    app.skip_url_button = Control()
    app.focus_run_status_var = Value("Ready")
    app._refresh_focus_run_deck = lambda: None
    app._launch_next_pending_job = lambda: False
    app._set_focus_run_controls_visible = lambda *_args: None
    app.focus_run_deck = object()
    app._focus_run_records = list
    app._reconcile_focus_after_library_removal = lambda *_args: None

    app._finish_run_ui(
        "Removed from Library; the run was stopped.",
        "Stopped",
        "Stopped  /  Removed from Library",
    )

    assert app.focus_transfer_var.get() == neutral_transfer
    assert app.focus_summary_text.value == neutral_summary


def test_neutral_manual_mp4_summary_and_transfer_follow_the_selected_audio_codec():
    app = DownloaderApp.__new__(DownloaderApp)
    app.output_type_var = Value("MP4")
    app.quality_var = Value("1080p Full HD")
    app.export_mode_var = Value("Manual Override")
    app.manual_audio_codec_var = Value("MP3")
    app.batch_urls = []
    app.worker = None
    app._focus_active_override = False
    app._focus_selected_run_id = None
    app.output_var = Value("/next/run")
    app.focus_command_hint_var = Value("")
    app.focus_active_profile_var = Value("")
    app.focus_active_detail_var = Value("Ready")
    app.focus_transfer_var = Value("")
    app.focus_summary_text = TextBuffer()

    app._sync_focus_settings_summary()

    assert app.focus_active_profile_var.get() == "1080p Full HD  •  Manual Override"
    assert app.focus_transfer_var.get() == "VOD-ready MP4 / H.264 video / MP3 audio"
    assert "Audio         MP3" in app.focus_summary_text.value
    assert "Output mode   Manual Override" in app.focus_summary_text.value
    focus_ui_source = inspect.getsource(DownloaderApp._build_focus_ui)
    assert re.search(
        r'self\.manual_audio_codec_var\.trace_add\(\s*"write",\s*'
        r"lambda \*_args: self\._sync_focus_settings_summary\(\)\s*\)",
        focus_ui_source,
    )


def test_run_log_updates_activity_and_only_the_selected_active_run(tmp_path: Path):
    active_job = make_job(tmp_path)
    worker_copy = replace(active_job)
    app = DownloaderApp.__new__(DownloaderApp)
    app.active_job = active_job
    app._focus_selected_run_id = active_job.run_id
    app.log = TextBuffer()
    app.focus_log = TextBuffer()

    app._append_job_log(worker_copy, "active-only line")

    assert "active-only line" in app.log.value
    assert "active-only line" in app.focus_log.value
    assert active_job.activity_lines == ["active-only line"]

    app._focus_selected_run_id = "completed-run"
    app._append_job_log(worker_copy, "background active line")

    assert "background active line" in app.log.value
    assert "background active line" not in app.focus_log.value
    assert active_job.activity_lines[-1] == "background active line"


def test_live_activity_follows_tail_only_when_reader_is_already_at_tail():
    following = ScrollAwareTextBuffer(last=1.0)
    reading_history = ScrollAwareTextBuffer(last=0.72)

    DownloaderApp._append_log_widget(following, "new tail line")
    DownloaderApp._append_log_widget(reading_history, "new tail line")

    assert following.seen == ["end"]
    assert reading_history.seen == []
    assert "new tail line" in following.value
    assert "new tail line" in reading_history.value


def test_live_activity_never_reclaims_tail_after_explicit_reader_scroll():
    reading_history = ScrollAwareTextBuffer(last=1.0)
    reading_history._vodforge_user_scroll_locked = True

    DownloaderApp._append_log_widget(reading_history, "new tail line")

    assert reading_history.seen == []
    assert "new tail line" in reading_history.value


def test_same_run_activity_refresh_preserves_reader_viewport(tmp_path: Path):
    app = DownloaderApp.__new__(DownloaderApp)
    app.focus_log = ScrollAwareTextBuffer(last=0.72)
    app.focus_log._vodforge_user_scroll_locked = True
    app._focus_log_owner_run_id = "run-1"
    app._focus_log_rendered_text = "older activity"
    app._set_text = lambda widget, value, **_kwargs: setattr(widget, "value", value)

    app._render_focus_run_activity("run-1", "older activity\nnew line")

    assert app.focus_log.moved_to == [0.0]
    assert app.focus_log.seen == []
    assert app.focus_log._vodforge_user_scroll_locked is True


def test_new_run_activity_resets_scroll_ownership(tmp_path: Path):
    app = DownloaderApp.__new__(DownloaderApp)
    app.focus_log = ScrollAwareTextBuffer(last=0.72)
    app.focus_log._vodforge_user_scroll_locked = True
    app._focus_log_owner_run_id = "run-1"
    app._focus_log_rendered_text = "older activity"
    app._set_text = lambda widget, value, **_kwargs: setattr(widget, "value", value)

    app._render_focus_run_activity("run-2", "queued")

    assert app.focus_log.moved_to == []
    assert app.focus_log.seen == ["end"]
    assert app.focus_log._vodforge_user_scroll_locked is False
    assert app._focus_log_owner_run_id == "run-2"


def test_opening_activity_view_starts_at_latest_line():
    activity_view = Control()
    activity_log = IdleTextBuffer(last=0.4)
    activity_log._vodforge_user_scroll_locked = True
    app = DownloaderApp.__new__(DownloaderApp)
    app._focus_views = {"activity": activity_view}
    app._focus_nav_buttons = {"activity": Control()}
    app._focus_nav_underlines = {"activity": Control()}
    app._focus_nav_icons = {"activity": (None, None)}
    app.log = activity_log

    app._select_focus_view("activity")

    assert activity_view.raised is True
    assert app._focus_selected_view == "activity"
    assert activity_log._vodforge_user_scroll_locked is False
    assert activity_log.seen == ["end"]


def test_primary_view_shortcuts_are_stable_across_platforms():
    assert focus_view_shortcut_bindings("darwin") == (
        ("<Command-Key-1>", "forge"),
        ("<Command-Key-2>", "library"),
        ("<Command-Key-3>", "activity"),
    )
    expected_control = (
        ("<Control-Key-1>", "forge"),
        ("<Control-Key-2>", "library"),
        ("<Control-Key-3>", "activity"),
    )
    assert focus_view_shortcut_bindings("win32") == expected_control
    assert focus_view_shortcut_bindings("linux") == expected_control


def test_primary_view_shortcuts_route_through_canonical_view_authority():
    app = DownloaderApp.__new__(DownloaderApp)
    selected: list[str] = []
    bindings: list[tuple[str, object, str | None]] = []
    app._select_focus_view = selected.append
    app.bind = lambda sequence, callback, add=None: bindings.append(
        (sequence, callback, add)
    )

    app._bind_focus_view_shortcuts()

    assert [sequence for sequence, _callback, _add in bindings] == [
        sequence for sequence, _view in focus_view_shortcut_bindings()
    ]
    assert all(add == "+" for _sequence, _callback, add in bindings)
    library_callback = next(
        callback for sequence, callback, _add in bindings if sequence.endswith("Key-2>")
    )
    assert callable(library_callback)
    assert library_callback(object()) == "break"
    assert selected == ["library"]


def test_primary_navigation_buttons_remain_keyboard_focusable():
    focus_ui_source = inspect.getsource(DownloaderApp._build_focus_ui)

    assert (
        'style="FocusNav.TButton",\n                takefocus=True,' in focus_ui_source
    )
    assert "self._bind_focus_view_shortcuts()" in focus_ui_source


def test_compact_layout_does_not_schedule_a_forced_activity_tail_jump():
    layout_source = inspect.getsource(DownloaderApp._apply_focus_layout)

    assert (
        'focus_log.after_idle(lambda: self.focus_log.see("end"))' not in layout_source
    )


def test_completed_selection_freezes_detail_progress_while_active_run_advances(
    tmp_path: Path,
):
    active_job = make_job(tmp_path, video_id="active")
    completed_info = {
        "id": "completed",
        "title": "Completed run",
        "uploader": "Completed creator",
        "duration": 60,
        "vodforge_output_type": "MP4",
        "vodforge_run_id": "completed-run",
        "vodforge_run_activity": ["persisted completed activity"],
        "vodforge_encoding_summary": {
            "output": {
                "Resolution": "1920x1080",
                "Output rate-control mode": "Auto CBR",
            }
        },
    }
    app = DownloaderApp.__new__(DownloaderApp)
    app.active_job = active_job
    app.worker = LiveWorker()
    app._focus_active_override = False
    app._focus_selected_run_id = "completed-run"
    app.focus_active_title_var = Value("")
    app.focus_active_detail_var = Value("")
    app.focus_active_duration_var = Value("")
    app.focus_active_profile_var = Value("")
    app.focus_display_progress_var = Value(0)
    app.focus_percent_var = Value("0%")
    app.focus_display_status_var = Value("")
    app.focus_transfer_var = Value("")
    app.focus_run_status_var = Value("28% / Active")
    app.focus_summary_text = TextBuffer()
    app.focus_log = TextBuffer()
    app.progress_var = Value(28)
    app._display_focus_record_thumbnail = lambda *_args: None

    app._display_focus_metadata_snapshot(
        {"run_id": "completed-run", "kind": "completed"},
        completed_info,
    )
    app.progress_var.set(64)
    app._sync_focus_progress()

    assert app.focus_active_title_var.get() == "Completed run"
    assert app.focus_display_progress_var.get() == 100
    assert app.focus_percent_var.get() == "100%"
    assert app.focus_run_status_var.get() == "64%  /  Active"
    assert "persisted completed activity" in app.focus_log.value


def test_completed_run_thumbnail_selection_uses_each_records_own_image(tmp_path: Path):
    first = tmp_path / "first.jpg"
    second = tmp_path / "second.jpg"
    first.touch()
    second.touch()
    app = DownloaderApp.__new__(DownloaderApp)
    loaded: list[tuple[Path, str, str]] = []
    app._load_thumbnail_file = lambda path, *, target, owner_run_id="": loaded.append(
        (path, target, owner_run_id)
    )

    app._display_focus_record_thumbnail(
        {"run_id": "first-run"},
        {"preview_thumbnail_path": str(first)},
    )
    app._display_focus_record_thumbnail(
        {"run_id": "second-run"},
        {"preview_thumbnail_path": str(second)},
    )

    assert loaded == [
        (first, "active", "first-run"),
        (second, "active", "second-run"),
    ]


def test_bounded_thumbnail_fetch_is_not_serialized_behind_media_provider(monkeypatch):
    app = DownloaderApp.__new__(DownloaderApp)
    app._closing = False
    app._thumbnail_preview_request_ids = {"active": 7, "library": 0}
    app.events = queue.Queue()
    monkeypatch.setattr(
        "yt_downloader.app.download_bounded_url_bytes",
        lambda *_args, **_kwargs: b"image",
    )
    app._provider_network_coordinator = lambda: (_ for _ in ()).throw(
        AssertionError("provider gate used")
    )

    app._fetch_thumbnail_preview_request(
        7, "https://example.test/thumb.jpg", "active", "run-7"
    )

    kind, payload = app.events.get_nowait()
    assert kind == "thumbnail_preview_result"
    assert payload["data"] == b"image"
    assert payload["run_id"] == "run-7"


def test_thumbnail_request_generations_are_independent_by_surface():
    app = DownloaderApp.__new__(DownloaderApp)
    app._thumbnail_preview_request_ids = {"active": 0, "library": 0}

    assert app._invalidate_thumbnail_request("active") == 1
    assert app._thumbnail_request_ids() == {"active": 1, "library": 0}
    assert app._invalidate_thumbnail_request("library") == 1
    assert app._thumbnail_request_ids() == {"active": 1, "library": 1}
    assert app._invalidate_thumbnail_request("active") == 2
    assert app._thumbnail_request_ids() == {"active": 2, "library": 1}


def test_thumbnail_loading_requires_an_explicit_single_surface_owner():
    file_target = inspect.signature(DownloaderApp._load_thumbnail_file).parameters[
        "target"
    ]
    url_target = inspect.signature(DownloaderApp._load_thumbnail_preview).parameters[
        "target"
    ]

    assert file_target.default is inspect.Parameter.empty
    assert url_target.default is inspect.Parameter.empty
    app = DownloaderApp.__new__(DownloaderApp)
    app._thumbnail_preview_request_ids = {"active": 0, "library": 0}
    for invalid_target in ("both", "", "forge"):
        try:
            app._invalidate_thumbnail_request(invalid_target)
        except ValueError:
            pass
        else:
            raise AssertionError(
                f"ambiguous thumbnail owner {invalid_target!r} was accepted"
            )


def test_thumbnail_errors_render_only_on_the_owning_surface():
    class Label:
        def __init__(self):
            self.text = ""

        def config(self, **kwargs):
            self.text = str(kwargs.get("text") or "")

    app = DownloaderApp.__new__(DownloaderApp)
    app._thumbnail_preview_request_ids = {"active": 4, "library": 9}
    app.focus_active_thumbnail_label = Label()
    app.thumbnail_label = Label()

    app._display_thumbnail_preview_result(
        {
            "id": 4,
            "url": "https://example.invalid/active.jpg",
            "target": "active",
            "error": "active failed",
        }
    )

    assert "active failed" in app.focus_active_thumbnail_label.text
    assert app.thumbnail_label.text == ""


def test_download_jobs_receive_unique_ids_and_replace_preserves_one_run(tmp_path: Path):
    first = make_job(tmp_path, video_id="first")
    second = make_job(tmp_path, video_id="second")
    normalized_worker_copy = replace(first, url="https://youtu.be/first")

    assert first.run_id != second.run_id
    assert normalized_worker_copy.run_id == first.run_id


def test_active_run_suppresses_its_just_committed_library_record(tmp_path: Path):
    """History may commit before done, but that transition still renders one run card."""
    active_job = make_job(tmp_path)
    active_job.preview_info = {
        "id": "authority-id",
        "title": "Authority title",
        "vodforge_output_type": "MP4",
    }
    saved = upsert_history([], active_job.preview_info, tmp_path)[0]
    active_job.history_identities.add(history_identity(saved))

    app = DownloaderApp.__new__(DownloaderApp)
    app._focus_preview_runs = None
    app._focus_active_override = False
    app.active_job = active_job
    app.worker = None
    app.pending_jobs = []
    app._terminal_jobs = []
    app.metadata_items = [saved]
    app.url_var = Value("")
    app.focus_active_title_var = Value("Authority title")
    app.focus_active_detail_var = Value("Authority creator")
    app.status_var = Value("Finalizing")
    app.progress_var = Value(99)

    records = app._focus_run_records()

    assert [(record["kind"], record["run_id"]) for record in records] == [
        ("active", active_job.run_id)
    ]


def test_retry_clears_all_prior_run_ownership_before_launch(tmp_path: Path):
    failed_job = make_job(tmp_path)
    failed_job.metadata_keys.add(("authority-id", "MP4"))
    failed_job.history_identities.add(("authority-id", str(tmp_path), "MP4"))
    failed_job.terminal_status = "Failed"
    app = DownloaderApp.__new__(DownloaderApp)
    app._terminal_jobs = [failed_job]
    app.active_job = None
    app.worker = None
    launched: list[DownloadJob] = []
    app._launch_download_job = launched.append

    app._retry_terminal_job(failed_job)

    assert len(launched) == 1
    assert launched[0].run_id != failed_job.run_id
    assert launched[0].metadata_keys == set()
    assert launched[0].history_identities == set()
    assert launched[0].terminal_status is None


def test_retry_preserves_playlist_identity_and_removes_the_old_terminal_row(
    tmp_path: Path,
):
    failed_job = make_job(tmp_path)
    failed_job.url = "https://youtu.be/authority-id"
    failed_job.terminal_status = "Failed"
    failed_job.preview_info = {
        "id": "authority-id",
        "playlist_id": "PLauthority",
        "vodforge_output_type": "MP4",
        "vodforge_terminal_run_id": failed_job.run_id,
    }
    app = DownloaderApp.__new__(DownloaderApp)
    app._terminal_jobs = [failed_job]
    app.metadata_items = [dict(failed_job.preview_info)]
    app.active_job = None
    app.worker = None
    launched: list[DownloadJob] = []
    app._launch_download_job = launched.append

    app._retry_terminal_job(failed_job)

    assert len(launched) == 1
    assert (
        launched[0].url
        == "https://www.youtube.com/watch?v=authority-id&list=PLauthority"
    )
    assert launched[0].urls == [launched[0].url]
    assert app.metadata_items == []


def test_skipped_item_is_one_terminal_run_not_a_preview_duplicate(tmp_path: Path):
    skipped = make_job(tmp_path)
    skipped.terminal_status = "Skipped"
    skipped.preview_info = {
        "id": "authority-id",
        "title": "Skipped item",
        "vodforge_output_type": "MP4",
        "vodforge_terminal_status": "Skipped",
        "vodforge_terminal_run_id": skipped.run_id,
    }
    skipped.metadata_keys.add(("authority-id", "MP4"))
    app = DownloaderApp.__new__(DownloaderApp)
    app._focus_preview_runs = None
    app._focus_active_override = False
    app.active_job = None
    app.worker = None
    app.pending_jobs = []
    app._terminal_jobs = [skipped]
    app._completed_jobs = []
    app.metadata_items = [dict(skipped.preview_info)]
    app.url_var = Value("")
    app.focus_active_title_var = Value("")
    app.focus_active_detail_var = Value("")
    app.status_var = Value("Ready")
    app.progress_var = Value(0)

    records = app._focus_run_records()

    assert [(record["kind"], record["run_id"]) for record in records] == [
        ("skipped", skipped.run_id)
    ]
    assert records[0]["metadata_index"] == 0


def test_retry_joins_latest_queue_position_with_fresh_authority(tmp_path: Path):
    failed = make_job(tmp_path, video_id="failed")
    failed.terminal_status = "Failed"
    active = make_job(tmp_path, video_id="active")
    queued = make_job(tmp_path, video_id="queued")
    app = DownloaderApp.__new__(DownloaderApp)
    app._terminal_jobs = [failed]
    app.metadata_items = []
    app.active_job = active
    app.worker = LiveWorker()
    app.pending_jobs = [queued]
    app._enqueue_queue_preview = lambda _job: None
    app._refresh_focus_run_deck = lambda: None

    app._retry_terminal_job(failed)

    assert app.pending_jobs[0] is queued
    assert app.pending_jobs[1].run_id != failed.run_id
    assert app.pending_jobs[1].url == failed.url


def test_newest_completed_run_remains_owner_of_a_repeated_history_identity(
    tmp_path: Path,
):
    info = {"id": "same", "title": "Same item", "vodforge_output_type": "MP4"}
    saved = upsert_history([], info, tmp_path)[0]
    identity = history_identity(saved)
    newest = make_job(tmp_path, video_id="same")
    oldest = make_job(tmp_path, video_id="same")
    newest.history_identities.add(identity)
    oldest.history_identities.add(identity)
    app = DownloaderApp.__new__(DownloaderApp)
    app._focus_preview_runs = None
    app._focus_active_override = False
    app.active_job = None
    app.worker = None
    app.pending_jobs = []
    app._terminal_jobs = []
    app._completed_jobs = [newest, oldest]
    app.metadata_items = [saved]
    app.url_var = Value("")
    app.focus_active_title_var = Value("")
    app.focus_active_detail_var = Value("")
    app.status_var = Value("Ready")
    app.progress_var = Value(0)

    records = app._focus_run_records()

    assert len(records) == 1
    assert records[0]["job"] is newest
    assert records[0]["run_id"] == newest.run_id


def test_one_item_skip_does_not_archive_a_second_parent_terminal_card(tmp_path: Path):
    parent = make_job(tmp_path)
    parent.item_terminal_emitted = True
    app = DownloaderApp.__new__(DownloaderApp)
    app.active_job = parent
    app._append_job_log = lambda *_args: None
    app._archive_active_terminal_job = lambda *_args: (_ for _ in ()).throw(
        AssertionError("duplicate parent terminal")
    )
    app.progress_var = Value(0)
    app.status_var = Value("")
    app.download_button = Control()
    app.cancel_button = Control()
    app.skip_video_button = Control()
    app.skip_url_button = Control()
    launches: list[DownloadJob] = []
    focused: list[DownloadJob] = []
    app._launch_next_pending_job = lambda: launches.append(parent) or False
    app._focus_terminal_job = focused.append

    app._finish_run_ui("Stopped after skip", "Stopped", "Stopped")

    assert app.status_var.get() == "Stopped after skip"
    assert launches == [parent]
    assert focused == []


def test_finish_run_orders_persistence_and_archive_before_successor_handoff(
    tmp_path: Path,
):
    finished = make_job(tmp_path, video_id="finished")
    successor = make_job(tmp_path, video_id="successor")
    app = DownloaderApp.__new__(DownloaderApp)
    app.active_job = finished
    events: list[str] = []
    app._library_run_is_suppressed = lambda _job: False
    app._append_job_log = lambda job, _message: events.append(f"log:{job.run_id}")
    app._persist_job_activity_to_history = lambda job: events.append(
        f"persist:{job.run_id}"
    )
    app._archive_active_terminal_job = lambda _status, _message: events.append(
        f"archive:{app.active_job.run_id}"
    )
    app._archive_active_completed_job = lambda *_args: (_ for _ in ()).throw(
        AssertionError("stopped run used completed archive")
    )
    app.progress_var = SimpleNamespace(
        set=lambda _value: events.append("render:progress")
    )
    app.status_var = SimpleNamespace(set=lambda _value: events.append("render:status"))
    app.download_button = SimpleNamespace(
        config=lambda **_kwargs: events.append("render:download")
    )
    app.cancel_button = SimpleNamespace(
        config=lambda **_kwargs: events.append("render:cancel")
    )
    app.skip_video_button = SimpleNamespace(
        config=lambda **_kwargs: events.append("render:skip-video")
    )
    app.skip_url_button = SimpleNamespace(
        config=lambda **_kwargs: events.append("render:skip-url")
    )

    def launch_successor() -> bool:
        events.append(f"launch:{app.active_job.run_id}")
        app.active_job = successor
        return True

    app._launch_next_pending_job = launch_successor
    app._focus_terminal_job = lambda job: events.append(f"focus:{job.run_id}")

    app._finish_run_ui("Stopped cleanly", "Stopped", "Stopped", progress=42)

    assert events == [
        f"log:{finished.run_id}",
        f"persist:{finished.run_id}",
        f"archive:{finished.run_id}",
        "render:progress",
        "render:status",
        "render:download",
        "render:cancel",
        "render:skip-video",
        "render:skip-url",
        f"launch:{finished.run_id}",
        f"focus:{finished.run_id}",
    ]
    assert app.active_job is successor


def test_suppressed_finish_reconciles_captured_run_after_successor_handoff(
    tmp_path: Path,
):
    finished = make_job(tmp_path, video_id="removed")
    successor = make_job(tmp_path, video_id="successor")
    unrelated_terminal = make_job(tmp_path, video_id="failed")
    unrelated_completed = make_job(tmp_path, video_id="completed")
    app = DownloaderApp.__new__(DownloaderApp)
    app.active_job = finished
    app._terminal_jobs = [finished, unrelated_terminal]
    app._completed_jobs = [finished, unrelated_completed]
    events: list[str] = []
    app._library_run_is_suppressed = lambda job: job is finished
    app._append_log = lambda _message: events.append("log")
    app._append_job_log = lambda *_args: (_ for _ in ()).throw(
        AssertionError("suppressed run received an owned log")
    )
    app._persist_job_activity_to_history = lambda *_args: (_ for _ in ()).throw(
        AssertionError("suppressed run persisted activity")
    )
    app._archive_active_terminal_job = lambda *_args: (_ for _ in ()).throw(
        AssertionError("suppressed run was archived")
    )
    app._archive_active_completed_job = app._archive_active_terminal_job
    app.progress_var = Value(12)
    app.status_var = Value("")
    app.download_button = Control()
    app.cancel_button = Control()
    app.skip_video_button = Control()
    app.skip_url_button = Control()

    def launch_successor() -> bool:
        events.append("launch")
        app.active_job = successor
        return True

    app._launch_next_pending_job = launch_successor

    def reconcile(removed_run_ids: set[str]) -> None:
        assert app.active_job is successor
        events.append("reconcile")
        assert removed_run_ids == {finished.run_id}

    app._reconcile_focus_after_library_removal = reconcile
    app._focus_terminal_job = lambda *_args: (_ for _ in ()).throw(
        AssertionError("suppressed run received terminal focus")
    )

    app._finish_run_ui("Removed from Library", "Stopped", "Stopped")

    assert events == ["log", "launch", "reconcile"]
    assert app._terminal_jobs == [unrelated_terminal]
    assert app._completed_jobs == [unrelated_completed]
    assert app.active_job is successor


def test_stopped_finish_without_focus_widgets_clears_active_run(tmp_path: Path):
    finished = make_job(tmp_path, video_id="headless")
    app = DownloaderApp.__new__(DownloaderApp)
    app.active_job = finished
    app.pending_jobs = []
    app._append_job_log = lambda *_args: None
    app._persist_job_activity_to_history = lambda *_args: None
    archived: list[tuple[str, str]] = []
    app._archive_active_terminal_job = lambda status, message: archived.append(
        (status, message)
    )
    app.progress_var = Value(27)
    app.status_var = Value("")
    app.download_button = Control()
    app.cancel_button = Control()
    app.skip_video_button = Control()
    app.skip_url_button = Control()
    launches: list[DownloadJob] = []

    def finish_without_successor() -> bool:
        launches.append(finished)
        app.active_job = None
        return False

    app._launch_next_pending_job = finish_without_successor

    app._finish_run_ui("Stopped cleanly", "Stopped", "Stopped")

    assert archived == [("Stopped", "Stopped cleanly")]
    assert launches == [finished]
    assert app.active_job is None
    assert app.status_var.get() == "Stopped cleanly"
    assert app.download_button.configured == [{"state": "normal"}]
    assert app.cancel_button.configured == [{"state": "disabled"}]
    assert app.skip_video_button.configured == [{"state": "disabled"}]
    assert app.skip_url_button.configured == [{"state": "disabled"}]


def test_single_url_worker_mutates_the_active_authority_not_a_private_copy(
    tmp_path: Path,
):
    active = make_job(tmp_path)
    app = DownloaderApp.__new__(DownloaderApp)

    def worker(received):
        assert received is active
        received.item_terminal_emitted = True

    app._download_worker_single = worker
    app._download_worker(active)

    assert active.item_terminal_emitted is True


def test_background_run_thumbnail_error_cannot_replace_selected_run_surface():
    class Label:
        def __init__(self):
            self.text = "selected thumbnail"

        def config(self, **kwargs):
            self.text = str(kwargs.get("text") or "")

    app = DownloaderApp.__new__(DownloaderApp)
    app._thumbnail_preview_request_ids = {
        "active": 0,
        "library": 0,
        "run:active-run": 3,
    }
    app._focus_selected_run_id = "completed-run"
    app.focus_active_thumbnail_label = Label()
    app.thumbnail_label = Label()
    app._refresh_focus_run_deck = lambda: None

    app._display_thumbnail_preview_result(
        {
            "id": 3,
            "url": "https://example.invalid/thumb.jpg",
            "target": "run:active-run",
            "run_id": "active-run",
            "error": "network failed",
        }
    )

    assert app.focus_active_thumbnail_label.text == "selected thumbnail"


def test_background_run_thumbnail_decode_error_cannot_replace_selected_run_surface(
    monkeypatch,
):
    class Label:
        def __init__(self):
            self.text = "selected thumbnail"

        def config(self, **kwargs):
            self.text = str(kwargs.get("text") or "")

    app = DownloaderApp.__new__(DownloaderApp)
    app._thumbnail_preview_request_ids = {
        "active": 0,
        "library": 0,
        "run:active-run": 3,
    }
    app._focus_selected_run_id = "completed-run"
    app.focus_active_thumbnail_label = Label()
    app.thumbnail_label = Label()
    app.focus_run_deck = object()
    app._refresh_focus_run_deck = lambda: None
    monkeypatch.setattr(
        app_module,
        "decode_bounded_thumbnail",
        lambda _data: (_ for _ in ()).throw(ValueError("invalid pixels")),
    )

    app._display_thumbnail_preview_result(
        {
            "id": 3,
            "url": "https://example.invalid/thumb.jpg",
            "target": "run:active-run",
            "run_id": "active-run",
            "data": b"not an image",
        }
    )

    assert app.thumbnail_label.text == "selected thumbnail"


def test_all_resizable_popouts_enforce_content_appropriate_minimums():
    settings_source = inspect.getsource(FocusSettingsDialog.__init__)
    output_source = inspect.getsource(DownloaderApp._show_focus_output_details)
    selected_source = inspect.getsource(DownloaderApp._show_selected_metadata_details)

    assert "popup.minsize(700, 540)" in settings_source
    assert "popup.minsize(480, 300)" in output_source
    assert "popup.minsize(560, 520)" in selected_source
    assert "height=135" in selected_source


def test_ui_builder_has_one_focus_ui_authority(monkeypatch):
    app = DownloaderApp.__new__(DownloaderApp)
    built: list[str] = []
    app._build_focus_ui = lambda: built.append("focus")
    monkeypatch.setenv("VODFORGE_LEGACY_UI", "1")

    app._build_ui()

    assert built == ["focus"]


def test_focus_settings_keep_manual_controls_in_the_mp4_flow_and_release_combo_selection():
    settings_source = inspect.getsource(FocusSettingsDialog._build_mp4_section)
    mode_source = inspect.getsource(FocusSettingsDialog._build_mp4_mode_controls)
    manual_source = inspect.getsource(FocusSettingsDialog._build_manual_controls)
    flags_source = inspect.getsource(FocusSettingsDialog._build_mp4_output_flags)
    combo_source = inspect.getsource(FocusSettingsDialog._bind_readonly_combo)
    show_source = inspect.getsource(DownloaderApp._show_focus_settings)

    description_index = settings_source.index("self._build_mp4_mode_controls")
    manual_index = settings_source.index("self._build_manual_controls")
    checkboxes_index = settings_source.index("self._build_mp4_output_flags")

    assert description_index < manual_index < checkboxes_index
    assert "textvariable=self.bindings.export_mode_description" in mode_source
    assert "manual = ttk.Frame(root" not in manual_source
    assert 'manual.grid(row=4, column=0, columnspan=2, sticky="ew"' in manual_source
    assert '"Video bitrate (kbps)"' in manual_source
    assert '"Audio bitrate (kbps)"' in manual_source
    assert '"Audio codec",' in manual_source
    assert "bindings.manual_audio_codec" in manual_source
    assert "self.options.manual_audio_codecs" in manual_source
    assert '"Sample rate"' in manual_source
    assert '"Channels"' in manual_source
    assert '"Encoding speed"' in manual_source
    assert 'text="Save thumbnail"' in flags_source
    assert "self.actions.refresh_manual_visibility" in mode_source
    assert "combo.selection_clear()" in combo_source
    assert "self.popup.focus_set()" in combo_source
    assert "self.use_nvenc_var.set(False)" in show_source
    assert 'nvenc.state(["disabled"])' in flags_source


def test_focus_settings_dialog_owns_conditional_widget_visibility():
    class Frame:
        def __init__(self):
            self.visible = True

        def winfo_exists(self):
            return True

        def grid(self):
            self.visible = True

        def grid_remove(self):
            self.visible = False

    dialog = FocusSettingsDialog.__new__(FocusSettingsDialog)
    dialog.mp4_frame = Frame()
    dialog.mp3_frame = Frame()
    dialog.manual_frame = Frame()
    dialog.cookie_file_frame = Frame()
    dialog.cookie_browser_frame = Frame()
    dialog.mp3_cover_file_frame = Frame()

    dialog.refresh_output_sections(OutputType.MP3)
    dialog.refresh_manual_settings(False)
    dialog.refresh_cookie_source(app_module.CookieSource.BROWSER)
    dialog.refresh_cover_art_mode("No Art")

    assert dialog.mp4_frame.visible is False
    assert dialog.mp3_frame.visible is True
    assert dialog.manual_frame.visible is False
    assert dialog.cookie_file_frame.visible is False
    assert dialog.cookie_browser_frame.visible is True
    assert dialog.mp3_cover_file_frame.visible is False


def test_focus_settings_preview_closes_only_after_success_and_close_is_idempotent():
    class Popup:
        def __init__(self):
            self.destroy_count = 0

        def destroy(self):
            self.destroy_count += 1

    preview_results = iter((False, True))
    closed: list[str] = []
    dialog = FocusSettingsDialog.__new__(FocusSettingsDialog)
    dialog.popup = Popup()
    dialog._closed = False
    dialog.actions = SimpleNamespace(
        preview_metadata=lambda: next(preview_results),
        on_closed=lambda: closed.append("closed"),
    )

    dialog._preview_and_close()
    assert dialog.popup.destroy_count == 0
    assert closed == []

    dialog._preview_and_close()
    dialog.close()
    assert dialog.popup.destroy_count == 1
    assert closed == ["closed"]


def test_focus_settings_duplicate_open_focuses_the_existing_window():
    class Popup:
        def __init__(self):
            self.lift_count = 0
            self.focus_count = 0

        def winfo_exists(self):
            return True

        def lift(self):
            self.lift_count += 1

        def focus_force(self):
            self.focus_count += 1

    dialog = FocusSettingsDialog.__new__(FocusSettingsDialog)
    dialog.popup = Popup()

    assert dialog.focus_existing() is True
    assert dialog.popup.lift_count == 1
    assert dialog.popup.focus_count == 1


def test_all_runs_uses_bounded_anchored_drop_up_with_internal_scrolling():
    run_list_source = inspect.getsource(DownloaderApp._show_focus_run_menu)
    forge_source = inspect.getsource(DownloaderApp._build_focus_forge_view)
    close_source = inspect.getsource(DownloaderApp._schedule_focus_run_menu_close)

    assert 'popup = tk.Frame(self, bg=THEME["border"]' in run_list_source
    assert "popup.overrideredirect(True)" not in run_list_source
    assert "popup.transient(self)" not in run_list_source
    assert "visible_rows = min(5, max(1, len(records)))" in run_list_source
    assert "tk.Canvas(" in run_list_source
    assert "yscrollincrement=1" in run_list_source
    assert "SleekScrollbar(root, command=run_list.yview)" in run_list_source
    assert (
        'run_list.grid(row=0, column=0, sticky="nsew", padx=(14, 6), pady=12)'
        in run_list_source
    )
    assert "bind_smooth_vertical_wheel(" in run_list_source
    assert 'mode="increments"' in run_list_source
    assert "button.winfo_rooty() - self.winfo_rooty() - height + 1" in run_list_source
    assert "popup.place(x=x, y=y, width=width, height=height)" in run_list_source
    assert "width = min(440" in run_list_source
    assert "height = min(184" in run_list_source
    assert re.search(
        r'self\.focus_run_overflow_button\.bind\(\s*"<Enter>"', forge_source
    )
    assert re.search(
        r'self\.focus_run_overflow_button\.bind\(\s*"<Leave>"', forge_source
    )
    assert "self._cancel_focus_run_menu_close()" in run_list_source
    assert "existing.destroy()" not in run_list_source
    assert re.search(r'popup\.bind\(\s*"<Enter>"', run_list_source)
    assert re.search(r'popup\.bind\(\s*"<Leave>"', run_list_source)
    assert "hovered is button or inside_popup" in close_source
    assert "self.after(40, close_if_pointer_left)" in close_source
    assert (
        'selected_run_id = str(self._focus_selected_run_id or "").strip()'
        in run_list_source
    )
    assert "selected_index = next(" in run_list_source
    assert (
        'str(record.get("run_id") or "").strip() == selected_run_id' in run_list_source
    )
    assert run_list_source.index("selected_index = next(") < run_list_source.index(
        "for index, record in enumerate(records):"
    )


def test_library_table_and_run_picker_keep_all_items_reachable_at_every_size():
    focus_ui_source = inspect.getsource(DownloaderApp._build_focus_ui)
    library_source = inspect.getsource(DownloaderApp._build_focus_library_view)
    forge_source = inspect.getsource(DownloaderApp._build_focus_forge_view)
    deck_source = inspect.getsource(DownloaderApp._refresh_focus_run_deck)
    tile_source = inspect.getsource(DownloaderApp._render_focus_run_deck_tile)
    layout_source = inspect.getsource(DownloaderApp._apply_focus_layout)
    library_layout_source = inspect.getsource(DownloaderApp._apply_focus_library_layout)
    deck_resize_source = inspect.getsource(
        DownloaderApp._schedule_focus_run_deck_geometry_refresh
    )
    root_resize_source = inspect.getsource(DownloaderApp._schedule_focus_layout)

    assert 'orient="horizontal"' in library_source
    assert "xscrollcommand=tree_x_scroll.set" in library_source
    assert (
        'video_tree.layout_column("creator", width=120, minwidth=90'
        in library_layout_source
    )
    assert (
        'video_tree.layout_column("location", width=140, minwidth=100'
        in library_layout_source
    )
    title_column_pattern = (
        r'video_tree\.layout_column\(\s*"title",\s*width=360,\s*minwidth=220,'
        r"\s*stretch=True,\s*stretchmax=None\s*\)"
    )
    assert re.search(title_column_pattern, library_layout_source)
    assert "width=0, minwidth=0" not in library_layout_source
    assert (
        "library_vertical_mode = focus_library_vertical_layout_mode(height)"
        in layout_source
    )
    assert re.search(
        r'library_mode\s*=\s*\(\s*"compact"\s*if compact or '
        r'library_vertical_mode == "compact"\s*else '
        r"focus_library_layout_mode\(width\)\s*\)",
        layout_source,
    )
    assert "focus_library_action_layout_mode(" not in library_layout_source
    assert "self.focus_library_action_buttons" not in library_layout_source
    assert (
        "if not self.focus_library_menu_button.winfo_manager():"
        in library_layout_source
    )
    assert "library_mode," in layout_source
    assert "library_vertical_mode," in layout_source
    assert "library_mode=library_mode," in layout_source
    assert "vertical_mode=library_vertical_mode," in layout_source
    assert 'if library_mode == "compact":' in library_layout_source
    assert "library_actions_collapsed" not in library_layout_source
    assert (
        'video_tree.layout_column("index", width=44, minwidth=38, stretch=True)'
        in library_layout_source
    )
    assert re.search(title_column_pattern, library_layout_source)
    assert (
        'video_tree.layout_column("duration", width=72, minwidth=62, stretch=True)'
        in library_layout_source
    )
    assert (
        'video_tree.layout_column("creator", width=120, minwidth=90, stretch=True)'
        in library_layout_source
    )
    assert (
        'video_tree.layout_column("id", width=90, minwidth=72, stretch=True)'
        in library_layout_source
    )
    assert (
        'video_tree.layout_column("location", width=140, minwidth=100, stretch=True)'
        in library_layout_source
    )
    assert (
        "self.focus_metadata_content.columnconfigure(0, weight=1)"
        in library_layout_source
    )
    assert (
        "self.focus_metadata_content.columnconfigure(1, weight=0, minsize=410)"
        in library_layout_source
    )
    assert (
        "self.focus_metadata_content.columnconfigure(1, weight=0, minsize=330)"
        in library_layout_source
    )
    library_layout_call = layout_source.index("self._apply_focus_library_layout(")
    destination_sync = layout_source.index("self._sync_focus_destination()")
    deck_refresh = layout_source.index("self._refresh_focus_run_deck()")
    assert library_layout_call < destination_sync < deck_refresh
    assert "limit = focus_run_deck_capacity(deck_width)" in deck_source
    assert "for column in range(4):" in deck_source
    assert "self._render_focus_run_deck_tile(" in deck_source
    assert "visible_count=len(visible)" in deck_source
    assert "right_pad = 5 if column < visible_count - 1 else 9" in tile_source
    assert re.search(
        r'deck\.bind\(\s*"<Configure>",\s*'
        r"self\._schedule_focus_run_deck_geometry_refresh",
        forge_source,
    )
    assert (
        'capacity == self.__dict__.get("_focus_run_deck_rendered_capacity")'
        in deck_resize_source
    )
    assert "self.focus_run_overflow_button.grid()" in deck_source
    assert "if self._focus_run_records():" in layout_source
    assert "ttk.Sizegrip(self" in focus_ui_source
    assert 'self.bind("<Configure>", self._schedule_focus_layout' in focus_ui_source
    assert "self.after(16, apply)" not in root_resize_source
    assert "self._apply_focus_layout(width=width, height=height)" in root_resize_source
    assert "self.after_idle(refresh)" not in deck_resize_source


def test_native_resize_applies_live_dimensions_without_waiting_for_pointer_release():
    class LayoutProbe:
        def __init__(self):
            self.calls = []

        def _apply_focus_layout(self, **kwargs):
            self.calls.append(kwargs)

    probe = LayoutProbe()
    event = SimpleNamespace(widget=probe, width=918, height=701)

    DownloaderApp._schedule_focus_layout(probe, event)

    assert probe.calls == [{"width": 918, "height": 701}]


def test_native_resize_callbacks_never_rewrite_the_window_anchor_or_opposite_edge():
    schedule_source = inspect.getsource(DownloaderApp._schedule_focus_layout)
    layout_source = inspect.getsource(DownloaderApp._apply_focus_layout)

    for source in (schedule_source, layout_source):
        assert ".geometry(" not in source
        assert ".wm_geometry(" not in source
        assert "winfo_rootx" not in source
        assert "winfo_rooty" not in source


def test_native_window_dimensions_do_not_propagate_from_responsive_children():
    init_source = inspect.getsource(DownloaderApp.__init__)

    geometry_index = init_source.index("self.geometry(initial_window_geometry")
    propagation_index = init_source.index("self.pack_propagate(False)")
    build_index = init_source.index("self._build_ui()")

    assert geometry_index < propagation_index < build_index
    assert "self.pack_propagate(True)" not in init_source


def test_library_padding_scheduler_runs_before_unchanged_layout_short_circuit():
    layout_source = inspect.getsource(DownloaderApp._apply_focus_layout)

    padding_index = layout_source.index(
        "self._schedule_focus_library_padding(library_padding)"
    )
    signature_guard = re.search(
        r"if\s*\(\s*layout_signature == self\.__dict__\.get\("
        r'"_focus_layout_signature"\)\s*and not force\s*\)',
        layout_source,
    )

    assert signature_guard is not None
    assert padding_index < signature_guard.start()


def test_slow_native_resize_coalesces_cosmetic_library_centering():
    class GridProbe:
        def __init__(self):
            self.padding = []

        def grid_configure(self, **kwargs):
            self.padding.append(kwargs["padx"])

    class PaddingProbe:
        _apply_pending_focus_library_padding = (
            DownloaderApp._apply_pending_focus_library_padding
        )
        _set_focus_library_padding = DownloaderApp._set_focus_library_padding

        def __init__(self):
            self.focus_library_actions = GridProbe()
            self.focus_metadata_content = GridProbe()
            self.focus_library_summary = GridProbe()
            self._focus_library_horizontal_padding = 18
            self.callbacks = {}
            self.cancelled = []
            self.delays = []

        def after(self, delay, callback):
            after_id = f"after-{len(self.delays) + 1}"
            self.delays.append(delay)
            self.callbacks[after_id] = callback
            return after_id

        def after_cancel(self, after_id):
            self.cancelled.append(after_id)
            self.callbacks.pop(after_id, None)

    probe = PaddingProbe()

    DownloaderApp._schedule_focus_library_padding(probe, 34)
    DownloaderApp._schedule_focus_library_padding(probe, 50)
    DownloaderApp._schedule_focus_library_padding(probe, 66)

    assert probe.focus_library_actions.padding == []
    assert probe.focus_metadata_content.padding == []
    assert probe.focus_library_summary.padding == []
    assert probe.delays == [120, 120, 120]
    assert probe.cancelled == ["after-1", "after-2"]
    assert tuple(probe.callbacks) == ("after-3",)

    probe.callbacks["after-3"]()

    assert probe.focus_library_actions.padding == [66]
    assert probe.focus_metadata_content.padding == [66]
    assert probe.focus_library_summary.padding == [66]
    assert probe._focus_library_horizontal_padding == 66


def test_returning_to_applied_library_padding_cancels_stale_resize_work():
    class PaddingProbe:
        _apply_pending_focus_library_padding = (
            DownloaderApp._apply_pending_focus_library_padding
        )
        _set_focus_library_padding = DownloaderApp._set_focus_library_padding

        def __init__(self):
            self._focus_library_horizontal_padding = 18
            self.callbacks = {}
            self.cancelled = []

        def after(self, _delay, callback):
            self.callbacks["pending"] = callback
            return "pending"

        def after_cancel(self, after_id):
            self.cancelled.append(after_id)
            self.callbacks.pop(after_id, None)

    probe = PaddingProbe()

    DownloaderApp._schedule_focus_library_padding(probe, 50)
    DownloaderApp._schedule_focus_library_padding(probe, 18)

    assert probe.cancelled == ["pending"]
    assert probe.callbacks == {}
    assert probe._focus_library_pending_horizontal_padding == 18


def test_ultrawide_resize_burst_releases_large_live_padding_once():
    class GridProbe:
        def __init__(self):
            self.padding = []

        def grid_configure(self, **kwargs):
            self.padding.append(kwargs["padx"])

    class PaddingProbe:
        _apply_pending_focus_library_padding = (
            DownloaderApp._apply_pending_focus_library_padding
        )
        _set_focus_library_padding = DownloaderApp._set_focus_library_padding

        def __init__(self):
            self.focus_library_actions = GridProbe()
            self.focus_metadata_content = GridProbe()
            self.focus_library_summary = GridProbe()
            self._focus_library_horizontal_padding = 480
            self.callbacks = {}
            self.cancelled = []
            self.delays = []

        def after(self, delay, callback):
            after_id = f"after-{len(self.delays) + 1}"
            self.delays.append(delay)
            self.callbacks[after_id] = callback
            return after_id

        def after_cancel(self, after_id):
            self.cancelled.append(after_id)
            self.callbacks.pop(after_id, None)

    probe = PaddingProbe()

    DownloaderApp._schedule_focus_library_padding(probe, 464)
    DownloaderApp._schedule_focus_library_padding(probe, 448)

    assert probe.focus_library_actions.padding == [18]
    assert probe.focus_metadata_content.padding == [18]
    assert probe.focus_library_summary.padding == [18]
    assert probe._focus_library_horizontal_padding == 18
    assert probe.cancelled == ["after-1"]

    probe.callbacks["after-2"]()

    assert probe.focus_library_actions.padding == [18, 448]
    assert probe.focus_metadata_content.padding == [18, 448]
    assert probe.focus_library_summary.padding == [18, 448]
    assert probe._focus_library_horizontal_padding == 448


def test_run_deck_capacity_crossing_refreshes_synchronously_once():
    class DeckProbe:
        def __init__(self):
            self._focus_run_deck_rendered_capacity = 3
            self.refreshes = 0

        def _refresh_focus_run_deck(self):
            self.refreshes += 1
            self._focus_run_deck_rendered_capacity = 4

    probe = DeckProbe()
    event = SimpleNamespace(width=900)

    DownloaderApp._schedule_focus_run_deck_geometry_refresh(probe, event)
    DownloaderApp._schedule_focus_run_deck_geometry_refresh(probe, event)

    assert probe.refreshes == 1


def test_run_deck_tile_extraction_preserves_interaction_and_update_order():
    deck_source = inspect.getsource(DownloaderApp._refresh_focus_run_deck)
    tile_source = inspect.getsource(DownloaderApp._render_focus_run_deck_tile)

    assert (
        "status_label.configure(textvariable=self.focus_run_status_var)" in tile_source
    )
    assert "variable=self.progress_var" in tile_source
    assert "job: DownloadJob = verified_retry_job" in tile_source
    assert "item: dict[str, Any] = record" in tile_source
    assert "card_widgets: tuple[tk.Widget, ...] = tuple(hover_widgets)" in tile_source
    assert "hover_widgets.append(retry_button)" in tile_source
    assert "hover_widgets.append(play_button)" in tile_source
    assert all(
        line.strip()
        not in {"widgets.append(retry_button)", "widgets.append(play_button)"}
        for line in tile_source.splitlines()
    )
    assert tile_source.index(
        "source = self._focus_thumbnail_source_for_record(record)"
    ) < tile_source.index("self._focus_run_thumbnail_images.append(thumbnail)")
    assert tile_source.index(
        'play_button.bind(\n                "<Button-1>",'
    ) < tile_source.index("hover_widgets.append(play_button)")
    render_index = deck_source.index("self._render_focus_run_deck_tile(")
    aggregate_index = deck_source.index("completed = sum(")
    count_index = deck_source.index("self.focus_run_count_var.set(", aggregate_index)
    overflow_index = deck_source.index(
        "self.focus_run_overflow_button.grid()",
        count_index,
    )
    assert render_index < aggregate_index < count_index < overflow_index


def test_library_actions_remain_one_stable_menu_at_every_width():
    library_source = inspect.getsource(DownloaderApp._build_focus_library_view)
    compact_actions_source = inspect.getsource(DownloaderApp._show_library_actions_menu)
    row_actions_source = inspect.getsource(DownloaderApp._show_library_row_menu)
    popup_source = inspect.getsource(DownloaderApp._show_selected_metadata_details)
    forge_actions_source = inspect.getsource(DownloaderApp._show_focus_run_actions_menu)

    assert 'text="Actions"' in library_source
    assert "width=7" in library_source
    assert "focus_library_action_buttons" not in library_source
    assert "focus_library_copy_buttons" not in library_source
    for label in (
        "Copy tags",
        "Copy description",
        "Copy thumbnail URL",
        "Copy YouTube URL",
        "Open saved location",
    ):
        assert label in compact_actions_source
    for source in (
        compact_actions_source,
        row_actions_source,
        popup_source,
        forge_actions_source,
    ):
        assert "Copy YouTube URL" in source
    assert compact_actions_source.count("_run_library_copy_action") == 4


def test_primary_scroll_surfaces_use_high_resolution_trackpad_bindings():
    library_source = inspect.getsource(DownloaderApp._build_focus_library_view)
    activity_source = inspect.getsource(DownloaderApp._build_focus_activity_view)
    forge_source = inspect.getsource(DownloaderApp._build_focus_forge_view)
    pixel_table_source = inspect.getsource(app_module.PixelScrollTable)
    wheel_binding_source = inspect.getsource(app_module.bind_smooth_vertical_wheel)

    assert "self.video_tree = PixelScrollTable(" in library_source
    assert 'target.bind("<TouchpadScroll>"' in pixel_table_source
    assert "tk::PreciseScrollDeltas" in inspect.getsource(
        app_module.touchpad_scroll_deltas
    )
    assert "yview_moveto" in pixel_table_source
    assert 'xview("moveto"' in pixel_table_source
    assert 'target.bind("<TouchpadScroll>"' in wheel_binding_source
    assert "pixel_scroll_target" in wheel_binding_source
    assert 'scroller.yview_scroll(pixels, "pixels")' in wheel_binding_source
    assert 'count("1.0", "end", "ypixels")' not in wheel_binding_source
    assert "bind_smooth_vertical_wheel(self.log" in activity_source
    assert 'mode="pixels"' in activity_source
    assert "bind_smooth_vertical_wheel(self.focus_log" in forge_source
    assert "bind_smooth_vertical_wheel(self.focus_summary_text" in forge_source


def test_library_tags_keep_a_usable_scrollable_surface_and_command_box_resize_is_native():
    library_source = inspect.getsource(DownloaderApp._build_focus_library_view)
    layout_source = inspect.getsource(DownloaderApp._apply_focus_layout)
    library_layout_source = inspect.getsource(DownloaderApp._apply_focus_library_layout)
    forge_source = inspect.getsource(DownloaderApp._build_focus_forge_view)

    assert "details.configure(width=410, height=360)" in library_source
    assert "details.rowconfigure(3, weight=2, minsize=96)" in library_source
    assert "details.rowconfigure(4, weight=3, minsize=120)" in library_source
    assert "focus_library_vertical_layout_mode(height)" in layout_source
    assert (
        "self.focus_library_view.rowconfigure(1, weight=4, minsize=360)"
        in library_layout_source
    )
    assert (
        "self.focus_library_view.rowconfigure(1, weight=2, minsize=360)"
        in library_layout_source
    )
    assert 'bind_smooth_vertical_wheel(text_widget, mode="pixels")' in library_source
    assert "rounded_canvas_rectangle_points" in forge_source
    assert 'Image.new("RGBA", (width * scale, height * scale)' not in forge_source


def test_pixel_scroll_library_columns_are_drag_resizable_without_losing_pixel_scroll():
    pixel_table_source = inspect.getsource(app_module.PixelScrollTable)
    column_layout_source = inspect.getsource(
        app_module.PixelScrollTable._layout_columns
    )
    report_yview_source = inspect.getsource(app_module.PixelScrollTable._report_yview)
    library_layout_source = inspect.getsource(DownloaderApp._apply_focus_library_layout)
    render_source = inspect.getsource(DownloaderApp._render_metadata_tree)

    assert (
        'self._header.bind("<ButtonPress-1>", self._begin_column_resize'
        in pixel_table_source
    )
    assert (
        'self._header.bind("<B1-Motion>", self._drag_column_resize'
        in pixel_table_source
    )
    assert (
        'self._header.bind("<ButtonRelease-1>", self._end_column_resize'
        in pixel_table_source
    )
    assert "rendered_width = next(" in pixel_table_source
    assert "layout[:-1]" in pixel_table_source
    assert "self._resize_margin = 8" in pixel_table_source
    assert "self._header.grab_set()" in pixel_table_source
    assert "self._header.grab_release()" in pixel_table_source
    assert 'else THEME["subtle"]' in pixel_table_source
    assert "self._manually_resized_columns.add(column)" in pixel_table_source
    assert "self._last_manually_resized_column = column" in pixel_table_source
    assert "responsive_table_stretch_indices" in column_layout_source
    assert (
        "heading_anchor = self._heading_anchors.get(column) or anchor"
        in pixel_table_source
    )
    assert 'anchor="w" if column == "duration" else None' in inspect.getsource(
        DownloaderApp._build_focus_library_view
    )
    assert "def layout_column" in pixel_table_source
    assert "stretched_table_column_widths" in column_layout_source
    assert "stretch_limits" in column_layout_source
    assert "def replace_rows" in pixel_table_source
    assert 'self._body.delete("all")' in pixel_table_source
    assert "pixel_table_visible_row_window(" in pixel_table_source
    assert "for row_index in range(first_row, last_row):" in pixel_table_source
    assert (
        'self._body.bind("<Configure>", lambda _event: self._schedule_redraw()'
        in pixel_table_source
    )
    assert "_schedule_redraw" not in report_yview_source
    assert (
        "Every supported scroll entry point already schedules a redraw"
        in report_yview_source
    )
    assert (
        "children = self.video_tree.replace_rows(rows, selected=target)"
        in render_source
    )
    assert "video_tree.layout_column(" in library_layout_source
    assert "xscrollincrement=1" in pixel_table_source


def test_pixel_scroll_table_keeps_tk_focus_and_body_event_contracts_separate():
    class BodyProbe:
        def __init__(self):
            self.calls = []

        def bind(self, sequence, callback, add):
            self.calls.append((sequence, callback, add))
            return "body-binding"

    def callback(_event: object) -> None:
        return None

    body = BodyProbe()
    bind_probe = SimpleNamespace(_body=body)

    assert app_module.PixelScrollTable.bind is app_module.tk.Misc.bind
    assert app_module.PixelScrollTable.focus is app_module.tk.Misc.focus
    assert (
        app_module.PixelScrollTable.bind_body_event(
            bind_probe,
            "<Button-1>",
            callback,
            "+",
        )
        == "body-binding"
    )
    assert body.calls == [("<Button-1>", callback, "+")]

    pixel_table = app_module.PixelScrollTable.__new__(app_module.PixelScrollTable)
    pixel_table._items = {"row": ()}
    pixel_table._focus_item = None
    app_module._focus_library_table_item(pixel_table, "row")
    assert pixel_table.focus_item() == "row"
    assert pixel_table.focus_item("missing") == "row"


def test_library_render_clears_an_inconsistent_widget_without_a_selection_target():
    class InconsistentTree:
        def selection(self):
            return ()

        def replace_rows(self, rows, *, selected):
            assert rows == []
            assert selected is None
            return ("orphaned-widget-row",)

        def focus(self, _target):
            raise AssertionError(
                "an orphaned widget row must not become Library authority"
            )

    app = DownloaderApp.__new__(DownloaderApp)
    app.video_tree = InconsistentTree()
    app.metadata_items = []
    app.library_output_type_var = Value("MP4")
    cleared: list[bool] = []
    app._clear_library_selection = lambda: cleared.append(True)
    app.focus_run_deck = object()
    app._refresh_focus_run_deck = lambda: None

    app._render_metadata_tree()

    assert cleared == [True]


def test_manual_column_width_keeps_responsive_stretch_authority():
    class ColumnProbe:
        def __init__(self):
            self._manually_resized_columns = {"title"}
            self.calls = []

        def column(self, column, **kwargs):
            self.calls.append((column, kwargs))
            return kwargs

    probe = ColumnProbe()

    app_module.PixelScrollTable.layout_column(
        probe,
        "title",
        width=360,
        minwidth=220,
        stretch=True,
        stretchmax=None,
    )

    assert probe.calls == [
        (
            "title",
            {"minwidth": 220, "stretch": True, "stretchmax": None},
        )
    ]


def test_column_release_does_not_rebase_untouched_columns():
    class HeaderProbe:
        def grab_current(self):
            return None

    class ResizeProbe:
        def __init__(self):
            self._columns = ("index", "title", "duration")
            self._column_options = {
                "index": {"width": 44, "stretch": True},
                "title": {"width": 360, "stretch": True},
                "duration": {"width": 72, "stretch": True},
            }
            self._resize_column = "title"
            self._header = HeaderProbe()
            self._resize_hover_column = None
            self.cursor = None
            self.redraws = 0

        def _drag_column_resize(self, _event):
            self._column_options["title"]["width"] = 420
            return "break"

        def _column_divider_at(self, _x):
            return None

        def _set_header_cursor(self, cursor):
            self.cursor = cursor

        def _redraw(self):
            self.redraws += 1

    probe = ResizeProbe()

    result = app_module.PixelScrollTable._end_column_resize(
        probe,
        SimpleNamespace(x=420),
    )

    assert result == "break"
    assert probe._resize_column is None
    assert probe._column_options == {
        "index": {"width": 44, "stretch": True},
        "title": {"width": 420, "stretch": True},
        "duration": {"width": 72, "stretch": True},
    }
    assert probe.redraws == 1


def test_preview_items_expose_fresh_forge_start_actions_without_library_ownership(
    tmp_path: Path,
):
    app = DownloaderApp.__new__(DownloaderApp)
    preview = {
        "id": "preview-id",
        "title": "Preview title",
        "webpage_url": "https://www.youtube.com/watch?v=preview-id",
        "playlist_id": "PLpreview",
        "vodforge_output_type": "MP3",
        "vodforge_preview_complete": True,
        "vodforge_preview_run_id": "preview:request",
    }
    built_job = make_job(tmp_path, video_id="fresh-preview")
    built_job.output_type = OutputType.MP3
    build_calls: list[tuple[list[str], dict[str, object]]] = []
    selected_views: list[str] = []
    submitted: list[tuple[DownloadJob, bool]] = []
    app.pending_jobs = []
    app._build_download_job_from_current_settings = lambda urls, **kwargs: (
        build_calls.append((list(urls), dict(kwargs))) or built_job
    )
    app._select_focus_view = selected_views.append
    app._start_or_queue_download_job = lambda job, *, clear_source: submitted.append(
        (job, clear_source)
    )

    app._start_preview_download(preview)

    assert build_calls == [
        (
            ["https://www.youtube.com/watch?v=preview-id&list=PLpreview"],
            {
                "output_type": OutputType.MP3,
                "single_video_only": True,
                "batch_mode": False,
            },
        )
    ]
    assert built_job.preview_info == {
        key: value
        for key, value in preview.items()
        if key
        not in {
            "vodforge_preview_complete",
            "vodforge_preview_run_id",
            app_module.ACTIVE_METADATA_RUN_ID_KEY,
        }
    }
    assert preview[app_module.ACTIVE_METADATA_RUN_ID_KEY] == built_job.run_id
    assert "vodforge_preview_complete" not in preview
    assert "vodforge_preview_run_id" not in preview
    assert ("preview-id", "MP3") in built_job.metadata_keys
    assert app._focus_selected_run_id == built_job.run_id
    assert selected_views == ["forge"]
    assert submitted == [(built_job, False)]

    deck_source = inspect.getsource(DownloaderApp._refresh_focus_run_deck)
    tile_source = inspect.getsource(DownloaderApp._render_focus_run_deck_tile)
    library_menu_source = inspect.getsource(DownloaderApp._show_library_row_menu)
    compact_menu_source = inspect.getsource(DownloaderApp._show_library_actions_menu)
    assert "self._render_focus_run_deck_tile(" in deck_source
    assert 'record_kind == "preview"' in tile_source
    assert "self._start_preview_record(item)" in tile_source
    assert "hover_widgets.append(play_button)" in tile_source
    assert all(
        line.strip() != "widgets.append(play_button)"
        for line in tile_source.splitlines()
    )
    assert 'label="Start download in Forge"' in library_menu_source
    assert 'label="Start download in Forge"' in compact_menu_source


def test_submitting_a_previewed_url_adopts_it_into_one_fresh_active_run(tmp_path: Path):
    preview = {
        "id": "preview-id",
        "title": "Preview title",
        "webpage_url": "https://www.youtube.com/watch?v=preview-id",
        "vodforge_output_type": "MP4",
        "vodforge_preview_complete": True,
        "vodforge_preview_run_id": "preview:old-presentation-id",
    }
    job = make_job(tmp_path, video_id="preview-id")
    app = DownloaderApp.__new__(DownloaderApp)
    app.metadata_items = [preview]

    adopted = app._adopt_matching_preview_for_download_job(job)

    assert adopted is True
    assert job.run_id != "preview:old-presentation-id"
    assert job.metadata_keys == {("preview-id", "MP4")}
    assert job.preview_info == {
        key: value
        for key, value in preview.items()
        if key != app_module.ACTIVE_METADATA_RUN_ID_KEY
    }
    assert preview[app_module.ACTIVE_METADATA_RUN_ID_KEY] == job.run_id
    assert "vodforge_preview_complete" not in preview
    assert "vodforge_preview_run_id" not in preview
    assert app.metadata_items == [preview]

    app._focus_preview_runs = None
    app._focus_active_override = False
    app.active_job = job
    app.worker = None
    app.pending_jobs = []
    app._terminal_jobs = []
    app._completed_jobs = []
    app.url_var = Value(job.url)
    app.focus_active_title_var = Value("")
    app.focus_active_detail_var = Value("")
    app.status_var = Value("Starting")
    app.progress_var = Value(0)

    records = app._focus_run_records()

    assert [(record["kind"], record["run_id"]) for record in records] == [
        ("active", job.run_id)
    ]
    start_source = inspect.getsource(DownloaderApp._start_download)
    assert start_source.index(
        "self._adopt_matching_preview_for_download_job(job)"
    ) < start_source.index("self._start_or_queue_download_job(job, clear_source=True)")


def test_preview_hero_replaces_large_status_with_start_download_action(tmp_path: Path):
    class GridControl:
        def __init__(self):
            self.visible = True
            self.configured: dict[str, object] = {}

        def grid(self):
            self.visible = True

        def grid_remove(self):
            self.visible = False

        def configure(self, **kwargs):
            self.configured.update(kwargs)

    app = DownloaderApp.__new__(DownloaderApp)
    app.focus_percent_label = GridControl()
    app.focus_preview_start_button = GridControl()
    preview = {
        "id": "preview-id",
        "webpage_url": "https://www.youtube.com/watch?v=preview-id",
        "vodforge_output_type": "MP4",
        "vodforge_preview_complete": True,
    }
    started: list[dict[str, object]] = []
    app._start_preview_download = started.append

    app._set_focus_preview_start_action(preview)

    assert app.focus_percent_label.visible is False
    assert app.focus_preview_start_button.visible is True
    assert app.focus_preview_start_button.configured["text"] == "Start download"
    assert app._focus_selected_preview_info == preview
    app._start_selected_preview_download()
    assert started == [preview]

    app._set_focus_preview_start_action(None)
    assert app.focus_percent_label.visible is True
    assert app.focus_preview_start_button.visible is False
    assert app._focus_selected_preview_info is None

    build_source = inspect.getsource(DownloaderApp._build_focus_forge_view)
    assert 'text="Start download"' in build_source
    assert "self.focus_preview_start_button.grid_remove()" in build_source


def test_terminal_focus_uses_retry_restart_actions_and_outcome_colors(tmp_path: Path):
    class GridControl:
        def __init__(self):
            self.visible = True
            self.configured: dict[str, object] = {}

        def grid(self):
            self.visible = True

        def grid_remove(self):
            self.visible = False

        def configure(self, **kwargs):
            self.configured.update(kwargs)

    class ProgressControl:
        def __init__(self):
            self.configured: dict[str, object] = {}

        def configure(self, **kwargs):
            self.configured.update(kwargs)

    app = DownloaderApp.__new__(DownloaderApp)
    app.focus_percent_label = GridControl()
    app.focus_preview_start_button = GridControl()
    app.progress_bar = ProgressControl()
    app.focus_active_title_var = Value("")
    app.focus_active_detail_var = Value("")
    app.focus_active_duration_var = Value("")
    app.focus_active_profile_var = Value("")
    app.focus_display_progress_var = Value(0)
    app.focus_percent_var = Value("")
    app.focus_display_status_var = Value("")
    app.focus_transfer_var = Value("")
    app.focus_summary_text = object()
    app._set_text = lambda *_args, **_kwargs: None
    app._render_focus_run_activity = lambda *_args, **_kwargs: None
    app._display_focus_record_thumbnail = lambda *_args, **_kwargs: None
    retried: list[DownloadJob] = []
    app._retry_terminal_job = retried.append
    terminal = make_job(tmp_path, video_id="terminal")
    terminal.preview_info = {
        "id": "terminal",
        "title": "Terminal item",
        "vodforge_output_type": "MP4",
    }

    terminal.terminal_status = "Failed"
    app._display_focus_metadata_snapshot(
        {"kind": "failed", "run_id": terminal.run_id, "job": terminal},
        {**terminal.preview_info, "vodforge_terminal_status": "Failed"},
    )

    assert app.focus_display_progress_var.get() == 100
    assert app.focus_percent_label.visible is False
    assert app.focus_preview_start_button.configured["text"] == "Retry Download"
    assert app.progress_bar.configured["bar_color"] == app_module.THEME["danger"]
    app.focus_preview_start_button.configured["command"]()
    assert retried == [terminal]

    terminal.terminal_status = "Skipped"
    app._display_focus_metadata_snapshot(
        {"kind": "skipped", "run_id": terminal.run_id, "job": terminal},
        {**terminal.preview_info, "vodforge_terminal_status": "Skipped"},
    )

    assert app.focus_preview_start_button.configured["text"] == "Restart Download"
    assert app.progress_bar.configured["bar_color"] == app_module.THEME["warning"]

    progress_source = inspect.getsource(app_module.SleekProgressbar.configure)
    assert 'if "bar_color" in kwargs:' in progress_source


def test_terminal_outcomes_become_the_explicit_forge_focus(monkeypatch, tmp_path: Path):
    terminal = make_job(tmp_path, video_id="terminal")
    terminal.terminal_status = "Failed"
    record = {"kind": "failed", "run_id": terminal.run_id, "job": terminal}
    app = DownloaderApp.__new__(DownloaderApp)
    app.focus_run_deck = object()
    app._focus_views = {"forge": object()}
    app._focus_run_records = lambda: [record]
    selected_views: list[str] = []
    selected_records: list[dict[str, object]] = []
    app._select_focus_view = selected_views.append
    app._focus_select_run_record = selected_records.append

    app._focus_terminal_job(terminal)

    assert app._focus_selected_run_id == terminal.run_id
    assert selected_views == ["forge"]
    assert selected_records == [record]

    dispatched_focus: list[DownloadJob] = []
    dispatch_app = DownloaderApp.__new__(DownloaderApp)
    dispatch_app._closing = False
    dispatch_app.active_job = terminal
    dispatch_app._library_run_is_suppressed = lambda _job: False
    dispatch_app._append_job_log = lambda *_args: None
    dispatch_app._archive_active_terminal_job = lambda *_args: None
    dispatch_app.progress_var = Value(100)
    dispatch_app.status_var = Value("")
    dispatch_app.download_button = Control()
    dispatch_app.cancel_button = Control()
    dispatch_app.skip_video_button = Control()
    dispatch_app.skip_url_button = Control()
    dispatch_app.focus_transfer_var = Value("")
    dispatch_app.focus_run_status_var = Value("")
    dispatch_app.focus_percent_var = Value("")
    dispatch_app._focus_follows_active_run = lambda: True
    dispatch_app._refresh_focus_run_deck = lambda: None
    dispatch_app._set_focus_run_controls_visible = lambda _visible: None
    dispatch_app._launch_next_pending_job = lambda: False
    dispatch_app._focus_terminal_job = dispatched_focus.append
    monkeypatch.setattr(app_module.messagebox, "showerror", lambda *_args: None)

    assert dispatch_app._handle_terminal_event("error", "download failed") is True
    assert dispatched_focus == [terminal]

    archived_focus: list[DownloadJob] = []
    archive_app = DownloaderApp.__new__(DownloaderApp)
    archive_app._library_run_is_suppressed = lambda _job: False
    archive_app._terminal_jobs = []
    archive_app.metadata_items = []
    archive_app._rebuild_output_dir_index = lambda: None
    archive_app._render_metadata_tree = lambda: None
    archive_app.focus_run_deck = object()
    archive_app._focus_terminal_job = archived_focus.append
    archive_app._refresh_focus_run_deck = lambda: None

    archive_app._archive_item_terminal_job(terminal, terminal.preview_info or {})

    assert archived_focus == [terminal]


def test_metadata_preview_focuses_once_and_completion_respects_manual_selection():
    settings_source = inspect.getsource(FocusSettingsDialog._preview_and_close)
    fetch_source = inspect.getsource(DownloaderApp._fetch_metadata)
    completion_source = inspect.getsource(DownloaderApp._display_metadata)

    assert "if self.actions.preview_metadata():" in settings_source
    assert settings_source.index(
        "if self.actions.preview_metadata():"
    ) < settings_source.index("self.close()")
    assert '"kind": "preview_loading"' in fetch_source
    assert "self._focus_selected_run_id = preview_run_id" in fetch_source
    assert "self._display_metadata_preview_request(preview_record)" in fetch_source
    assert "self._focus_selected_run_id = preview_run_id" not in completion_source
    assert (
        'self.__dict__.get("_focus_selected_run_id") == preview_run_id'
        in completion_source
    )


def test_custom_popouts_are_positioned_before_they_become_visible():
    settings_init_source = inspect.getsource(FocusSettingsDialog.__init__)
    settings_show_source = inspect.getsource(FocusSettingsDialog.show)
    output_source = inspect.getsource(DownloaderApp._show_focus_output_details)
    selected_source = inspect.getsource(DownloaderApp._show_selected_metadata_details)

    assert "popup.withdraw()" in settings_init_source
    assert "reveal_toplevel(" in settings_show_source
    assert (
        "self.owner.after_idle(self.actions.record_cloud_cta_seen)"
        in settings_show_source
    )
    for source in (output_source, selected_source):
        assert "popup.withdraw()" in source
        assert "reveal_toplevel(popup," in source
        assert source.index("popup.withdraw()") < source.index("reveal_toplevel(popup,")

    assert (
        "centered_toplevel_geometry(self.owner, width, height)" in settings_show_source
    )
    assert "centered_toplevel_geometry(self, 560, 360)" in output_source
    assert "centered_toplevel_geometry(self, 680, 620)" in selected_source


def test_remove_from_library_never_deletes_the_media_file(monkeypatch, tmp_path: Path):
    output_dir = (
        tmp_path / "Creator" / "playlists" / "Playlist" / "Video [authority-id]"
    )
    output_dir.mkdir(parents=True)
    media = output_dir / "Video.mp4"
    media.write_bytes(b"keep me")
    info = {"id": "authority-id", "title": "Video", "vodforge_output_type": "MP4"}
    saved = upsert_history([], info, output_dir)[0]
    app = DownloaderApp.__new__(DownloaderApp)
    app.video_tree = SelectedTree()
    app.metadata_items = [saved]
    app.download_history = [saved]
    app.history_path = tmp_path / "history.json"
    app._terminal_jobs = []
    app._completed_jobs = []
    app.status_var = Value("")
    app._render_metadata_tree = lambda: None
    monkeypatch.setattr(
        app_module.messagebox, "askyesno", lambda *_args, **_kwargs: True
    )

    app._remove_selected_library_item()

    assert media.read_bytes() == b"keep me"
    assert app.metadata_items == []
    assert app.download_history == []
    assert "not deleted" in app.status_var.get()


def test_remove_active_library_item_stops_and_tombstones_only_its_execution(
    monkeypatch, tmp_path: Path
):
    info = {
        "id": "active-item",
        "title": "Active item",
        "vodforge_output_type": "MP4",
    }
    item_key = app_module.metadata_run_key(info)
    assert item_key is not None
    active = make_job(tmp_path, video_id="active-item")
    active.preview_info = dict(info)
    active.metadata_keys.add(item_key)
    queued_same_item = make_job(tmp_path, video_id="active-item")
    queued_same_item.preview_info = dict(info)
    queued_same_item.metadata_keys.add(item_key)
    unrelated_queued = make_job(tmp_path, video_id="other-item")
    unrelated_queued.preview_info = {
        "id": "other-item",
        "title": "Other item",
        "vodforge_output_type": "MP4",
    }
    unrelated_key = app_module.metadata_run_key(unrelated_queued.preview_info)
    assert unrelated_key is not None
    unrelated_queued.metadata_keys.add(unrelated_key)

    app = DownloaderApp.__new__(DownloaderApp)
    app.video_tree = SelectedTree()
    claimed_info = dict(info)
    claimed_info[app_module.ACTIVE_METADATA_RUN_ID_KEY] = active.run_id
    app.metadata_items = [claimed_info]
    app.download_history = []
    app.history_path = tmp_path / "history.json"
    app.active_job = active
    app.pending_jobs = [queued_same_item, unrelated_queued]
    app._terminal_jobs = []
    app._completed_jobs = []
    app._library_suppressed_run_ids = set()
    app.status_var = Value("")
    cancellations: list[str] = []
    reconciled: list[set[str]] = []
    app._cancel = lambda: cancellations.append(active.run_id)
    app._render_metadata_tree = lambda: None
    app._reconcile_focus_after_library_removal = lambda run_ids: reconciled.append(
        set(run_ids)
    )
    monkeypatch.setattr(
        app_module.messagebox, "askyesno", lambda *_args, **_kwargs: True
    )

    app._remove_selected_library_item()

    assert cancellations == [active.run_id]
    assert app.metadata_items == []
    assert app.pending_jobs == [queued_same_item, unrelated_queued]
    assert app._library_suppressed_run_ids == {active.run_id}
    assert active.run_id in reconciled[0]
    assert queued_same_item.run_id not in reconciled[0]
    assert app._active_run_for_metadata_event(replace(active)) is None

    # Worker completion, failure, and playlist-item events arriving after the
    # removal cannot resurrect the run on either Library or Forge.
    app._archive_active_terminal_job("Stopped", "late stop")
    app._archive_active_completed_job("Completed", "late completion")
    child = replace(
        active,
        run_id="child-item-run",
        origin_run_id=active.run_id,
        preview_info=dict(info),
    )
    app._archive_item_terminal_job(child, dict(info))
    assert app._terminal_jobs == []
    assert app._completed_jobs == []
    assert app.metadata_items == []


def test_remove_claimed_preview_queue_preserves_other_same_video_attempts(
    monkeypatch, tmp_path: Path
):
    preview = {
        "id": "same-video",
        "title": "Claimed preview",
        "vodforge_output_type": "MP4",
        "vodforge_preview_complete": True,
        "vodforge_preview_run_id": "preview:old",
    }
    claimed_queue = make_job(tmp_path, video_id="same-video")
    claimed_queue.preview_info = {
        "id": "same-video",
        "title": "Claimed preview",
        "vodforge_output_type": "MP4",
    }
    claimed_queue.metadata_keys.add(("same-video", "MP4"))
    app_module.claim_active_metadata_row(
        preview, claimed_queue.preview_info, claimed_queue.run_id
    )

    other_same_video = make_job(tmp_path, video_id="same-video")
    other_same_video.preview_info = {
        "id": "same-video",
        "title": "Separate attempt",
        "vodforge_output_type": "MP4",
    }
    other_same_video.metadata_keys.add(("same-video", "MP4"))
    unrelated = make_job(tmp_path, video_id="other-video")

    app = DownloaderApp.__new__(DownloaderApp)
    app.video_tree = SelectedTree()
    app.metadata_items = [preview]
    app.download_history = []
    app.history_path = tmp_path / "history.json"
    app.active_job = None
    app.pending_jobs = [claimed_queue, other_same_video, unrelated]
    app._terminal_jobs = []
    app._completed_jobs = []
    app._library_suppressed_run_ids = set()
    app.status_var = Value("")
    reconciled: list[set[str]] = []
    app._render_metadata_tree = lambda: None
    app._reconcile_focus_after_library_removal = lambda run_ids: reconciled.append(
        set(run_ids)
    )
    monkeypatch.setattr(
        app_module.messagebox, "askyesno", lambda *_args, **_kwargs: True
    )

    app._remove_selected_library_item()

    assert app.metadata_items == []
    assert app.pending_jobs == [other_same_video, unrelated]
    assert app._library_suppressed_run_ids == {claimed_queue.run_id}
    assert reconciled == [{claimed_queue.run_id, "history:0"}]


def test_remove_active_library_item_after_history_commit_still_stops_its_exact_run(
    monkeypatch, tmp_path: Path
):
    active = make_job(tmp_path, video_id="active-item")
    older_terminal = make_job(tmp_path, video_id="active-item")
    older_terminal.terminal_status = "Failed"
    older_terminal.preview_info = {
        "id": "active-item",
        "title": "Older failed attempt",
        "vodforge_output_type": "MP4",
    }
    older_terminal.metadata_keys.add(("active-item", "MP4"))
    output_dir = (
        tmp_path / "Creator" / "videos - no playlist" / "Active item [active-item]"
    )
    output_dir.mkdir(parents=True)
    (output_dir / "Active item.mp4").write_bytes(b"committed output")
    saved = upsert_history(
        [],
        {
            "id": "active-item",
            "title": "Active item",
            "vodforge_output_type": "MP4",
            "vodforge_run_id": active.run_id,
        },
        output_dir,
    )[0]

    app = DownloaderApp.__new__(DownloaderApp)
    app.video_tree = SelectedTree()
    app.metadata_items = [saved]
    app.download_history = [saved]
    app.history_path = tmp_path / "history.json"
    app.active_job = active
    app.pending_jobs = []
    app._terminal_jobs = [older_terminal]
    app._completed_jobs = []
    app._library_suppressed_run_ids = set()
    app.status_var = Value("")
    cancellations: list[str] = []
    reconciled: list[set[str]] = []
    app._cancel = lambda: cancellations.append(active.run_id)
    app._render_metadata_tree = lambda: None
    app._rebuild_output_dir_index = lambda: None
    app._reconcile_focus_after_library_removal = lambda run_ids: reconciled.append(
        set(run_ids)
    )
    monkeypatch.setattr(
        app_module.messagebox, "askyesno", lambda *_args, **_kwargs: True
    )

    app._remove_selected_library_item()

    assert cancellations == [active.run_id]
    assert app._library_suppressed_run_ids == {active.run_id}
    assert app.metadata_items == []
    assert app.download_history == []
    assert app._terminal_jobs == []
    assert len(reconciled) == 1
    assert active.run_id in reconciled[0]
    assert older_terminal.run_id in reconciled[0]


def test_library_history_save_failure_has_no_partial_removal_side_effects(
    monkeypatch, tmp_path: Path
):
    active = make_job(tmp_path, video_id="persist-first")
    output_dir = tmp_path / "Creator" / "videos - no playlist" / "Saved [persist-first]"
    output_dir.mkdir(parents=True)
    media = output_dir / "Saved.mp4"
    media.write_bytes(b"committed media remains authoritative")
    saved = upsert_history(
        [],
        {
            "id": "persist-first",
            "title": "Saved",
            "vodforge_output_type": "MP4",
            "vodforge_run_id": active.run_id,
        },
        output_dir,
    )[0]
    queued = make_job(tmp_path, video_id="queued-unrelated")
    terminal = make_job(tmp_path, video_id="terminal-unrelated")
    completed = make_job(tmp_path, video_id="persist-first")
    completed.history_identities.add(history_identity(saved))

    app = DownloaderApp.__new__(DownloaderApp)
    app.video_tree = SelectedTree()
    app.metadata_items = [saved]
    app.download_history = [saved]
    app.history_path = tmp_path / "history.json"
    app.active_job = active
    app.pending_jobs = [queued]
    app._terminal_jobs = [terminal]
    app._completed_jobs = [completed]
    app._library_suppressed_run_ids = set()
    app.status_var = Value("Before removal")
    cancellations: list[str] = []
    renders: list[bool] = []
    rebuilds: list[bool] = []
    reconciled: list[set[str]] = []
    persisted: list[list[dict]] = []
    errors: list[tuple[str, str]] = []
    app._cancel = lambda: cancellations.append(active.run_id)
    app._render_metadata_tree = lambda: renders.append(True)
    app._rebuild_output_dir_index = lambda: rebuilds.append(True)
    app._reconcile_focus_after_library_removal = lambda run_ids: reconciled.append(
        set(run_ids)
    )
    monkeypatch.setattr(
        app_module.messagebox, "askyesno", lambda *_args, **_kwargs: True
    )
    monkeypatch.setattr(
        app_module.messagebox,
        "showerror",
        lambda title, message: errors.append((title, message)),
    )

    def fail_save(_path: Path, records: list[dict]) -> None:
        persisted.append(list(records))
        raise HistoryError("injected history save failure")

    monkeypatch.setattr(app_module, "save_history", fail_save)

    app._remove_selected_library_item()

    assert persisted == [[]]
    assert cancellations == []
    assert app._library_suppressed_run_ids == set()
    assert app.pending_jobs == [queued]
    assert app.metadata_items == [saved]
    assert app.download_history == [saved]
    assert app._terminal_jobs == [terminal]
    assert app._completed_jobs == [completed]
    assert completed.history_identities == {history_identity(saved)}
    assert renders == []
    assert rebuilds == []
    assert reconciled == []
    assert app.status_var.get() == "Before removal"
    assert media.read_bytes() == b"committed media remains authoritative"
    assert errors == [(app_module.APP_NAME, "injected history save failure")]


def test_manual_mp3_in_mp4_rejects_unsupported_bitrate_before_launch():
    app = DownloaderApp.__new__(DownloaderApp)
    app.manual_video_bitrate_var = Value("10000")
    app.manual_audio_bitrate_var = Value("1024")
    app.manual_sample_rate_var = Value("48000")
    app.manual_channels_var = Value("Stereo")
    app.manual_audio_codec_var = Value(ManualAudioCodec.MP3.value)
    app.manual_preset_var = Value("medium")

    try:
        app._manual_export_settings()
    except ValueError as exc:
        assert "encoder-supported values" in str(exc)
        assert "320" in str(exc)
    else:
        raise AssertionError("unsupported MP3 bitrate was accepted")

    app.manual_audio_bitrate_var.set("256")
    settings = app._manual_export_settings()
    assert settings.audio_codec is ManualAudioCodec.MP3
    assert settings.audio_bitrate_kbps == 256


def test_hidden_manual_values_cannot_block_auto_or_strict_mp4_runs(
    monkeypatch, tmp_path: Path
):
    app = DownloaderApp.__new__(DownloaderApp)
    app.output_var = Value(str(tmp_path))
    app.tags_var = Value("")
    app.quality_var = Value("1080p Full HD")
    app.use_nvenc_var = Value(False)
    app.embed_thumbnail_var = Value(False)
    app.write_thumbnail_var = Value(False)
    app.embed_metadata_var = Value(False)
    app.write_info_json_var = Value(False)
    app._selected_cookie_source = lambda: app_module.CookieSource.PUBLIC
    app._cookie_inputs = lambda: (False, None, None)
    app._manual_export_settings = lambda: (_ for _ in ()).throw(
        AssertionError("hidden Manual settings were parsed")
    )
    app._mp3_export_settings = lambda: Mp3ExportSettings()
    monkeypatch.setattr(
        app_module, "validate_output_directory_access", lambda _path: None
    )

    for mode in (ExportMode.AUTO_CBR, ExportMode.STRICT_COMPLIANCE):
        app.export_mode_var = Value(mode.value)
        job = app._build_download_job_from_current_settings(
            ["https://www.youtube.com/watch?v=authority-id"],
            output_type=OutputType.MP4,
            single_video_only=True,
            batch_mode=False,
        )

        assert job is not None
        assert job.export_mode is mode
        assert job.manual_settings == ManualExportSettings()


def test_submission_phases_preserve_the_complete_mp4_job_contract(
    monkeypatch, tmp_path: Path
):
    app = DownloaderApp.__new__(DownloaderApp)
    cookie_file = tmp_path / "cookies.txt"
    manual_settings = ManualExportSettings(
        video_bitrate_kbps=14000,
        audio_bitrate_kbps=256,
        audio_sample_rate="44100",
        audio_channels="1",
        audio_codec=ManualAudioCodec.AAC,
        x264_preset="slow",
    )
    app.output_var = Value(str(tmp_path))
    app.tags_var = Value(" alpha, , beta ")
    app.quality_var = Value("1440p 2K")
    app.export_mode_var = Value(ExportMode.MANUAL_OVERRIDE.value)
    app.use_nvenc_var = Value(True)
    app.embed_thumbnail_var = Value(True)
    app.write_thumbnail_var = Value(True)
    app.embed_metadata_var = Value(True)
    app.write_info_json_var = Value(True)
    app._selected_cookie_source = lambda: app_module.CookieSource.FILE
    app._cookie_inputs = lambda: (True, cookie_file, None)
    app._manual_export_settings = lambda: manual_settings
    app._mp3_export_settings = lambda: (_ for _ in ()).throw(
        AssertionError("MP3 settings were read for an MP4 submission")
    )
    validated_paths: list[Path] = []
    monkeypatch.setattr(
        app_module,
        "validate_output_directory_access",
        validated_paths.append,
    )

    job = app._build_download_job_from_current_settings(
        [
            " https://www.youtube.com/watch?v=first-id ",
            "",
            "https://www.youtube.com/watch?v=second-id",
        ],
        output_type=OutputType.MP4,
        single_video_only=False,
        batch_mode=True,
    )

    assert validated_paths == [tmp_path]
    assert job is not None
    assert job.url == "https://www.youtube.com/watch?v=first-id"
    assert job.urls == [
        "https://www.youtube.com/watch?v=first-id",
        "https://www.youtube.com/watch?v=second-id",
    ]
    assert job.output_dir == tmp_path
    assert job.output_type is OutputType.MP4
    assert job.quality_label == "1440p 2K"
    assert job.export_mode is ExportMode.MANUAL_OVERRIDE
    assert job.manual_settings is manual_settings
    assert job.mp3_settings == Mp3ExportSettings()
    assert job.single_video_only is False
    assert job.use_nvenc is True
    assert job.embed_thumbnail is True
    assert job.write_thumbnail is True
    assert job.embed_metadata is True
    assert job.write_info_json is True
    assert job.tags == ["alpha", "beta"]
    assert job.use_cookies is True
    assert job.cookie_file == cookie_file
    assert job.cookie_browser is None
    assert job.batch_mode is True


def test_mp3_submission_does_not_capture_mp4_only_controls(monkeypatch, tmp_path: Path):
    class DiagnosticOnlyValue(Value):
        reads = 0

        def get(self):
            self.reads += 1
            if self.reads > 1:
                raise AssertionError("NVENC was read again while building an MP3 job")
            return super().get()

    class UnreadValue(Value):
        def get(self):
            raise AssertionError("an MP4-only control was read for an MP3 job")

    app = DownloaderApp.__new__(DownloaderApp)
    nvenc = DiagnosticOnlyValue(True)
    mp3_settings = Mp3ExportSettings(
        bitrate_kbps=192,
        sample_rate="44100",
        channels="1",
        embed_metadata=False,
    )
    app.output_var = Value(str(tmp_path))
    app.tags_var = Value("spoken, audio")
    app.quality_var = Value("1080p Full HD")
    app.export_mode_var = Value(ExportMode.AUTO_CBR.value)
    app.use_nvenc_var = nvenc
    app.embed_thumbnail_var = UnreadValue(True)
    app.write_thumbnail_var = UnreadValue(True)
    app.embed_metadata_var = UnreadValue(True)
    app.write_info_json_var = UnreadValue(True)
    app._selected_cookie_source = lambda: app_module.CookieSource.PUBLIC
    app._cookie_inputs = lambda: (False, None, None)
    app._manual_export_settings = lambda: (_ for _ in ()).throw(
        AssertionError("manual MP4 settings were read for an MP3 submission")
    )
    app._mp3_export_settings = lambda: mp3_settings
    monkeypatch.setattr(
        app_module, "validate_output_directory_access", lambda _path: None
    )

    job = app._build_download_job_from_current_settings(
        ["https://www.youtube.com/watch?v=audio-id"],
        output_type=OutputType.MP3,
        single_video_only=True,
        batch_mode=False,
    )

    assert job is not None
    assert nvenc.reads == 1
    assert job.output_type is OutputType.MP3
    assert job.manual_settings == ManualExportSettings()
    assert job.mp3_settings is mp3_settings
    assert job.use_nvenc is False
    assert job.embed_thumbnail is False
    assert job.write_thumbnail is False
    assert job.embed_metadata is False
    assert job.write_info_json is False
    assert job.tags == ["spoken", "audio"]


def test_submission_validation_failure_preserves_read_and_dialog_order(
    monkeypatch, tmp_path: Path
):
    events: list[str] = []

    class TrackedValue(Value):
        def __init__(self, label: str, value):
            super().__init__(value)
            self.label = label

        def get(self):
            events.append(self.label)
            return super().get()

    app = DownloaderApp.__new__(DownloaderApp)
    app.output_var = TrackedValue("output", str(tmp_path))
    app.tags_var = TrackedValue("tags", "alpha")
    app.quality_var = TrackedValue("quality", "1080p Full HD")
    app.export_mode_var = TrackedValue("export_mode", ExportMode.MANUAL_OVERRIDE.value)
    app.use_nvenc_var = TrackedValue("diagnostic_nvenc", True)
    app.embed_thumbnail_var = TrackedValue("embed_thumbnail", True)
    app.write_thumbnail_var = TrackedValue("write_thumbnail", True)
    app.embed_metadata_var = TrackedValue("embed_metadata", True)
    app.write_info_json_var = TrackedValue("write_info_json", True)
    app._selected_cookie_source = lambda: (
        events.append("cookie_source") or app_module.CookieSource.PUBLIC
    )
    app._cookie_inputs = lambda: events.append("cookie_inputs") or (False, None, None)

    def invalid_manual_settings() -> ManualExportSettings:
        events.append("manual_settings")
        raise ValueError("Injected invalid manual settings.")

    app._manual_export_settings = invalid_manual_settings
    app._mp3_export_settings = lambda: (_ for _ in ()).throw(
        AssertionError("MP3 settings were read after the manual failure")
    )
    monkeypatch.setattr(
        app_module,
        "validate_output_directory_access",
        lambda _path: events.append("validate_output"),
    )
    errors: list[tuple[str, str]] = []
    monkeypatch.setattr(
        app_module.messagebox,
        "showerror",
        lambda title, message: (
            events.append("dialog") or errors.append((title, message))
        ),
    )

    job = app._build_download_job_from_current_settings(
        ["https://www.youtube.com/watch?v=authority-id"],
        output_type=OutputType.MP4,
        single_video_only=True,
        batch_mode=False,
    )

    assert job is None
    assert events == [
        "cookie_source",
        "cookie_inputs",
        "diagnostic_nvenc",
        "output",
        "validate_output",
        "tags",
        "export_mode",
        "manual_settings",
        "dialog",
    ]
    assert errors == [(app_module.APP_NAME, "Injected invalid manual settings.")]


def test_submission_phase_failures_keep_dialogs_and_stop_boundaries(
    monkeypatch, tmp_path: Path
):
    app = DownloaderApp.__new__(DownloaderApp)
    errors: list[tuple[str, str]] = []
    monkeypatch.setattr(
        app_module.messagebox,
        "showerror",
        lambda title, message: errors.append((title, message)),
    )

    app.output_var = Value("")
    assert app._validated_submission_output_directory() is None
    assert errors.pop() == (app_module.APP_NAME, "Choose an output folder.")

    app.output_var = Value(str(tmp_path))
    monkeypatch.setattr(
        app_module,
        "validate_output_directory_access",
        lambda _path: (_ for _ in ()).throw(OSError("injected output failure")),
    )
    assert app._validated_submission_output_directory() is None
    assert errors.pop() == (
        app_module.APP_NAME,
        (
            "VODForge cannot write to the selected output folder. "
            "Choose another folder or allow access, then try again.\n\n"
            "injected output failure"
        ),
    )

    assert (
        app._submission_cookie_inputs_are_valid(
            app_module.CookieSource.FILE, None, None
        )
        is False
    )
    assert errors.pop() == (
        app_module.APP_NAME,
        "Choose a YouTube cookies.txt file, or switch YouTube access back to Public.",
    )
    assert (
        app._submission_cookie_inputs_are_valid(
            app_module.CookieSource.BROWSER, None, None
        )
        is False
    )
    assert errors.pop() == (
        app_module.APP_NAME,
        "Choose a browser profile, or switch YouTube access back to Public.",
    )
    assert errors == []


def test_missing_url_dialog_keeps_cookie_and_diagnostic_read_boundary(monkeypatch):
    events: list[str] = []

    class TrackedValue(Value):
        def get(self):
            events.append("diagnostic_nvenc")
            return super().get()

    app = DownloaderApp.__new__(DownloaderApp)
    app.use_nvenc_var = TrackedValue(False)
    app.output_var = Value("")
    app._selected_cookie_source = lambda: (
        events.append("cookie_source") or app_module.CookieSource.PUBLIC
    )
    app._cookie_inputs = lambda: events.append("cookie_inputs") or (False, None, None)
    errors: list[tuple[str, str]] = []
    monkeypatch.setattr(
        app_module.messagebox,
        "showerror",
        lambda title, message: (
            events.append("dialog") or errors.append((title, message))
        ),
    )

    job = app._build_download_job_from_current_settings(
        ["  "],
        output_type=OutputType.MP4,
        single_video_only=True,
        batch_mode=False,
    )

    assert job is None
    assert events == [
        "cookie_source",
        "cookie_inputs",
        "diagnostic_nvenc",
        "dialog",
    ]
    assert errors == [
        (
            app_module.APP_NAME,
            "Paste a YouTube URL first or load a URL list text file.",
        )
    ]


def test_single_video_playlist_failure_precedes_submission_state_reads(monkeypatch):
    app = DownloaderApp.__new__(DownloaderApp)
    app._selected_cookie_source = lambda: (_ for _ in ()).throw(
        AssertionError("cookie state was read before single-video URL validation")
    )
    errors: list[tuple[str, str]] = []
    monkeypatch.setattr(
        app_module.messagebox,
        "showerror",
        lambda title, message: errors.append((title, message)),
    )

    job = app._build_download_job_from_current_settings(
        ["https://www.youtube.com/playlist?list=PLonly"],
        output_type=OutputType.MP4,
        single_video_only=True,
        batch_mode=False,
    )

    assert job is None
    assert errors == [(app_module.APP_NAME, app_module.SINGLE_VIDEO_PLAYLIST_ERROR)]


def test_active_metadata_claims_a_same_item_terminal_row_before_library_removal(
    monkeypatch, tmp_path: Path
):
    terminal = make_job(tmp_path, video_id="same-item")
    terminal.terminal_status = "Failed"
    terminal.preview_info = {
        "id": "same-item",
        "title": "Old failed attempt",
        "vodforge_output_type": "MP4",
    }
    terminal.metadata_keys.add(("same-item", "MP4"))
    active = make_job(tmp_path, video_id="same-item")
    terminal_row = {
        **terminal.preview_info,
        "vodforge_terminal_status": "Failed",
        "vodforge_terminal_message": "old failure",
        "vodforge_terminal_run_id": terminal.run_id,
    }
    app = DownloaderApp.__new__(DownloaderApp)
    app.active_job = active
    app.metadata_items = [terminal_row]
    app.library_output_type_var = Value("MP4")
    app.status_var = Value("Active")
    app._render_metadata_tree = lambda **_kwargs: None
    app._display_active_job_metadata = lambda *_args, **_kwargs: None

    app._display_metadata(
        {
            "id": "same-item",
            "title": "Fresh active attempt",
            "vodforge_output_type": "MP4",
        },
        active_job=active,
    )

    claimed = app.metadata_items[0]
    assert claimed[app_module.ACTIVE_METADATA_RUN_ID_KEY] == active.run_id
    assert claimed["title"] == "Fresh active attempt"
    assert "vodforge_terminal_status" not in claimed
    assert "vodforge_terminal_run_id" not in claimed

    app.video_tree = SelectedTree()
    app.download_history = []
    app.history_path = tmp_path / "history.json"
    app.pending_jobs = []
    app._terminal_jobs = [terminal]
    app._completed_jobs = []
    app._library_suppressed_run_ids = set()
    cancellations: list[str] = []
    app._cancel = lambda: cancellations.append(active.run_id)
    app._reconcile_focus_after_library_removal = lambda _run_ids: None
    monkeypatch.setattr(
        app_module.messagebox, "askyesno", lambda *_args, **_kwargs: True
    )

    app._remove_selected_library_item()

    assert cancellations == [active.run_id]
    assert active.run_id in app._library_suppressed_run_ids
    assert app.metadata_items == []


def test_late_worker_events_cannot_resurrect_a_library_removed_run(tmp_path: Path):
    active = make_job(tmp_path, video_id="removed-item")
    active.preview_info = {
        "id": "removed-item",
        "title": "Removed item",
        "vodforge_output_type": "MP4",
    }
    child = replace(
        active,
        run_id="late-child",
        origin_run_id=active.run_id,
        preview_info=dict(active.preview_info),
    )
    unrelated = make_job(tmp_path, video_id="unrelated")
    app = DownloaderApp.__new__(DownloaderApp)
    app.active_job = active
    app.pending_jobs = [unrelated]
    app._library_suppressed_run_ids = {active.run_id}
    app.events = queue.Queue()
    app.events.put(
        (
            "history_record",
            {
                "job": replace(active),
                "info": dict(active.preview_info),
                "output_dir": str(tmp_path / "late"),
            },
        )
    )
    app.events.put(("item_terminal", {"job": child, "info": dict(active.preview_info)}))
    app.events.put(("log", "later event still drained"))
    app._record_download_history = lambda *_args, **_kwargs: (_ for _ in ()).throw(
        AssertionError("late history resurrected")
    )
    app._archive_item_terminal_job = lambda *_args, **_kwargs: (_ for _ in ()).throw(
        AssertionError("late terminal resurrected")
    )
    logs: list[str] = []
    app._append_log = logs.append
    app.after = lambda *_args, **_kwargs: None

    app._pump_events()

    assert app.pending_jobs == [unrelated]
    assert logs == ["later event still drained"]


def test_remove_from_library_clears_matching_stopped_forge_recent(
    monkeypatch, tmp_path: Path
):
    stopped = make_job(tmp_path, video_id="stopped-item")
    stopped.output_type = OutputType.MP4
    stopped.terminal_status = "Stopped"
    stopped.preview_info = {
        "id": "stopped-item",
        "title": "Stopped item",
        "vodforge_output_type": "MP4",
    }
    stopped.metadata_keys.add(("stopped-item", "MP4"))
    unrelated = make_job(tmp_path, video_id="other-item")
    unrelated.output_type = OutputType.MP4
    unrelated.terminal_status = "Stopped"
    unrelated.preview_info = {
        "id": "other-item",
        "title": "Other item",
        "vodforge_output_type": "MP4",
    }
    unrelated.metadata_keys.add(("other-item", "MP4"))
    active = make_job(tmp_path, video_id="stopped-item")
    queued = make_job(tmp_path, video_id="stopped-item")

    app = DownloaderApp.__new__(DownloaderApp)
    app.video_tree = SelectedTree()
    # Reproduce the legacy cancellation row: it has media identity but no
    # vodforge_terminal_run_id linking it to the Forge terminal collection.
    app.metadata_items = [dict(stopped.preview_info)]
    app.download_history = []
    app.history_path = tmp_path / "history.json"
    app._terminal_jobs = [stopped, unrelated]
    app._completed_jobs = []
    app.active_job = active
    app.pending_jobs = [queued]
    app.status_var = Value("")
    app._render_metadata_tree = lambda: None
    app._focus_selected_run_id = stopped.run_id
    app.focus_run_deck = object()
    app._focus_run_records = lambda: [{"kind": "completed", "run_id": unrelated.run_id}]
    selected_records: list[dict[str, object]] = []
    app._focus_select_run_record = selected_records.append
    refreshes: list[bool] = []
    app._refresh_focus_run_deck = lambda: refreshes.append(True)
    monkeypatch.setattr(
        app_module.messagebox, "askyesno", lambda *_args, **_kwargs: True
    )

    app._remove_selected_library_item()

    assert app.metadata_items == []
    assert [job.run_id for job in app._terminal_jobs] == [unrelated.run_id]
    assert app.active_job is active
    assert app.pending_jobs == [queued]
    assert selected_records == [{"kind": "completed", "run_id": unrelated.run_id}]
    assert refreshes == [True]
    assert "Library and Forge recents" in app.status_var.get()

    removal_source = inspect.getsource(
        DownloaderApp._remove_library_item_from_forge_recents
    )
    assert "without deleting media files" in removal_source
    assert "active_job" not in removal_source
    assert "pending_jobs" not in removal_source


def test_cancelled_active_run_links_its_library_row_to_the_terminal_recent(
    tmp_path: Path,
):
    stopped = make_job(tmp_path, video_id="stopped-item")
    stopped.preview_info = {
        "id": "stopped-item",
        "title": "Stopped item",
        "vodforge_output_type": "MP4",
    }
    stopped.metadata_keys.add(("stopped-item", "MP4"))
    app = DownloaderApp.__new__(DownloaderApp)
    app.active_job = stopped
    app._terminal_jobs = []
    app.metadata_items = [dict(stopped.preview_info)]
    app._focus_active_thumbnail_source_image = None
    app._focus_active_thumbnail_is_placeholder = True
    app._focus_selected_run_id = stopped.run_id

    app._archive_active_terminal_job("Stopped", "Cancelled by user")

    assert app.metadata_items[0]["vodforge_terminal_status"] == "Stopped"
    assert app.metadata_items[0]["vodforge_terminal_message"] == "Cancelled by user"
    assert app.metadata_items[0]["vodforge_terminal_run_id"] == stopped.run_id
