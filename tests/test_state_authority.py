"""Cross-surface state authority contracts for the VODForge desktop UI.

These tests intentionally guard ownership boundaries rather than individual
widget arrangements. A Forge run owns Forge identity and progress; Library
selection owns Library inspection; worker events may enrich only their run ID;
and each thumbnail surface owns its own asynchronous request generation.
"""

from dataclasses import replace
import inspect
from pathlib import Path
import queue

import yt_downloader.app as app_module

from yt_downloader.app import (
    DownloadJob,
    DownloaderApp,
    ExportMode,
    ManualExportSettings,
    Mp3ExportSettings,
    OutputType,
)
from yt_downloader.history import history_identity, upsert_history


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
        return None

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
    app._display_focus_queued_job_snapshot = lambda record, job: displayed.append((record, job))
    app._display_focus_job_snapshot = lambda _job: (_ for _ in ()).throw(AssertionError("active run leaked"))

    record = {"kind": "queued", "run_id": queued_job.run_id}
    app._focus_select_run_record(record)

    assert app._focus_selected_run_id == queued_job.run_id
    assert displayed == [(record, queued_job)]


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
    app._load_thumbnail_preview = lambda url, *, target="both", **_kwargs: thumbnail_requests.append((url, target))

    app._display_selected_metadata(0)

    assert app.focus_active_title_var.get() == "Forge-owned title"
    assert app.focus_active_detail_var.get() == "Forge-owned creator"
    assert app.focus_active_duration_var.get() == "9:59"
    assert app.focus_active_profile_var.get() == "Forge-owned profile"
    assert app.status_var.get() == "Ready"
    assert thumbnail_requests == [("https://i.ytimg.com/vi/library-only-id/hqdefault.jpg", "library")]
    assert "Library selection" in app.selected_title_var.get()


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


def test_compact_layout_does_not_schedule_a_forced_activity_tail_jump():
    layout_source = inspect.getsource(DownloaderApp._apply_focus_layout)

    assert 'focus_log.after_idle(lambda: self.focus_log.see("end"))' not in layout_source


def test_completed_selection_freezes_detail_progress_while_active_run_advances(tmp_path: Path):
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
    app._load_thumbnail_file = lambda path, *, target, owner_run_id="": loaded.append((path, target, owner_run_id))

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
    monkeypatch.setattr("yt_downloader.app.download_bounded_url_bytes", lambda *_args, **_kwargs: b"image")
    app._provider_network_coordinator = lambda: (_ for _ in ()).throw(AssertionError("provider gate used"))

    app._fetch_thumbnail_preview_request(7, "https://example.test/thumb.jpg", "active", "run-7")

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
    file_target = inspect.signature(DownloaderApp._load_thumbnail_file).parameters["target"]
    url_target = inspect.signature(DownloaderApp._load_thumbnail_preview).parameters["target"]

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
            raise AssertionError(f"ambiguous thumbnail owner {invalid_target!r} was accepted")


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
        {"id": 4, "url": "https://example.invalid/active.jpg", "target": "active", "error": "active failed"}
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


def test_retry_preserves_playlist_identity_and_removes_the_old_terminal_row(tmp_path: Path):
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
    assert launched[0].url == "https://www.youtube.com/watch?v=authority-id&list=PLauthority"
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


def test_newest_completed_run_remains_owner_of_a_repeated_history_identity(tmp_path: Path):
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
    app._archive_active_terminal_job = lambda *_args: (_ for _ in ()).throw(AssertionError("duplicate parent terminal"))
    app.progress_var = Value(0)
    app.status_var = Value("")
    app.download_button = Control()
    app.cancel_button = Control()
    app.skip_video_button = Control()
    app.skip_url_button = Control()
    app._launch_next_pending_job = lambda: False

    app._finish_run_ui("Stopped after skip", "Stopped", "Stopped")

    assert app.status_var.get() == "Stopped after skip"


def test_single_url_worker_mutates_the_active_authority_not_a_private_copy(tmp_path: Path):
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
    app._thumbnail_preview_request_ids = {"active": 0, "library": 0, "run:active-run": 3}
    app._focus_selected_run_id = "completed-run"
    app.focus_active_thumbnail_label = Label()
    app.thumbnail_label = Label()
    app._refresh_focus_run_deck = lambda: None

    app._display_thumbnail_preview_result({
        "id": 3,
        "url": "https://example.invalid/thumb.jpg",
        "target": "run:active-run",
        "run_id": "active-run",
        "error": "network failed",
    })

    assert app.focus_active_thumbnail_label.text == "selected thumbnail"


