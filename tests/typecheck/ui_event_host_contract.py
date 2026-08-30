from queue import Queue

from yt_downloader.app import DownloaderApp
from yt_downloader.models import DownloadJob
from yt_downloader.ui_events import (
    UiEvent,
    UiEventSink,
    _UiEventHost,
    history_record_event,
    job_info_event,
    job_log_event,
    thumbnail_preview_event,
)


def _assert_downloader_app_contract(app: DownloaderApp) -> None:
    host: _UiEventHost = app
    assert host is app


def _assert_ui_event_contract(job: DownloadJob, info: dict[str, object]) -> None:
    events: Queue[UiEvent] = Queue()
    sink: UiEventSink = events
    sink.put(job_log_event(job, "started"))
    sink.put(job_info_event("job_metadata", job, info))
    sink.put(history_record_event(job, info, "/output"))
    sink.put(
        thumbnail_preview_event(
            1,
            "https://example.test/thumb.jpg",
            "active",
            job.run_id,
            data=b"preview",
        )
    )
