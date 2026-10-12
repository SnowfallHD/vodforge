"""Preview ownership across real admission, persistence and projection boundaries."""

from yt_downloader import download_service as app_module
from yt_downloader.library_state import LibraryProjectionOwner


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


def submit(app, route):
    if route == "forge":
        app._start_download()
    else:
        preview = next(
            row for row in app.metadata_items if row.get("id") == "preview-0"
        )
        app._start_preview_download(preview)
    app._reconcile_library_projection()


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
