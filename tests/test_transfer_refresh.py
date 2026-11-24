"""Synthetic split transfer; no provider, credentials, or native GUI."""

from copy import deepcopy
from types import SimpleNamespace
from urllib.error import HTTPError

import pytest

from yt_downloader import download_service as app
from yt_downloader.transfer_refresh import (
    SplitTransferRefresh,
    TransferRefreshError,
    TransferRestartRefresh,
)


def metadata():
    return {
        "id": "synthetic",
        "duration": 2,
        "availability": "public",
        "formats": [
            {
                "format_id": "v",
                "url": "https://example.invalid/video",
                "ext": "mp4",
                "vcodec": "h264",
                "acodec": "none",
                "width": 160,
                "height": 90,
            },
            {
                "format_id": "a",
                "url": "https://example.invalid/audio-old",
                "ext": "m4a",
                "vcodec": "none",
                "acodec": "aac",
                "abr": 64,
                "asr": 48000,
                "audio_channels": 1,
                "language": "en",
            },
        ],
    }


def prepared(tmp_path):
    info = metadata()
    fresh = deepcopy(info)
    fresh["formats"][1]["url"] = "https://example.invalid/audio-fresh"
    path = tmp_path / "synthetic.fv.mp4"
    path.write_bytes(b"completed original video")
    guard = SplitTransferRefresh(info, "v", "a", tmp_path)
    return info, fresh, path, guard


def finished(guard, path):
    guard.observe(
        {"status": "finished", "filename": str(path), "info_dict": {"format_id": "v"}}
    )


def test_refresh_reselects_exact_formats_once_preserving_video(tmp_path, monkeypatch):
    info, fresh, path, guard = prepared(tmp_path)
    calls, logs, refreshes = [], [], []
    original = path.read_bytes()

    def transfer(module, options, current, cookies, *, control_check):
        calls.append((options, current, cookies))
        if len(calls) == 1:
            for hook in options["progress_hooks"]:
                hook(
                    {
                        "status": "finished",
                        "filename": str(path),
                        "info_dict": {"format_id": "v"},
                    }
                )
            raise HTTPError(info["formats"][1]["url"], 403, "Forbidden", None, None)
        assert path.read_bytes() == original
        return current, cookies

    def refresh():
        refreshes.append(True)
        return fresh, ("same-session",)

    monkeypatch.setattr(app, "_download_preflight_result_step", transfer)
    options = {"format": "v+a/best", "progress_hooks": []}
    result, cookies = app._download_with_audio_url_refresh(
        object(),
        options,
        info,
        (),
        guard,
        refresh=refresh,
        control_check=lambda: None,
        emit_log=logs.append,
    )
    assert len(calls) == 2 and len(refreshes) == 1 and len(logs) == 2
    assert calls[1][0]["format"] == "v+a"
    assert options == {"format": "v+a/best", "progress_hooks": []}
    assert result is fresh and cookies == ("same-session",)


@pytest.mark.parametrize(
    "change",
    [
        "id",
        "duration",
        "private",
        "premium_only",
        "drm",
        "audio_missing",
        "audio_bitrate",
        "codec",
        "language",
        "channels",
        "video_size",
        "same_url",
    ],
)
def test_fresh_metadata_cannot_change_identity_access_or_selected_quality(
    tmp_path, change
):
    info, fresh, path, guard = prepared(tmp_path)
    finished(guard, path)
    if change in {"id", "duration"}:
        fresh[change] = "changed"
    elif change in {"private", "premium_only"}:
        fresh["availability"] = change
    elif change == "audio_missing":
        fresh["formats"] = fresh["formats"][:1]
    elif change == "drm":
        fresh["formats"][1]["has_drm"] = True
    elif change == "video_size":
        fresh["formats"][0]["width"] = 80
    elif change == "same_url":
        fresh["formats"][1]["url"] = info["formats"][1]["url"]
    else:
        key, value = {
            "audio_bitrate": ("abr", 32),
            "codec": ("acodec", "opus"),
            "language": ("language", "fr"),
            "channels": ("audio_channels", 2),
        }[change]
        fresh["formats"][1][key] = value
    with pytest.raises(TransferRefreshError):
        guard.checked_refresh(fresh)
    assert path.read_bytes() == b"completed original video"


