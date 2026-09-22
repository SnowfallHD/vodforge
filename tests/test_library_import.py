"""Import inspection preserves files and distinguishes cover art from video."""

import json
import threading
from types import SimpleNamespace

import pytest

from yt_downloader import library_import


def inspect_fixture(
    tmp_path, monkeypatch, suffix, streams, *, duration="8", mutate=None
):
    path = tmp_path / ("media" + suffix)
    path.write_bytes(b"controlled media bytes")
    before = path.read_bytes()
    monkeypatch.setattr(library_import, "find_runtime_executable", lambda _: "ffprobe")

    def run(argv, **options):
        assert (
            "stream_disposition=attached_pic" in argv[argv.index("-show_entries") + 1]
        )
        assert argv[-1] == str(path) and options["timeout"] == 15
        if mutate:
            mutate(path)
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {"streams": streams, "format": {"duration": duration}}
            ).encode(),
        )

    monkeypatch.setattr(library_import.subprocess, "run", run)
    result = library_import.inspect_local_media(path, threading.Event())
    assert path.read_bytes() == before
    return result


@pytest.mark.parametrize(
    "suffix,expected",
    [
        (".mp3", "MP3"),
        (".m4a", "Original audio"),
        (".flac", "Original audio"),
        (".ogg", "Original audio"),
        (".opus", "Original audio"),
    ],
)
def test_audio_with_album_cover_stays_audio_and_original_file_is_unchanged(
    tmp_path, monkeypatch, suffix, expected
):
    cover = {
        "index": 0,
        "codec_type": "video",
        "codec_name": "mjpeg",
        "width": 600,
        "height": 600,
        "disposition": {"attached_pic": 1},
    }
    audio = {
        "index": 1,
        "codec_type": "audio",
        "codec_name": "aac",
        "sample_rate": "44100",
        "channels": 2,
    }
    result = inspect_fixture(tmp_path, monkeypatch, suffix, [cover, audio])
    assert result["vodforge_output_type"] == expected
    assert "Output resolution" not in result["vodforge_encoding_summary"]["output"]


def test_mp4_motion_video_after_cover_is_the_output_video(tmp_path, monkeypatch):
    result = inspect_fixture(
        tmp_path,
        monkeypatch,
        ".mp4",
        [
            {
                "codec_type": "video",
                "codec_name": "mjpeg",
                "width": 600,
                "height": 600,
                "disposition": {"attached_pic": 1},
            },
            {
                "codec_type": "video",
                "codec_name": "h264",
                "width": 1920,
                "height": 1080,
                "disposition": {"attached_pic": 0},
            },
        ],
    )
    assert result["vodforge_output_type"] == "MP4"
    assert (
        result["vodforge_encoding_summary"]["output"]["Output resolution"]
        == "1920x1080"
    )


@pytest.mark.parametrize("duration", ["nan", "inf", "0", "-4"])
def test_invalid_duration_never_creates_an_import_record(
    tmp_path, monkeypatch, duration
):
    with pytest.raises(ValueError, match="duration"):
        inspect_fixture(
            tmp_path, monkeypatch, ".mp3", [{"codec_type": "audio"}], duration=duration
        )


def test_cover_without_audio_does_not_become_a_playable_video(tmp_path, monkeypatch):
    with pytest.raises(ValueError, match="No playable"):
        inspect_fixture(
            tmp_path,
            monkeypatch,
            ".mp3",
            [{"codec_type": "video", "disposition": {"attached_pic": 1}}],
        )


def test_motion_video_mislabeled_as_audio_is_rejected(tmp_path, monkeypatch):
    with pytest.raises(ValueError, match="MP4"):
        inspect_fixture(
            tmp_path,
            monkeypatch,
            ".m4a",
            [{"codec_type": "video", "disposition": {"attached_pic": 0}}],
        )


def test_file_changed_during_probe_cannot_be_committed(tmp_path, monkeypatch):
    with pytest.raises(ValueError, match="changed"):
        inspect_fixture(
            tmp_path,
            monkeypatch,
            ".mp3",
            [{"codec_type": "audio"}],
            mutate=lambda path: path.write_bytes(b"replacement changed bytes"),
        )


def test_cancelled_import_does_not_inspect_or_touch_file(tmp_path, monkeypatch):
    cancel = threading.Event()
    cancel.set()
    monkeypatch.setattr(
        library_import.subprocess,
        "run",
        lambda *_a, **_kw: pytest.fail("Cancelled import ran ffprobe"),
    )
    with pytest.raises(InterruptedError):
        library_import.inspect_local_media(tmp_path / "does-not-exist.mp3", cancel)


def test_failed_batch_persistence_does_not_publish_partial_history(tmp_path):
    from yt_downloader.history import HistoryError

    history = [{"id": "existing", "title": "Existing", "vodforge_output_dir": "/saved"}]
    original = list(history)
    imports = [
        {
            "id": str(i),
            "title": f"Imported {i}",
            "vodforge_output_type": "MP3",
            "vodforge_output_path": str(tmp_path / f"{i}.mp3"),
        }
        for i in range(3)
    ]

    def failed_save(_path, _prospective):
        raise HistoryError("disk unavailable")

    with pytest.raises(HistoryError):
        library_import.commit_imports(
            history, imports, tmp_path / "history.json", save=failed_save
        )
    assert history == original


def test_batch_history_is_written_once_before_returning_new_snapshot(tmp_path):
    writes = []
    history = []
    imports = [
        {
            "id": str(i),
            "title": f"Imported {i}",
            "vodforge_output_type": "MP3",
            "vodforge_output_path": str(tmp_path / f"{i}.mp3"),
        }
        for i in range(3)
    ]
    result = library_import.commit_imports(
        history,
        imports,
        tmp_path / "history.json",
        save=lambda path, items: writes.append((path, list(items))),
    )
    assert history == [] and len(writes) == 1
    assert len(result) == 3 and result == writes[0][1]
