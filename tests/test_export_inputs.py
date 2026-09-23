"""The Tk and Qt entrypoints must submit the same validated export choices."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from yt_downloader.app import DownloaderApp
from yt_downloader.export_inputs import manual_export_settings, mp3_export_settings
from yt_downloader.models import ExportMode, OutputType
from yt_downloader.qt_quick.runtime import DownloadRuntime


class _Value:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value


@pytest.mark.parametrize("rate_control", ["CBR", "Quality"])
def test_manual_choices_match_tk_adapter_and_qt_job(tmp_path: Path, rate_control: str):
    values = {
        "manual_rate_control": rate_control,
        "manual_video_bitrate": "7000",
        "manual_audio_bitrate": "192",
        "manual_audio_codec": "MP3",
        "manual_sample_rate": "44100",
        "manual_channels": "Mono",
        "manual_preset": "slow",
        "manual_crf": "19",
    }
    app = DownloaderApp.__new__(DownloaderApp)
    for key, value in values.items():
        setattr(app, f"{key}_var", _Value(value))
    expected = app._manual_export_settings()
    assert manual_export_settings(values) == expected

    runtime = _idle_runtime()
    job = runtime.start(
        "https://example.com/watch?v=abc123",
        tmp_path,
        OutputType.MP4.value,
        ExportMode.MANUAL_OVERRIDE.value,
        manual_settings=expected,
    )
    assert job.manual_settings == expected
    assert job.manual_settings.video_crf == (19 if rate_control == "Quality" else None)


def test_invalid_manual_value_blocks_both_entrypoints():
    values = {"manual_audio_bitrate": "garbage"}
    with pytest.raises(ValueError, match="whole number"):
        manual_export_settings(values)
    with pytest.raises(ValueError, match="encoder-supported"):
        manual_export_settings(
            {"manual_audio_codec": "MP3", "manual_audio_bitrate": "133"}
        )


def test_mp3_choices_match_tk_adapter_and_qt_job(tmp_path: Path):
    values = {
        "mp3_quality": "High — 256 kbps CBR",
        "mp3_sample_rate": "44.1 kHz — music",
        "mp3_channels": "Mono",
        "mp3_cover_art_mode": "No Art",
        "mp3_embed_metadata": False,
    }
    app = DownloaderApp.__new__(DownloaderApp)
    for key, value in values.items():
        setattr(app, f"{key}_var", _Value(value))
    app.mp3_custom_cover_art_path = None
    expected = app._mp3_export_settings()
    assert mp3_export_settings(values) == expected

    runtime = _idle_runtime()
    job = runtime.start(
        "https://example.com/watch?v=abc123",
        tmp_path,
        OutputType.MP3.value,
        ExportMode.EVERYDAY.value,
        mp3_settings=expected,
    )
    assert job.mp3_settings == expected
    with pytest.raises(ValueError, match="custom cover image"):
        mp3_export_settings({"mp3_cover_art_mode": "Custom art"})


def _idle_runtime() -> DownloadRuntime:
    runtime = DownloadRuntime.__new__(DownloadRuntime)
    runtime._closing = False
    runtime.recovery_notice = None
    runtime.active_job = None
    runtime.worker = None
    runtime.queued = []
    runtime.recovery = SimpleNamespace()
    runtime._launch = lambda job: None
    return runtime