@pytest.mark.parametrize(
    "status,url,video_done,audio_done",
    [
        (401, "audio-old", True, False),
        (403, "video", True, False),
        (403, "audio-old", False, False),
        (403, "audio-old", True, True),
    ],
)
def test_no_refresh_for_unrelated_restricted_or_non_split_failure(
    tmp_path, status, url, video_done, audio_done
):
    _, _, path, guard = prepared(tmp_path)
    if video_done:
        finished(guard, path)
    guard.audio_finished = audio_done
    error = HTTPError("https://example.invalid/" + url, status, "Rejected", None, None)
    assert not guard.eligible(status, [error])


def test_repeated403_stops_after_one_refresh(tmp_path, monkeypatch):
    info, fresh, path, guard = prepared(tmp_path)
    finished(guard, path)
    calls, refreshes = [], []

    def transfer(module, options, current, cookies, *, control_check):
        calls.append(True)
        raise HTTPError(current["formats"][1]["url"], 403, "Forbidden", None, None)

    monkeypatch.setattr(app, "_download_preflight_result_step", transfer)

    def refresh():
        refreshes.append(True)
        return fresh, ()

    with pytest.raises(TransferRefreshError, match="rejected again"):
        app._download_with_audio_url_refresh(
            object(),
            {},
            info,
            (),
            guard,
            refresh=refresh,
            control_check=lambda: None,
            emit_log=lambda _: None,
        )
    assert len(calls) == 2 and len(refreshes) == 1
    assert path.read_bytes() == b"completed original video"


@pytest.mark.parametrize("phase", ["before_refresh", "after_refresh"])
def test_cancel_prevents_further_transfer(tmp_path, monkeypatch, phase):
    info, fresh, path, guard = prepared(tmp_path)
    finished(guard, path)
    calls, refreshes = [], []

    def transfer(*args, **kwargs):
        calls.append(True)
        raise HTTPError(info["formats"][1]["url"], 403, "Forbidden", None, None)

    monkeypatch.setattr(app, "_download_preflight_result_step", transfer)

    def refresh():
        refreshes.append(True)
        return fresh, ()

    def control():
        if phase == "before_refresh" or refreshes:
            raise RuntimeError("synthetic cancel")

    with pytest.raises(RuntimeError, match="synthetic cancel"):
        app._download_with_audio_url_refresh(
            object(),
            {},
            info,
            (),
            guard,
            refresh=refresh,
            control_check=control,
            emit_log=lambda _: None,
        )
    assert len(calls) == 1
    assert len(refreshes) == (phase == "after_refresh")


def test_changed_or_outside_video_is_not_reused(tmp_path):
    _, fresh, path, guard = prepared(tmp_path)
    finished(guard, path)
    path.write_bytes(b"changed")
    with pytest.raises(TransferRefreshError, match="changed"):
        guard.checked_refresh(fresh)
    outside = tmp_path.parent / "outside-synthetic.mp4"
    outside.write_bytes(b"outside")
    other = SplitTransferRefresh(metadata(), "v", "a", tmp_path)
    finished(other, outside)
    assert other.completed_video is None


def test_response_url_error_chain_supported(tmp_path):
    info, _, path, guard = prepared(tmp_path)
    finished(guard, path)
    error = RuntimeError("wrapped")
    error.response = SimpleNamespace(url=info["formats"][1]["url"])
    assert guard.eligible(403, [error])


