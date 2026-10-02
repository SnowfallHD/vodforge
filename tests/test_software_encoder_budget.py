from pathlib import Path

import pytest

from yt_downloader.app import build_vod_ffmpeg_command


@pytest.mark.parametrize(
    ("cores", "budget"), [(None, 1), (1, 1), (2, 1), (4, 2), (8, 4), (64, 4)]
)
def test_software_scopes_cpu_budget(monkeypatch, cores, budget):
    monkeypatch.setattr("yt_downloader.app.os.cpu_count", lambda: cores)
    command = build_vod_ffmpeg_command("ffmpeg", Path("input"), Path("output"))
    input_at = command.index("-i")
    thread_positions = [i for i, value in enumerate(command) if value == "-threads:v:0"]
    assert len(thread_positions) == 2
    assert thread_positions[0] < input_at < thread_positions[1] < len(command) - 1
    assert [command[i + 1] for i in thread_positions] == [str(budget)] * 2
    for option in ("-filter_threads", "-filter_complex_threads"):
        assert command.index(option) < input_at
        assert command[command.index(option) + 1] == str(budget)
    assert command[command.index("-c:v") + 1] == "libx264"
    assert command[command.index("-preset") + 1] == "medium"
    assert command[command.index("-b:v") + 1] == "10000k"


def test_nvenc_keeps_hardware_contract():
    command = build_vod_ffmpeg_command(
        "ffmpeg", Path("input"), Path("output"), use_nvenc=True
    )
    assert "-threads:v:0" not in command
    assert "-filter_threads" not in command
    assert command[command.index("-c:v") + 1] == "h264_nvenc"
    assert command[command.index("-preset") + 1] == "p6"


def test_custom_crf_fallback_and_artwork_are_preserved():
    command = build_vod_ffmpeg_command(
        "ffmpeg",
        Path("input"),
        Path("output"),
        use_nvenc=True,
        video_crf=20,
        preserve_attached_picture=True,
    )
    assert command[command.index("-c:v:0") + 1] == "libx264"
    assert command[command.index("-crf:v:0") + 1] == "20"
    assert command.count("-threads:v:0") == 2
    assert "-threads:v:1" not in command
    assert command[command.index("-c:v:1") + 1] == "copy"
    assert "0:v:disp:attached_pic:0?" in command
    assert command[command.index("-disposition:v:1") + 1] == "attached_pic"
