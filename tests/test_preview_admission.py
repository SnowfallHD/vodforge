"""Preview ownership across real admission, persistence and projection boundaries."""

import queue

import pytest

from tests.test_state_authority import Control, LiveWorker, Value, make_job
from yt_downloader import app as app_module
from yt_downloader.app import DownloaderApp
from yt_downloader.library_annotations import LibraryAnnotation, LibraryAnnotationsOwner
from yt_downloader.library_state import PROJECTION_OWNER_KEY, LibraryProjectionOwner


class Recovery:
    def __init__(self, reject):
        self.reject = reject
        self.calls = []

    def queue_changed(self, jobs, **_kwargs):
        self.calls.append(("queue", len(jobs)))
        if self.reject:
            raise app_module.RunStateError("controlled persistence rejection")

    def removed_or_retried(self, run_id):
        self.calls.append(("retired", run_id))

    def begin(self, job, jobs, **_kwargs):
        self.calls.append(("begin", len(jobs)))
        if self.reject:
            raise app_module.RunStateError("controlled persistence rejection")


class HeldWorker:
    """Retain the actual launch boundary without starting a network download."""

    def __init__(self, *, target, args, daemon):
        self.args = args
        self.started = False

    def start(self):
        self.started = True

    def is_alive(self):
        return self.started


def prepared_app(
    tmp_path, monkeypatch, *, busy, reject=False, duplicate=False, hold_worker=True
):
    app = DownloaderApp.__new__(DownloaderApp)
    app.tk = None
    app._closing = False
    app._focus_views = {}
    app._focus_selected_run_id = "prior-selection"
    app.download_history = []
    app._terminal_jobs = []
    app.pending_jobs = []
    app.library_projection = LibraryProjectionOwner()
    app.library_annotations = LibraryAnnotationsOwner(tmp_path / "annotations.json")
    rows = [
        {
            "id": f"preview-{index}",
            "title": f"Private preview {index}",
            "webpage_url": f"https://www.youtube.com/watch?v=preview-{index}",
            "vodforge_output_type": "MP4",
        }
        for index in range(3)
    ]
    app.library_projection.record_preview("preview-batch", rows)
    for index in range(3):
        app.library_annotations.replace(
            f"preview:preview-batch:{index}",
            LibraryAnnotation(note=f"Private note {index}", category="Personal"),
        )
    app.active_job = (
        make_job(
            tmp_path, video_id="preview-0" if duplicate and busy else "other-active"
        )
        if busy
        else None
    )
    app.worker = LiveWorker() if busy else None
    if duplicate and not busy:
        app.pending_jobs = [make_job(tmp_path, video_id="preview-0")]
    app.run_recovery = Recovery(reject)
    app.status_var = Value("Before submission")
    app.progress_var = Value(0)
    app.events = queue.Queue()
    app.batch_urls = []
    app.url_var = Value("https://www.youtube.com/watch?v=preview-0")
    app.url_list_file_var = Value("No URL list loaded")
    app.single_video_only_var = Value(True)
    app._selected_output_type = lambda: app_module.OutputType.MP4
    app.views = []
    app._select_focus_view = app.views.append
    app._append_log = lambda *_args: None
    app._record_queue_event = lambda *_args: None
    app._enqueue_queue_preview = lambda *_args: app._reconcile_library_projection()
    app._focus_run_records = lambda: [
        {"run_id": job.run_id} for job in app.pending_jobs
    ]
    app._display_focus_queued_job_snapshot = lambda *_args: None
    for name in (
        "download_button",
        "cancel_button",
        "skip_video_button",
        "skip_url_button",
    ):
        setattr(app, name, Control())
    if hold_worker:
        monkeypatch.setattr(app_module.threading, "Thread", HeldWorker)
    else:
        app._download_worker = lambda _job: None
    app.errors = []
    monkeypatch.setattr(
        app_module.messagebox, "showerror", lambda *args: app.errors.append(args)
    )
    app._reconcile_library_projection()
    app.built_job = make_job(tmp_path, video_id="preview-0")
    app._build_download_job_from_current_settings = lambda *_args, **_kwargs: (
        app.built_job
    )
    return app