def test_background_run_thumbnail_decode_error_cannot_replace_selected_run_surface(monkeypatch):
    class Label:
        def __init__(self):
            self.text = "selected thumbnail"

        def config(self, **kwargs):
            self.text = str(kwargs.get("text") or "")

    app = DownloaderApp.__new__(DownloaderApp)
    app._thumbnail_preview_request_ids = {"active": 0, "library": 0, "run:active-run": 3}
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

    app._display_thumbnail_preview_result({
        "id": 3,
        "url": "https://example.invalid/thumb.jpg",
        "target": "run:active-run",
        "run_id": "active-run",
        "data": b"not an image",
    })

    assert app.thumbnail_label.text == "selected thumbnail"


def test_all_resizable_popouts_enforce_content_appropriate_minimums():
    compact_source = inspect.getsource(DownloaderApp._build_ui)
    settings_source = inspect.getsource(DownloaderApp._show_focus_settings)
    output_source = inspect.getsource(DownloaderApp._show_focus_output_details)
    selected_source = inspect.getsource(DownloaderApp._show_selected_metadata_details)

    assert "popup.minsize(popup_width, popup_height)" in compact_source
    assert "popup.minsize(700, 540)" in settings_source
    assert "popup.minsize(480, 300)" in output_source
    assert "popup.minsize(560, 520)" in selected_source
    assert "height=135" in selected_source


def test_focus_settings_keep_manual_controls_in_the_mp4_flow_and_release_combo_selection():
    settings_source = inspect.getsource(DownloaderApp._show_focus_settings)

    description_index = settings_source.index("textvariable=self.export_mode_description_var")
    manual_index = settings_source.index('manual = ttk.Frame(mp4_output, style="FocusShell.TFrame")')
    checkboxes_index = settings_source.index('text="Save thumbnail"')

    assert description_index < manual_index < checkboxes_index
    assert "manual = ttk.Frame(root" not in settings_source
    assert 'manual.grid(row=4, column=0, columnspan=2, sticky="ew"' in settings_source
    assert '"Video bitrate (kbps)"' in settings_source
    assert '"Audio bitrate (kbps)"' in settings_source
    assert '"Sample rate"' in settings_source
    assert '"Channels"' in settings_source
    assert '"Encoding speed"' in settings_source
    assert "bind_readonly_combo(export_combo, self._refresh_manual_settings_visibility)" in settings_source
    assert "combo.selection_clear()" in settings_source
    assert "popup.focus_set()" in settings_source


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
    assert 'run_list.grid(row=0, column=0, sticky="nsew", padx=(14, 6), pady=12)' in run_list_source
    assert "bind_smooth_vertical_wheel(" in run_list_source
    assert 'mode="increments"' in run_list_source
    assert "button.winfo_rooty() - self.winfo_rooty() - height - 6" in run_list_source
    assert "popup.place(x=x, y=y, width=width, height=height)" in run_list_source
    assert "width = min(440" in run_list_source
    assert "height = min(184" in run_list_source
    assert 'focus_run_overflow_button.bind("<Enter>"' in forge_source
    assert 'focus_run_overflow_button.bind("<Leave>"' in forge_source
    assert "self._cancel_focus_run_menu_close()" in run_list_source
    assert "existing.destroy()" not in run_list_source
    assert 'popup.bind("<Enter>"' in run_list_source
    assert 'popup.bind("<Leave>"' in run_list_source
    assert "hovered is button or inside_popup" in close_source
    assert "self.after(40, close_if_pointer_left)" in close_source
    assert 'selected_run_id = str(self._focus_selected_run_id or "").strip()' in run_list_source
    assert "if selected_run_id and record_run_id == selected_run_id:" in run_list_source