@pytest.mark.parametrize("restriction", ["private", "premium_only", "drm"])
def test_original_restriction_is_not_refresh_eligible(tmp_path, restriction):
    info, _, path, _ = prepared(tmp_path)
    if restriction == "drm":
        info["formats"][1]["has_drm"] = True
    else:
        info["availability"] = restriction
    guard = SplitTransferRefresh(info, "v", "a", tmp_path)
    finished(guard, path)
    error = HTTPError(info["formats"][1]["url"], 403, "Forbidden", None, None)
    assert not guard.eligible(403, [error])


@pytest.mark.parametrize(
    "error",
    [
        TimeoutError("bounded refresh timeout"),
        HTTPError(
            "https://example.invalid/source", 401, "Authentication required", None, None
        ),
    ],
)
def test_failed_refresh_does_not_start_another_transfer(tmp_path, monkeypatch, error):
    info, _, path, guard = prepared(tmp_path)
    finished(guard, path)
    calls, refreshes = [], []

    def transfer(*args, **kwargs):
        calls.append(True)
        raise HTTPError(info["formats"][1]["url"], 403, "Forbidden", None, None)

    def refresh():
        refreshes.append(True)
        raise error

    monkeypatch.setattr(app, "_download_preflight_result_step", transfer)
    with pytest.raises(type(error)):
        app._download_with_audio_url_refresh(
            object(),
            {},
            info,
            (),
            guard,
            refresh=refresh,
            control_check=lambda: None,
            emit_log=lambda _: None,
        )
    assert len(calls) == len(refreshes) == 1
    assert path.read_bytes() == b"completed original video"


def test_original_selected_characteristics_are_snapshotted(tmp_path):
    info, fresh, path, guard = prepared(tmp_path)
    finished(guard, path)
    info["formats"][1]["abr"] = 32
    assert guard.checked_refresh(fresh) is fresh


def test_no_guard_does_not_refresh_any403(tmp_path, monkeypatch):
    info = metadata()

    def transfer(*args, **kwargs):
        raise HTTPError(info["formats"][1]["url"], 403, "Forbidden", None, None)

    monkeypatch.setattr(app, "_download_preflight_result_step", transfer)
    with pytest.raises(HTTPError):
        app._download_with_audio_url_refresh(
            object(),
            {},
            info,
            (),
            None,
            refresh=lambda: pytest.fail("unexpected refresh"),
            control_check=lambda: None,
            emit_log=lambda _: None,
        )


def test_worker_refresh_keeps_same_session_and_bounded_analysis(tmp_path, monkeypatch):
    from tests.worker_fixtures import (
        _worker_test_app,
        _worker_test_export_plan,
        _worker_test_job,
    )

    worker = _worker_test_app()
    job = _worker_test_job(tmp_path, url="https://www.youtube.com/watch?v=abcdefghijk")
    job.use_cookies = True
    job.cookie_browser = "firefox"
    worker._find_ffmpeg = lambda: "synthetic-ffmpeg"
    worker._find_deno = lambda: None
    worker._build_ydl_options = lambda *args, **kwargs: {
        "format": "137+140/best",
        "progress_hooks": [],
    }
    monkeypatch.setattr(app, "log_options", lambda *args: None)
    monkeypatch.setattr(app, "write_diagnostic", lambda *args: None)
    info, fresh, path, _ = prepared(tmp_path)
    for value in (info, fresh):
        value["formats"][0]["format_id"] = "137"
        value["formats"][1]["format_id"] = "140"
    analyzed = app._AnalyzedDownloadItem(
        info, info, _worker_test_export_plan(), ("same-cookie",), True
    )
    item = app._DownloadItemContext(info, 1, 1, job.url, "Synthetic item")
    calls, analyses, boundaries = [], [], []

    def transfer(module, options, current, cookies, *, control_check):
        calls.append(True)
        if len(calls) == 1:
            for hook in options["progress_hooks"]:
                hook(
                    {
                        "status": "finished",
                        "filename": str(path),
                        "info_dict": {"format_id": "137"},
                    }
                )
            raise HTTPError(info["formats"][1]["url"], 403, "Forbidden", None, None)
        return fresh, cookies

    def analyze(module, options, cookies, url, label, **kwargs):
        analyses.append(True)
        assert cookies == ("same-cookie",) and url == job.url
        assert "cookiefile" not in options and "cookiesfrombrowser" not in options
        return fresh, cookies

    def boundary(step, cancel_requested, **kwargs):
        boundaries.append(kwargs)
        assert cancel_requested() is False
        return step()

    monkeypatch.setattr(app, "_download_preflight_result_step", transfer)
    monkeypatch.setattr(app, "_analyze_source_formats_step", analyze)
    monkeypatch.setattr(app, "run_cancellable_blocking_step", boundary)
    result = worker._download_item_to_staging(
        job,
        object(),
        app.ProviderNetworkCoordinator(),
        item,
        {},
        analyzed,
        tmp_path,
        control_check=lambda: None,
        progress_callback=lambda _: None,
    )
    assert result.session_cookies == ("same-cookie",)
    assert len(calls) == 2 and len(analyses) == 1 and len(boundaries) == 1
    assert boundaries[0]["timeout_seconds"] == app.ANALYSIS_TIMEOUT_SECONDS


