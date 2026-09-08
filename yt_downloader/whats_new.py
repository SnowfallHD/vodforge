"""Curated feature announcements, independent of release notes and telemetry."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class FeatureHighlight:
    key: str
    title: str
    description: str
    artwork: str
    crop: tuple[float, float, float, float]


# Editorial opt-in: change this ID ONLY when intentionally shipping a new
# showcase. A new app version, patch release, or release-note edit is not enough.
# An empty highlights tuple disables the showcase. Keep copy factual and short.
SHOWCASE_ID = "library-and-local-video"
HIGHLIGHTS = (
    FeatureHighlight(
        "local-video",
        "Turn audio into video",
        "Pair an MP3 with a still image to create an MP4, up to 4K. "
        "Find it in Library and your selected output folder.",
        "local-video.png",
        (0.02, 0.18, 0.98, 0.65),
    ),
    FeatureHighlight(
        "library",
        "Make your Library your own",
        "Search your saved media. Add notes, tags, and categories to keep "
        "everything easy to find.",
        "library.png",
        (0.03, 0.22, 0.97, 0.85),
    ),
    FeatureHighlight(
        "player",
        "Play without leaving VODForge",
        "Watch or listen right in the app. Jump to preview moments and "
        "chapters when your media includes them. Works offline.",
        "player.png",
        (0.02, 0.06, 0.98, 0.97),
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