def test_library_table_and_run_picker_keep_all_items_reachable_at_every_size():
    library_source = inspect.getsource(DownloaderApp._build_focus_library_view)
    deck_source = inspect.getsource(DownloaderApp._refresh_focus_run_deck)
    layout_source = inspect.getsource(DownloaderApp._apply_focus_layout)

    assert 'orient="horizontal"' in library_source
    assert "xscrollcommand=tree_x_scroll.set" in library_source
    assert 'self.video_tree.layout_column("creator", width=120, minwidth=90' in layout_source
    assert 'self.video_tree.layout_column("location", width=140, minwidth=100' in layout_source
    assert 'self.video_tree.layout_column("title", width=360, minwidth=220, stretch=False)' in layout_source
    assert 'width=0, minwidth=0' not in layout_source
    assert 'library_mode = "compact" if compact else focus_library_layout_mode(width)' in layout_source
    assert "library_mode," in layout_source
    assert 'if library_mode == "compact":' in layout_source
    assert "library_actions_collapsed" not in layout_source
    assert 'self.focus_metadata_content.columnconfigure(0, weight=1)' in layout_source
    assert 'self.focus_metadata_content.columnconfigure(1, weight=0, minsize=340)' in layout_source
    assert 'self.focus_metadata_content.columnconfigure(1, weight=0, minsize=300)' in layout_source
    assert "limit = focus_run_deck_capacity(deck_width)" in deck_source
    assert "self.focus_run_overflow_button.grid()" in deck_source
    assert "if self._focus_run_records():" in layout_source


def test_primary_scroll_surfaces_use_high_resolution_trackpad_bindings():
    library_source = inspect.getsource(DownloaderApp._build_focus_library_view)
    activity_source = inspect.getsource(DownloaderApp._build_focus_activity_view)
    forge_source = inspect.getsource(DownloaderApp._build_focus_forge_view)
    pixel_table_source = inspect.getsource(app_module.PixelScrollTable)
    wheel_binding_source = inspect.getsource(app_module.bind_smooth_vertical_wheel)

    assert "self.video_tree = PixelScrollTable(" in library_source
    assert 'target.bind("<TouchpadScroll>"' in pixel_table_source
    assert "tk::PreciseScrollDeltas" in inspect.getsource(app_module.touchpad_scroll_deltas)
    assert "yview_moveto" in pixel_table_source
    assert "xview(\"moveto\"" in pixel_table_source
    assert 'target.bind("<TouchpadScroll>"' in wheel_binding_source
    assert "bind_smooth_vertical_wheel(self.log" in activity_source
    assert 'mode="pixels"' in activity_source
    assert "bind_smooth_vertical_wheel(self.focus_log" in forge_source
    assert "bind_smooth_vertical_wheel(self.focus_summary_text" in forge_source


def test_pixel_scroll_library_columns_are_drag_resizable_without_losing_pixel_scroll():
    pixel_table_source = inspect.getsource(app_module.PixelScrollTable)
    layout_source = inspect.getsource(DownloaderApp._apply_focus_layout)

    assert 'self._header.bind("<ButtonPress-1>", self._begin_column_resize' in pixel_table_source
    assert 'self._header.bind("<B1-Motion>", self._drag_column_resize' in pixel_table_source
    assert 'self._header.bind("<ButtonRelease-1>", self._end_column_resize' in pixel_table_source
    assert "rendered_width = next(" in pixel_table_source
    assert "layout[:-1]" in pixel_table_source
    assert "self._resize_margin = 8" in pixel_table_source
    assert "self._header.grab_set()" in pixel_table_source
    assert "self._header.grab_release()" in pixel_table_source
    assert 'else THEME["subtle"]' in pixel_table_source
    assert "self._manually_resized_columns.add(column)" in pixel_table_source
    assert "def layout_column" in pixel_table_source
    assert "self.video_tree.layout_column(" in layout_source
    assert 'xscrollincrement=1' in pixel_table_source


def test_preview_items_expose_fresh_forge_start_actions_without_library_ownership(tmp_path: Path):
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
    app._start_or_queue_download_job = lambda job, *, clear_source: submitted.append((job, clear_source))

    app._start_preview_download(preview)

    assert build_calls == [
        (
            ["https://www.youtube.com/watch?v=preview-id&list=PLpreview"],
            {"output_type": OutputType.MP3, "single_video_only": True, "batch_mode": False},
        )
    ]
    assert built_job.preview_info == {
        key: value
        for key, value in preview.items()
        if key not in {"vodforge_preview_complete", "vodforge_preview_run_id"}
    }
    assert ("preview-id", "MP3") in built_job.metadata_keys
    assert app._focus_selected_run_id == built_job.run_id
    assert selected_views == ["forge"]
    assert submitted == [(built_job, False)]

    deck_source = inspect.getsource(DownloaderApp._refresh_focus_run_deck)
    library_menu_source = inspect.getsource(DownloaderApp._show_library_row_menu)
    compact_menu_source = inspect.getsource(DownloaderApp._show_library_actions_menu)
    assert 'record_kind == "preview"' in deck_source
    assert 'self._start_preview_record(item)' in deck_source
    assert "hover_widgets.append(play_button)" in deck_source
    assert all(line.strip() != "widgets.append(play_button)" for line in deck_source.splitlines())
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
        if key not in {"vodforge_preview_complete", "vodforge_preview_run_id"}
    }
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

    assert [(record["kind"], record["run_id"]) for record in records] == [("active", job.run_id)]
    start_source = inspect.getsource(DownloaderApp._start_download)
    assert start_source.index("self._adopt_matching_preview_for_download_job(job)") < start_source.index(
        "self._start_or_queue_download_job(job, clear_source=True)"
    )


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


