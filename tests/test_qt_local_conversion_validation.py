"""UI selection mistakes must not become conversion jobs/failure telemetry."""

from types import SimpleNamespace

import pytest

from yt_downloader.qt_quick.main import Bridge


@pytest.mark.parametrize(
    "audio,image,expected",
    [
        ("", "", "MP3 audio file and a still image"),
        ("", "cover.png", "MP3 audio file"),
        ("sound.mp3", "", "still image"),
        ("sound.mp4", "cover.png", "MP3 audio file"),
        ("sound.mp3", "cover.txt", "JPG, PNG, or WebP"),
        ("gone.mp3", "cover.png", "MP3 audio file"),
        ("sound.mp3", "empty.png", "still image"),
        ("sound.mp3", "cover.png", None),
    ],
)
def test_local_selection_validates_before_job_creation(
    tmp_path, audio, image, expected
):
    for name in ("sound.mp3", "sound.mp4", "cover.png", "cover.txt"):
        (tmp_path / name).write_bytes(b"fixture")
    (tmp_path / "empty.png").touch()
    calls = []
    emit = SimpleNamespace(emit=lambda: None)
    bridge = SimpleNamespace(
        _relink=SimpleNamespace(active=False),
        _import_pending=False,
        _file_action_busy=False,
        _settings_writable=True,
        _local_audio=str(tmp_path / audio) if audio else "",
        _local_image=str(tmp_path / image) if image else "",
        _output_path=str(tmp_path / "output"),
        _local_profile="Everyday",
        _local=SimpleNamespace(start=lambda *args: calls.append(args)),
        _local_running=False,
        _local_progress="",
        _status="",
        statusChanged=emit,
        localChanged=emit,
    )
    Bridge.startLocalConversion(bridge)
    if expected:
        assert not calls and not bridge._local_running
        assert expected in bridge._local_progress
        assert "download could not finish" not in bridge._local_progress
    else:
        assert len(calls) == 1 and bridge._local_running
        assert calls[0][:2] == (tmp_path / audio, tmp_path / image)
    assert not (tmp_path / "output").exists()
