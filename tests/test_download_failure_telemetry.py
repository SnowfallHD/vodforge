import json
from dataclasses import replace
from pathlib import Path
from urllib.error import HTTPError

import pytest

from tests.test_metadata_helpers import _worker_test_app, _worker_test_job
from tests.test_product_telemetry import _permitted_installation
from yt_downloader import download_service as download
from yt_downloader.export_planning import build_mp3_export_plan
from yt_downloader.failure_diagnostics import (
    DownloadArtifactError,
    capture_failure,
    validate_failure_detail,
)
from yt_downloader.models import OutputType
from yt_downloader.product_telemetry import ProductTelemetryOwner, _load_outbox


@pytest.mark.usefixtures("production_telemetry_contract")
@pytest.mark.parametrize("consent", [True, False])
def test_mp3_playlist_reports_observed_transfer_boundaries_without_private_data(
    tmp_path, monkeypatch, consent
):
    # Substitute the provider and native probe, while retaining the real
    # item loop, staged output checks, commit and telemetry persistence.
    app = _worker_test_app()
    app._find_ffmpeg = lambda: "ffmpeg"
    app._find_ffprobe = lambda: "ffprobe"
    app._find_deno = lambda: None
    monkeypatch.setattr(download, "load_yt_dlp", lambda: object())
    monkeypatch.setattr(download, "write_diagnostic", lambda _message: None)
    monkeypatch.setattr(download, "BATCH_FAILURE_REPORT_PATH", tmp_path / "failures.txt")
    monkeypatch.setattr(
        download, "save_cached_thumbnail_image", lambda *_a, **_kw: None
    )
    monkeypatch.setattr(
        download,
        "validate_output_artifact",
        lambda *_a, **_kw: {
            "format": {"format_name": "mp3", "duration": "1.0"},
            "streams": [{"codec_type": "audio", "codec_name": "mp3"}],
        },
    )

    job = replace(_worker_test_job(tmp_path), output_type=OutputType.MP3)
    entries = [
        {
            "id": f"PRIVATE_ID_{index}",
            "title": f"PRIVATE_TITLE_{index}",
            "webpage_url": f"https://www.youtube.com/watch?v=PRIVATE_ID_{index}",
            "formats": [{"format_id": "140", "acodec": "aac", "vcodec": "none"}],
        }
        for index in range(4)
    ]
    app._expand_download_source = lambda *_a, **_kw: download._ExpandedDownloadSource(
        {"id": "PRIVATE_PLAYLIST", "title": "PRIVATE_PLAYLIST"}, entries
    )
    app._analyze_download_item = lambda _job, _ydl, _network, item, *_a, **_kw: (
        download._AnalyzedDownloadItem(
            preflight_info=item.entry,
            display_info=item.entry,
            plan=build_mp3_export_plan(item.entry, job.mp3_settings),
            session_cookies=(),
            cookie_source_loaded=False,
        )
    )

    attempted = []

    def transfer(_ydl, options, info, _cookies, **_kwargs):
        attempted.append(info["id"])
        staging = Path(options["paths"]["home"])
        if info["id"] == entries[0]["id"]:
            return None, ()
        if info["id"] == entries[1]["id"]:
            # A nonempty intermediate is not the promised MP3.
            (staging / "PRIVATE_INTERMEDIATE.webm").write_bytes(b"partial")
        elif info["id"] == entries[2]["id"]:
            raise RuntimeError("PRIVATE_WRAPPER") from HTTPError(
                "https://private.invalid/a?access_token=PRIVATE_TOKEN",
                403,
                "PRIVATE_MESSAGE",
                None,
                None,
            )
        else:
            (staging / "fixture.mp3").write_bytes(b"offline placeholder")
        return dict(info), ()

    monkeypatch.setattr(download, "_download_preflight_result_step", transfer)
    installation = tmp_path / "installation.json"
    state = tmp_path / "event-outbox.json"
    if consent:
        _permitted_installation(installation)

    def owner(recorder):
        return ProductTelemetryOwner(
            state_path=state,
            installation_state_path=installation,
            app_version="0.2.9",
            platform_name="darwin",
            d1_recorder=recorder,
            posthog_recorder=lambda _event: False,
        )

    delivery_attempts = []

    def offline(event):
        delivery_attempts.append(event.event_id)
        return False

    app.product_telemetry = telemetry = owner(offline)

    outcome = app._download_worker_single(job)
    assert telemetry.shutdown(2)
    assert attempted == [entry["id"] for entry in entries]
    assert outcome.success_count == 1 and outcome.failure_count == 3
    terminals = [
        kind for kind, _ in app.events.queue if kind in {"done", "partial", "error"}
    ]
    assert terminals == ["partial"]
    [committed] = list(tmp_path.rglob("*.mp3"))
    assert committed.read_bytes() == b"offline placeholder"
    assert not list(tmp_path.rglob("*.webm"))

    events = [event.public_payload() for event in _load_outbox(state)]
    if not consent:
        assert not events
        assert not delivery_attempts
        return

    failures = [
        event
        for event in events
        if event.get("feature") == "download_operation"
        and event.get("action") == "failed"
    ]
    assert len(failures) == 3
    assert len({event["dimensions"]["operation_id"] for event in failures}) == 3
    started = {
        event["dimensions"]["operation_id"]
        for event in events
        if event.get("feature") == "download_operation"
        and event.get("action") == "started"
    }
    assert all(event["dimensions"]["operation_id"] in started for event in failures)
    assert len({event["attempt_id"] for event in failures}) == 1

    details = [validate_failure_detail(event["failure_detail"]) for event in failures]
    assert [detail.failure_code for detail in details] == [
        "download_metadata_missing",
        "staged_output_missing",
        "http_forbidden",
    ]
    assert [detail.reason for detail in details] == [
        "unknown",
        "validation",
        "provider_extraction",
    ]
    assert [detail.stage for detail in details] == ["download"] * 3
    assert [detail.source_module for detail in details] == ["download_service"] * 3
    assert all(
        detail.source_trace.startswith("download_service:") for detail in details
    )
    assert details[0].source_line != details[1].source_line
    assert details[2].http_status == 403
    assert details[2].error_chain == "RuntimeError>HTTPError"
    assert sum(event["event_name"] == "media_exported" for event in events) == 1

    serialized = json.dumps(events)
    for private in ("PRIVATE_", "https://", str(tmp_path), "access_token", job.run_id):
        assert private not in serialized

    delivered = []

    def acknowledge(event):
        delivered.append(event.public_payload())
        return True

    restarted = owner(acknowledge)
    restarted.flush_async()
    assert restarted.shutdown(2)
    assert delivered == events
    assert not _load_outbox(state)


@pytest.mark.parametrize("inspect_text", [True, False])
def test_missing_metadata_is_a_typed_observation_not_a_guessed_reason(inspect_text):
    error = DownloadArtifactError(
        "PRIVATE title, login required, /PRIVATE/path",
        code="download_metadata_missing",
    )
    detail = capture_failure(error, stage="download", inspect_text=inspect_text)
    assert detail.payload() == {
        "failure_code": "download_metadata_missing",
        "reason": "unknown",
        "stage": "download",
        "error_type": "RuntimeError",
    }


@pytest.mark.parametrize(
    "injection",
    [
        {"failure_code": "https://private.invalid/"},
        {"source_trace": "download_service:42>private/path:7"},
        {"stderr": "private FFmpeg command argument"},
    ],
)
def test_new_diagnostics_do_not_accept_private_detail(injection):
    with pytest.raises(ValueError):
        validate_failure_detail(
            {
                "failure_code": "staged_output_missing",
                "source_module": "download_service",
                "source_line": 42,
                "source_scope": "first_party_frame",
                "source_trace": "download_service:42",
                **injection,
            }
        )
