"""Curated feature announcements, independent of release notes and telemetry."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class NativePreview(str, Enum):
    WELCOME_ACTIVITY = "welcome-activity"
    ACTIVITY = "ui-activity"
    SETTINGS = "ui-settings"
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
SHOWCASE_ID = "ui-updates-library-and-local-video"
HIGHLIGHTS = (
    FeatureHighlight(
        "ui-activity",
        "UI Updates",
        "Follow your download with clear progress stages in Forge. "
        "Switch to Technical details for the full log, or open Activity.",
        NativePreview.ACTIVITY,
    ),
    FeatureHighlight(
        "ui-settings",
        "Cleaner controls",
        "Refined dropdowns, checkboxes, and buttons make Settings easier to scan. "
        "Your theme carries through the app.",
        NativePreview.SETTINGS,
    ),
    FeatureHighlight(
        "ui-player",
        "A more polished Player",
        "Refined playback controls, a clearer timeline, and a cleaner volume "
        "slider keep the focus on your media.",
        NativePreview.TRANSPORT,
    ),
    FeatureHighlight(
        "activity-mode",
        "Friendly or technical. Your call.",
        "Slide up to the happy face for simple progress. Slide down to the "
        "frowny face for the live technical log. Same run, your preferred detail.",
        NativePreview.ACTIVITY_MODE,
    ),
    FeatureHighlight(
        "local-video",
        "Turn audio into video",
        "Pair an MP3 with a still image to create an MP4, up to 4K. "
        "Find it in Library and your selected output folder.",
        NativePreview.LOCAL_VIDEO,
    ),
    FeatureHighlight(
        "original-audio",
        "Original audio. No extra compression.",
        "Choose Original audio to keep the best available Opus or AAC stream "
        "without re-encoding. MP3 is still here when you need it.",
        NativePreview.ORIGINAL_AUDIO,
    ),
    FeatureHighlight(
        "library",
        "Make your Library your own",
        "Search your saved media. Add notes, tags, and categories to keep "
        "everything easy to find.",
        NativePreview.LIBRARY,
    ),
    FeatureHighlight(
        "player",
        "Play without leaving VODForge",
        "Watch or listen right in the app. Jump to preview moments and "
        "chapters when your media includes them. Works offline.",
        NativePreview.PLAYER,
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
        highlights: tuple[FeatureHighlight, ...] = HIGHLIGHTS,
    ) -> None:
        self.parent, self.seen, self.ready = parent, seen, ready
        self.showcase_id, self.highlights = showcase_id, highlights
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

        self.panel = WhatsNewPanel(self.parent, self.highlights, self._dismissed)

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
