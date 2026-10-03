from dataclasses import FrozenInstanceError
from types import SimpleNamespace

import pytest

from yt_downloader.settings_store import load_settings, save_settings
from yt_downloader.whats_new import (
    DID_YOU_KNOW_HIGHLIGHTS,
    HIGHLIGHTS,
    SHOWCASE_ID,
    FeatureHighlight,
    NativePreview,
)
from yt_downloader.whats_new import (
    WhatsNewOwner as ReleaseWhatsNewOwner,
)


class Seen:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


def WhatsNewOwner(*args, **kwargs):
    # Keep evergreen showcase behavior explicit in owner tests.
    kwargs.setdefault("mode", "whats-new")
    return ReleaseWhatsNewOwner(*args, **kwargs)


@pytest.mark.parametrize(
    ("seen", "pending"), [("", True), (SHOWCASE_ID, False), ("older-release", True)]
)
def test_upcoming_release_explicitly_enables_orientation(seen, pending):
    events = []
    owner = ReleaseWhatsNewOwner(
        None, Seen(seen), lambda: True, on_feature=events.append
    )
    assert owner.pending is pending
    assert owner.highlights == HIGHLIGHTS
    assert owner.heading == "What’s new"
    assert events == []  # Eligibility alone does not announce a display.


def test_orientation_catalog_names_real_destinations_and_supported_previews():
    assert [h.key for h in HIGHLIGHTS] == [
        "workspace",
        "watch",
        "library",
        "captions",
    ]
    copy = " ".join(h.description for h in HIGHLIGHTS)
    assert "Everyday" not in copy
    assert "Optimized for" not in copy
    assert HIGHLIGHTS[1].title == "An updated Watch player"
    for destination in (
        "Forge",
        "Watch",
        "Activity",
        "Library",
        "My Files",
        "Issues & Recovery",
        "Settings",
    ):
        assert destination in copy
    owner = WhatsNewOwner(None, Seen("output-settings-presets-v2"), lambda: True)
    assert owner.pending and owner.highlights == HIGHLIGHTS


def test_showcase_dismissal_survives_settings_reload(tmp_path):
    path = tmp_path / "settings.json"
    seen = Seen()
    owner = WhatsNewOwner(None, seen, lambda: True)
    assert owner.pending
    owner._dismissed()
    save_settings(path, {"whats_new_seen": seen.get()})
    restarted = WhatsNewOwner(
        None, Seen(load_settings(path)["whats_new_seen"]), lambda: True
    )
    assert not restarted.pending


def test_catalog_is_curated_immutable_and_native_only():
    assert len({h.key for h in HIGHLIGHTS}) == len(HIGHLIGHTS)
    for feature in HIGHLIGHTS:
        assert isinstance(feature.preview, NativePreview)
        assert len(feature.description) < 180
    with pytest.raises(FrozenInstanceError):
        HIGHLIGHTS[0].title = "changed"


def test_seen_showcase_does_not_repeat_for_an_app_version_change():
    owner = WhatsNewOwner(None, Seen(SHOWCASE_ID), lambda: True)
    assert not owner.pending  # Eligibility deliberately has no app-version input.
    new = WhatsNewOwner(None, owner.seen, lambda: True, showcase_id="next-feature")
    assert new.pending


def test_future_slides_cannot_fall_back_to_screenshot_artwork():
    with pytest.raises(TypeError, match="native preview"):
        FeatureHighlight("future", "Future", "A feature", "screenshot.png")
    from yt_downloader.engagement_state import WELCOME_SLIDES

    assert {
        feature.preview
        for feature in (*HIGHLIGHTS, *WELCOME_SLIDES, *DID_YOU_KNOW_HIGHLIGHTS)
    } <= set(NativePreview)


def test_tip_uses_same_once_seen_owner_and_replaces_release_slides():
    seen = Seen()
    owner = WhatsNewOwner(
        None, seen, lambda: True, mode="did-you-know", showcase_id="tip-release"
    )
    assert owner.heading == "Did you know?"
    assert owner.highlights == DID_YOU_KNOW_HIGHLIGHTS
    assert owner.pending
    owner._dismissed()
    assert not WhatsNewOwner(
        None, seen, lambda: True, mode="did-you-know", showcase_id="tip-release"
    ).pending


def test_release_without_curated_highlights_is_silent():
    assert not WhatsNewOwner(None, Seen(), lambda: True, highlights=()).pending


def test_dismissal_persists_but_application_shutdown_does_not_acknowledge():
    seen = Seen()
    owner = WhatsNewOwner(None, seen, lambda: True)
    owner._dismissed()
    assert seen.get() == SHOWCASE_ID
    seen.set("")
    calls = []
    owner.panel = SimpleNamespace(close=lambda **kwargs: calls.append(kwargs))
    owner.close()
    assert calls == [{"acknowledge": False}]
    assert seen.get() == ""


@pytest.mark.parametrize("ready,grab", [(False, None), (True, object())])
def test_waits_for_consent_and_other_modals(ready, grab):
    scheduled = []
    parent = SimpleNamespace(
        after=lambda delay, fn: scheduled.append((delay, fn)) or "timer",
        grab_current=lambda: grab,
    )
    owner = WhatsNewOwner(parent, Seen(), lambda: ready)
    owner._poll()
    assert scheduled[0][0] == 300 and owner.panel is None


def test_start_is_idempotent_and_close_cancels_wait():
    scheduled, cancelled = [], []
    parent = SimpleNamespace(
        after=lambda delay, fn: scheduled.append(fn) or "timer",
        after_cancel=cancelled.append,
    )
    owner = WhatsNewOwner(parent, Seen(), lambda: True)
    owner.start()
    owner.start()
    assert len(scheduled) == 1
    owner.close()
    assert cancelled == ["timer"]
    scheduled[0]()
    assert owner.panel is None


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
    assert len(entries) == len(HIGHLIGHTS) == 4
    # Full-window previews must share a visual footprint across the carousel.
    assert {(entry["width"], entry["height"]) for entry in entries} == {(960, 646)}
    assert {(h.recording, h.poster) for h in HIGHLIGHTS} == {
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


@pytest.mark.parametrize("highlight", HIGHLIGHTS, ids=lambda item: item.key)
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
