from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from yt_downloader.media_player import (
    MediaPlayerError,
    probe_media_duration,
    resolve_library_media_path,
)


def test_resolve_library_media_path_prefers_exact_committed_file(
    tmp_path: Path,
) -> None:
    media = tmp_path / "video.mp4"
    media.write_bytes(b"valid")

    assert (
        resolve_library_media_path(
            {
                "vodforge_output_dir": str(tmp_path),
                "vodforge_output_path": str(media),
                "vodforge_output_type": "MP4",
            }
        )
        == media
    )


def test_resolve_library_media_path_falls_back_only_when_unambiguous(
    tmp_path: Path,
) -> None:
    first = tmp_path / "first.mp3"
    first.write_bytes(b"audio")
    record = {"vodforge_output_dir": str(tmp_path), "vodforge_output_type": "MP3"}
    assert resolve_library_media_path(record) == first

    (tmp_path / "second.mp3").write_bytes(b"audio")
    assert resolve_library_media_path(record) is None


def test_resolve_library_media_path_never_substitutes_for_missing_exact_file(
    tmp_path: Path,
) -> None:
    other = tmp_path / "other.mp4"
    other.write_bytes(b"different media")

    assert (
        resolve_library_media_path(
            {
                "vodforge_output_dir": str(tmp_path),
                "vodforge_output_path": str(tmp_path / "missing.mp4"),
                "vodforge_output_type": "MP4",
            }
        )
        is None
    )


def test_probe_duration_uses_fixed_json_contract(tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def runner(command, **_kwargs):
        calls.append(command)
        return SimpleNamespace(stdout=json.dumps({"format": {"duration": "42.5"}}))

    assert (
        probe_media_duration("/trusted/ffprobe", tmp_path / "video.mp4", runner=runner)
        == 42.5
    )
    assert calls[0][0] == "/trusted/ffprobe"
    assert calls[0][-1].endswith("video.mp4")


def test_probe_duration_rejects_malformed_or_unbounded_values(tmp_path: Path) -> None:
    def runner(*_args, **_kwargs):
        return SimpleNamespace(stdout='{"format":{"duration":"nan"}}')

    with pytest.raises(MediaPlayerError):
        probe_media_duration("ffprobe", tmp_path / "bad.mp4", runner=runner)
