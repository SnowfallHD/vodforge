"""YouTube's bot check stops a playlist early and points to YouTube access."""

from __future__ import annotations

from pathlib import Path

import pytest

import yt_downloader.download_service as app_module
from tests.test_metadata_helpers import _worker_test_app, _worker_test_job
from yt_downloader.download_error_presentation import (
    YouTubeAccessMessage,
    download_error_message,
)
from yt_downloader.models import DownloadOutcome


def _playlist_app(monkeypatch, failures):
    """Run a playlist whose items fail as listed: "bot" or "other"."""
    monkeypatch.setattr(app_module, "load_yt_dlp", lambda: object())
    monkeypatch.setattr(app_module, "write_diagnostic", lambda _message: None)
    monkeypatch.setattr(
        app_module, "append_batch_failure_report", lambda *_args, **_kwargs: None
    )
    app = _worker_test_app()
    entries = [
        {
            "id": f"v{index}",
            "title": f"Video {index}",
            "webpage_url": f"https://www.youtube.com/watch?v=v{index}",
        }
        for index in range(1, len(failures) + 1)
    ]
    app._expand_download_source = lambda *_args, **_kwargs: (
        app_module._ExpandedDownloadSource(
            playlist_info={"id": "playlist", "title": "Playlist"}, entries=entries
        )
    )
    analyzed = []

    def analyze_item(job, _ytdlp, _network, item, *_args, **_kwargs):
        analyzed.append(item.index)
        # The real logger records yt-dlp's warning; analysis then finds no formats.
        job.extractor_warnings.clear()
        if failures[item.index - 1] == "bot":
            job.extractor_warnings.add("bot_challenge")
            raise RuntimeError("No usable video source was available.")
        raise RuntimeError("provider failure")

    app._analyze_download_item = analyze_item
    return app, analyzed


def _terminals(app):
    return [
        (kind, payload)
        for kind, payload in app.events.queue
        if kind in {"done", "partial", "stopped", "error"}
    ]


@pytest.mark.parametrize("use_cookies", [False, True])
def test_bot_check_on_three_videos_in_a_row_stops_the_playlist(
    monkeypatch, tmp_path: Path, use_cookies
):
    app, analyzed = _playlist_app(monkeypatch, ["bot"] * 10)
    job = _worker_test_job(tmp_path)
    job.use_cookies = use_cookies

    outcome = app._download_worker_single(job)

    assert analyzed == [1, 2, 3]
    assert outcome == DownloadOutcome(failure_count=3)
    [(kind, message)] = _terminals(app)
    assert kind == "error"
    assert isinstance(message, YouTubeAccessMessage)
    assert message.action == "open_youtube_access"
    assert "3 videos in a row" in message
    assert ("choose Browser" in message) is not use_cookies
    assert ("cookies.txt" in message) is use_cookies
    logs = [payload["line"] for kind, payload in app.events.queue if kind == "job_log"]
    assert any("stopped before the remaining 7 video(s)" in line for line in logs)
    assert job.failure_diagnostic.reason == "authentication_required"


def test_unrelated_failures_break_the_streak_and_the_playlist_continues(
    monkeypatch, tmp_path: Path
):
    app, analyzed = _playlist_app(
        monkeypatch, ["bot", "bot", "other", "bot", "bot", "other"]
    )

    outcome = app._download_worker_single(_worker_test_job(tmp_path))

    assert analyzed == [1, 2, 3, 4, 5, 6]
    assert outcome == DownloadOutcome(failure_count=6)
    [(kind, message)] = _terminals(app)
    assert kind == "error"
    assert not isinstance(message, YouTubeAccessMessage)


def test_bot_check_on_the_last_videos_finishes_without_an_early_stop(
    monkeypatch, tmp_path: Path
):
    app, analyzed = _playlist_app(monkeypatch, ["other", "bot", "bot", "bot"])

    app._download_worker_single(_worker_test_job(tmp_path))

    assert analyzed == [1, 2, 3, 4]
    [(kind, message)] = _terminals(app)
    assert kind == "error"
    assert not isinstance(message, YouTubeAccessMessage)


def test_single_video_bot_check_offers_youtube_access(monkeypatch, tmp_path: Path):
    app, analyzed = _playlist_app(monkeypatch, ["bot"])

    app._download_worker_single(
        _worker_test_job(tmp_path, url="https://www.youtube.com/watch?v=v1")
    )

    assert analyzed == [1]
    [(kind, message)] = _terminals(app)
    assert kind == "error"
    assert isinstance(message, YouTubeAccessMessage)
    assert "could not read this video" in message


def test_provider_bot_text_offers_youtube_access():
    message = download_error_message(
        RuntimeError("ERROR: [youtube] v1: Sign in to confirm you're not a bot")
    )
    assert isinstance(message, YouTubeAccessMessage)
    assert message.action_label == "YouTube access"
