import json
from types import SimpleNamespace
from uuid import uuid4

import pytest

from yt_downloader.app import DownloadWorkerCore, _build_download_item_plan
from yt_downloader.export_planning import build_auto_export_plan
from yt_downloader.failure_diagnostics import SourceSelectionError, capture_failure
from yt_downloader.models import ExportMode, ManualExportSettings, OutputType
from yt_downloader.source_selection import selection_observation
from yt_downloader.telemetry_features import export_dimensions, validate_dimensions


def video(ident="video", *, height=1080, audio=False, **values):
    return dict(
        format_id=ident,
        height=height,
        width=1920,
        vcodec="avc1",
        acodec="aac" if audio else "none",
        ext="mp4",
        vbr=4000,
        abr=128 if audio else 0,
        fps=30,
        **values,
    )


def audio():
    return {
        "format_id": "audio",
        "vcodec": "none",
        "acodec": "opus",
        "ext": "webm",
        "abr": 160,
        "asr": 48000,
    }


def plan(formats, **kwargs):
    return build_auto_export_plan(
        {"formats": formats}, mode=ExportMode.EVERYDAY, **kwargs
    )


@pytest.mark.parametrize(
    "mode",
    [
        ExportMode.EVERYDAY,
        ExportMode.AUTO_CBR,
        ExportMode.STRICT_COMPLIANCE,
        ExportMode.MANUAL_OVERRIDE,
    ],
)
def test_same_tier_combined_fallback_preserves_format_and_mode(mode):
    result = build_auto_export_plan(
        {"formats": [video(), video("combined", audio=True)]}, mode=mode
    )
    assert (
        result.format_selector
        == result.video_format_id
        == result.audio_format_id
        == "combined"
    )
    assert result.mode == mode and result.source_quality_tier == 1080
    assert result.selection_dimensions["selection_decision"] == "progressive_fallback"
    assert result.selection_dimensions["selection_has_audio"] == "yes"


def test_available_audio_only_keeps_original_split_selection():
    result = plan([video(), video("combined", audio=True), audio()])
    assert result.format_selector == "video+audio"
    assert result.selection_dimensions["selection_decision"] == "split"
    assert result.selection_dimensions["selection_audio_only_count"] == "1"


def test_progressive_only_remains_direct():
    assert (
        plan([video("combined", audio=True)]).selection_dimensions["selection_decision"]
        == "progressive"
    )


@pytest.mark.parametrize("height", [720, 1440])
def test_fallback_never_changes_selected_tier_or_exceeds_ceiling(height):
    with pytest.raises(SourceSelectionError) as caught:
        plan(
            [video(), video("different-tier", height=height, audio=True)],
            max_height=1080,
        )
    assert caught.value.selection_dimensions["selection_decision"] == "no_audio"
    assert caught.value.selection_dimensions["selection_same_tier_av_count"] == "0"


@pytest.mark.parametrize(
    "change", [{"dynamic_range": "HDR"}, {"fps": 144}, {"vbr": 0, "tbr": 0}, {"abr": 0}]
)
def test_fallback_requires_usable_sdr_bitrate_audio_and_frame_rate(change):
    combined = video("combined", audio=True)
    combined.update(change)
    with pytest.raises(SourceSelectionError) as caught:
        plan([video(), combined])
    assert caught.value.selection_dimensions["selection_same_tier_av_count"] == "1"
    assert caught.value.selection_dimensions["selection_usable_av_count"] == "0"


def test_fallback_retains_preferred_original_language():
    dubbed = video("dubbed", audio=True, language_preference=-10)
    original = video("original", audio=True, language_preference=10)
    assert plan([video(), dubbed, original]).format_selector == "original"


def test_codec_ranking_and_encoder_preferences_survive_fallback():
    avc = video("avc", audio=True)
    vp9 = video("vp9", audio=True)
    vp9.update(vcodec="vp9", vbr=3000)
    result = plan([video(), vp9, avc], use_nvenc=True)
    assert result.format_selector == "avc" and result.video_codec == "avc1"


def job():
    return SimpleNamespace(
        output_type=OutputType.MP4,
        export_mode=ExportMode.EVERYDAY,
        use_nvenc=False,
        url="https://youtube.com/watch?v=private",
        run_id=uuid4().hex,
        retry_of_run_id=None,
        failure_stage="analysis",
        telemetry_operation_id=str(uuid4()),
    )


def test_manual_settings_and_selection_facts_survive_real_item_planning():
    current = job()
    current.export_mode = ExportMode.MANUAL_OVERRIDE
    current.manual_settings = ManualExportSettings(
        video_bitrate_kbps=4000,
        audio_bitrate_kbps=128,
        audio_sample_rate="44100",
        audio_channels="1",
        x264_preset="fast",
    )
    result = _build_download_item_plan(
        current, {"formats": [video(), video("combined", audio=True)]}, max_height=1080
    )
    assert result.video_bitrate_kbps == 4000 and result.audio_bitrate_kbps == 128
    assert (
        result.audio_sample_rate == "44100"
        and result.audio_channels == "1"
        and result.x264_preset == "fast"
    )
    assert current.selection_dimensions == result.selection_dimensions


