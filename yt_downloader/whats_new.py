"""Curated feature announcements, independent of release notes and telemetry."""

from __future__ import annotations

import re
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
    recording: str = ""
    poster: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.preview, NativePreview):
            raise TypeError("What's New requires a supported native preview")
        if bool(self.recording) != bool(self.poster):
            raise ValueError("Recorded previews require both a clip and poster")
        for name, extension in ((self.recording, "mp4"), (self.poster, "jpg")):
            if name and not re.fullmatch(r"[a-z0-9][a-z0-9-]*\." + extension, name):
                raise ValueError("Recorded previews require a packaged asset basename")


# Editorial opt-in: change this ID ONLY when intentionally shipping a new
# showcase. A new app version, patch release, or release-note edit is not enough.
# An empty highlights tuple disables the showcase. Keep copy factual and short.
SHOWCASE_ID = "workspace-orientation-v1"
HIGHLIGHTS = (
    FeatureHighlight(
        "workspace",
        "Feedback beside your download",
        "Forge keeps URL feedback beside the download controls. Selected-run details "
        "stay separate from new input notices, with Activity available for the full log.",
        NativePreview.ACTIVITY,
        recording="forge-feedback.mp4",
        poster="forge-feedback.jpg",
    ),
    FeatureHighlight(
        "watch",
        "An updated Watch player",
        "Watch keeps the video in view as the layout changes. Move playback between "
        "the main player, Pop out and Fullscreen without starting it over.",
        NativePreview.PLAYER,
        recording="watch-player.mp4",
        poster="watch-player.jpg",
    ),
    FeatureHighlight(
        "library",
        "Clearer file and recovery actions",
        "Library brings file actions back into the selected item. In My Files, open "
        "Issues & Recovery to find a missing file, retry a download or dismiss an issue.",
        NativePreview.LIBRARY,
        recording="library-actions.mp4",
        poster="library-actions.jpg",
    ),
    FeatureHighlight(
        "captions",
        "Independent captions and subtitles",
        "Use Captions for a saved original track and Subtitles for a saved translation. "
        "To request a translation with a new MP4, choose its language in Settings.",
        NativePreview.TRANSPORT,
        recording="captions-player.mp4",
        poster="captions-player.jpg",
    ),
)

# Release editorial switch: choose one surface, never both. Keep the current
# mode until a release explicitly changes its editorial choice and SHOWCASE_ID.
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
        if mode not in {"none", "whats-new", "did-you-know"}:
            raise ValueError("Unknown showcase mode")
        self.heading = "Did you know?" if mode == "did-you-know" else "What’s new"
        self.open_settings = open_settings
        self.on_feature = on_feature or (lambda _action: None)
        self.is_tip = mode == "did-you-know"
        self.showcase_id = showcase_id
        self.highlights = (
            ()
            if mode == "none"
            else (
                highlights
                if highlights is not None
                else (DID_YOU_KNOW_HIGHLIGHTS if mode == "did-you-know" else HIGHLIGHTS)
            )
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
