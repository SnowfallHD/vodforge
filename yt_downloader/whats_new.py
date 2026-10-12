"""Curated feature announcements, independent of release notes and telemetry."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


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
SHOWCASE_ID = "release-0.2.5-design-v1"
HIGHLIGHTS = (
    FeatureHighlight(
        "design",
        "A refreshed VODForge workspace",
        "Subtle glass, sculpted controls, theme accents and fluid transitions connect "
        "the workspace. File, Edit, View, Window and Help are now in the menu bar.",
        NativePreview.ACTIVITY,
        recording="forge-feedback.mp4",
        poster="forge-feedback.jpg",
    ),
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
        "custom-output",
        "Custom settings, kept in view",
        "Options expands smoothly for Custom controls. Choose Quality with CRF or CBR with "
        "a video bitrate; only the relevant field appears. Selections stay open until you close Options.",
        NativePreview.OUTPUT_SETTINGS,
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
        "Library’s responsive channel and playlist cards keep artwork in view. Select items "
        "for file actions, or open My Files → Issues & Recovery for missing media.",
        NativePreview.LIBRARY,
        recording="library-actions.mp4",
        poster="library-actions.jpg",
    ),
    FeatureHighlight(
        "file-moves",
        "Move your selection with care",
        "Move selected media together in Library. Loose imports move as individual files; "
        "VODForge-managed media keeps its recognized archive structure when relocated.",
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
    FeatureHighlight(
        "release-fixes",
        "Folder and download fixes",
        "This update improves folder-picker shortcuts and file-move confirmation, "
        "retries temporary file locks, and can retry an expired download link with a refreshed URL.",
        NativePreview.ACTIVITY,
    ),
)

# Release editorial switch: choose one surface, never both. Keep the current
# mode until a release explicitly changes its editorial choice and SHOWCASE_ID.
SHOWCASE_MODE = "none"
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
