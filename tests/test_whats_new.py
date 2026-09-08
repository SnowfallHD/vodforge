from dataclasses import FrozenInstanceError
from types import SimpleNamespace

import pytest

from yt_downloader.settings_store import load_settings, save_settings
from yt_downloader.whats_new import (
    HIGHLIGHTS,
    SHOWCASE_ID,
    FeatureHighlight,
    NativePreview,
    WhatsNewOwner,
)


class Seen:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


def test_ui_updates_lead_without_replacing_existing_features():
    assert [h.key for h in HIGHLIGHTS] == [
        "ui-activity",
        "ui-settings",
        "ui-player",
        "activity-mode",
        "local-video",
        "original-audio",
        "library",
        "player",
    ]
    assert HIGHLIGHTS[0].title == "UI Updates"
    assert WhatsNewOwner(None, Seen("library-and-local-video"), lambda: True).pending


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
    assert {feature.preview for feature in HIGHLIGHTS} == set(NativePreview)


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