def submit(app, route):
    if route == "forge":
        app._start_download()
    else:
        preview = next(
            row for row in app.metadata_items if row.get("id") == "preview-0"
        )
        app._start_preview_download(preview)
    app._reconcile_library_projection()


@pytest.mark.parametrize("route", ["library", "forge"])
@pytest.mark.parametrize("busy", [False, True])
def test_rejected_admission_preserves_preview_siblings_notes_selection_and_input(
    tmp_path, monkeypatch, route, busy
):
    app = prepared_app(tmp_path, monkeypatch, busy=busy, reject=True)
    before = app.library_projection.snapshot
    annotations = dict(app.library_annotations.snapshot)
    submit(app, route)
    assert app.library_projection.snapshot == before
    assert dict(app.library_annotations.snapshot) == annotations
    assert app.views == []
    assert app._focus_selected_run_id == "prior-selection"
    assert app.url_var.get().endswith("preview-0")
    assert not app.pending_jobs
    assert app.active_job is not app.built_job
    assert len(app.errors) == 1


@pytest.mark.parametrize("route", ["library", "forge"])
@pytest.mark.parametrize("busy", [False, True])
def test_admitted_subject_transfers_notes_and_preserves_exact_sibling_owners(
    tmp_path, monkeypatch, route, busy
):
    app = prepared_app(tmp_path, monkeypatch, busy=busy)
    siblings = {
        row[PROJECTION_OWNER_KEY]: row
        for row in app.metadata_items
        if row.get("id") in {"preview-1", "preview-2"}
    }
    submit(app, route)
    after = {row[PROJECTION_OWNER_KEY]: row for row in app.metadata_items}
    assert all(after[key] == row for key, row in siblings.items())
    assert "preview:preview-batch:0" not in after
    admitted = after[f"run:{app.built_job.run_id}"]
    assert admitted["vodforge_user_note"] == "Private note 0"
    assert app.library_annotations.annotation_for("preview:preview-batch:0").empty
    assert app.built_job.preview_source_owner is None
    assert not app.errors
    assert (
        (app.pending_jobs == [app.built_job])
        if busy
        else (app.active_job is app.built_job)
    )
    if route == "library":
        assert app.views == ["forge"]
        assert app._focus_selected_run_id == app.built_job.run_id
    else:
        assert app.url_var.get() == ""
    # Consume the next subject without renumbering its surviving sibling.
    next_preview = after["preview:preview-batch:1"]
    assert (
        app.library_projection.preview_subject(next_preview)
        == "preview:preview-batch:1"
    )
    assert app.library_projection.consume_preview_subject("preview:preview-batch:1")
    app._reconcile_library_projection()
    surviving = next(row for row in app.metadata_items if row.get("id") == "preview-2")
    assert surviving == siblings["preview:preview-batch:2"]


@pytest.mark.parametrize("route", ["library", "forge"])
@pytest.mark.parametrize("busy", [False, True])
def test_duplicate_focuses_existing_attempt_without_consuming_preview(
    tmp_path, monkeypatch, route, busy
):
    app = prepared_app(tmp_path, monkeypatch, busy=busy, duplicate=True)
    existing = app.active_job if busy else app.pending_jobs[0]
    before = app.library_projection.snapshot
    annotations = dict(app.library_annotations.snapshot)
    submit(app, route)
    assert app.library_projection.snapshot == before
    assert dict(app.library_annotations.snapshot) == annotations
    assert app._focus_selected_run_id == existing.run_id
    assert app.views == ["forge"]
    assert not app.run_recovery.calls
    assert not app.errors
    assert app.built_job is not existing
    assert app.url_var.get() == (
        "" if route == "forge" else "https://www.youtube.com/watch?v=preview-0"
    )


@pytest.mark.parametrize("route", ["library", "forge"])
def test_validation_failure_preserves_canonical_preview(tmp_path, monkeypatch, route):
    app = prepared_app(tmp_path, monkeypatch, busy=True)
    before = app.library_projection.snapshot
    app._build_download_job_from_current_settings = lambda *_args, **_kwargs: None
    submit(app, route)
    assert app.library_projection.snapshot == before
    assert app.views == []
    assert not app.run_recovery.calls


