"""Curated feature announcements, independent of release notes and telemetry."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class NativePreview(str, Enum):
    YOUTUBE_ACCESS_EXPANDED = "youtube-access-expanded"
    PLAYLISTS = "playlists"
    YOUTUBE_ACCESS = "youtube-access"
    WELCOME_ACTIVITY = "welcome-activity"
    ACTIVITY = "ui-activity"
    SETTINGS = "ui-settings"
    OUTPUT_SETTINGS = "output-settings"
    TRANSPORT = "ui-player"
    ACTIVITY_MODE = "activity-mode"
    LOCAL_VIDEO = "local-video"
    ORIGINAL_AUDIO = "original-audio"
    LIBRARY = "library"
    PLAYER = "player"


@dataclass(frozen=True, slots=True)
class FeatureHighlight:
    key: str
    title: str
    description: str
    preview: NativePreview

    def __post_init__(self) -> None:
        if not isinstance(self.preview, NativePreview):
            raise TypeError("What's New requires a supported native preview")


# Editorial opt-in: change this ID ONLY when intentionally shipping a new
# showcase. A new app version, patch release, or release-note edit is not enough.
# An empty highlights tuple disables the showcase. Keep copy factual and short.
SHOWCASE_ID = "output-settings-presets-v2"
HIGHLIGHTS = (
    FeatureHighlight(
        "output-settings",
        "Output settings for your next step",
        "Source-aware MP4 presets for your next task, tuned for CPU and optional NVIDIA "
        "encoding on Windows. Choose a preset or Custom in Settings → Optimize for.",
        NativePreview.OUTPUT_SETTINGS,
    ),
)


# Release editorial switch: choose one surface, never both. Keep the current
# mode until a release explicitly opts into the tip and changes SHOWCASE_ID.
SHOWCASE_MODE = "whats-new"
DID_YOU_KNOW_HIGHLIGHTS = (
    FeatureHighlight(
        "youtube-access-tip",
        "Age-restricted & sign-in-required videos",
        "Did you know? YouTube access can help download videos your account "
        "can access. In Settings → YouTube access, choose Browser and select "
        "the browser where you are signed in to YouTube.",
        NativePreview.YOUTUBE_ACCESS_EXPANDED,
    ),
)


class WhatsNewOwner:
    """Own one showcase's eligibility and lifetime; settings own persistence."""

    def __init__(
        self,
        parent: Any,
        seen: Any,
        ready: Any,
        *,
        showcase_id: str = SHOWCASE_ID,
        highlights: tuple[FeatureHighlight, ...] | None = None,
        mode: str = SHOWCASE_MODE,
        open_settings: Any = None,
        on_feature: Any = None,
    ) -> None:
        self.parent, self.seen, self.ready = parent, seen, ready
        if mode not in {"whats-new", "did-you-know"}:
            raise ValueError("Unknown showcase mode")
        self.heading = "Did you know?" if mode == "did-you-know" else "What’s new"
        self.open_settings = open_settings
        self.on_feature = on_feature or (lambda _action: None)
        self.is_tip = mode == "did-you-know"
        self.showcase_id = showcase_id
        self.highlights = (
            highlights
            if highlights is not None
            else (DID_YOU_KNOW_HIGHLIGHTS if mode == "did-you-know" else HIGHLIGHTS)
        )
        self.panel: Any = None
        self.closed = False
        self.timer: Any = None

    @property
    def pending(self) -> bool:
        return bool(
            self.highlights and self.showcase_id and self.seen.get() != self.showcase_id
        )

    def start(self) -> None:
        if (
            not self.closed
            and self.pending
            and self.timer is None
            and self.panel is None
        ):
            self.timer = self.parent.after(1000, self._poll)

    def _poll(self) -> None:
        self.timer = None
        if self.closed or not self.pending:
            return
        if not self.ready() or self.parent.grab_current() is not None:
            self.timer = self.parent.after(300, self._poll)
            return
        self.show()

    def show(self) -> None:
        if self.closed or not self.highlights or self.panel is not None:
            return
        from .whats_new_ui import WhatsNewPanel

        settings_action = self.is_tip or (
            len(self.highlights) == 1 and self.highlights[0].key == "output-settings"
        )
        self.panel = WhatsNewPanel(
            self.parent,
            self.highlights,
            self._dismissed,
            heading=self.heading,
            finish_label="Try it" if settings_action else None,
            on_finish=self._try_it if settings_action else None,
        )

        self.on_feature("shown")

    def _try_it(self) -> None:
        self.on_feature("try_it")
        if self.open_settings is not None:
            self.open_settings()

    def _dismissed(self) -> None:
        self.seen.set(self.showcase_id)
        self.panel = None

    def close(self) -> None:
        self.closed = True
        if self.timer is not None:
            self.parent.after_cancel(self.timer)
            self.timer = None
        if self.panel is not None:
            self.panel.close(acknowledge=False)
            self.panel = None
