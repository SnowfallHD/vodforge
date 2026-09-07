"""The design changes typography, never the technical facts or their authority."""

from dataclasses import FrozenInstanceError
from types import SimpleNamespace

import pytest

from yt_downloader.activity_ui import ActivityLogText
from yt_downloader.detail_ui import FactsText, detail_lines


def test_detail_lines_keep_every_raw_line_in_order():
    raw = (
        "Container/ext: mp4\nResolution: 3840x2160\nVideo bitrate: 158 kbps\n"
        "Output file path: C:\\Media\\Creator\\video.mp4\n"
        "Source URL: https://example.invalid/video?v=sample\n"
        "Validation status: Failed\nUnrecognized provider diagnostic\n\n"
        "Warning: Keep this warning, including: extra details\n"
        "Format        MP4\nA completely new field: preserved"
    )
    lines = detail_lines(raw)
    assert tuple(line.raw for line in lines) == tuple(raw.splitlines())
    assert len(lines) == 11
    assert lines[3].value == r"C:\Media\Creator\video.mp4"
    assert lines[4].value == "https://example.invalid/video?v=sample"
    assert lines[-1].value == "preserved"
    assert lines[-2].label == "Format"
    with pytest.raises(FrozenInstanceError):
        lines[0].value = "changed"  # type: ignore[misc]


@pytest.mark.parametrize("owner", [FactsText, ActivityLogText])
def test_identical_snapshot_does_no_widget_work(owner):
    # Any Tk access would fail on this deliberately minimal probe.
    assert owner.request(SimpleNamespace(_snapshot="unchanged"), "unchanged") is False


def test_unknown_and_empty_details_are_not_filtered():
    assert detail_lines("") == ()
    assert detail_lines("\n\n")[0].raw == ""
    assert (
        detail_lines("Provider omitted metadata")[0].raw == "Provider omitted metadata"
    )


@pytest.mark.parametrize(
    "raw", ["https://example.invalid/media", r"C:\Media\video.mp4"]
)
def test_standalone_urls_and_windows_paths_are_not_labels(raw):
    line = detail_lines(raw)[0]
    assert line.raw == raw
    assert line.label == ""