def test_annotation_write_failure_keeps_original_preview_notes_after_admission(
    tmp_path, monkeypatch
):
    app = prepared_app(tmp_path, monkeypatch, busy=True)

    def denied(*_args):
        raise app_module.LibraryAnnotationsError(
            "controlled private annotation write failure"
        )

    monkeypatch.setattr(app.library_annotations, "transfer", denied)
    submit(app, "library")
    assert app.pending_jobs == [app.built_job]
    assert (
        app.library_annotations.annotation_for("preview:preview-batch:0").note
        == "Private note 0"
    )
    assert (
        sum(row.get("vodforge_preview_complete") is True for row in app.metadata_items)
        == 3
    )


@pytest.mark.parametrize("reject", [True, False])
def test_queued_removal_changes_projection_only_after_persistence(
    tmp_path, monkeypatch, reject
):
    app = prepared_app(tmp_path, monkeypatch, busy=True, reject=reject)
    target = app.built_job
    target.preview_info = {"id": "queued-target", "title": "Queued target"}
    app.pending_jobs = [target]
    app._reconcile_library_projection()
    captured = next(
        row
        for row in app.metadata_items
        if row[PROJECTION_OWNER_KEY] == f"run:{target.run_id}"
    )
    before = app.library_projection.snapshot
    observed = []
    app._record_feature = lambda *args, **_kwargs: observed.append(args)
    monkeypatch.setattr(app_module.messagebox, "askyesno", lambda *_args: True)
    app._remove_selected_library_item(dict(captured))
    app._reconcile_library_projection()
    if reject:
        assert app.pending_jobs == [target]
        assert app.library_projection.snapshot == before
        assert target.run_id not in app.__dict__.get(
            "_library_suppressed_run_ids", set()
        )
        assert not observed
        assert app.errors
    else:
        assert not app.pending_jobs
        assert all(
            row[PROJECTION_OWNER_KEY] != f"run:{target.run_id}"
            for row in app.metadata_items
        )
        assert observed == [("library", "removed")]
        assert not app.errors


def test_preview_removal_preserves_sibling_notes_and_group_navigation(
    tmp_path, monkeypatch
):
    app = prepared_app(tmp_path, monkeypatch, busy=False)
    previews = {row[PROJECTION_OWNER_KEY]: row for row in app.metadata_items}
    captured = previews["preview:preview-batch:0"]
    observed = []
    app._record_feature = lambda *args, **_kwargs: observed.append(args)
    monkeypatch.setattr(app_module.messagebox, "askyesno", lambda *_args: True)
    removed = []
    app._reconcile_focus_after_library_removal = removed.append
    app._remove_selected_library_item(dict(captured))
    survivors = {row[PROJECTION_OWNER_KEY]: row for row in app.metadata_items}
    assert survivors == {
        key: row for key, row in previews.items() if key != "preview:preview-batch:0"
    }
    assert app.library_annotations.annotation_for("preview:preview-batch:0").empty
    assert (
        app.library_annotations.annotation_for("preview:preview-batch:1").note
        == "Private note 1"
    )
    assert removed == [set()]
    assert observed == [("library", "removed")]
    assert not app.errors


def test_repeated_playlist_media_requires_canonical_subject_identity():
    owner = LibraryProjectionOwner()
    source = {"id": "repeat", "vodforge_output_type": "MP4"}
    owner.record_preview("batch", [source, source])
    assert owner.preview_subject({**source, "vodforge_preview_run_id": "batch"}) is None
    rows = owner.reconcile(
        history_items=[], active_job=None, queued_jobs=[], terminal_jobs=[]
    ).rows
    assert owner.preview_subject(rows[0]) == "preview:batch:0"
    assert owner.consume_preview_subject("preview:batch:0")
    assert owner.preview_subject(rows[1]) == "preview:batch:1"
    assert owner.claim_preview("batch") == [source]
