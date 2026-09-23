"""The Tk and Qt entrypoints must submit the same validated export choices."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from yt_downloader.app import DownloaderApp
from yt_downloader.cookie_inputs import windows_chromium_cookie_warning
from yt_downloader.export_inputs import manual_export_settings, mp3_export_settings
from yt_downloader.models import CookieSource, ExportMode, OutputType
from yt_downloader.qt_quick.runtime import DownloadRuntime
from yt_downloader.url_list_inputs import parse_url_list_text, read_url_list_file


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


def test_url_list_parser_and_qt_batch_job_use_the_same_source_order(tmp_path: Path):
    lines = "# skip\nhttps://example.com/one title\n<https://example.com/two|Label>\n"
    path = tmp_path / "sources.txt"
    path.write_text(lines, encoding="utf-8")
    urls = parse_url_list_text(lines)
    assert (
        read_url_list_file(path)
        == urls
        == [
            "https://example.com/one",
            "https://example.com/two",
        ]
    )
    runtime = _idle_runtime()
    job = runtime.start(
        "",
        tmp_path,
        OutputType.MP4.value,
        ExportMode.EVERYDAY.value,
        urls=urls,
        batch_mode=True,
    )
    assert job.url == urls[0]
    assert job.urls == urls
    assert job.batch_mode is True


def test_qt_cookie_access_uses_only_the_explicit_session_choice(tmp_path: Path):
    cookie_file = tmp_path / "cookies.txt"
    cookie_file.write_text("private")
    runtime = _idle_runtime()
    base = ("https://example.com/watch?v=abc123", tmp_path, "MP4", "Everyday")

    public = runtime.start(
        *base,
        cookie_source=CookieSource.PUBLIC,
        cookie_file=cookie_file,
        cookie_browser="Firefox",
    )
    assert (public.use_cookies, public.cookie_file, public.cookie_browser) == (
        False,
        None,
        None,
    )
    browser = runtime.start(
        *base,
        cookie_source=CookieSource.BROWSER,
        cookie_file=cookie_file,
        cookie_browser="Firefox",
    )
    assert (browser.use_cookies, browser.cookie_file, browser.cookie_browser) == (
        True,
        None,
        "firefox",
    )
    file = runtime.start(
        *base,
        cookie_source=CookieSource.FILE,
        cookie_file=cookie_file,
        cookie_browser="Firefox",
    )
    assert (file.use_cookies, file.cookie_file, file.cookie_browser) == (
        True,
        cookie_file,
        None,
    )
    with pytest.raises(ValueError, match="existing YouTube cookies"):
        runtime.start(*base, cookie_source=CookieSource.FILE)
    with pytest.raises(ValueError, match="browser profile"):
        runtime.start(*base, cookie_source=CookieSource.BROWSER, cookie_browser="bad")
    assert windows_chromium_cookie_warning("Chrome", platform="win32")
    assert windows_chromium_cookie_warning("Firefox", platform="win32") is None


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