# --- One fresh link after any rejected transfer (MP3, original audio, first stream)


def _forbidden(url):
    return HTTPError(url, 403, "Forbidden", None, None)


def _restart_run(monkeypatch, info, selector, fresh, failures, **kw):
    """Run the transfer step; `failures` are raised in order, then it succeeds."""
    restart = TransferRestartRefresh(info, selector)
    pending = list(failures)
    calls, refreshes, logs = [], [], []

    def transfer(module, options, current, cookies, *, control_check):
        calls.append((dict(options), current))
        if pending:
            raise pending.pop(0)
        return {"id": current["id"]}, ("cookie",)

    monkeypatch.setattr(app, "_download_preflight_result_step", transfer)

    def refresh():
        refreshes.append(True)
        return fresh, ("fresh-cookie",)

    def run():
        return app._download_with_audio_url_refresh(
            object(),
            {"format": selector},
            info,
            (),
            kw.get("guard"),
            refresh=refresh,
            control_check=kw.get("control_check", lambda: None),
            emit_log=logs.append,
            restart=restart,
            prepare_refreshed=kw.get("prepare_refreshed"),
        )

    return run, calls, refreshes, logs


@pytest.mark.parametrize(
    ("selector", "rejected"),
    [("a", 1), ("v+a", 0), ("v+a", 1)],
    ids=["audio only", "first stream of a split", "audio of a split"],
)
def test_any_rejected_transfer_gets_one_fresh_link(monkeypatch, selector, rejected):
    info = metadata()
    fresh = deepcopy(info)
    for item in fresh["formats"]:
        item["url"] += "-fresh"
    old_url = info["formats"][rejected]["url"]
    run, calls, refreshes, logs = _restart_run(
        monkeypatch, info, selector, fresh, [_forbidden(old_url)]
    )
    result, cookies = run()
    assert result == {"id": "synthetic"} and cookies == ("cookie",)
    assert len(calls) == 2 and len(refreshes) == 1
    # Same formats, fresh metadata; the selector is never widened.
    assert calls[1][0]["format"] == selector and calls[1][1] is fresh
    assert any("HTTP 403" in line for line in logs)
    assert not any("example.invalid" in line for line in logs)


def test_second_rejection_stops_with_a_wait_message(monkeypatch):
    info = metadata()
    fresh = deepcopy(info)
    fresh["formats"][1]["url"] = "https://example.invalid/audio-fresh"
    run, calls, refreshes, _ = _restart_run(
        monkeypatch,
        info,
        "a",
        fresh,
        [
            _forbidden(info["formats"][1]["url"]),
            _forbidden(fresh["formats"][1]["url"]),
        ],
    )
    with pytest.raises(TransferRefreshError, match="rejected the transfer again"):
        run()
    assert len(calls) == 2 and len(refreshes) == 1