def test_failure_fields_distinguish_missing_audio_from_missing_video_and_drop_private_values():
    for formats, decision in (([video()], "no_audio"), ([audio()], "no_video")):
        current = job()
        with pytest.raises(SourceSelectionError):
            _build_download_item_plan(
                current,
                {"formats": formats, "title": "private", "url": "https://private"},
                max_height=1080,
            )
        fields = export_dimensions(current)
        assert fields["selection_decision"] == decision
        assert fields["selection_scope"] == "last_analyzed_item"
        validate_dimensions(fields)
        assert "private" not in json.dumps(fields)
        for bad in (
            {**current.selection_dimensions, "url": "https://private"},
            {**current.selection_dimensions, "selection_decision": []},
            {**current.selection_dimensions, "selection_video_tier": "9" * 10000},
        ):
            assert selection_observation(bad, scope="item") == {}


def test_item_boundary_clears_stale_selection_before_unrelated_failure(monkeypatch):
    current = job()
    _build_download_item_plan(current, {"formats": [video(), audio()]}, max_height=1080)
    monkeypatch.setattr(
        "yt_downloader.app.build_auto_export_plan",
        lambda *_a, **_k: (_ for _ in ()).throw(
            RuntimeError("unrelated provider failure")
        ),
    )
    with pytest.raises(RuntimeError):
        _build_download_item_plan(current, {"formats": []}, max_height=1080)
    assert current.selection_dimensions == {}


def test_selection_counters_are_bounded_and_never_serialize_provider_content():
    with pytest.raises(SourceSelectionError) as caught:
        plan([audio() for _ in range(10001)])
    assert caught.value.selection_dimensions["selection_audio_only_count"] == "10000"
    combined = video("private-format-id", audio=True)
    combined.update(
        url="https://private.invalid/token",
        headers={"Cookie": "private-cookie"},
        filepath="/private/output",
    )
    current = job()
    _build_download_item_plan(
        current,
        {"title": "private-title", "formats": [video(), combined]},
        max_height=1080,
    )
    assert "private" not in json.dumps(export_dimensions(current))


@pytest.mark.usefixtures("production_telemetry_contract")
@pytest.mark.parametrize("permitted", [False, True])
def test_actual_producer_consent_and_bounded_selection_payloads(
    tmp_path, permitted, monkeypatch
):
    from yt_downloader.analytics_consent import AnalyticsConsentOwner
    from yt_downloader.cloud_funnel import (
        load_or_create_installation_state,
        mark_attribution_claim_confirmed,
    )
    from yt_downloader.product_telemetry import ProductTelemetryOwner
    from yt_downloader.qt_quick.runtime import DownloadRuntime
    from yt_downloader.telemetry_credentials import TelemetryCredentialOwner

    monkeypatch.setattr(
        "yt_downloader.telemetry_credentials.telemetry_collection_allowed", lambda: True
    )

    installation = tmp_path / "installation.json"
    state = load_or_create_installation_state(installation)
    AnalyticsConsentOwner(tmp_path).choose(permitted)
    mark_attribution_claim_confirmed(installation, state.install_id)
    observed = []
    wire = []
    credential = SimpleNamespace(
        first_launch=lambda *_a: True,
        _credential=lambda: "synthetic-local-credential",
        _post=lambda _action, body, _key: (
            wire.extend(body["events"]) or {"accepted": 1}
        ),
    )

    def local_delivery(event):
        payload = event.public_payload()
        observed.append(payload)
        return TelemetryCredentialOwner.event(credential, payload)

    owner = ProductTelemetryOwner(
        state_path=tmp_path / "events.json",
        installation_state_path=installation,
        app_version="0.2.4",
        d1_recorder=local_delivery,
        heycatch_recorder=lambda *_a, **_k: True,
    )
    worker = SimpleNamespace(product_telemetry=owner)
    for formats, terminal in (
        ([video(), video("combined", audio=True)], "run_completed"),
        ([video()], "run_failed"),
    ):
        current = job()
        diagnostic = None
        try:
            _build_download_item_plan(current, {"formats": formats}, max_height=1080)
        except SourceSelectionError as exc:
            diagnostic = capture_failure(exc, stage="analysis")
        DownloadWorkerCore._observe_download_operation(
            worker,
            current,
            "failed" if diagnostic else "completed",
            stage="analysis" if diagnostic else "commit",
            failure_detail=diagnostic,
        )
        current.failure_diagnostic = diagnostic
        DownloadRuntime._observe_run(
            worker, terminal, current, status="Failed" if diagnostic else "Completed"
        )
    assert owner.shutdown(2)
    assert len(observed) == (4 if permitted else 0)
    assert len(wire) == len(observed)
    assert all("install_id" not in event for event in wire)
    if permitted:
        for event in observed:
            assert event["dimensions"]["selection_decision"] in {
                "progressive_fallback",
                "no_audio",
            }
            assert "private" not in json.dumps(event)
        # Deliberately local producer fixture for actual Worker/D1 tests.
        import os
        from pathlib import Path

        if output := os.environ.get("VODFORGE_SELECTION_FIXTURE"):
            Path(output).write_text(json.dumps(observed, indent=2) + "\n")
            Path(output).with_name("source-selection-wire.json").write_text(
                json.dumps(wire, indent=2) + "\n"
            )
