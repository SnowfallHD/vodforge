"""Streaming resources belong to the corpus, never to the caller's checkout."""

import subprocess
from pathlib import Path

import pytest
from quality_harness import fixtures


@pytest.mark.parametrize("relative_root", [False, True])
def test_original_audio_resources_stay_in_corpus(tmp_path, monkeypatch, relative_root):
    caller = tmp_path / "unrelated caller"
    caller.mkdir()
    monkeypatch.chdir(caller)
    root = Path("corpus") if relative_root else tmp_path / "corpus"
    root.mkdir()
    ffmpeg = fixtures.find_ffmpeg()
    source = root / "tone.m4a"
    subprocess.run(
        [
            ffmpeg,
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440",
            "-t",
            "2.2",
            "-c:a",
            "aac",
            str(source),
        ],
        check=True,
        capture_output=True,
        timeout=30,
    )
    fixtures._generate_original_audio_fixtures(ffmpeg, source, root)
    opus = root / "original-opus"
    assert list(opus.glob("init*.webm"))
    assert list(opus.glob("chunk*.webm"))
    assert not list(caller.glob("*.webm"))
    # Resolve references from the manifest, then decode the concatenated WebM.
    # This also works with FFmpeg builds that omit the optional DASH demuxer.
    resources = fixtures._dash_fixture_resources(opus / "manifest.mpd")
    decoded = subprocess.run(
        [ffmpeg, "-v", "error", "-i", "pipe:0", "-f", "null", "-"],
        input=b"".join(path.read_bytes() for path in resources),
        capture_output=True,
        timeout=30,
        check=False,
    )
    assert decoded.returncode == 0, decoded.stderr.decode(errors="replace")
    resources[-1].unlink()
    with pytest.raises(ValueError, match="missing or empty"):
        fixtures._generate_original_audio_fixtures(ffmpeg, source, root)


def test_relative_chunk_writer_is_given_manifest_directory(tmp_path, monkeypatch):
    """Model the observed Windows muxer's relative-file behavior independently."""
    root = tmp_path / "corpus"
    (root / "original-aac").mkdir(parents=True)
    (root / "original-aac" / "media.m3u8").touch()
    caller = tmp_path / "caller"
    caller.mkdir()
    monkeypatch.chdir(caller)

    def writer(command, **kwargs):
        destination = Path(kwargs.get("cwd") or Path.cwd())
        (destination / "init-stream0.webm").write_bytes(b"owned resource")
        Path(command[-1]).write_text(
            '<MPD xmlns="urn:mpeg:dash:schema:mpd:2011"><Representation id="0">'
            '<SegmentTemplate initialization="init-stream$RepresentationID$.webm" '
            'media="init-stream$RepresentationID$.webm"><SegmentTimeline><S d="1" />'
            "</SegmentTimeline></SegmentTemplate></Representation></MPD>"
        )
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(fixtures.subprocess, "run", writer)
    fixtures._generate_original_audio_fixtures("ffmpeg", tmp_path / "source", root)
    assert (
        root / "original-opus" / "init-stream0.webm"
    ).read_bytes() == b"owned resource"
    assert not list(caller.iterdir())
