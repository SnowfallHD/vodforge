"""Application producer contracts, separate from transport/storage regressions."""

from types import SimpleNamespace

import pytest

from yt_downloader.app import DownloaderApp
from yt_downloader.models import OutputType


class Recorder:
    def __init__(self):
        self.events = []

    def record(self, name, **fields):
        self.events.append((name, fields))


@pytest.mark.parametrize(
    "output,expected",
    [
        (OutputType.MP4, "mp4"),
        (OutputType.MP3, "mp3"),
        (OutputType.ORIGINAL, "original"),
    ],
)
@pytest.mark.parametrize(
    "status,event",
    [
        ("Completed", "run_completed"),
        ("Partial", "run_completed"),
        ("Failed", "run_failed"),
        ("Stopped", "run_stopped"),
    ],
)
def test_terminal_producer_preserves_attempt_identity_and_actual_format(
    output, expected, status, event
):
    recorder = Recorder()
    app = SimpleNamespace(product_telemetry=recorder)
    job = SimpleNamespace(
        run_id="attempt-1", output_type=output, failure_diagnostic=None
    )
    DownloaderApp._record_product_run_outcome(app, job, status)
    assert recorder.events == [
        (
            event,
            {
                "dedupe_key": "attempt-1",
                "attempt_key": "attempt-1",
                "retry_key": None,
                "dimensions": {
                    "input_kind": "single",
                    "item_count_bucket": "1",
                    "metadata": "disabled",
                    "outcome": {
                        "Completed": "complete",
                        "Partial": "partial",
                        "Failed": "failed",
                        "Stopped": "stopped",
                    }[status],
                },
                "run_kind": "youtube",
                "output_type": expected,
                "failure_reason": None,
                "failure_detail": None,
            },
        )
    ]


@pytest.mark.parametrize("status", ["Queued", "Preparing", "Downloading", "Skipped"])
def test_nonterminal_or_skipped_attempt_is_not_a_completion(status):
    recorder = Recorder()
    app = SimpleNamespace(product_telemetry=recorder)
    DownloaderApp._record_product_run_outcome(app, SimpleNamespace(), status)
    assert recorder.events == []


def test_shutdown_cannot_emit_another_app_open():
    app = SimpleNamespace(
        _closing=True,
        product_telemetry=SimpleNamespace(
            record_app_opened=lambda: pytest.fail("closing app emitted an open")
        ),
    )
    DownloaderApp._record_product_app_opened(app)


@pytest.mark.parametrize(
    "output,expected",
    [
        (OutputType.MP4, "mp4"),
        (OutputType.MP3, "mp3"),
        (OutputType.ORIGINAL, "original"),
    ],
)
def test_playback_producer_keeps_original_audio_unlabeled(output, expected):
    recorder = Recorder()
    DownloaderApp._record_product_playback_started(
        SimpleNamespace(product_telemetry=recorder),
        {"vodforge_output_type": output.value},
    )
    assert recorder.events == [("playback_started", {"output_type": expected})]


@pytest.mark.parametrize(
    "output,expected",
    [
        (OutputType.MP4, "mp4"),
        (OutputType.MP3, "mp3"),
        (OutputType.ORIGINAL, "original"),
    ],
)
def test_actual_worker_launch_emits_start_with_attempt_identity(output, expected):
    import queue
    import threading

    recorder = Recorder()
    started = threading.Event()
    control = SimpleNamespace(config=lambda **kwargs: None)
    value = SimpleNamespace(set=lambda value: None)
    app = SimpleNamespace(
        _closing=False,
        product_telemetry=recorder,
        _project_preparing_job_to_library=lambda job: None,
        progress_var=value,
        status_var=value,
        events=queue.Queue(),
        download_button=control,
        cancel_button=control,
        skip_video_button=control,
        skip_url_button=control,
        _download_worker=lambda job: started.set(),
    )
    job = SimpleNamespace(run_id="actual-worker-attempt", output_type=output)
    assert DownloaderApp._launch_download_job(app, job, select_detail=False)
    app.worker.join(timeout=2)
    assert started.is_set()
    assert recorder.events == [
        (
            "run_started",
            {
                "dedupe_key": job.run_id,
                "attempt_key": job.run_id,
                "retry_key": None,
                "dimensions": {
                    "input_kind": "single",
                    "item_count_bucket": "1",
                    "metadata": "disabled",
                },
                "run_kind": "youtube",
                "output_type": expected,
            },
        )
    ]
    app._closing = True
    assert not DownloaderApp._launch_download_job(app, job, select_detail=False)
    assert len(recorder.events) == 1
