from dataclasses import FrozenInstanceError

import pytest

from yt_downloader.whats_new import (
    DID_YOU_KNOW_HIGHLIGHTS,
    HIGHLIGHTS,
    FeatureHighlight,
    NativePreview,
)


def test_catalog_is_curated_immutable_and_native_only():
    assert len({h.key for h in HIGHLIGHTS}) == len(HIGHLIGHTS)
    for feature in HIGHLIGHTS:
        assert isinstance(feature.preview, NativePreview)
        assert len(feature.description) < 180
    with pytest.raises(FrozenInstanceError):
        HIGHLIGHTS[0].title = "changed"


def test_future_slides_cannot_fall_back_to_screenshot_artwork():
    with pytest.raises(TypeError, match="native preview"):
        FeatureHighlight("future", "Future", "A feature", "screenshot.png")
    from yt_downloader.engagement_state import WELCOME_SLIDES

    assert {
        feature.preview
        for feature in (*HIGHLIGHTS, *WELCOME_SLIDES, *DID_YOU_KNOW_HIGHLIGHTS)
    } <= set(NativePreview)


def test_recorded_editorial_assets_are_paired_packaged_basenames():
    slide = FeatureHighlight(
        "clip",
        "Clip",
        "Actual UI",
        NativePreview.PLAYER,
        recording="watch-transfer.mp4",
        poster="watch-transfer.jpg",
    )
    assert slide.recording == "watch-transfer.mp4"
    for name in (
        "../private.mp4",
        "https://example.test/clip.mp4",
        "/tmp/clip.mp4",
        "clip.mov",
    ):
        with pytest.raises(ValueError, match="packaged asset basename"):
            FeatureHighlight(
                "clip",
                "Clip",
                "Actual UI",
                NativePreview.PLAYER,
                recording=name,
                poster="watch-transfer.jpg",
            )
    with pytest.raises(ValueError, match="both a clip and poster"):
        FeatureHighlight(
            "clip",
            "Clip",
            "Actual UI",
            NativePreview.PLAYER,
            recording="watch-transfer.mp4",
        )


def test_recorded_showcase_manifest_integrity_and_explicit_packaging():
    import hashlib
    import json
    from pathlib import Path

    root = Path(__file__).parents[1]
    assets = root / "assets/whats-new"
    manifest = json.loads((assets / "manifest.json").read_text())
    entries = manifest["clips"]
    assert len(entries) == 4
    assert len(HIGHLIGHTS) == 8
    # Full-window previews must share a visual footprint across the carousel.
    assert {(entry["width"], entry["height"]) for entry in entries} == {(960, 646)}
    assert {(h.recording, h.poster) for h in HIGHLIGHTS if h.recording} == {
        (entry["recording"], entry["poster"]) for entry in entries
    }
    names = {"manifest.json"}
    for entry in entries:
        assert 3 < entry["duration_seconds"] < 8
        assert entry["width"] == 960
        for field, hash_field in (("recording", "sha256"), ("poster", "poster_sha256")):
            name = entry[field]
            assert Path(name).name == name
            payload = (assets / name).read_bytes()
            assert hashlib.sha256(payload).hexdigest() == entry[hash_field]
            names.add(name)
    assert sum((assets / name).stat().st_size for name in names) < 12_000_000
    for script, separator in (("build_macos.sh", ":"), ("build_windows.ps1", ";")):
        source = (root / script).read_text()
        for name in names:
            assert f"assets/whats-new/{name}{separator}assets/whats-new" in source
    public = (assets / "manifest.json").read_text()
    assert "/Users/" not in public and "launch_id" not in public


@pytest.mark.parametrize(
    "highlight", [h for h in HIGHLIGHTS if h.recording], ids=lambda item: item.key
)
def test_recorded_showcase_poster_matches_opening_frame(highlight):
    import io
    import shutil
    import subprocess
    from pathlib import Path

    from PIL import Image, ImageChops, ImageStat

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        pytest.skip("Existing FFmpeg is required to compare decoded opening frames")
    assets = Path(__file__).parents[1] / "assets/whats-new"
    frame = subprocess.run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(assets / highlight.recording),
            "-frames:v",
            "1",
            "-f",
            "image2pipe",
            "-c:v",
            "png",
            "pipe:1",
        ],
        check=True,
        capture_output=True,
        timeout=15,
    ).stdout
    opening = Image.open(io.BytesIO(frame)).convert("RGB")
    poster = Image.open(assets / highlight.poster).convert("RGB")
    assert poster.size == opening.size
    # JPEG compression is allowed; a different camera/result frame is not.
    difference = ImageStat.Stat(ImageChops.difference(poster, opening))
    assert max(difference.mean) < 4