@pytest.mark.parametrize(
    "failure",
    [
        HTTPError("https://example.invalid/audio-old", 404, "Gone", None, None),
        HTTPError("https://example.invalid/thumbnail", 403, "Forbidden", None, None),
        RuntimeError("postprocessing failed"),
    ],
    ids=["other status", "403 from another request", "not a network error"],
)
def test_unrelated_failures_are_not_retried(monkeypatch, failure):
    info = metadata()
    run, calls, refreshes, _ = _restart_run(monkeypatch, info, "a", info, [failure])
    with pytest.raises(type(failure)):
        run()
    assert len(calls) == 1 and not refreshes


@pytest.mark.parametrize(
    "change",
    [
        lambda info: info.update(availability="needs_auth"),
        lambda info: info["formats"][1].update(has_drm=True),
        lambda info: info.pop("id"),
    ],
    ids=["restricted", "drm", "no identity"],
)
def test_restricted_or_unidentified_sources_are_not_retried(monkeypatch, change):
    info = metadata()
    change(info)
    run, calls, refreshes, _ = _restart_run(
        monkeypatch, info, "a", info, [_forbidden(info["formats"][1]["url"])]
    )
    with pytest.raises(HTTPError):
        run()
    assert len(calls) == 1 and not refreshes


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda f: f.update(id="other"), "identity changed"),
        (lambda f: f.update(availability="private"), "restricted"),
        (lambda f: f.update(duration=3), "duration changed"),
        (lambda f: f["formats"][1].update(abr=32), "formats changed"),
        (lambda f: f["formats"].pop(1), "formats changed"),
        (lambda f: None, "same rejected link"),
    ],
    ids=["identity", "access", "duration", "quality", "missing", "same link"],
)
def test_fresh_link_must_be_the_same_source_and_quality(monkeypatch, change, message):
    info = metadata()
    fresh = deepcopy(info)
    if message != "same rejected link":
        fresh["formats"][1]["url"] = "https://example.invalid/audio-fresh"
    change(fresh)
    run, calls, refreshes, _ = _restart_run(
        monkeypatch, info, "a", fresh, [_forbidden(info["formats"][1]["url"])]
    )
    with pytest.raises(TransferRefreshError, match=message):
        run()
    assert len(calls) == 1 and len(refreshes) == 1


def test_cancel_after_rejection_starts_nothing_more(monkeypatch):
    info = metadata()
    state = {"rejected": False}

    def control_check():
        if state["rejected"]:
            raise RuntimeError("cancelled by user")

    run, calls, refreshes, _ = _restart_run(
        monkeypatch,
        info,
        "a",
        info,
        [_forbidden(info["formats"][1]["url"])],
        control_check=control_check,
    )
    original = app._download_preflight_result_step

    def transfer(*args, **kwargs):
        try:
            return original(*args, **kwargs)
        finally:
            state["rejected"] = True

    monkeypatch.setattr(app, "_download_preflight_result_step", transfer)
    with pytest.raises(RuntimeError, match="cancelled"):
        run()
    assert len(calls) == 1 and not refreshes


def test_split_recovery_still_takes_priority_and_keeps_the_video(tmp_path, monkeypatch):
    info, fresh, path, guard = prepared(tmp_path)
    finished(guard, path)
    run, calls, refreshes, logs = _restart_run(
        monkeypatch,
        info,
        "v+a",
        fresh,
        [_forbidden(info["formats"][1]["url"])],
        guard=guard,
    )
    run()
    assert len(calls) == 2 and len(refreshes) == 1
    assert any("without redownloading completed video" in line for line in logs)
    assert path.read_bytes() == b"completed original video"


