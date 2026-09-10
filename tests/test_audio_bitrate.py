import subprocess

import pytest

from yt_downloader.audio_bitrate import (
    measure_packet_average,
    needs_packet_average,
    packet_average_bps,
)


def test_packet_weighted_average_excludes_container():
    assert (
        packet_average_bps(
            {
                "packets": [
                    {"size": "100", "duration_time": ".01"},
                    {"size": "500", "duration_time": ".03"},
                ]
            }
        )
        == 120000
    )


@pytest.mark.parametrize(
    "packet", [{}, {"size": 4, "duration_time": 0}, {"size": 4, "duration_time": "nan"}]
)
def test_incomplete_evidence_not_guessed(packet):
    assert packet_average_bps({"packets": [packet]}) is None


def test_only_missing_audio_rate_needs_scan():
    assert not needs_packet_average({"streams": []})
    assert not needs_packet_average(
        {"streams": [{"codec_type": "audio", "bit_rate": "128000"}]}
    )
    assert needs_packet_average({"streams": [{"codec_type": "audio"}]})


def test_optional_probe_failure_and_cancellation(tmp_path):
    def failed(command):
        raise subprocess.TimeoutExpired(command, 1)

    assert measure_packet_average("ffprobe", tmp_path / "a.opus", failed) is None

    def cancelled(command):
        raise RuntimeError("cancelled")

    with pytest.raises(RuntimeError, match="cancelled"):
        measure_packet_average("ffprobe", tmp_path / "a.opus", cancelled)


def test_summary_labels_average():
    from yt_downloader.app import _ffprobe_output_summary

    data = {
        "streams": [{"codec_type": "audio", "codec_name": "opus"}],
        "measured_audio_packet_bps": 121589.763,
    }
    assert (
        _ffprobe_output_summary(data)["Measured audio bitrate"]
        == "121.6 kbps (average)"
    )