def test_terminal_outcomes_become_the_explicit_forge_focus(tmp_path: Path):
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

    pump_source = inspect.getsource(DownloaderApp._pump_events)
    finish_source = inspect.getsource(DownloaderApp._finish_run_ui)
    archive_source = inspect.getsource(DownloaderApp._archive_item_terminal_job)
    assert "self._focus_terminal_job(failed_job)" in pump_source
    assert "self._focus_terminal_job(finished_job)" in finish_source
    assert "self._focus_terminal_job(job)" in archive_source


def test_metadata_preview_focuses_once_and_completion_respects_manual_selection():
    settings_source = inspect.getsource(DownloaderApp._show_focus_settings)
    fetch_source = inspect.getsource(DownloaderApp._fetch_metadata)
    completion_source = inspect.getsource(DownloaderApp._display_metadata)

    assert "def preview_and_close()" in settings_source
    assert "if self._fetch_metadata():" in settings_source
    assert settings_source.index("if self._fetch_metadata():") < settings_source.index("close_popup()", settings_source.index("def preview_and_close()"))
    assert '"kind": "preview_loading"' in fetch_source
    assert "self._focus_selected_run_id = preview_run_id" in fetch_source
    assert "self._display_metadata_preview_request(preview_record)" in fetch_source
    assert "self._focus_selected_run_id = preview_run_id" not in completion_source
    assert 'self.__dict__.get("_focus_selected_run_id") == preview_run_id' in completion_source


def test_custom_popouts_are_positioned_before_they_become_visible():
    compact_source = inspect.getsource(DownloaderApp._build_ui)
    settings_source = inspect.getsource(DownloaderApp._show_focus_settings)
    output_source = inspect.getsource(DownloaderApp._show_focus_output_details)
    selected_source = inspect.getsource(DownloaderApp._show_selected_metadata_details)

    for source in (compact_source, settings_source, output_source, selected_source):
        assert "popup.withdraw()" in source
        assert "reveal_toplevel(popup," in source
        assert source.index("popup.withdraw()") < source.index("reveal_toplevel(popup,")

    assert "centered_toplevel_geometry(self, width, height)" in settings_source
    assert "centered_toplevel_geometry(self, 560, 360)" in output_source
    assert "centered_toplevel_geometry(self, 680, 620)" in selected_source


def test_remove_from_library_never_deletes_the_media_file(monkeypatch, tmp_path: Path):
    output_dir = tmp_path / "Creator" / "playlists" / "Playlist" / "Video [authority-id]"
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
    monkeypatch.setattr(app_module.messagebox, "askyesno", lambda *_args, **_kwargs: True)

    app._remove_selected_library_item()

    assert media.read_bytes() == b"keep me"
    assert app.metadata_items == []
    assert app.download_history == []
    assert "not deleted" in app.status_var.get()


def test_remove_from_library_clears_matching_stopped_forge_recent(monkeypatch, tmp_path: Path):
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
    monkeypatch.setattr(app_module.messagebox, "askyesno", lambda *_args, **_kwargs: True)

    app._remove_selected_library_item()

    assert app.metadata_items == []
    assert [job.run_id for job in app._terminal_jobs] == [unrelated.run_id]
    assert app.active_job is active
    assert app.pending_jobs == [queued]
    assert selected_records == [{"kind": "completed", "run_id": unrelated.run_id}]
    assert refreshes == [True]
    assert "Library and Forge recents" in app.status_var.get()

    removal_source = inspect.getsource(DownloaderApp._remove_library_item_from_forge_recents)
    assert "never execution or files" in removal_source
    assert "active_job" not in removal_source
    assert "pending_jobs" not in removal_source


def test_cancelled_active_run_links_its_library_row_to_the_terminal_recent(tmp_path: Path):
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
