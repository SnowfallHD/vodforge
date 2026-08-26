"""Cross-surface state authority contracts for the VODForge desktop UI.

These tests intentionally guard ownership boundaries rather than individual
widget arrangements. A Forge run owns Forge identity and progress; Library
selection owns Library inspection; worker events may enrich only their run ID;
and each thumbnail surface owns its own asynchronous request generation.
"""

from dataclasses import replace
import inspect
from pathlib import Path

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
    thumbnail_requests: list[tuple[str, str]] = []
    app._load_thumbnail_preview = lambda url, *, target="both", **_kwargs: thumbnail_requests.append((url, target))

    app._display_selected_metadata(0)

    assert app.focus_active_title_var.get() == "Forge-owned title"
    assert app.focus_active_detail_var.get() == "Forge-owned creator"
    assert app.focus_active_duration_var.get() == "9:59"
    assert app.focus_active_profile_var.get() == "Forge-owned profile"
    assert thumbnail_requests == [("https://i.ytimg.com/vi/library-only-id/hqdefault.jpg", "library")]
    assert "Library selection" in app.selected_title_var.get()


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