def test_caption_choice_is_reapplied_to_the_fresh_link(monkeypatch):
    info = metadata()
    fresh = deepcopy(info)
    fresh["formats"][1]["url"] = "https://example.invalid/audio-fresh"
    prepared_info = {**fresh, "prepared": True}
    run, calls, _, _ = _restart_run(
        monkeypatch,
        info,
        "a",
        fresh,
        [_forbidden(info["formats"][1]["url"])],
        prepare_refreshed=lambda value: prepared_info,
    )
    run()
    assert calls[1][1] is prepared_info


def test_fragmented_formats_match_by_fragment_base():
    info = metadata()
    info["formats"][1].update(
        url="https://example.invalid/manifest.mpd",
        fragment_base_url="https://example.invalid/frag/",
    )
    restart = TransferRestartRefresh(info, "a")
    assert restart.eligible(403, [_forbidden("https://example.invalid/frag/sq/7")])
    assert not restart.eligible(403, [_forbidden("https://example.invalid/other/7")])


def test_worker_gives_an_mp3_download_one_fresh_link(tmp_path, monkeypatch):
    """The reported case: an MP3 run rejected with 403 used to fail outright."""
    from dataclasses import replace

    from tests.worker_fixtures import _worker_test_app, _worker_test_job
    from yt_downloader.export_planning import build_mp3_export_plan
    from yt_downloader.models import OutputType

    worker = _worker_test_app()
    job = replace(
        _worker_test_job(tmp_path, url="https://www.youtube.com/watch?v=abcdefghijk"),
        output_type=OutputType.MP3,
    )
    worker._find_ffmpeg = lambda: "synthetic-ffmpeg"
    worker._find_deno = lambda: None
    worker._build_ydl_options = lambda *args, **kwargs: {
        "format": kwargs["format_selector"],
        "progress_hooks": [],
    }
    monkeypatch.setattr(app, "log_options", lambda *args: None)
    monkeypatch.setattr(app, "write_diagnostic", lambda *args: None)
    info = metadata()
    info["formats"] = [info["formats"][1]]
    fresh = deepcopy(info)
    fresh["formats"][0]["url"] = "https://example.invalid/audio-fresh"
    plan = build_mp3_export_plan(info, job.mp3_settings)
    assert plan.format_selector == "a"
    analyzed = app._AnalyzedDownloadItem(info, info, plan, (), False)
    item = app._DownloadItemContext(info, 1, 1, job.url, "Synthetic item")
    calls, analyses = [], []

    def transfer(module, options, current, cookies, *, control_check):
        calls.append((options["format"], current["formats"][0]["url"]))
        if len(calls) == 1:
            raise HTTPError(current["formats"][0]["url"], 403, "Forbidden", None, None)
        (tmp_path / "synthetic.mp3").write_bytes(b"offline placeholder")
        return current, cookies

    def analyze(module, options, cookies, url, label, **kwargs):
        analyses.append(url)
        return fresh, cookies

    monkeypatch.setattr(app, "_download_preflight_result_step", transfer)
    monkeypatch.setattr(app, "_analyze_source_formats_step", analyze)
    monkeypatch.setattr(
        app, "run_cancellable_blocking_step", lambda step, cancelled, **kw: step()
    )
    worker._download_item_to_staging(
        job,
        object(),
        app.ProviderNetworkCoordinator(),
        item,
        {},
        analyzed,
        tmp_path,
        control_check=lambda: None,
        progress_callback=lambda _: None,
    )
    assert calls == [
        ("a", "https://example.invalid/audio-old"),
        ("a", "https://example.invalid/audio-fresh"),
    ]
    assert analyses == [job.url]
    lines = [p["line"] for kind, p in worker.events.queue if kind == "job_log"]
    assert any("requesting a fresh link once" in line for line in lines)
    assert not any("example.invalid" in line for line in lines)
