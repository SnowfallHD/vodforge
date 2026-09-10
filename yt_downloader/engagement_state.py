"""Local welcome/rating eligibility. Installation state remains the durable owner."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .cloud_funnel import (
    load_or_create_installation_state,
    record_rating_success,
    update_onboarding,
)
from .whats_new import FeatureHighlight, NativePreview

WELCOME_SLIDES = (
    FeatureHighlight(
        "welcome",
        "Welcome to VODForge",
        "Paste a YouTube link, choose your output, and start your download. Your media saves locally.",
        NativePreview.ACTIVITY,
    ),
    FeatureHighlight(
        "outputs",
        "Your media, your format",
        "Choose MP4, MP3, or Original audio. Settings controls quality and your default save folder.",
        NativePreview.ORIGINAL_AUDIO,
    ),
    FeatureHighlight(
        "detail",
        "Friendly or technical",
        "Try the happy/frowny slider: friendly progress or technical detail. It changes the view, not your download quality.",
        NativePreview.WELCOME_ACTIVITY,
    ),
    FeatureHighlight(
        "library",
        "Find it in Library",
        "Play and organize saved media in Library. Recent items appear in Run Deck. Help & feedback is always available above.",
        NativePreview.LIBRARY,
    ),
    FeatureHighlight(
        "playlists",
        "Download full playlists",
        "In Settings, turn off Ignore playlists. Paste a video link connected to "
        "a playlist, or paste a playlist link directly, to download the full playlist.",
        NativePreview.PLAYLISTS,
    ),
    FeatureHighlight(
        "youtube-access",
        "Age Restricted Content",
        "In Settings → YouTube access, try Browser and select your browser where "
        "YouTube is signed in. Your computer may ask for a password — "
        "cookies.txt is a manual alternative.",
        NativePreview.YOUTUBE_ACCESS,
    ),
)


class EngagementState:
    """UI-thread consumer of canonical operation outcomes; never counts playlist children."""

    def __init__(self, path: Path):
        self.path = path

    def snapshot(self) -> dict[str, Any]:
        return load_or_create_installation_state(self.path).onboarding or {}

    @property
    def welcome_pending(self) -> bool:
        state = self.snapshot()
        return state.get("welcome_eligible") is True and not state.get(
            "welcome_presented"
        )

    def presented_welcome(self) -> None:
        update_onboarding(self.path, welcome_presented=True)

    def completed_download(self, run_id: str) -> None:
        record_rating_success(self.path, run_id)

    @property
    def rating_pending(self) -> bool:
        state = self.snapshot()
        ids = state.get("rating_successes", [])
        return (
            isinstance(ids, list)
            and len(ids) >= 3
            and not state.get("rating_presented")
        )

    def presented_rating(self) -> None:
        update_onboarding(self.path, rating_presented=True)
