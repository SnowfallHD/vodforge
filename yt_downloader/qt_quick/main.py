"""Qt Quick application under port; release entrypoint remains the Tk app."""

from __future__ import annotations

import argparse
import importlib
import json
import os
import re
import sys
import tempfile
import threading
import time
import uuid
from dataclasses import asdict, fields, replace
from datetime import datetime, timezone
from pathlib import Path
from subprocess import SubprocessError  # nosec B404 - exception type only
from typing import Any, Literal, TypedDict, cast, overload

SOURCE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SOURCE))

from PIL import Image
from PySide6.QtCore import (
    Property,
    QCoreApplication,
    QEvent,
    QLocale,
    QObject,
    QPointF,
    QProcess,
    QSize,
    Qt,
    QTimer,
    QUrl,
    Signal,
    Slot,
)
from PySide6.QtGui import QDesktopServices, QFont, QGuiApplication, QImage, QWindow
from PySide6.QtMultimedia import QMediaPlayer, QVideoFrame, QVideoSink
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickImageProvider, QQuickItem
from PySide6.QtQuickControls2 import QQuickStyle

from yt_downloader.analytics_consent import ANALYTICS_BENEFITS, ANALYTICS_DESCRIPTION
from yt_downloader.app import (
    DIAGNOSTICS_LOG_PATH,
    DownloaderApp,
    ProviderNetworkCoordinator,
    append_activity_log,
    canonical_youtube_url,
    close_activity_log,
    iter_video_infos,
    load_activity_log_tail,
    prepare_activity_log,
    retry_url_for_item,
    runtime_smoke,
)
from yt_downloader.archive_browser import (
    PAGE_SIZE,
    ArchiveBrowserModel,
    ArchiveComponent,
    archive_directory,
)
from yt_downloader.archive_observations import (
    bind_operation,
    operation,
    relink_dimensions,
)
from yt_downloader.archive_paths import ArchivePath
from yt_downloader.archive_relink import record_fingerprint
from yt_downloader.archive_work import ArchiveWorkOwner
from yt_downloader.caption_languages import (
    PROVIDER_SUBTITLE_LANGUAGES,
    translated_subtitle_language,
)
from yt_downloader.cloud_funnel import (
    InstallationIdentityError,
    cloud_page_url,
    installation_state_path,
    load_or_create_installation_state,
    mark_cloud_seen_confirmed,
    record_cloud_click,
    record_cloud_seen,
)
from yt_downloader.cookie_inputs import browser_cookie_value
from yt_downloader.download_error_presentation import download_error_message
from yt_downloader.engagement_state import WELCOME_SLIDES, EngagementState
from yt_downloader.export_inputs import (
    MP3_CHANNEL_OPTIONS,
    MP3_COVER_ART_OPTIONS,
    MP3_QUALITY_OPTIONS,
    MP3_SAMPLE_RATE_OPTIONS,
    manual_export_settings,
    mp3_export_settings,
    validate_custom_cover_art,
)
from yt_downloader.export_planning import (
    EXPORT_MODES,
    QUALITY_OPTIONS,
    export_mode_description,
    export_mode_display_name,
    export_mode_from_display_name,
    migrate_export_preferences,
)
from yt_downloader.failure_diagnostics import FailureDiagnostic
from yt_downloader.forge_activity import (
    ForgeActivityProjection,
    friendly_saved_activity,
)
from yt_downloader.history import (
    HISTORY_MEDIA_MISSING,
    HistoryError,
    application_data_dir,
    history_annotation_owner,
    history_archive_owner,
    history_identity,
    history_media_file_state,
    history_output_path,
    sanitize_chapters,
    sanitize_heatmap,
    sanitize_run_activity,
    save_history,
)
from yt_downloader.library_annotations import (
    MAX_NOTE_CHARS,
    MAX_TAG_CHARS,
    MAX_TAGS,
    LibraryAnnotationsError,
    LibraryAnnotationsOwner,
)
from yt_downloader.library_import import commit_imports, inspect_local_media
from yt_downloader.library_media_recovery import (
    LibraryMediaRecoveryOwner,
    LibraryMediaRecoveryPlan,
)
from yt_downloader.library_media_recovery_ui import library_media_recovery_prompt
from yt_downloader.library_scene_facts import library_detail_facts
from yt_downloader.library_search import (
    LIBRARY_ALL_CATEGORIES,
    LIBRARY_ALL_MEDIA,
    LIBRARY_AUDIO_MEDIA,
    LIBRARY_VIDEO_MEDIA,
    library_categories,
    library_visible_indices,
)
from yt_downloader.library_state import (
    ANNOTATION_OWNER_KEY,
    PROJECTION_OWNER_KEY,
    PROJECTION_OWNER_KIND_KEY,
    RUN_STATUS_KEY,
    LibraryProjectionOwner,
    format_duration,
    is_metadata_preview,
    library_phase_from_status,
    metadata_output_type,
    metadata_run_key,
    persisted_run_deck_records,
    resolve_library_removal_plan,
)
from yt_downloader.local_audio_video import (
    LOCAL_VIDEO_PROFILE_OPTIONS,
    LocalAudioVideoError,
    LocalAudioVideoProgress,
    LocalAudioVideoResult,
)
from yt_downloader.local_video_labels import (
    local_video_profile_label,
    local_video_profile_text,
    local_video_profile_value,
)
from yt_downloader.media_player import resolve_library_media_path
from yt_downloader.models import (
    CookieSource,
    ExportMode,
    ManualExportSettings,
    Mp3ExportSettings,
    OutputType,
)
from yt_downloader.platform_services import diagnostics_dir
from yt_downloader.playback_backend import PlaybackSnapshot, PlaybackStatus
from yt_downloader.playback_progress import PlaybackProgressOwner
from yt_downloader.playback_progress_binding import PlaybackProgressBinding
from yt_downloader.player_related import player_related_plan
from yt_downloader.product_telemetry import BoundProductOperation, product_output_kind
from yt_downloader.qt_quick.analytics import QtAnalyticsSession
from yt_downloader.qt_quick.artwork import QtArtwork, ThumbnailReductionProvider
from yt_downloader.qt_quick.library_files import QtLibraryFiles
from yt_downloader.qt_quick.library_window_model import register_window_model
from yt_downloader.qt_quick.local_conversion import LocalConversionRuntime
from yt_downloader.qt_quick.mac_windowing import integrate_qt_main_window
from yt_downloader.qt_quick.metadata_preview import QtMetadataPreview
from yt_downloader.qt_quick.presentation import QtPresentationProbe
from yt_downloader.qt_quick.previews import QtPreviewSession
from yt_downloader.qt_quick.relink import QtRelinkSession
from yt_downloader.qt_quick.run_controls import RunControlEvents, RunControlPresentation
from yt_downloader.qt_quick.runtime import DownloadPreferences, DownloadRuntime
from yt_downloader.qt_quick.scene_projection import (
    collection_picker,
    library_scene,
    watch_progress,
    watch_scene,
)
from yt_downloader.qt_quick.subtitle_session import SubtitleSession
from yt_downloader.qt_quick.support import QtSupportSession
from yt_downloader.qt_quick.update_session import QtUpdateSession
from yt_downloader.quality_e2e import (
    QualityE2EAttestationError,
    quality_e2e_mode_enabled,
    write_quality_e2e_qt_library_visibility_receipt,
    write_quality_e2e_startup_attestation,
)
from yt_downloader.run_identity import annotate_job_metadata, metadata_output_profile
from yt_downloader.run_state import RunStateError, run_admission_failure_message
from yt_downloader.settings_store import (
    SettingsError,
    load_settings,
    save_settings,
    settings_file_path,
)
from yt_downloader.support_diagnostics import (
    FailureContext,
    diagnostics_attachment,
    failure_context,
    public_video_url,
)
from yt_downloader.telemetry_features import settings_dimensions, time_bucket
from yt_downloader.telemetry_policy import telemetry_site_origin
from yt_downloader.ui_button_contract import BUTTON_METRICS
from yt_downloader.ui_chrome import (
    action_button_image,
    field_border_image,
    popup_shadow_image,
)
from yt_downloader.ui_materials import backdrop_pixels
from yt_downloader.ui_theme import (
    CUSTOM_THEME_NAME,
    DEFAULT_THEME_NAME,
    FONT_MONO_FAMILY,
    FONT_UI_FAMILY,
    THEME,
    THEME_NAMES,
    ThemeRenderOwner,
    apply_theme_selection,
    theme_motif,
)
from yt_downloader.updates import RELEASES_PAGE, record_update_telemetry_receipts
from yt_downloader.url_list_inputs import parse_url_list_text
from yt_downloader.version import __version__
from yt_downloader.volume_storage import StorageCapacityOwner, format_storage_bytes
from yt_downloader.watch_library import watch_media_kind
from yt_downloader.watch_queue import QueueToken, WatchQueueOwner, queue_media_key
from yt_downloader.whats_new import (
    DID_YOU_KNOW_HIGHLIGHTS,
    HIGHLIGHTS,
    SHOWCASE_ID,
    SHOWCASE_MODE,
    FeatureHighlight,
)
from yt_downloader.youtube_access import COOKIE_BROWSER_OPTIONS

# PySide6 accepts Qt metatype names here; its typing stub models only classes.
_QVARIANT_LIST = cast(type, "QVariantList")
_QVARIANT_MAP = cast(type, "QVariantMap")


class _SubmitJobOptions(TypedDict):
    batch_list_path: str
    urls: list[str] | None
    batch_mode: bool
    cookie_source: CookieSource
    cookie_file: Path | None
    cookie_browser: str | None
    nvenc_applicable: bool | None
    tags: list[str] | None
    translated_subtitle_language: str | None


def qt_image(source: Image.Image) -> QImage:
    image = source.convert("RGBA")
    pixels = image.tobytes()
    return QImage(
        pixels, image.width, image.height, image.width * 4, QImage.Format_RGBA8888
    ).copy()


class Materials(QQuickImageProvider):
    """Adapter for the existing VODForge material and artwork owners."""

    def __init__(self) -> None:
        super().__init__(QQuickImageProvider.Image)
        self.images: dict[str, QImage] = {}

    def requestImage(self, image_id: str, size: QSize, requested_size: QSize) -> QImage:
        del requested_size
        image = self.images.get(image_id)
        if image is None:
            parts = image_id.split("/")
            if len(parts) > 1 and re.fullmatch(r"r\d+", parts[-1]):
                parts.pop()
            if parts[0] == "backdrop" and len(parts) == 1:
                source = backdrop_pixels(
                    theme_motif(), THEME["bg"], THEME["accent"], (1920, 1200)
                )
            elif parts[0] == "watch-welcome" and len(parts) == 1:
                from yt_downloader.ui_chrome import watch_welcome_emblem

                source = watch_welcome_emblem()
            elif parts[0] == "button" and (
                len(parts) == 5
                or (len(parts) == 6 and parts[5] in {"primary", "outlined"})
            ):
                width, height = int(parts[1]), int(parts[2])
                # StoneButton also paints responsive artwork cards, not only controls.
                if not (1 <= width <= 4096 and 1 <= height <= 2048):
                    raise ValueError("button image dimensions out of bounds")
                source = action_button_image(
                    width,
                    height,
                    accent=parts[4] == "1",
                    state=parts[3],
                    primary=len(parts) == 6 and parts[5] == "primary",
                    outlined=len(parts) == 6 and parts[5] == "outlined",
                )
            elif parts[0] == "field" and len(parts) == 4:
                width, height = int(parts[1]), int(parts[2])
                if not (1 <= width <= 4096 and 1 <= height <= 2048):
                    raise ValueError("field image dimensions out of bounds")
                source = field_border_image(width, height, focused=parts[3] == "focus")
            elif parts[0] == "popup-shadow" and len(parts) == 3:
                width, height = int(parts[1]), int(parts[2])
                if not (1 <= width <= 4096 and 1 <= height <= 2048):
                    raise ValueError("popup shadow dimensions out of bounds")
                source = popup_shadow_image(width, height)
            elif parts[0] == "icon" and len(parts) == 2:
                if parts[1] not in {
                    "download.png",
                    "folder.png",
                    "link-2.png",
                    "play.png",
                    "activity.png",
                    "settings.png",
                }:
                    raise ValueError("unknown icon")
                with Image.open(
                    SOURCE / "assets" / "icons" / "lucide" / parts[1]
                ) as original:
                    alpha = original.getchannel("A")
                    if max(original.size) > 64:
                        alpha = alpha.resize((64, 64), Image.Resampling.LANCZOS)
                    source = Image.new("RGBA", alpha.size, THEME["icon"])
                    source.putalpha(alpha)
            elif parts[0] == "activity-icon" and len(parts) == 2:
                tone = {
                    "circle-dashed": THEME["accent"],
                    "check": THEME["success"],
                    "warning": THEME["warning"],
                    "error": THEME["danger"],
                }.get(parts[1])
                if tone is None:
                    raise ValueError("unknown activity icon")
                filename = "check.png" if parts[1] == "check" else "circle-dashed.png"
                with Image.open(
                    SOURCE / "assets" / "icons" / "lucide" / filename
                ) as original:
                    source = Image.new("RGBA", original.size, tone)
                    source.putalpha(original.getchannel("A"))
            else:
                raise ValueError("unknown material request")
            image = qt_image(source)
            if len(self.images) > 512:
                self.images.clear()
            self.images[image_id] = image
        size.setWidth(image.width())
        size.setHeight(image.height())
        return image


def _system_reduced_motion() -> bool:
    """Read the macOS accessibility preference without changing system state."""
    if sys.platform != "darwin":
        return False
    try:
        appkit = importlib.import_module("AppKit")
        return bool(
            appkit.NSWorkspace.sharedWorkspace().accessibilityDisplayShouldReduceMotion()
        )
    except (ImportError, AttributeError, RuntimeError):
        return False


class Bridge(QObject):
    pointerGestureEnded = Signal()
    outputFolderRecoveryRequested = Signal(str)
    statusChanged = Signal()
    operationFeedback = Signal(str)
    libraryRemovalRequested = Signal()
    outputPathChanged = Signal()
    selectionChanged = Signal()
    issueRetrySettingsRequested = Signal()
    progressChanged = Signal()
    runningChanged = Signal()
    historyChanged = Signal()
    librarySceneChanged = Signal()
    activityChanged = Signal()
    runDeckChanged = Signal()
    forgePreviewChanged = Signal()
    exportModeChanged = Signal()
    outputFormatChanged = Signal()
    qualityChanged = Signal()
    playbackUrlChanged = Signal()
    playerSceneChanged = Signal()
    watchSceneChanged = Signal()
    watchProgressChanged = Signal(str)
    artworkChanged = Signal()
    playbackPreviewsChanged = Signal()
    playbackRequested = Signal(int)
    playbackSeekRequested = Signal(float)
    librarySearchChanged = Signal()
    activeSearchChanged = Signal()
    libraryTypeChanged = Signal()
    localChanged = Signal()
    downloadOptionsChanged = Signal()
    nvencAvailableChanged = Signal()
    exportSettingsChanged = Signal()
    extraTagsChanged = Signal()
    appearanceChanged = Signal()
    themeRevisionChanged = Signal()
    missingMediaChanged = Signal()
    missingMediaRequested = Signal()
    sourcePrepared = Signal(str)
    relinkChanged = Signal()
    folderRelinkRequested = Signal(str)
    fileRelinkRequested = Signal(str)
    batchListChanged = Signal()
    sourceAccepted = Signal()
    cookieAccessChanged = Signal()
    libraryCategoryChanged = Signal()
    librarySortChanged = Signal()
    importBusyChanged = Signal()
    storageChanged = Signal()
    annotationChanged = Signal()
    analyticsChanged = Signal()
    analyticsPromptRequested = Signal()
    updateChanged = Signal()
    fileActionChanged = Signal()
    fileActionRequested = Signal()
    supportChanged = Signal()
    supportRequested = Signal()
    editorialChanged = Signal()
    editorialRequested = Signal()
    socialInvitationRequested = Signal()

    def __init__(self, event_log: Path | None) -> None:
        super().__init__()
        self._runtime = DownloadRuntime()
        self._download_poll_failed = False
        self._run_menu_identity_job: Any | None = None
        self._run_menu_identity_token = ""  # nosec B105 - empty UI identity sentinel
        self._run_menu_admitted_job: Any | None = None
        self._run_controls = RunControlPresentation()
        self._run_control_events = RunControlEvents()
        self._runtime.events = self._run_control_events
        self._selected_run_key = ""
        self._recent_interrupted_run_id = ""
        self._artwork_records: dict[str, dict[str, Any] | None] = {}
        self._artwork_history_id: int | None = None
        self._artwork_history_count = -1
        self.historyChanged.connect(self._clear_artwork_records)
        self.historyChanged.connect(self.playerSceneChanged.emit)
        self.historyChanged.connect(self.watchSceneChanged.emit)
        self.historyChanged.connect(self.librarySceneChanged.emit)
        self.librarySearchChanged.connect(self.activeSearchChanged.emit)
        self.historyChanged.connect(self.activeSearchChanged.emit)
        self.selectionChanged.connect(self.activeSearchChanged.emit)
        self.historyChanged.connect(self.runDeckChanged.emit)
        self._support = QtSupportSession(self._runtime.history_path.parent)
        self._latest_failure: FailureContext | None = None
        self._engagement = EngagementState(
            installation_state_path(data_dir=self._runtime.history_path.parent)
        )
        self._installation_path = installation_state_path(
            data_dir=self._runtime.history_path.parent
        )
        self._cloud_work = ArchiveWorkOwner()
        self._cloud_seen_attempted = False
        self._cloud_seen_install_id = ""
        self._social_invitation_open = False
        self._social_idle_since = time.monotonic()
        self._editorial_kind = ""
        self._editorial_slides: tuple[FeatureHighlight, ...] = ()
        self._activity_log_path = diagnostics_dir() / "activity.log"
        prepare_activity_log(self._activity_log_path)
        self._activity_log_text = load_activity_log_tail(self._activity_log_path)
        self._forge_activity = ForgeActivityProjection()
        self._forge_run_id = ""
        self._forge_technical = ""
        self._append_activity_line(
            "Session started "
            + datetime.now(timezone.utc).isoformat(timespec="seconds")
        )
        self._analytics = QtAnalyticsSession(
            application_data_dir(), __version__, self._runtime.recovery
        )
        self._runtime.product_telemetry = self._analytics.telemetry
        self._analytics_allowed = self._analytics.allowed
        self._analytics_snapshot_sent = False
        self._updates = QtUpdateSession(__version__)
        self._files = QtLibraryFiles(self._runtime.history_path)
        self._import_work = ArchiveWorkOwner()
        self._relink = QtRelinkSession(self._runtime.history_path)
        self._presentation_probe: QtPresentationProbe | None = None
        self._relink_operation: Any | None = None
        self._availability_work = ArchiveWorkOwner()
        self._availability_requests: list[tuple[str, Any]] = []
        self._folder_listing_pending = ""
        self._folder_listing_error = False
        self._missing_files: dict[str, str] = {}
        self._availability_checked = False
        self._availability_error = False
        self._media_recovery = LibraryMediaRecoveryOwner()
        self._missing_media: dict[str, str] = {}
        self._missing_plan: LibraryMediaRecoveryPlan | None = None
        self._missing_fingerprint = ""
        self._recovery_source_url = ""
        self._import_pending = False
        self._import_request_count = 0
        self._import_started_at = 0.0
        self._import_operation: Any | None = None
        self._storage = StorageCapacityOwner()
        self._storage_snapshot = self._storage.snapshot
        self._artwork = QtArtwork(self._runtime.history_path.parent / "artwork")
        self._artwork_revision = 0
        self._files.refresh_recovery()
        self._file_action_busy = self._files.uncertain
        if self._files.uncertain and self._runtime.recovery_notice is None:
            self._runtime.recovery_notice = (
                "Library file recovery must finish before new downloads."
            )
        self._runtime.resume_queued()
        self._window: Any | None = None
        self._pointer_press: tuple[QWindow, QPointF] | None = None
        self._input_application = QGuiApplication.instance()
        self._annotations_writable = True
        self._annotations = LibraryAnnotationsOwner(
            self._runtime.history_path.parent / "library-annotations.json",
            diagnostic=lambda _message: setattr(self, "_annotations_writable", False),
        )
        self._annotations.load()
        self._library_projection = LibraryProjectionOwner()
        self._metadata = QtMetadataPreview(
            getattr(self._runtime, "provider_network", ProviderNetworkCoordinator())
        )
        self._metadata.product_telemetry = self._analytics.telemetry
        self._metadata_preview_record: dict[str, Any] = {}
        self._metadata_preview_info: dict[str, Any] | None = None
        self._metadata_pending_run_id = ""
        self._preview_download_info: dict[str, Any] | None = None
        self._annotation_owner = ""
        self._library_detail_owner = ""
        self._folder_inspector_owner = ""
        self._folder_inspector_key = ""
        self._folder_inspector_versions: list[dict[str, str]] = []
        self._folder_file_path = ""
        self._folder_file_owner = ""
        self._folder_file_detail_text = ""
        self._remove_run_request: tuple[Any, tuple[str, ...]] | None = None
        self._issue_run_id = ""
        self._missing_issue_owner = ""
        self._missing_retry_run_id = ""
        self._pending_folder_missing_owner = ""
        self._issue_live_phase = ""
        self._issue_settings: dict[str, Any] = {}
        self._library_detail_origin: tuple[str, str, str] | None = None
        self._pending_library_removal: tuple[str, str] | None = None
        self._annotation_values = {"note": "", "tags": "", "category": ""}
        self._local = LocalConversionRuntime()
        self._local.product_telemetry = self._analytics.telemetry
        self._playback_progress = PlaybackProgressOwner(
            self._runtime.history_path.parent / "watch-progress.json"
        )
        self._playback_progress.load()
        self._playback_binding: PlaybackProgressBinding | None = None
        self._playback_path: Path | None = None
        self._playback_record: dict[str, Any] | None = None
        self._previews = QtPreviewSession(DownloaderApp._find_ffmpeg())
        self._subtitles = SubtitleSession(DownloaderApp._find_ffmpeg(), self)
        self._playback_position = 0.0
        self._playback_duration = 0.0
        self._playback_status: PlaybackStatus = "Ready"
        self._playback_recorded = False
        self._playback_operation: BoundProductOperation | None = None
        self._playback_phases: set[str] = set()
        self._playback_started_at = time.monotonic()
        self._playback_output_type = ""
        self._playback_chapters: list[dict[str, Any]] = []
        self._playback_heatmap: list[dict[str, float]] = []
        self._playback_generation = 0
        self._playback_retained_frame = QVideoFrame()
        self._playback_frame_owner = ""
        self._playback_frame_generation = -1
        self._playback_frame_url = ""
        self._watch_queue_observations: dict[str, Any] = {}
        self._watch_queue = WatchQueueOwner(
            records=lambda: self._runtime.history,
            open_record=self._open_queued_watch_record,
            schedule=lambda callback: QTimer.singleShot(0, callback),
            observe=self._record_watch_queue_operation,
            unavailable=lambda: self._set_status("Queued media is unavailable."),
        )
        self._settings_path = settings_file_path()
        try:
            self._settings = migrate_export_preferences(
                load_settings(self._settings_path)
            )
            self._settings_writable = True
        except SettingsError:
            self._settings = {}
            self._settings_writable = False
        selection = apply_theme_selection(
            self._settings.get("appearance_theme", DEFAULT_THEME_NAME),
            self._settings.get("custom_accent", "#7170ff"),
        )
        self._appearance_theme = selection.name
        self._custom_accent = selection.custom_accent
        self._theme_revision = 0
        self._theme_engine: QQmlApplicationEngine | None = None
        self._theme_materials: Materials | None = None
        self._theme_owner = ThemeRenderOwner(self._render_theme)
        defaults = DownloadPreferences()
        self._nvenc_available = False
        self._saved_nvenc_preference = self._settings.get("use_nvenc") is True
        preference_values: dict[str, bool] = {}
        for preference_field in fields(DownloadPreferences):
            value = self._settings.get(preference_field.name)
            preference_values[preference_field.name] = (
                value
                if isinstance(value, bool)
                else getattr(defaults, preference_field.name)
            )
        preferences = DownloadPreferences(**preference_values)
        self._download_preferences = (
            replace(preferences, use_nvenc=False)
            if preferences.use_nvenc
            else preferences
        )
        try:
            self._translated_subtitle_language = translated_subtitle_language(
                self._settings.get("translated_subtitle_language")
            )
        except ValueError:
            self._translated_subtitle_language = None
        self._nvenc_probe: QProcess | None = None
        if sys.platform == "win32":
            QTimer.singleShot(0, self._start_nvenc_probe)
        self._manual_values = {
            key: str(value)
            if (value := self._settings.get(key)) is not None
            else default
            for key, default in {
                "manual_rate_control": "CBR",
                "manual_crf": "21",
                "manual_video_bitrate": "10000",
                "manual_audio_bitrate": "320",
                "manual_audio_codec": "AAC",
                "manual_sample_rate": "48000",
                "manual_channels": "Stereo",
                "manual_preset": "medium",
            }.items()
        }
        self._mp3_values: dict[str, str | bool] = {
            "mp3_quality": str(
                self._settings.get("mp3_quality", "Maximum — 320 kbps CBR")
            ),
            "mp3_sample_rate": str(
                self._settings.get("mp3_sample_rate", "Preserve source")
            ),
            "mp3_channels": str(self._settings.get("mp3_channels", "Preserve source")),
            "mp3_cover_art_mode": str(
                self._settings.get("mp3_cover_art_mode", "No Art")
            ),
            "mp3_embed_metadata": self._settings.get("mp3_embed_metadata") is not False,
        }
        if self._mp3_values["mp3_cover_art_mode"] == "Custom art":
            self._mp3_values["mp3_cover_art_mode"] = "No Art"
        self._mp3_custom_cover: Path | None = None
        self._status = self._runtime.recovery_notice or (
            "Settings need attention before changes can be saved."
            if not self._settings_writable
            else "Ready"
        )
        saved_output = str(self._settings.get("output_dir") or "")
        try:
            saved_output_available = (
                bool(saved_output)
                and Path(saved_output).is_absolute()
                and Path(saved_output).is_dir()
            )
        except OSError:
            # Keep the chosen path when a provider/permission probe fails. Opening
            # the app must not require access to every retained output folder;
            # download admission still validates it before writing any media.
            saved_output_available = True
            self._status = (
                "The saved output folder is unavailable. Choose another folder "
                "before starting a download."
            )
        self._output_path = (
            saved_output if saved_output_available else str(Path.home() / "Downloads")
        )
        self._selection = "Forge"
        self._progress = 0.0
        saved_mode = str(self._settings.get("export_mode") or "Everyday")
        self._export_mode = (
            saved_mode
            if saved_mode in {mode.value for mode in ExportMode}
            else "Everyday"
        )
        saved_format = str(self._settings.get("output_type") or "MP4")
        self._output_format = (
            saved_format
            if saved_format in {item.value for item in OutputType}
            else "MP4"
        )
        saved_quality = str(self._settings.get("quality") or "1080p Full HD")
        self._quality = (
            saved_quality if saved_quality in QUALITY_OPTIONS else "1080p Full HD"
        )
        self._playback_url = QUrl()
        self._library_search = ""
        self._library_type = LIBRARY_ALL_MEDIA
        self._library_category = LIBRARY_ALL_CATEGORIES
        self._library_scene_route = "home"
        self._library_history: list[tuple[str, str, str]] = []
        self._library_detail_from_watch = False
        self._folder_browser = ArchiveBrowserModel()
        self._detail_versions: list[dict[str, str]] = []
        self._library_sort = "recent"
        self._library_group_key = ""
        self._library_group_kind = ""
        self._watch_scene_route = "home"
        self._watch_group_key = ""
        self._watch_group_kind = ""
        self._watch_search = ""
        self._watch_history: list[tuple[str, str, str, str]] = []
        self._playback_origin_selection = "Watch"
        self._watch_hero_seen_key = ""
        self._local_audio = ""
        self._local_image = ""
        self._local_profile = LOCAL_VIDEO_PROFILE_OPTIONS[0]
        self._local_progress = ""
        self._local_running = False
        self._composer_resume_run_id = ""
        self._batch_path = ""
        self._batch_snapshot_admitted = False
        self._batch_path_checked_at = 0.0
        self._batch_urls: list[str] = []
        self._batch_name = ""
        self._extra_tags = ""
        self._cookie_source = CookieSource.PUBLIC
        self._cookie_browser = ""
        self._cookie_file: Path | None = None
        self._event_log = event_log
        self._closed = False
        if self._input_application is not None:
            self._input_application.installEventFilter(self)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._pump)
        self._timer.start(50)
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.timeout.connect(self._save_preferences)
        self._feedback_ready = True

    @property
    def _status(self) -> str:
        return self._status_text

    @_status.setter
    def _status(self, message: str) -> None:
        # User actions have one feedback channel. Execution presentation comes
        # exclusively from the runtime's owner-bound active projection.
        self._status_text = message
        if getattr(self, "_feedback_ready", False):
            self.operationFeedback.emit(message)

    @Property(str, notify=statusChanged)
    def status(self) -> str:
        return self._status

    @Property(bool, notify=analyticsChanged)
    def analyticsAvailable(self) -> bool:
        return self._analytics.owner is not None

    @Property(bool, notify=analyticsChanged)
    def analyticsAllowed(self) -> bool:
        return self._analytics.allowed

    @Property(str, notify=updateChanged)
    def updateStatus(self) -> str:
        return self._updates.status

    @Property(bool, notify=updateChanged)
    def updateBusy(self) -> bool:
        return self._updates.busy

    @Property(bool, notify=updateChanged)
    def updateRestartPending(self) -> bool:
        return self._updates.pending_install or self._updates.handoff_started

    @Property(str, notify=updateChanged)
    def updateStage(self) -> str:
        return self._updates.stage

    @Property(bool, notify=updateChanged)
    def updateAvailable(self) -> bool:
        return self._updates.available

    @Property(bool, notify=updateChanged)
    def updateManualAvailable(self) -> bool:
        return self._updates.manual

    @Property(bool, notify=updateChanged)
    def updateReady(self) -> bool:
        return self._updates.ready is not None

    @Property(bool, notify=updateChanged)
    def updateRecovery(self) -> bool:
        return self._updates.recovery

    @Property(str, notify=fileActionChanged)
    def fileActionStatus(self) -> str:
        message = self._files.status
        if self._files.phase == "preview" and self._files.plan is not None:
            paths = [
                str(artifact.path)
                for item in self._files.plan.items
                if item.state == "ready"
                for artifact in item.artifacts
            ]
            if paths:
                message += "\n\nVerified owned files:\n" + "\n".join(paths)
            if self._remove_run_request:
                message += "\n\nThe run is removed only after all selected entries are cleared. Unverified files and unrelated folders are kept."
        return message

    @Property(str, notify=fileActionChanged)
    def fileActionName(self) -> str:
        return self._files.action

    @Property(bool, notify=fileActionChanged)
    def fileActionBusy(self) -> bool:
        return self._files.phase in {"checking", "working"}

    @Property(bool, notify=fileActionChanged)
    def fileActionEligible(self) -> bool:
        return self._files.phase == "preview" and (
            self._files.eligible
            or bool(self._remove_run_request and not self._remove_run_request[1])
        )

    @Property(str, notify=fileActionChanged)
    def fileActionReviewOwner(self) -> str:
        plan = self._files.plan
        if self._files.phase != "preview" or self._files.eligible or plan is None:
            return ""
        if len(plan.items) != 1:
            return ""
        selected = plan.items[0]
        item = self._saved_item_for_owner(selected.owner)
        if item is None or record_fingerprint(item) != selected.fingerprint:
            return ""
        return selected.owner

    @Property(bool, notify=fileActionChanged)
    def fileActionRecovery(self) -> bool:
        return self._files.phase == "recovery"

    @Property(bool, notify=fileActionChanged)
    def fileActionCanFinish(self) -> bool:
        return self._files.can_finish

    @Property(_QVARIANT_MAP, notify=missingMediaChanged)
    def missingMedia(self) -> dict[str, str]:
        return dict(self._missing_media)

    @Property(_QVARIANT_MAP, notify=relinkChanged)
    def relinkInfo(self) -> dict[str, str | bool | int]:
        return {
            "phase": self._relink.phase,
            "status": self._relink.status,
            "owner": self._relink.owner,
            "source": self._relink.source,
            "destination": self._relink.destination,
            "eligible": self._relink.eligible,
            "mode": self._relink.mode,
            "readyCount": len(self._relink.ready_indices),
            "selectedCount": len(self._relink.selected),
        }

    def _can_begin_relink(self) -> bool:
        if (
            self._runtime.active_job is not None
            or self._runtime.busy
            or self._runtime.queued
            or self._local_running
            or self._import_pending
            or self._file_action_busy
            or self._files.busy
            or self._runtime.recovery_notice
        ):
            self._status = "Finish active work before changing saved locations."
            self.statusChanged.emit()
            return False
        return True

    @Slot(str, QUrl, result=bool)
    def beginRelink(self, owner: str, url: QUrl) -> bool:
        if not url.isLocalFile() or not self._can_begin_relink():
            return False
        started = self._relink.begin(
            owner, Path(url.toLocalFile()), self._runtime.history
        )
        if started:
            self._relink_operation = bind_operation(
                self._analytics.telemetry,
                "archive_relink_operation",
                operation_key=str(uuid.uuid4()),
            )
            operation(
                self._analytics.telemetry,
                "archive_relink_operation",
                "requested",
                self._relink_operation,
                {"relink_mode": "file", "item_count": "1"},
            )
            self.relinkChanged.emit()
        return started

    @Slot(str, QUrl, result=bool)
    def beginFolderRelink(self, captured_path: str, url: QUrl) -> bool:
        if not url.isLocalFile() or not self._can_begin_relink():
            return False
        self._reconcile_folder_browser()
        model = self._folder_browser
        if (
            model.mode != "folders"
            or model.path is None
            or str(model.path) != captured_path
        ):
            return False
        try:
            destination = ArchivePath.parse(url.toLocalFile())
        except ValueError:
            return False
        owners = tuple(
            history_archive_owner(dict(model.records[index]))
            for index in model.folder_relink_indices()
        )
        try:
            started = self._relink.begin_folder(
                model.path, destination, owners, self._runtime.history
            )
        except ValueError:
            return False
        if started:
            self._relink_operation = bind_operation(
                self._analytics.telemetry,
                "archive_relink_operation",
                operation_key=str(uuid.uuid4()),
            )
            operation(
                self._analytics.telemetry,
                "archive_relink_operation",
                "requested",
                self._relink_operation,
                {"relink_mode": "folder", "item_count": str(len(owners))},
            )
            self.relinkChanged.emit()
        return started

    @Slot(str)
    def requestFolderRelink(self, path: str) -> None:
        self._reconcile_folder_browser()
        model = self._folder_browser
        if (
            self._selection == "Library"
            and model.mode == "folders"
            and (model.path is not None and str(model.path) == path)
        ):
            self.folderRelinkRequested.emit(path)

    @Slot(result=bool)
    def openLibraryCurrentFolder(self) -> bool:
        self._reconcile_folder_browser()
        model = self._folder_browser
        if self._selection != "Library" or model.mode != "folders":
            return False
        path = model.path
        if path is None or not Path(str(path)).is_dir():
            return False
        return QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    @Slot(result=bool)
    def openSelectedFolderFileLocation(self) -> bool:
        if self._selection != "Library" or self._folder_browser.mode != "folders":
            return False
        path = Path(self._folder_file_path)
        if not self._folder_file_path or not path.parent.is_dir():
            return False
        return QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.parent)))

    @Property(_QVARIANT_MAP, notify=historyChanged)
    def inspectorRecoveryActions(self) -> dict[str, Any]:
        """Offer actions for the exact displayed owner, not a mutable list index."""
        if self._library_scene_route != "folders" or not self._folder_inspector_key:
            return {}
        item = self.libraryFolderInspector
        job = self._issue_job(self._issue_run_id) if self._issue_run_id else None
        location = (
            str(job.output_dir) if job is not None else str(item.get("location") or "")
        )
        path = Path(location) if location else None
        folder = (
            path
            if job is not None or item.get("folder")
            else path.parent
            if path
            else None
        )
        try:
            can_open_location = folder is not None and folder.is_dir()
        except OSError:
            can_open_location = False
        return {
            "selectionKey": self._folder_inspector_key,
            "location": location,
            "canOpenLocation": can_open_location,
            "dismissRunId": job.run_id
            if job is not None
            and job in self._runtime.recovered
            and job.terminal_status
            in {"Failed", "Stopped", "Skipped", "Paused", "Partial"}
            else "",
            "savedOwner": str(item.get("owner") or self._missing_issue_owner or ""),
        }

    @Slot(str, result=bool)
    def openInspectorLocation(self, selection_key: str) -> bool:
        if self._selection != "Library" or selection_key != self._folder_inspector_key:
            return False
        actions = self.inspectorRecoveryActions
        if not actions.get("canOpenLocation"):
            return False
        path = Path(str(actions["location"]))
        job = self._issue_job(self._issue_run_id) if self._issue_run_id else None
        if job is None and not self.libraryFolderInspector.get("folder"):
            path = path.parent
        return QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    @Slot(str, result=bool)
    def requestInspectorLibraryRemoval(self, selection_key: str) -> bool:
        if self._selection != "Library" or selection_key != self._folder_inspector_key:
            return False
        actions = self.inspectorRecoveryActions
        if actions.get("dismissRunId"):
            return self.requestRunRemoval(str(actions["dismissRunId"]))
        owner = str(actions.get("savedOwner") or "")
        if not owner or not self.startFileActions("delete", [owner], QUrl()):
            return False
        self.fileActionRequested.emit()
        return True

    @Slot(str, str, str, result=bool)
    def saveSelectedFolderMetadata(
        self, owner: str, description: str, tags_text: str
    ) -> bool:
        if (
            self._folder_browser.mode != "folders"
            or owner != self._folder_file_owner
            or Path(self._folder_file_path).name != "metadata.json"
            or not self._annotations_writable
        ):
            return False
        row = next(
            (
                item
                for item in self._projected_library()
                if history_archive_owner(item) == owner
            ),
            None,
        )
        if row is None or len(description) > MAX_NOTE_CHARS:
            return False
        tags = tuple(part.strip() for part in tags_text.split(",") if part.strip())
        if (
            len(tags) > MAX_TAGS
            or any(len(tag) > MAX_TAG_CHARS for tag in tags)
            or len({tag.casefold() for tag in tags}) != len(tags)
        ):
            self._set_status("Check the tags and try again.")
            return False
        annotation_owner = str(row.get(ANNOTATION_OWNER_KEY) or "")
        if not annotation_owner:
            return False
        try:
            self._annotations.replace(
                annotation_owner,
                replace(
                    self._annotations.annotation_for(annotation_owner),
                    description=description,
                    tags=tags,
                ),
            )
        except LibraryAnnotationsError as exc:
            self._set_status(str(exc))
            return False
        self._set_status("Tags and description saved.")
        self.historyChanged.emit()
        return True

    @Slot(result=bool)
    def acceptRelink(self) -> bool:
        if (
            self._runtime.active_job is not None
            or self._runtime.busy
            or self._runtime.queued
            or self._local_running
            or self._import_pending
            or self._file_action_busy
            or self._files.busy
        ):
            return False
        accepted = self._relink.accept(self._runtime.history)
        if accepted:
            operation(
                self._analytics.telemetry,
                "archive_relink_operation",
                "commit_requested",
                self._relink_operation,
                {"item_count": str(len(self._relink.ready_indices))},
            )
        self.relinkChanged.emit()
        return accepted

    @Slot()
    def cancelRelink(self) -> None:
        if self._relink.active and self._relink.phase != "working":
            operation(
                self._analytics.telemetry,
                "archive_relink_operation",
                "cancelled",
                self._relink_operation,
            )
            self._relink_operation = None
        self._relink.cancel()
        self.relinkChanged.emit()

    def _current_missing_record(self) -> dict[str, Any] | None:
        owner = self._missing_media.get("owner", "")
        item = self._saved_item_for_owner(owner)
        return (
            item
            if item is not None
            and record_fingerprint(item) == self._missing_fingerprint
            else None
        )

    @Slot(result=bool)
    @Slot(QUrl, result=bool)
    def openMissingInForge(self, folder: QUrl | None = None) -> bool:
        plan = self._missing_plan
        item = self._current_missing_record()
        if plan is None or item is None:
            return False
        destination = plan.destination
        if plan.requires_destination_choice:
            if folder is None or not folder.isLocalFile():
                return False
            destination = Path(folder.toLocalFile())
            if not destination.is_dir():
                return False
        source_url = (
            plan.job.url if plan.job is not None else canonical_youtube_url(item)
        )
        if not source_url:
            return False
        self._media_recovery.clear_destination()
        self._recovery_source_url = source_url
        if destination is not None:
            self._media_recovery.prepare_destination(
                source_url,
                destination,
                export_mode=ExportMode.EVERYDAY if plan.preset_migrated else None,
            )
        self.setOutputFormat(metadata_output_type(item).value)
        self.outputPathChanged.emit()
        self.exportModeChanged.emit()
        self.select("Forge")
        self.sourcePrepared.emit(source_url)
        self._status = (
            "Review the saved destination and output settings, then Forge again."
        )
        self.statusChanged.emit()
        return True

    @Slot(result=bool)
    @Slot(QUrl, result=bool)
    def redownloadMissingTo(self, folder: QUrl | None = None) -> bool:
        plan = self._missing_plan
        item = self._current_missing_record()
        if plan is None or item is None or not plan.can_redownload:
            return False
        if self._relink.active or self._file_action_busy or self._import_pending:
            return False
        if plan.requires_destination_choice:
            if folder is None or not folder.isLocalFile():
                return False
            try:
                plan = self._media_recovery.with_destination(
                    plan, Path(folder.toLocalFile())
                )
            except ValueError:
                return False
        job = plan.job
        if job is None:
            return False
        job.recovery_reason = "missing_media"
        job.annotation_source_owner = plan.previous_annotation_owner
        try:
            self._runtime.start_job(job)
        except (OSError, RuntimeError, RunStateError, ValueError) as exc:
            self._status = str(exc)
            self.statusChanged.emit()
            return False
        self._record_update_feature(
            "missing_media", "accepted", {"input_kind": "single"}
        )
        if plan.preset_migrated:
            self._record_update_feature(
                "missing_media",
                "preset_migrated",
                {"preset": "everyday", "input_kind": "single"},
            )
        # Keep the missing Library card until a replacement has been committed.
        # The history owner's record_file removes it atomically on success.
        self._status = "Redownloading this saved video with its output profile."
        self.select("Forge")
        self.runningChanged.emit()
        self.activityChanged.emit()
        self.statusChanged.emit()
        return True

    @Slot(str, str, QUrl, result=bool)
    def startFileAction(self, action: str, owner: str, destination: QUrl) -> bool:
        return self.startFileActions(action, [owner], destination)

    @Slot(str, "QVariantList", QUrl, result=bool)
    def startFileActions(
        self, action: str, owners: list[str], destination: QUrl
    ) -> bool:
        if (
            not owners
            or any(not isinstance(owner, str) or not owner for owner in owners)
            or len(owners) != len(set(owners))
        ):
            self._status = "Select saved media again before changing files."
            self.statusChanged.emit()
            return False
        if self._relink.active:
            self._status = "Finish the saved-location review first."
            self.statusChanged.emit()
            return False
        pending = self._files.refresh_recovery()
        self._file_action_busy = self._files.uncertain
        if pending:
            self.fileActionChanged.emit()
            return True
        self._remove_run_request = None
        items = [self._saved_item_for_owner(owner) for owner in owners]
        if any(item is None for item in items):
            self._status = "Selected Library items changed. Select them again."
        elif (
            self._runtime.active_job is not None
            or self._runtime.busy
            or self._runtime.queued
            or self._local_running
            or self._import_pending
            or self._file_action_busy
            or self._runtime.recovery_notice
        ):
            self._status = "Finish active work before changing saved media."
        elif self._playback_path is not None and any(
            item is not None and history_output_path(item) == self._playback_path
            for item in items
        ):
            self._status = "Close Watch playback before changing this media."
        else:
            folder = Path(destination.toLocalFile()) if action == "move" else None
            if self._files.begin(
                action, owners, self._runtime.history, destination=folder
            ):
                self.fileActionChanged.emit()
                return True
            self._status = self._files.status or "This file action could not start."
        self.statusChanged.emit()
        return False

    @Slot(result=bool)
    def confirmFileAction(self) -> bool:
        if (
            self._relink.active
            or self._runtime.active_job is not None
            or self._runtime.busy
            or self._runtime.queued
            or self._local_running
            or self._import_pending
            or self._file_action_busy
        ):
            return False
        if self._remove_run_request:
            job, owners = self._remove_run_request
            if (
                self._issue_job(job.run_id) is not job
                or job not in self._runtime.recovered
            ):
                self._files.phase = "error"
                self._files.status = "Run changed. Select it again. No files changed."
                self._remove_run_request = None
                self.fileActionChanged.emit()
                return False
            current_owners = tuple(
                history_archive_owner(row)
                for row in self._runtime.history
                if row.get("vodforge_run_id") == job.run_id
            )
            if current_owners != owners:
                self._files.phase = "error"
                self._files.status = (
                    "Run files changed. Review Remove again. No files changed."
                )
                self._remove_run_request = None
                self.fileActionChanged.emit()
                return False
            if not owners and self._files.phase == "preview":
                self._files.phase = "done"
                self._finish_run_removal()
                self.fileActionChanged.emit()
                return True
        started = self._files.confirm(self._runtime.history)
        if started:
            self._file_action_busy = True
        self.fileActionChanged.emit()
        return started

    @Slot(bool, result=bool)
    def recoverFileAction(self, finish: bool) -> bool:
        if self._relink.active:
            return False
        started = self._files.recover(finish=finish)
        if started:
            self._file_action_busy = True
            self.fileActionChanged.emit()
        return started

    @Slot()
    def checkForUpdates(self) -> None:
        self._updates.telemetry = self._analytics.telemetry
        if self._updates.check():
            self.updateChanged.emit()

    @Slot()
    def downloadUpdate(self) -> None:
        self._updates.telemetry = self._analytics.telemetry
        if self._updates.download(install_when_ready=True):
            self._record_update_feature("updater", "download_started")
            self.updateChanged.emit()

    @Slot()
    def repairUpdate(self) -> None:
        self._updates.telemetry = self._analytics.telemetry
        if self._updates.download(repair=True, install_when_ready=True):
            self._record_update_feature("guidance", "recovery_selected")
            self._record_update_feature("updater", "repair_started")
            self.updateChanged.emit()

    def _record_update_feature(
        self, feature: str, action: str, dimensions: dict[str, str] | None = None
    ) -> None:
        telemetry = self._analytics.telemetry
        if telemetry is None:
            return
        try:
            telemetry.record_feature(feature, action, dimensions=dimensions)
            if (feature, action) in {
                ("archive", "folders"),
                ("archive", "all_media"),
                ("archive", "issues"),
                ("archive", "folder_opened"),
                ("watch", "opened"),
                ("watch", "channel_opened"),
                ("library", "opened"),
                ("library", "selected"),
            }:
                operation(
                    telemetry,
                    "navigation_operation",
                    "visited",
                    bind_operation(
                        telemetry,
                        "navigation_operation",
                        operation_key=str(uuid.uuid4()),
                    ),
                    {
                        "navigation_feature": feature,
                        "navigation_action": action,
                        **(dimensions or {}),
                    },
                )
        except (OSError, ValueError):
            pass

    def _auto_check_updates(self) -> None:
        if self._updates.busy:
            QTimer.singleShot(30 * 1000, self._auto_check_updates)
            return
        self._updates.telemetry = self._analytics.telemetry
        if self._updates.check(automatic=True):
            self.updateChanged.emit()
        QTimer.singleShot(6 * 60 * 60 * 1000, self._auto_check_updates)

    @Slot()
    def updateOfferShown(self) -> None:
        if self._updates.available or self._updates.manual or self._updates.ready:
            self._updates.observe("shown")

    @Slot(bool)
    def updateOfferClosed(self, explicitly_deferred: bool = False) -> None:
        if self._updates.available or self._updates.manual or self._updates.ready:
            self._updates.observe("deferred" if explicitly_deferred else "dismissed")

    @Slot()
    def openDownloadPage(self) -> None:
        opened = QDesktopServices.openUrl(QUrl(RELEASES_PAGE))
        self._updates.observe("manual_opened" if opened else "manual_failed")

    def _update_work_pending(self) -> bool:
        return bool(
            self._download_poll_failed
            or self._runtime.recovery_notice
            or self._runtime.active_job is not None
            or self._runtime.busy
            or self._runtime.queued
            or self._local_running
            or self._import_pending
            or self._file_action_busy
            or self._files.busy
            or self._files.uncertain
            or self._files.pending
            or self._relink.active
        )

    def _download_poll_can_resume(self) -> bool:
        # A failed poll may already have consumed an event or partly persisted a
        # terminal transition. Never infer idle from an empty event queue alone.
        if (
            self._runtime.active_job is not None
            or self._runtime.busy
            or self._runtime.queued
            or not self._runtime.events.empty()
        ):
            return False
        try:
            return (
                self._runtime.recovery.store.load() is None
                and not self._runtime.recovery.store.load_queued_jobs()
            )
        except (HistoryError, OSError, RunStateError, ValueError):
            return False

    @Slot()
    def installUpdate(self) -> None:
        window = self._window
        bounds = (
            (window.x(), window.y(), window.width(), window.height())
            if window is not None
            else None
        )
        telemetry = self._analytics.telemetry
        accepted = self._updates.install(
            downloads_busy=self._update_work_pending(),
            telemetry_permitted=telemetry is not None and telemetry.permitted(),
            window_bounds=bounds,
        )
        self.updateChanged.emit()
        if accepted:
            self._record_update_feature("updater", "handoff")
            QTimer.singleShot(250, QCoreApplication.quit)
        for action, dimensions in self._updates.take_observations():
            self._record_update_feature("updater", action, dimensions)

    @Slot()
    def startSession(self) -> None:
        self._analytics.start()

    @Slot(bool, result=bool)
    def chooseAnalytics(self, enabled: bool) -> bool:
        saved = self._analytics.choose(enabled)
        self._analytics_allowed = self._analytics.allowed
        self.analyticsChanged.emit()
        if self._analytics_allowed:
            self._record_settings_snapshot()
            self._analytics_snapshot_sent = True
            self._analytics.start_first_launch_delivery()
        else:
            self._analytics_snapshot_sent = False
        if not saved:
            self._status = (
                "Analytics choice could not be saved. Check the app data folder."
            )
            self.statusChanged.emit()
        else:
            QTimer.singleShot(6000, self._record_update_telemetry_receipt)
        return saved

    @Slot()
    def recordCloudCtaSeen(self) -> None:
        if not self._analytics.allowed or self._cloud_seen_attempted:
            return
        try:
            state = load_or_create_installation_state(self._installation_path)
        except (InstallationIdentityError, OSError, ValueError):
            return
        if state.cloud_seen_confirmed:
            self._cloud_seen_attempted = True
            return
        self._cloud_seen_install_id = state.install_id
        if (
            self._cloud_work.submit(
                "cloud_seen",
                lambda _cancelled: record_cloud_seen(state, app_version=__version__),
            )
            is not None
        ):
            self._cloud_seen_attempted = True

    @Slot()
    def openCloudEarlyAccess(self) -> None:
        try:
            state = load_or_create_installation_state(self._installation_path)
        except (InstallationIdentityError, OSError, ValueError):
            state = None
        destination = cloud_page_url(state.install_id if state is not None else None)
        if state is not None:
            threading.Thread(
                target=record_cloud_click,
                args=(state,),
                name="vodforge-qt-cloud-click",
                daemon=True,
            ).start()
        QDesktopServices.openUrl(QUrl(destination))

    def _record_update_telemetry_receipt(self) -> None:
        telemetry = self._analytics.telemetry
        if telemetry is None or not self._analytics.update_receipt_decided:
            return
        record_update_telemetry_receipts(
            telemetry,
            application_data_dir() / "updates",
            Path(sys.executable),
            inherited_receipt=os.environ.get("VODFORGE_UPDATE_RECEIPT"),
        )
        os.environ.pop("VODFORGE_UPDATE_RECEIPT", None)

    @Slot()
    def openPrivacy(self) -> None:
        QDesktopServices.openUrl(QUrl(f"{telemetry_site_origin()}/privacy/"))

    @Slot()
    def openSocialAccount(self) -> None:
        QDesktopServices.openUrl(QUrl("https://x.com/VODForge"))

    @Property(str, notify=outputPathChanged)
    def outputPath(self) -> str:
        if self._recovery_source_url:
            return self._media_recovery.destination_for(
                self._recovery_source_url, self._output_path
            )
        return self._output_path

    @Property(QUrl, notify=outputPathChanged)
    def outputFolderUrl(self) -> QUrl:
        """Give the chooser an existing user folder without changing the destination."""
        home = Path.home()
        for value in (self.outputPath, str(home / "Downloads"), str(home)):
            path = Path(value)
            try:
                if path.is_absolute() and path.is_dir():
                    return QUrl.fromLocalFile(str(path))
            except (OSError, ValueError):
                continue
        # Even if the home provider is temporarily unavailable, never supply a
        # relative/empty URL that lets the native dialog choose the app cwd.
        return QUrl.fromLocalFile(str(home))

    @Property(str, notify=selectionChanged)
    def selection(self) -> str:
        return self._selection

    @Property(float, notify=progressChanged)
    def progress(self) -> float:
        return self._progress

    @Property(bool, notify=runningChanged)
    def running(self) -> bool:
        return self._runtime.active_job is not None

    @Property(str, notify=exportModeChanged)
    def exportMode(self) -> str:
        if self._recovery_source_url:
            mode = self._media_recovery.export_mode_for(self._recovery_source_url)
            if mode is not None:
                return mode.value
        return self._export_mode

    @Property(str, notify=exportModeChanged)
    def exportModeLabel(self) -> str:
        return export_mode_display_name(self.exportMode)

    @Property(str, notify=outputFormatChanged)
    def outputFormat(self) -> str:
        return self._output_format

    @Property(str, notify=qualityChanged)
    def quality(self) -> str:
        return self._quality

    @Property(QUrl, notify=playbackUrlChanged)
    def playbackUrl(self) -> QUrl:
        return self._playback_url

    @Property(QObject, constant=True)
    def playbackCaptions(self) -> QObject:
        return self._subtitles

    @Property(_QVARIANT_LIST, notify=playbackUrlChanged)
    def playbackChapters(self) -> list[dict[str, Any]]:
        return list(self._playback_chapters)

    @Property(_QVARIANT_LIST, notify=playbackUrlChanged)
    def playbackHeatmap(self) -> list[dict[str, float]]:
        return list(self._playback_heatmap)

    @Property(_QVARIANT_LIST, notify=playbackPreviewsChanged)
    def playbackPreviews(self) -> list[dict[str, Any]]:
        return self._previews.records

    @Property(_QVARIANT_MAP, notify=playerSceneChanged)
    def playerScene(self) -> dict[str, Any]:
        snapshot = self._playback_record
        if snapshot is None:
            return {}
        records = self._projected_library()
        owner = history_archive_owner(snapshot)
        current = next(
            (
                row
                for row in records
                if str(row.get(PROJECTION_OWNER_KEY) or history_archive_owner(row))
                == owner
            ),
            snapshot,
        )
        plan = player_related_plan(records, current, self._watch_queue.remaining_keys)

        def cards(videos: tuple[Any, ...]) -> list[dict[str, Any]]:
            return [
                {
                    "title": video.title,
                    "owner": history_archive_owner(records[video.indices[0]]),
                    "creator": str(
                        records[video.indices[0]].get("channel")
                        or records[video.indices[0]].get("uploader")
                        or "Saved media"
                    ),
                    "type": str(
                        records[video.indices[0]].get("vodforge_output_type") or ""
                    ),
                    "artwork": self._artwork.request(
                        records[video.indices[0]], (244, 138), "media"
                    ),
                }
                for video in videos
            ]

        source, output = library_detail_facts(current)
        return {
            "owner": history_archive_owner(current),
            "title": str(current.get("title") or "Saved media"),
            "artwork": self._artwork.request(current, (244, 138), "media"),
            "creator": str(
                current.get("channel") or current.get("uploader") or "Unknown creator"
            ),
            "category": str(current.get("vodforge_user_category") or ""),
            "kind": watch_media_kind(current),
            "description": str(
                current.get("vodforge_user_description", current.get("description"))
                or ""
            ),
            "note": str(current.get("vodforge_user_note") or ""),
            "tags": [str(tag) for tag in current.get("vodforge_user_tags") or ()],
            "source": [{"label": label, "value": value} for label, value, _ in source],
            "output": [{"label": label, "value": value} for label, value, _ in output],
            "upNext": cards(plan.up_next),
            "recent": cards(plan.recent),
            "queued": self._watch_queue.remaining_keys is not None,
        }

    @Slot(str, result=bool)
    def playPlayerRelated(self, owner: str) -> bool:
        scene = self.playerScene
        if owner == scene.get("owner") or owner not in {
            row["owner"] for row in [*scene.get("upNext", []), *scene.get("recent", [])]
        }:
            return False
        item = self._saved_item_for_owner(owner)
        if item is None:
            return False
        key = queue_media_key(item)
        opened = (
            self._watch_queue.jump(key)
            if key in (self._watch_queue.remaining_keys or ())
            else self.openLibraryItem(self._runtime.history.index(item))
        )
        if opened:
            self._record_update_feature("player", "related_selected")
        return opened

    @Slot(str, result=bool)
    def detailsPlayerRelated(self, owner: str) -> bool:
        scene = self.playerScene
        if owner not in {
            row["owner"] for row in [*scene.get("upNext", []), *scene.get("recent", [])]
        }:
            return False
        opened = self.openWatchDetails(owner)
        if opened:
            self._record_update_feature("player", "related_details")
        return opened

    @Property(_QVARIANT_LIST, notify=historyChanged)
    def history(self) -> list[dict[str, Any]]:
        projected = self._projected_library()
        history_owners = {
            history_archive_owner(row): index
            for index, row in enumerate(self._runtime.history)
        }
        return [
            {
                "projectionIndex": index,
                "sourceIndex": history_owners.get(
                    str(item.get(PROJECTION_OWNER_KEY) or ""), -1
                ),
                "archiveOwner": str(item.get(PROJECTION_OWNER_KEY) or ""),
                "title": str(item.get("title") or "Untitled media"),
                "type": str(item.get("vodforge_output_type") or "MP4"),
                "category": str(item.get("vodforge_user_category") or ""),
                "status": str(
                    item.get("vodforge_terminal_status")
                    or item.get(RUN_STATUS_KEY)
                    or ""
                ),
            }
            for index in library_visible_indices(
                projected,
                self._library_type,
                self._library_search,
                self._library_category,
            )
            for item in [projected[index]]
        ]

    @Property(int, notify=historyChanged)
    def savedCount(self) -> int:
        return len(self._runtime.history)

    @Property(_QVARIANT_MAP, notify=librarySceneChanged)
    def libraryScene(self) -> dict[str, Any]:
        return library_scene(
            self._projected_library(),
            self._library_scene_route,
            self._library_group_key,
            self._library_group_kind,
            self._artwork.request
            if self._selection == "Library"
            else lambda _record, _size, _role: "",
            self._library_search,
            ""
            if self._library_category == LIBRARY_ALL_CATEGORIES
            else self._library_category,
            self._library_sort,
            media_type=self._library_type,
            defer_media_artwork=True,
            defer_group_artwork=True,
        )

    def _clear_artwork_records(self) -> None:
        self._artwork_records.clear()
        self._artwork_history_id = None
        self._artwork_history_count = -1

    def _artwork_record_for_owner(self, owner: str) -> dict[str, Any] | None:
        history = self._runtime.history
        history_id = id(history)
        if self._artwork_history_id != history_id or self._artwork_history_count != len(
            history
        ):
            records: dict[str, dict[str, Any] | None] = {}
            for record in history:
                key = history_archive_owner(record)
                records[key] = None if key in records else record
            self._artwork_records = records
            self._artwork_history_id = history_id
            self._artwork_history_count = len(history)
        return self._artwork_records.get(owner)

    @Slot(str, result=str)
    def mediaArtwork(self, owner: str) -> str:
        record = self._artwork_record_for_owner(owner)
        if not record or not record.get("vodforge_output_dir"):
            return ""
        return self._artwork.request(record, (320, 180), "media")

    @Property(int, notify=artworkChanged)
    def artworkRevision(self) -> int:
        return self._artwork_revision

    @Slot(str, result=str)
    def mediaArtworkState(self, owner: str) -> str:
        return self._artwork.state(owner, (320, 180), "media")

    @Slot(str, int, int, result=str)
    def sizedMediaArtworkState(self, owner: str, width: int, height: int) -> str:
        return self._artwork.state(owner, (width, height), "media")

    @Slot(str, str, result=str)
    def watchGroupArtwork(self, owner: str, kind: str) -> str:
        return self._group_artwork(owner, kind)

    @Slot(str, str, result=str)
    def groupArtworkState(self, owner: str, kind: str) -> str:
        if kind not in {"channel", "playlist", "collection"}:
            return "idle"
        return self._artwork.state(
            owner,
            (160, 160) if kind == "channel" else (480, 200),
            "avatar" if kind == "channel" else "playlist",
        )

    @Slot(str, result=str)
    def watchChannelBanner(self, owner: str) -> str:
        item = self._artwork_record_for_owner(owner)
        return self._artwork.request(item, (1100, 350), "banner") if item else ""

    @Slot(str, result=str)
    def watchChannelAvatar(self, owner: str) -> str:
        item = self._artwork_record_for_owner(owner)
        return self._artwork.request(item, (160, 160), "avatar") if item else ""

    @Slot(str, str, result=str)
    def libraryGroupArtwork(self, owner: str, kind: str) -> str:
        return self._group_artwork(owner, kind)

    def _group_artwork(self, owner: str, kind: str) -> str:
        if kind not in {"channel", "playlist", "collection"}:
            return ""
        item = self._artwork_record_for_owner(owner)
        if item is None:
            return ""
        return self._artwork.request(
            item,
            (160, 160) if kind == "channel" else (480, 200),
            "avatar" if kind == "channel" else "playlist",
        )

    @Property(_QVARIANT_MAP, notify=historyChanged)
    def libraryFolders(self) -> dict[str, Any]:
        self._reconcile_folder_browser()
        model = self._folder_browser
        return {
            "mode": model.mode,
            "selectedKey": self._folder_inspector_key,
            "path": str(model.path) if model.path is not None else "",
            "folderName": model.path.name if model.path is not None else "",
            "parentName": (
                model.parent_path.name
                if model.parent_path is not None
                else "Locations"
                if model.path is not None and len(model.locations) > 1
                else ""
            ),
            "canGoUp": model.parent_path is not None
            or model.path is not None
            and len(model.locations) > 1,
            "breadcrumbs": [
                {"key": str(path), "label": path.name, "current": path == model.path}
                for path in model.breadcrumbs
            ],
            "locations": [
                {
                    "key": component.key,
                    "title": component.title,
                    "detail": component.detail,
                }
                for component in model.locations
            ],
            "components": [
                {
                    "key": component.key,
                    "kind": component.kind,
                    "title": component.title,
                    "detail": (
                        self._issue_live_phase
                        if model.mode == "issues"
                        and self._issue_live_phase
                        and component.key == self._folder_inspector_key
                        and self._runtime.active_job is not None
                        and (
                            self._issue_job(self._issue_run_id)
                            is self._runtime.active_job
                            or self._issue_job(self._missing_retry_run_id)
                            is self._runtime.active_job
                        )
                        else component.detail
                    ),
                    "count": len(component.indices),
                }
                for component in model.components[: (model.page + 1) * PAGE_SIZE]
            ],
            "count": len(model.components),
            "unavailableCount": len(model.unavailable_indices)
            if model.mode == "folders"
            and not self._folder_listing_pending
            and not self._folder_listing_error
            else 0,
            "relinkCount": len(model.folder_relink_indices()),
            "checkingAvailability": model.mode == "issues"
            and not self._availability_checked,
            "availabilityError": model.mode == "issues" and self._availability_error,
            "checkingFolder": model.mode == "folders"
            and bool(self._folder_listing_pending),
            "folderError": model.mode == "folders" and self._folder_listing_error,
        }

    def _reconcile_folder_browser(self) -> None:
        projected = self._projected_library()
        projected_history = {
            history_archive_owner(row): row
            for row in projected
            if row.get(PROJECTION_OWNER_KIND_KEY) == "history"
        }
        records = [
            dict(projected_history.get(history_archive_owner(row), row))
            for row in self._runtime.history
            if archive_directory(row) is not None
        ]
        recovery_run_ids = {
            job.run_id
            for job in [
                self._runtime.active_job,
                *self._runtime.queued,
                *self._runtime.recovered,
            ]
            if job is not None and job.recovery_reason == "missing_media"
        }
        for row in projected:
            if row.get(PROJECTION_OWNER_KIND_KEY) == "history":
                continue
            run_id = str(
                row.get("vodforge_terminal_run_id")
                or row.get("vodforge_active_run_id")
                or row.get("vodforge_queued_run_id")
                or ""
            )
            if run_id in recovery_run_ids:
                continue
            attempt = dict(row)
            attempt.pop("vodforge_output_dir", None)
            attempt.pop("vodforge_output_path", None)
            records.append(attempt)
        missing = frozenset(
            owner
            for row in self._runtime.history
            if (owner := history_archive_owner(row)) in self._missing_files
            and self._missing_files[owner] == record_fingerprint(row)
        )
        self._folder_browser.replace(
            records, range(len(records)), missing_owners=missing
        )

    def _queue_availability_scan(
        self, records: list[dict[str, Any]], *, full: bool
    ) -> None:
        if full:
            self._availability_work.cancel()
            self._availability_requests.clear()
            self._availability_checked = False
            self._availability_error = False
            self._missing_files.clear()
        self._availability_requests.append(
            ("availability_full" if full else "availability_one", records)
        )
        self._start_availability_scan()
        self.historyChanged.emit()

    def _queue_folder_listing(self) -> None:
        model = self._folder_browser
        self._availability_work.cancel()
        self._availability_requests.clear()
        self._folder_listing_error = False
        self._folder_listing_pending = str(model.path) if model.path is not None else ""
        if model.mode == "folders" and model.path is not None:
            # A pending scan is not an authoritative empty directory. Keep the
            # known routes (or this folder's last listing) until its result arrives.
            self._availability_requests.append(("folder_list", str(model.path)))
            self._start_availability_scan()
        self.historyChanged.emit()

    @staticmethod
    def _folder_file_detail(name: str, size: int) -> str:
        extension = Path(name).suffix.casefold()
        kind = (
            "Image"
            if extension in {".jpg", ".jpeg", ".png", ".webp"}
            else "Metadata"
            if extension == ".json"
            else "Video"
            if extension in {".mp4", ".mkv", ".mov", ".webm"}
            else "Audio"
            if extension in {".mp3", ".m4a", ".opus", ".flac", ".wav"}
            else "File"
        )
        return (
            f"{kind} · {size / 1024 / 1024:.1f} MB"
            if size >= 1024 * 1024
            else f"{kind} · {size:,} bytes"
        )

    def _start_availability_scan(self) -> None:
        if self._availability_work.busy or not self._availability_requests:
            return
        kind, payload = self._availability_requests.pop(0)

        if kind == "folder_list":

            def list_folder(cancelled: threading.Event) -> dict[str, Any]:
                entries: list[tuple[str, str, int]] = []
                with os.scandir(str(payload)) as iterator:
                    for entry in iterator:
                        if cancelled.is_set() or len(entries) >= 5000:
                            break
                        try:
                            if entry.is_symlink():
                                continue
                            if entry.is_dir(follow_symlinks=False):
                                entries.append((entry.name, "folder", 0))
                            elif entry.is_file(follow_symlinks=False):
                                entries.append(
                                    (
                                        entry.name,
                                        "file",
                                        entry.stat(follow_symlinks=False).st_size,
                                    )
                                )
                        except OSError:
                            continue
                entries.sort(key=lambda item: (item[1] != "folder", item[0].casefold()))
                return {"path": str(payload), "entries": entries}

            if self._availability_work.submit(kind, list_folder) is None:
                self._availability_requests.insert(0, (kind, payload))
            return

        rows = payload

        def check(cancelled: threading.Event) -> dict[str, tuple[str, str]]:
            result: dict[str, tuple[str, str]] = {}
            for row in rows:
                if cancelled.is_set():
                    break
                result[history_archive_owner(row)] = (
                    record_fingerprint(row),
                    history_media_file_state(row),
                )
            return result

        if self._availability_work.submit(kind, check) is None:
            self._availability_requests.insert(0, (kind, rows))

    @Property(_QVARIANT_MAP, notify=watchSceneChanged)
    def watchScene(self) -> dict[str, Any]:
        scene = watch_scene(
            self._projected_library(),
            self._watch_scene_route,
            self._artwork.request
            if self._selection == "Watch"
            else lambda _record, _size, _role: "",
            self._watch_group_key,
            self._watch_group_kind,
            self._watch_search,
            self._playback_progress.for_record,
            defer_media_artwork=True,
            defer_group_artwork=True,
            defer_hero_artwork=True,
            channel_profile=self._artwork.channel_profile,
        )
        prior_route = self._watch_history[-1][0] if self._watch_history else "home"
        scene["backLabel"] = (
            "Back to results"
            if self._watch_history and self._watch_history[-1][3]
            else "Back to " + ("Watch" if prior_route == "home" else prior_route)
        )
        scene["canGoBack"] = bool(self._watch_history)
        hero_owner = str(scene["hero"].get("owner") or "")
        if (
            self._selection == "Watch"
            and scene["route"] == "home"
            and hero_owner
            and hero_owner != self._watch_hero_seen_key
        ):
            self._watch_hero_seen_key = hero_owner
            self._record_update_feature(
                "watch", "hero_shown", {"watch_mode": self._watch_mode()}
            )
        return scene

    @Slot(str, result=_QVARIANT_MAP)
    def watchHeroProgress(self, owner: str) -> dict[str, Any]:
        record = self._saved_item_for_owner(owner)
        return watch_progress(
            self._playback_progress.for_record(record) if record is not None else None
        )

    @Property(str, notify=supportChanged)
    def supportKind(self) -> str:
        return self._support.kind

    @Property(str, notify=supportChanged)
    def supportStatus(self) -> str:
        return self._support.status

    @Property(bool, notify=supportChanged)
    def supportBusy(self) -> bool:
        return self._support.busy

    @Property(bool, notify=supportChanged)
    def supportSent(self) -> bool:
        return self._support.sent

    @Property(_QVARIANT_MAP, notify=supportChanged)
    def supportContext(self) -> dict[str, str]:
        context = self._support.context
        return {
            "diagnostics": context.diagnostics if context is not None else "",
            "videoUrl": (public_video_url(context.video_url or "") or "")
            if context is not None
            else "",
            "outputFolder": (context.output_folder or "")
            if context is not None
            else "",
        }

    @Slot(bool, bool, bool, result=str)
    def supportAttachmentPreview(
        self, diagnostics: bool, video_url: bool, output_folder: bool
    ) -> str:
        context = self._support.context
        attachment = diagnostics_attachment(
            context,
            include_diagnostics=diagnostics,
            include_output_folder=output_folder,
        )
        if context is not None and video_url:
            source = public_video_url(context.video_url or "")
            if source:
                attachment += "\n\nYouTube source link: " + source
        return attachment.strip() or "No diagnostic attachments selected."

    @Property(bool, constant=True)
    def whatsNewAvailable(self) -> bool:
        return bool(SHOWCASE_MODE == "whats-new" and SHOWCASE_ID and HIGHLIGHTS)

    @Property(str, notify=editorialChanged)
    def editorialHeading(self) -> str:
        return {
            "welcome": "Welcome to VODForge",
            "welcome-tour": "Welcome to VODForge",
            "whats-new": "What’s new",
            "did-you-know": "Did you know?",
        }.get(self._editorial_kind, "")

    @Property(bool, notify=editorialChanged)
    def compactWelcome(self) -> bool:
        return self._editorial_kind == "welcome"

    @Property(str, notify=editorialChanged)
    def editorialFinishLabel(self) -> str:
        if self._editorial_kind == "welcome":
            return "Get started"
        if self._editorial_kind == "welcome-tour":
            return "Start using VODForge"
        if self._editorial_kind == "did-you-know" or (
            len(self._editorial_slides) == 1
            and self._editorial_slides[0].key == "output-settings"
        ):
            return "Try it"
        return "Done"

    @Property(_QVARIANT_LIST, notify=editorialChanged)
    def editorialSlides(self) -> list[dict[str, str]]:
        return [
            {
                "key": slide.key,
                "title": slide.title,
                "description": slide.description,
                "preview": slide.preview.value,
                "recording": slide.recording,
                "poster": slide.poster,
            }
            for slide in self._editorial_slides
        ]

    @Property(_QVARIANT_MAP, notify=historyChanged)
    def libraryDetail(self) -> dict[str, Any]:
        return self._library_detail_projection(
            self._library_detail_owner,
            self._detail_versions,
            bool(
                self._library_detail_origin
                and self._library_detail_origin[0] == "folders"
            ),
        )

    @Property(_QVARIANT_MAP, notify=historyChanged)
    def libraryFolderInspector(self) -> dict[str, Any]:
        if self._library_scene_route != "folders":
            return {}
        if self._folder_browser.mode == "issues" and self._issue_run_id:
            row = next(
                (
                    row
                    for row in self._projected_library()
                    if str(row.get(PROJECTION_OWNER_KEY) or "")
                    == self._folder_inspector_key
                ),
                None,
            )
            if row is not None:
                return {
                    "issue": True,
                    "title": str(row.get("title") or "Interrupted download"),
                    "artwork": self._artwork.request(row),
                    "creator": str(row.get("channel") or row.get("uploader") or ""),
                    "type": str(self._issue_settings.get("output_type") or ""),
                    "status": (
                        self._issue_live_phase
                        if self._issue_live_phase
                        and self._runtime.active_job is not None
                        and self._issue_job(self._issue_run_id)
                        is self._runtime.active_job
                        else str(
                            row.get("vodforge_terminal_status")
                            or row.get("vodforge_run_status")
                            or ""
                        )
                    ),
                    "source": str(self._issue_settings.get("source") or ""),
                    "modeLabel": export_mode_display_name(
                        str(self._issue_settings.get("export_mode") or "Everyday")
                    ),
                    "settings": dict(self._issue_settings),
                }
        if self._folder_browser.mode == "issues" and self._missing_issue_owner:
            row = self._saved_item_for_owner(self._missing_issue_owner)
            if row is not None and self._missing_issue_owner in self._missing_files:
                status = "Saved file missing"
                retry = self._issue_job(self._missing_retry_run_id)
                if retry is not None:
                    if retry in self._runtime.queued:
                        status = "Queued"
                    elif retry is self._runtime.active_job:
                        status = self._recovery_progress_label()
                    elif retry.terminal_status:
                        status = retry.terminal_status
                return {
                    "issue": True,
                    "missing": True,
                    "title": str(row.get("title") or "Saved media"),
                    "artwork": self._artwork.request(row),
                    "creator": str(row.get("channel") or row.get("uploader") or ""),
                    "type": str(self._issue_settings.get("output_type") or ""),
                    "status": status,
                    "source": str(self._issue_settings.get("source") or ""),
                    "location": str(history_output_path(row) or ""),
                    "modeLabel": export_mode_display_name(
                        str(self._issue_settings.get("export_mode") or "Everyday")
                    ),
                    "settings": dict(self._issue_settings),
                    "canRedownload": self._missing_plan is not None,
                }
        if self._folder_browser.mode == "folders" and self._folder_file_path:
            path = Path(self._folder_file_path)
            if self._folder_browser.path == ArchivePath.parse(str(path.parent)):
                extension = path.suffix.casefold()
                is_image = extension in {".jpg", ".jpeg", ".png", ".webp"}
                is_metadata = path.name == "metadata.json"
                row = next(
                    (
                        item
                        for item in self._projected_library()
                        if history_archive_owner(item) == self._folder_file_owner
                    ),
                    None,
                )
                return {
                    "file": True,
                    "title": path.name,
                    "location": str(path),
                    "type": self._folder_file_detail_text,
                    "artwork": QUrl.fromLocalFile(str(path)).toString()
                    if is_image
                    else "",
                    "isMetadata": is_metadata and row is not None,
                    "associatedOwner": self._folder_file_owner
                    if row is not None
                    else "",
                    "description": str(
                        row.get("vodforge_user_description", row.get("description"))
                        or ""
                    )
                    if row is not None
                    else "",
                    "tags": list(row.get("vodforge_user_tags") or ())
                    if row is not None
                    else [],
                }
        if (
            self._folder_browser.mode == "folders"
            and self._folder_browser.path is not None
            and not self._folder_inspector_owner
        ):
            folder_path = self._folder_browser.path
            unavailable = (
                self._folder_browser.unavailable_indices
                if not self._folder_listing_pending and not self._folder_listing_error
                else ()
            )
            return {
                "folder": True,
                "title": folder_path.name,
                "location": str(folder_path),
                "count": len(self._folder_browser.components),
                "unavailableCount": len(unavailable),
                "unavailableItems": [
                    {
                        "owner": history_archive_owner(
                            dict(self._folder_browser.records[index])
                        ),
                        "title": str(
                            self._folder_browser.records[index].get("title")
                            or "Saved media"
                        ),
                    }
                    for index in unavailable[:1]
                ],
            }
        return self._library_detail_projection(
            self._folder_inspector_owner, self._folder_inspector_versions, True
        )

    def _recovery_progress_label(self) -> str:
        message = self._runtime.active_status.casefold()
        if "prepar" in message:
            return "Preparing"
        if "transcod" in message or "convert" in message:
            return "Transcoding"
        if "download" in message:
            return "Downloading"
        return "Preparing"

    def _library_detail_projection(
        self, owner: str, versions: list[dict[str, str]], from_folders: bool
    ) -> dict[str, Any]:
        if not owner:
            return {}
        row = next(
            (
                row
                for row in self._projected_library()
                if history_archive_owner(row) == owner
                and row.get("vodforge_output_dir")
            ),
            None,
        )
        if row is None:
            return {}
        source, output = library_detail_facts(row)
        return {
            "owner": owner,
            "title": str(row.get("title") or "Saved media"),
            "creator": str(row.get("channel") or row.get("uploader") or "Local media"),
            "type": str(row.get("vodforge_output_type") or ""),
            "category": str(row.get("vodforge_user_category") or ""),
            "description": str(
                row.get("vodforge_user_description", row.get("description"))
                or "Saved in your Library."
            ),
            "descriptionInput": str(
                row.get("vodforge_user_description", row.get("description")) or ""
            ),
            "userDescription": "vodforge_user_description" in row,
            "note": str(row.get("vodforge_user_note") or ""),
            "location": str(history_output_path(row) or ""),
            "tags": [str(tag) for tag in row.get("vodforge_user_tags") or ()],
            "artwork": self._artwork.request(row),
            "source": [{"label": label, "value": value} for label, value, _ in source],
            "output": [{"label": label, "value": value} for label, value, _ in output],
            "versions": list(versions),
            "fromFolders": from_folders,
        }

    @Property(_QVARIANT_LIST, notify=historyChanged)
    def collectionCandidates(self) -> list[dict[str, Any]]:
        return collection_picker(self._runtime.history)["videos"]

    @Property(_QVARIANT_MAP, notify=historyChanged)
    def collectionPicker(self) -> dict[str, list[dict[str, Any]]]:
        return collection_picker(self._runtime.history)

    def _projected_library(self) -> list[dict[str, Any]]:
        projection = self._library_projection.reconcile(
            history_items=self._runtime.history,
            active_job=self._runtime.active_job,
            queued_jobs=getattr(self._runtime, "queued", []),
            terminal_jobs=getattr(self._runtime, "recovered", []),
            annotations=self._annotations.snapshot,
        )
        return [dict(row) for row in projection.rows]

    @Property(str, notify=libraryCategoryChanged)
    def libraryCategory(self) -> str:
        return self._library_category

    @Property(str, notify=librarySortChanged)
    def librarySort(self) -> str:
        return self._library_sort

    @Property(bool, notify=importBusyChanged)
    def importBusy(self) -> bool:
        return self._import_pending

    @Property(_QVARIANT_MAP, notify=storageChanged)
    def storageSummary(self) -> dict[str, Any]:
        snapshot = self._storage_snapshot
        capacity = snapshot.capacity
        if capacity is None:
            return {
                "label": "Local Library",
                "detail": "Checking drive…"
                if snapshot.status == "loading"
                else "Drive unavailable",
                "fraction": 0.0,
            }
        return {
            "label": capacity.volume.label,
            "detail": f"{format_storage_bytes(capacity.used)} of {format_storage_bytes(capacity.total)} used",
            "free": f"{format_storage_bytes(capacity.free)} free",
            "fraction": capacity.fraction_used,
        }

    @Property(_QVARIANT_LIST, notify=storageChanged)
    def storageChoices(self) -> list[dict[str, str]]:
        return [
            {"path": volume.path, "label": volume.label}
            for volume in self._storage_snapshot.choices
        ]

    @Slot(str)
    def selectStorageVolume(self, path: str) -> None:
        if path not in {volume.path for volume in self._storage_snapshot.choices}:
            return
        self._storage.select(path)
        self._storage_snapshot = self._storage.snapshot
        self.storageChanged.emit()

    @Slot()
    def refreshStorage(self) -> None:
        self._storage.refresh()

    @Slot("QVariantList", result=bool)
    def importMedia(self, urls: list[QUrl]) -> bool:
        if not urls or len(urls) > 64:
            self._status = "Choose up to 64 media files."
        elif (
            self._import_pending
            or self._relink.active
            or self._file_action_busy
            or self._runtime.recovery_notice
            or self._runtime.active_job is not None
            or self._runtime.busy
            or self._runtime.queued
            or self._local_running
        ):
            self._status = (
                "Finish the current Library or download work before importing."
            )
        else:
            paths = [Path(url.toLocalFile()) for url in urls if url.isLocalFile()]
            if len(paths) != len(urls):
                self._status = "Choose media files from this computer."
            else:

                def inspect(cancelled: Any) -> tuple[list[dict[str, Any]], int]:
                    completed: list[dict[str, Any]] = []
                    failed = 0
                    for path in paths:
                        if cancelled.is_set():
                            break
                        try:
                            completed.append(inspect_local_media(path, cancelled))
                        except (
                            OSError,
                            ValueError,
                            RuntimeError,
                            SubprocessError,
                        ):
                            failed += 1
                    return completed, failed

                if self._import_work.submit("library_import", inspect) is not None:
                    self._import_pending = True
                    self._import_request_count = len(paths)
                    self._import_started_at = time.monotonic()
                    self._import_operation = bind_operation(
                        self._analytics.telemetry,
                        "library_import_operation",
                        operation_key=str(uuid.uuid4()),
                    )
                    operation(
                        self._analytics.telemetry,
                        "library_import_operation",
                        "requested",
                        self._import_operation,
                        {"item_count": str(len(paths))},
                    )
                    self.importBusyChanged.emit()
                    self._status = "Checking selected media…"
                    self.statusChanged.emit()
                    return True
                self._status = "Media could not be checked. Please try again."
        self.statusChanged.emit()
        return False

    @Property(_QVARIANT_LIST, notify=historyChanged)
    def libraryCategories(self) -> list[str]:
        return [LIBRARY_ALL_CATEGORIES, *library_categories(self._projected_library())]

    @Property(_QVARIANT_MAP, notify=annotationChanged)
    def annotationValues(self) -> dict[str, str]:
        return dict(self._annotation_values)

    @Property(str, notify=librarySearchChanged)
    def librarySearch(self) -> str:
        return self._library_search

    @Property(str, notify=libraryTypeChanged)
    def libraryType(self) -> str:
        return self._library_type

    @Property(str, notify=localChanged)
    def localAudio(self) -> str:
        return self._local_audio

    @Property(str, notify=localChanged)
    def localImage(self) -> str:
        return self._local_image

    @Property(str, notify=localChanged)
    def localProfile(self) -> str:
        return local_video_profile_label(self._local_profile)

    @Property(str, notify=localChanged)
    def localProgress(self) -> str:
        return self._local_progress

    @Property(bool, notify=localChanged)
    def localRunning(self) -> bool:
        return self._local_running

    @Property(_QVARIANT_MAP, notify=downloadOptionsChanged)
    def downloadOptions(self) -> dict[str, bool]:
        return asdict(self._download_preferences)

    @Property(str, notify=downloadOptionsChanged)
    def translatedSubtitleLanguage(self) -> str:
        return self._translated_subtitle_language or ""

    @Property(str, notify=downloadOptionsChanged)
    def translatedSubtitleLabel(self) -> str:
        code = self._translated_subtitle_language
        return (QLocale(code).nativeLanguageName() or code) if code else "Off"

    @Property(_QVARIANT_LIST, constant=True)
    def subtitleLanguageChoices(self) -> list[dict[str, str]]:
        choices = [{"code": "", "label": "Off"}]
        languages = [
            {
                "code": code,
                "label": (QLocale(code).nativeLanguageName() or code) + f" ({code})",
            }
            for code in PROVIDER_SUBTITLE_LANGUAGES
        ]
        return choices + sorted(languages, key=lambda entry: entry["label"].casefold())

    @Slot(str)
    def setTranslatedSubtitleLanguage(self, value: str) -> None:
        try:
            selected = translated_subtitle_language(value)
        except ValueError:
            return
        if selected == self._translated_subtitle_language:
            return
        self._translated_subtitle_language = selected
        self.downloadOptionsChanged.emit()
        self._schedule_preferences_save()

    @Property(bool, notify=nvencAvailableChanged)
    def nvencAvailable(self) -> bool:
        return self._nvenc_available

    def _start_nvenc_probe(self) -> None:
        if self._closed or sys.platform != "win32":
            return
        probe = QProcess(self)
        self._nvenc_probe = probe
        probe.finished.connect(self._finish_nvenc_probe)
        probe.errorOccurred.connect(self._fail_nvenc_probe)
        probe.start(
            "nvidia-smi",
            ["--query-gpu=driver_version", "--format=csv,noheader,nounits"],
        )
        QTimer.singleShot(
            3000,
            lambda: (
                probe.kill()
                if self._nvenc_probe is probe and probe.state() != QProcess.NotRunning
                else None
            ),
        )

    def _finish_nvenc_probe(self, exit_code: int, _exit_status: object) -> None:
        probe = self._nvenc_probe
        if probe is None or self._closed:
            return
        versions = (
            bytes(probe.readAllStandardOutput())
            .decode("ascii", errors="ignore")
            .strip()
            .splitlines()
        )
        available = (
            exit_code == 0
            and bool(versions)
            and bool(
                re.fullmatch(r"[0-9]{1,6}(?:\.[0-9]{1,6}){0,3}", versions[0].strip())
            )
        )
        if available and self._analytics.telemetry is not None:
            try:
                self._analytics.telemetry.observe_nvidia_driver(versions[0].strip())
            except ValueError:
                pass  # Unsupported driver spelling is not a capability failure.
        self._nvenc_probe = None
        probe.deleteLater()
        if available != self._nvenc_available:
            self._nvenc_available = available
            self.nvencAvailableChanged.emit()
        if available and self._saved_nvenc_preference:
            self._download_preferences = replace(
                self._download_preferences, use_nvenc=True
            )
            self.downloadOptionsChanged.emit()

    def _fail_nvenc_probe(self, _error: object) -> None:
        probe = self._nvenc_probe
        self._nvenc_probe = None
        if probe is not None:
            probe.deleteLater()

    @Property(_QVARIANT_MAP, notify=exportSettingsChanged)
    def manualValues(self) -> dict[str, str]:
        return dict(self._manual_values)

    @Property(_QVARIANT_MAP, notify=exportSettingsChanged)
    def mp3Values(self) -> dict[str, str | bool]:
        return dict(self._mp3_values)

    @Property(_QVARIANT_LIST, constant=True)
    def analyticsBenefits(self) -> list[dict[str, str]]:
        return [{"icon": icon, "label": label} for icon, label in ANALYTICS_BENEFITS]

    @Property(str, constant=True)
    def analyticsDescription(self) -> str:
        return ANALYTICS_DESCRIPTION

    @Property(_QVARIANT_LIST, constant=True)
    def mp3QualityOptions(self) -> list[str]:
        return list(MP3_QUALITY_OPTIONS)

    @Property(_QVARIANT_LIST, constant=True)
    def exportModeOptions(self) -> list[dict[str, str]]:
        return [
            {"label": label, "value": export_mode_from_display_name(label).value}
            for label in EXPORT_MODES
        ]

    @Slot(str, result=str)
    def describeExportMode(self, value: str) -> str:
        try:
            return export_mode_description(value)
        except ValueError:
            return ""

    @Property(_QVARIANT_LIST, constant=True)
    def mp3SampleRateOptions(self) -> list[str]:
        return list(MP3_SAMPLE_RATE_OPTIONS)

    @Property(_QVARIANT_LIST, constant=True)
    def mp3ChannelOptions(self) -> list[str]:
        return list(MP3_CHANNEL_OPTIONS)

    @Property(_QVARIANT_LIST, constant=True)
    def mp3CoverOptions(self) -> list[str]:
        return list(MP3_COVER_ART_OPTIONS)

    @Property(str, notify=exportSettingsChanged)
    def mp3CoverName(self) -> str:
        return self._mp3_custom_cover.name if self._mp3_custom_cover else "Choose image"

    @Property(bool, notify=exportSettingsChanged)
    def mp3CoverAvailable(self) -> bool:
        return self._mp3_custom_cover is not None

    @Property(str, notify=extraTagsChanged)
    def extraTags(self) -> str:
        return self._extra_tags

    @Property(bool, constant=True)
    def reducedMotion(self) -> bool:
        return _system_reduced_motion()

    @Property(str, notify=appearanceChanged)
    def appearanceTheme(self) -> str:
        return self._appearance_theme

    @Property(str, notify=appearanceChanged)
    def customAccent(self) -> str:
        return self._custom_accent

    @Property(_QVARIANT_LIST, constant=True)
    def appearanceThemes(self) -> list[str]:
        return list(THEME_NAMES)

    @Property(int, notify=themeRevisionChanged)
    def themeRevision(self) -> int:
        return self._theme_revision

    def _render_theme(self, _previous: object, _incoming: object) -> None:
        if self._theme_materials is not None:
            self._theme_materials.images.clear()
        if self._theme_engine is not None:
            self._theme_engine.rootContext().setContextProperty("theme", dict(THEME))
        self._theme_revision += 1
        self.themeRevisionChanged.emit()
        telemetry = self._analytics.telemetry
        if telemetry is not None and telemetry.permitted():
            telemetry.record_feature(
                "appearance",
                "changed",
                dimensions={
                    "theme": "custom"
                    if self._appearance_theme == CUSTOM_THEME_NAME
                    else self._appearance_theme.lower()
                },
            )

    @Slot(str, str, result=bool)
    def setAppearance(self, name: str, accent: str) -> bool:
        if name not in THEME_NAMES or not re.fullmatch(r"#[0-9a-fA-F]{6}", accent):
            self._status = "Choose a theme and use a #RRGGBB custom accent."
            self.statusChanged.emit()
            return False
        if (name, accent.lower()) == (self._appearance_theme, self._custom_accent):
            return True
        self._appearance_theme = name
        self._custom_accent = accent.lower()
        self._theme_owner.request(name, accent)
        self.appearanceChanged.emit()
        self._schedule_preferences_save()
        return True

    @Slot(str, result=bool)
    def setExtraTags(self, value: str) -> bool:
        tags = [item.strip() for item in value.split(",") if item.strip()]
        if len(value) > 10_000 or len(tags) > 64 or any(len(tag) > 80 for tag in tags):
            self._status = "Use up to 64 tags of 80 characters each."
            self.statusChanged.emit()
            return False
        if value != self._extra_tags:
            self._extra_tags = value
            self.extraTagsChanged.emit()
        return True

    @Property(bool, notify=batchListChanged)
    def composerResume(self) -> bool:
        return any(
            job.run_id == self._composer_resume_run_id
            and job.terminal_status == "Paused"
            for job in self._runtime.recovered
        )

    @Slot()
    def restorePausedComposer(self) -> None:
        paused = next(
            (job for job in self._runtime.recovered if job.terminal_status == "Paused"),
            None,
        )
        if paused is not None:
            self.selectRunRecord("terminal:" + paused.run_id)

    def _prepare_paused_composer(self, job: Any) -> None:
        self._composer_resume_run_id = job.run_id
        self._batch_snapshot_admitted = True
        self._batch_path = job.batch_list_path
        self._batch_urls = list(job.urls) if job.batch_mode else []
        self._batch_name = (
            Path(job.batch_list_path).name if job.batch_list_path else "Saved URL list"
        )
        self._recent_interrupted_run_id = job.run_id
        self.batchListChanged.emit()
        self.sourcePrepared.emit(job.batch_list_path or job.url)

    @Property(bool, notify=batchListChanged)
    def batchLoaded(self) -> bool:
        return bool(self._batch_urls)

    @Property(str, notify=batchListChanged)
    def batchPath(self) -> str:
        return self._batch_path

    @Property(str, notify=batchListChanged)
    def batchSummary(self) -> str:
        if not self._batch_urls:
            return "No URL list loaded"
        return f"{self._batch_name} · {len(self._batch_urls)} URL(s) loaded"

    @Property(str, notify=cookieAccessChanged)
    def cookieSource(self) -> str:
        return self._cookie_source.value

    @Property(str, notify=cookieAccessChanged)
    def cookieBrowser(self) -> str:
        return self._cookie_browser or "Choose a browser"

    @Property(str, notify=cookieAccessChanged)
    def cookieFileName(self) -> str:
        return self._cookie_file.name if self._cookie_file else "Choose cookies.txt"

    @Property(_QVARIANT_LIST, constant=True)
    def cookieBrowserOptions(self) -> list[str]:
        return list(COOKIE_BROWSER_OPTIONS[1:])

    @Property(_QVARIANT_LIST, notify=activityChanged)
    def activity(self) -> list[dict[str, str]]:
        return self._runtime.activity

    @Property(str, notify=activityChanged)
    def activityLog(self) -> str:
        return self._activity_log_text

    @Property(_QVARIANT_MAP, notify=activityChanged)
    def forgeActivity(self) -> dict[str, str]:
        selection = self.forgeSelection
        if selection and selection.get("kind") != "active":
            run_id = str(selection.get("runId") or "")
            job = next(
                (
                    row
                    for row in [*self._runtime.queued, *self._runtime.recovered]
                    if row.run_id == run_id
                ),
                None,
            )
            saved = (
                self._saved_item_for_owner(str(selection.get("owner") or ""))
                if selection.get("kind") == "completed"
                else None
            )
            if job is not None:
                lines = job.activity_lines
            elif saved is not None:
                lines = [
                    local_video_profile_text(line)
                    for line in sanitize_run_activity(
                        saved.get("vodforge_run_activity")
                    )
                ]
            else:
                lines = []
            technical = "\n".join(lines)[-50_000:]
            status = (
                "Completed"
                if selection.get("kind") == "completed"
                else str(selection.get("status") or "")
            )
            return {
                "friendly": friendly_saved_activity(status, lines),
                "technical": technical or "No technical activity for this run yet.",
            }
        return {
            "friendly": self._forge_activity.friendly(
                self._forge_run_id, self._forge_technical
            ),
            "technical": self._forge_technical
            or "No technical activity for this run yet.",
        }

    @Slot()
    def openTechnicalDetails(self) -> None:
        self._record_update_feature("guidance", "technical_opened")

    def _append_activity_line(self, line: str) -> None:
        append_activity_log(line, self._activity_log_path)
        combined = (
            self._activity_log_text + ("\n" if self._activity_log_text else "") + line
        )
        if len(combined) > 500_000:
            combined = combined[-500_000:]
            newline = combined.find("\n")
            if newline >= 0:
                combined = combined[newline + 1 :]
        self._activity_log_text = combined
        self.activityChanged.emit()

    @Slot()
    def openActivityLogFolder(self) -> None:
        folder = self._activity_log_path.parent
        if folder.is_dir():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))
        else:
            self._status = "The Activity log folder is unavailable."
            self.statusChanged.emit()

    @Property(_QVARIANT_MAP, notify=forgePreviewChanged)
    def forgePreview(self) -> dict[str, Any]:
        record = self._metadata_preview_record
        info = self._metadata_preview_info or {}
        return {
            "phase": str(record.get("phase") or "idle"),
            "title": str(info.get("title") or record.get("title") or ""),
            "creator": str(info.get("uploader") or info.get("channel") or ""),
            "status": str(record.get("status") or ""),
            "type": str(record.get("type") or ""),
            "artwork": self._artwork.request(info) if info else "",
            "canStart": bool(
                is_metadata_preview(info) and record.get("phase") == "complete"
            ),
        }

    @Property(_QVARIANT_LIST, notify=runDeckChanged)
    def runControls(self) -> list[dict[str, str]]:
        return self._run_controls.actions(self._runtime.active_job)

    @Property(_QVARIANT_MAP, notify=runDeckChanged)
    def runDeck(self) -> dict[str, Any]:
        records: list[dict[str, Any]] = []
        preview = self.forgePreview
        if preview["phase"] in {"loading", "failed"}:
            records.append(
                {
                    "runId": str(self._metadata_preview_record.get("runId") or ""),
                    "selectionKey": "preview:"
                    + str(self._metadata_preview_record.get("runId") or ""),
                    "owner": "",
                    "kind": "preview",
                    "phase": preview["phase"],
                    "title": preview["title"],
                    "status": preview["status"],
                    "type": preview["type"],
                    "progress": 100 if preview["phase"] == "complete" else 0,
                    "artwork": preview["artwork"],
                    "duration": "",
                }
            )
        active = self._runtime.active_job
        if active is not None:
            if active is not self._run_menu_identity_job:
                self._run_menu_identity_job = active
                self._run_menu_identity_token = uuid.uuid4().hex
            preview = active.preview_info or {}
            records.append(
                {
                    "runId": active.run_id,
                    "selectionKey": "active:" + active.run_id,
                    "executionToken": self._run_menu_identity_token,
                    "controls": self.runControls,
                    "kind": "active",
                    "title": str(
                        preview.get("title") or f"{active.output_type.value} download"
                    ),
                    "detail": str(
                        preview.get("uploader") or preview.get("channel") or ""
                    ),
                    "status": self._runtime.active_status,
                    "type": active.output_type.value,
                    "progress": self._runtime.active_progress,
                    "duration": format_duration(preview.get("duration")),
                    "_artwork_info": preview,
                }
            )
        for kind, jobs in (
            ("queued", self._runtime.queued),
            ("terminal", self._runtime.recovered),
        ):
            for job in jobs:
                preview = job.preview_info or {}
                records.append(
                    {
                        "runId": job.run_id,
                        "selectionKey": kind + ":" + job.run_id,
                        "kind": kind,
                        "title": "Batch List"
                        if job.batch_mode and job.terminal_status == "Paused"
                        else str(
                            preview.get("title") or f"{job.output_type.value} download"
                        ),
                        "detail": str(
                            preview.get("uploader")
                            or preview.get("channel")
                            or job.terminal_message
                            or ""
                        ),
                        "status": job.terminal_status or "Queued",
                        "type": job.output_type.value,
                        "progress": 100
                        * job.completed_batch_items
                        / max(1, len(job.urls)),
                        "duration": format_duration(preview.get("duration")),
                        "_artwork_info": preview,
                    }
                )
        projected = self._projected_library()
        for record in persisted_run_deck_records(projected, completed_jobs=()):
            index = record.get("metadata_index")
            if not isinstance(index, int):
                continue
            item = projected[index]
            records.append(
                {
                    "runId": str(record["run_id"]),
                    "selectionKey": "saved:"
                    + str(
                        item.get(PROJECTION_OWNER_KEY) or history_archive_owner(item)
                    ),
                    "owner": str(
                        item.get(PROJECTION_OWNER_KEY) or history_archive_owner(item)
                    ),
                    "hasYoutubeUrl": bool(canonical_youtube_url(item)),
                    "kind": str(record["kind"]),
                    "title": str(record["title"]),
                    "detail": str(record["detail"]),
                    "status": str(record["status"]),
                    "type": str(record["output_type"]),
                    "progress": 100,
                    "duration": format_duration(item.get("duration")),
                    "_artwork_info": item,
                }
            )
        records.sort(
            key=lambda record: (
                1.5
                if record.get("status") == "Paused"
                else {
                    "preview": 0,
                    "active": 1,
                    "queued": 2,
                    "completed": 4,
                    "terminal": 3
                    if record.get("runId") == self._recent_interrupted_run_id
                    else 5,
                }.get(str(record["kind"]), 5)
            )
        )
        visible_work = 0
        for record in records:
            info = record.pop("_artwork_info", None)
            if info is not None:
                record["artwork"] = (
                    self._artwork.request(info) if visible_work < 4 and info else ""
                )
            if record["kind"] != "preview":
                visible_work += 1
        counts: dict[str, int] = {}
        for record in records:
            kind = record["kind"]
            counts[kind] = counts.get(kind, 0) + 1
        summary = (
            "No runs yet"
            if not records
            else f"{len(records)} run{'s' if len(records) != 1 else ''}"
        )
        for kind in ("active", "queued", "completed", "terminal", "preview"):
            if count := counts.get(kind, 0):
                summary += f"  •  {count} {kind}"
        for record in records:
            if record.get("duration") == "—":
                record["duration"] = ""
        return {
            "records": records,
            "visible": records[:4],
            "count": len(records),
            "summary": summary,
        }

    @Slot(str, result=str)
    def runDeckArtwork(self, selection_key: str) -> str:
        """Request artwork only for an instantiated visible or scrolled run card."""
        kind, separator, identity = selection_key.partition(":")
        if not separator or not identity:
            return ""
        if kind == "saved":
            record = self._artwork_record_for_owner(identity)
        elif kind == "active":
            job = self._runtime.active_job
            record = job.preview_info if job and job.run_id == identity else None
        elif kind in {"queued", "terminal"}:
            jobs = self._runtime.queued if kind == "queued" else self._runtime.recovered
            job = next(
                (candidate for candidate in jobs if candidate.run_id == identity), None
            )
            record = job.preview_info if job else None
        else:
            return ""
        return self._artwork.request(record) if record else ""

    @Property(_QVARIANT_MAP, notify=runDeckChanged)
    def forgeSelection(self) -> dict[str, Any]:
        records = self.runDeck["records"]
        selected = next(
            (
                record
                for record in records
                if record["selectionKey"] == self._selected_run_key
            ),
            None,
        )
        selected = selected or (records[0] if records else {})
        if selected and not selected.get("artwork"):
            source: dict[str, Any] | None = None
            kind = str(selected.get("kind") or "")
            if kind == "completed":
                source = self._saved_item_for_owner(str(selected.get("owner") or ""))
            elif kind in {"active", "queued", "terminal"}:
                jobs = (
                    [self._runtime.active_job]
                    if kind == "active"
                    else self._runtime.queued
                    if kind == "queued"
                    else self._runtime.recovered
                )
                source = next(
                    (
                        job.preview_info
                        for job in jobs
                        if job is not None
                        and job.run_id == selected.get("runId")
                        and job.preview_info
                    ),
                    None,
                )
            if source:
                selected = {
                    **selected,
                    "artwork": self._artwork.request(source, (304, 171), "hero"),
                }
        return selected

    @Property(_QVARIANT_MAP, notify=runDeckChanged)
    def forgeSelectedFacts(self) -> dict[str, Any]:
        """Project selected-run facts from its owner, not pending download options."""
        selected = self.forgeSelection
        run_id = str(selected.get("runId") or "")
        kind = str(selected.get("kind") or "")
        if kind in {"active", "queued", "terminal"}:
            jobs = [
                job
                for job in [
                    self._runtime.active_job,
                    *self._runtime.queued,
                    *self._runtime.recovered,
                ]
                if job is not None and job.run_id == run_id
            ]
            if len(jobs) == 1:
                job = jobs[0]
                from .output_config_facts import chosen_config_facts, job_config

                rows = chosen_config_facts(
                    job_config(job), nvenc_available=job.nvenc_applicable
                )
                if kind != "active":
                    rows.append(
                        {
                            "label": "Status",
                            "value": str(selected.get("status") or "Queued"),
                        }
                    )
                return {
                    "heading": f"Chosen settings: {job.output_type.value} (not measured output)",
                    "rows": rows,
                }
        if kind == "completed":
            owner = str(selected.get("owner") or "")
            item = self._saved_item_for_owner(owner)
            if item is not None:
                _source, output = library_detail_facts(item)
                from .output_config_facts import (
                    chosen_config_facts,
                    job_config,
                    recorded_config,
                )

                retained = self._issue_job(str(item.get("vodforge_run_id") or ""))
                config = (
                    job_config(retained)
                    if retained is not None
                    else recorded_config(item)
                )
                chosen = (
                    chosen_config_facts(
                        config,
                        nvenc_available=retained.nvenc_applicable
                        if retained is not None
                        else config.get("nvenc_applicable"),
                    )
                    if config is not None
                    else [
                        {
                            "label": "Chosen settings",
                            "value": "Full configuration not recorded for this saved output.",
                        }
                    ]
                )
                return {
                    "heading": "Saved output — measured facts",
                    "rows": [
                        {"label": label, "value": value}
                        for label, value, _icon in output
                    ]
                    + chosen,
                }
        if kind == "preview":
            return {
                "heading": "Metadata preview — no output configuration applied",
                "rows": [],
            }
        from .output_config_facts import chosen_config_facts

        config = {
            **self.downloadOptions,
            "format": self.outputFormat,
            "mode": self.exportMode,
            "quality": self.quality,
            "folder": self.outputPath,
            "access": self.cookieSource,
            "browser": self.cookieBrowser,
            "manual": self.manualValues,
            "mp3": self.mp3Values,
            "tags": self._current_extra_tags(),
            "batch_count": len(self._batch_urls),
            "translated_subtitle_language": self._translated_subtitle_language,
        }
        return {
            "heading": "Chosen output settings (not measured output)",
            "rows": chosen_config_facts(config, nvenc_available=self.nvencAvailable),
        }

    @Slot(str, result=bool)
    def selectRunRecord(self, selection_key: str) -> bool:
        if not selection_key or not any(
            record["selectionKey"] == selection_key
            for record in self.runDeck["records"]
        ):
            return False
        self._selected_run_key = selection_key
        paused = next(
            (
                job
                for job in self._runtime.recovered
                if selection_key == "terminal:" + job.run_id
                and job.terminal_status == "Paused"
            ),
            None,
        )
        if paused is not None:
            self._prepare_paused_composer(paused)
        self.runDeckChanged.emit()
        self.activityChanged.emit()
        self.select("Forge")
        return True

    def _record(self, action: str, outcome: str) -> None:
        if self._event_log is not None:
            with self._event_log.open("a", encoding="utf-8") as file:
                file.write(json.dumps({"action": action, "outcome": outcome}) + "\n")

    @Slot(str)
    def select(self, name: str) -> None:
        if name not in {"Forge", "Library", "Watch", "Activity"}:
            return
        if name == "Watch" and self._selection != "Watch":
            self._record_update_feature("watch", "opened")
        if name == "Library" and self._selection != "Library":
            self._record_update_feature("library", "opened")
        self._selection = name
        self.selectionChanged.emit()
        self._record("select", name)

    @Slot(str)
    @Slot(str, bool)
    def selectHome(self, name: str, keep_playing: bool = False) -> None:
        """Top-level navigation always opens the destination's main screen."""
        if name not in {"Forge", "Library", "Watch", "Activity"}:
            return
        if (
            self._playback_url.isValid()
            and not self._playback_url.isEmpty()
            and not keep_playing
        ):
            self.closePlayback()
        if name == "Library":
            self.setLibrarySearch("")
            if self._library_scene_route != "home" or self._library_history:
                self.navigateLibrary("home")
        elif name == "Watch":
            if (
                self._watch_scene_route != "home"
                or self._watch_search
                or self._watch_history
            ):
                self.navigateWatch("home")
        self.select(name)

    def _remember_library_route(self) -> None:
        current = (
            self._library_scene_route,
            self._library_group_kind,
            self._library_group_key,
        )
        if not self._library_history or self._library_history[-1] != current:
            self._library_history.append(current)
            del self._library_history[:-32]

    @Slot()
    def backLibrary(self) -> None:
        if self._library_scene_route == "detail" and self._library_detail_from_watch:
            self._library_detail_from_watch = False
            self.returnLibraryDetails()
            self.select("Watch")
            return
        if self._library_scene_route == "detail":
            self.returnLibraryDetails()
            return
        if self._library_history:
            route, kind, key = self._library_history.pop()
            self._library_scene_route = route
            self._library_group_kind = kind
            self._library_group_key = key
        else:
            self._library_scene_route = "home"
            self._library_group_kind = self._library_group_key = ""
        if self._library_scene_route != "all" and self._library_search:
            self.setLibrarySearch("")
        self.historyChanged.emit()

    def _set_status(self, value: str) -> None:
        self._status = value
        self.statusChanged.emit()

    def _watch_mode(self) -> str:
        return (
            "channels"
            if self._watch_group_kind == "channel"
            or self._watch_scene_route == "channels"
            else "collections"
            if self._watch_group_kind == "collection"
            or self._watch_scene_route == "collections"
            else "playlists"
        )

    def _record_watch_queue_operation(
        self,
        action: str,
        operation: str,
        dimensions: dict[str, str],
        *,
        failure_detail: FailureDiagnostic | None = None,
    ) -> None:
        telemetry = self._analytics.telemetry
        if action == "requested":
            self._watch_queue_observations[operation] = (
                telemetry.bind_operation(
                    "watch_queue_operation", operation_key=operation
                )
                if telemetry is not None
                else None
            )
        observation = self._watch_queue_observations.get(operation)
        try:
            if observation is not None:
                observation.record(action, dimensions, failure_detail=failure_detail)
        finally:
            if action in {"completed", "cancelled", "failed"}:
                self._watch_queue_observations.pop(operation, None)

    def _open_queued_watch_record(
        self, record: dict[str, Any], token: QueueToken
    ) -> None:
        owner = history_archive_owner(record)
        index = next(
            (
                index
                for index, candidate in enumerate(self._runtime.history)
                if history_archive_owner(candidate) == owner
            ),
            None,
        )
        if index is None or not self.openLibraryItem(index, token):
            self._watch_queue.cancel(
                "failed",
                failure_boundary="media",
                failure_reason="saved_output_missing",
            )
            self._set_status("Queued media is unavailable.")

    @Slot("QVariantList", str, bool, result=bool)
    def startWatchQueue(self, keys: list[str], kind: str, shuffled: bool) -> bool:
        scene = self.watchScene
        if (
            self._watch_scene_route != "group"
            or kind != scene["queueKind"]
            or list(keys) != scene["queueKeys"]
            or not keys
        ):
            return False
        self._watch_queue.start(keys, kind=kind, shuffled=shuffled)
        return self._watch_queue.token is not None

    @Slot(str)
    def navigateLibrary(self, route: str) -> None:
        if route not in {
            "home",
            "all",
            "channels",
            "playlists",
            "collections",
            "videos",
            "audio",
            "folders",
        }:
            return
        if route == "home":
            self._library_history.clear()
        elif route != self._library_scene_route:
            self._remember_library_route()
        self._library_detail_from_watch = False
        if route == "folders":
            self._reconcile_folder_browser()
            self._folder_browser.navigate(None, mode="folders")
            self._queue_folder_listing()
            self._folder_inspector_owner = ""
            self._folder_file_path = ""
            self._folder_inspector_key = ""
            self._folder_inspector_versions = []
            self._issue_run_id = ""
            self._missing_issue_owner = ""
            self._issue_live_phase = ""
        self._library_scene_route = route
        self._library_group_key = ""
        self._library_group_kind = ""
        self._library_detail_owner = ""
        self._detail_versions = []
        self._library_detail_origin = None
        self.historyChanged.emit()
        if route == "folders":
            self._record_update_feature(
                "archive", "folders", {"archive_mode": "folders"}
            )

    @Slot()
    def openLibraryStorage(self) -> None:
        """Open saved-file paths on the drive represented by the storage tile."""
        self.navigateLibrary("folders")
        capacity = self._storage_snapshot.capacity
        if capacity is None:
            return
        try:
            drive = ArchivePath.parse(capacity.volume.path)
        except ValueError:
            return
        matches = [
            item
            for item in self._folder_browser.locations
            if item.path is not None and item.path.relative_to(drive) is not None
        ]
        if len(matches) == 1:
            self._folder_browser.navigate(matches[0].path)
            self._queue_folder_listing()
            self.historyChanged.emit()

    @Slot(str, str)
    def navigateLibraryGroup(self, kind: str, key: str) -> None:
        if kind not in {"channel", "playlist", "collection"} or not key:
            return
        if (
            self._library_scene_route,
            self._library_group_kind,
            self._library_group_key,
        ) != ("group", kind, key):
            self._remember_library_route()
        self._library_scene_route = "group"
        self._library_group_kind = kind
        self._library_group_key = key
        self.historyChanged.emit()

    @Slot(str, result=bool)
    def openLibraryDetails(self, owner: str) -> bool:
        if self._saved_item_for_owner(owner) is None:
            self._status = "That Library item changed. Select it again."
            self.statusChanged.emit()
            return False
        if self._library_scene_route != "detail":
            self._library_detail_from_watch = False
            if self._library_scene_route != "folders":
                self._detail_versions = []
            self._library_detail_origin = (
                self._library_scene_route,
                self._library_group_kind,
                self._library_group_key,
            )
        self._library_detail_owner = owner
        self._library_scene_route = "detail"
        self.historyChanged.emit()
        self._record_update_feature("library", "selected")
        return True

    @Slot()
    def returnLibraryDetails(self) -> None:
        if self._library_scene_route != "detail":
            return
        origin = self._library_detail_origin or ("home", "", "")
        self._library_scene_route, self._library_group_kind, self._library_group_key = (
            origin
        )
        self._library_detail_owner = ""
        self._detail_versions = []
        self._library_detail_origin = None
        self.historyChanged.emit()

    @Slot(str)
    def navigateLibraryFolders(self, mode: str) -> None:
        if mode not in {"folders", "all", "activity", "issues"}:
            return
        self._pending_folder_missing_owner = ""
        if self._library_scene_route != "folders":
            self._remember_library_route()
        self._reconcile_folder_browser()
        self._folder_browser.navigate(
            None, mode=cast(Literal["folders", "all", "activity", "issues"], mode)
        )
        self._folder_inspector_owner = ""
        self._folder_file_path = ""
        self._folder_inspector_key = ""
        self._folder_inspector_versions = []
        self._issue_run_id = ""
        self._missing_issue_owner = ""
        self._issue_settings = {}
        self._library_scene_route = "folders"
        self._record_update_feature(
            "archive",
            {
                "folders": "folders",
                "all": "all_media",
                "activity": "activity",
                "issues": "issues",
            }[mode],
            {"archive_mode": mode},
        )
        if mode == "issues":
            self._queue_availability_scan(
                [
                    dict(row)
                    for row in self._runtime.history
                    if archive_directory(row) is not None
                ],
                full=True,
            )
        else:
            if mode == "folders":
                self._queue_folder_listing()
            else:
                self._availability_work.cancel()
                self._availability_requests.clear()
                self.historyChanged.emit()

    @Slot(str, result=bool)
    def openFolderMissingIssue(self, owner: str) -> bool:
        model = self._folder_browser
        if (
            self._selection != "Library"
            or self._library_scene_route != "folders"
            or model.mode != "folders"
            or self._folder_listing_pending
            or self._folder_listing_error
            or owner
            not in {
                history_archive_owner(dict(model.records[index]))
                for index in model.unavailable_indices
            }
        ):
            return False
        self.navigateLibraryFolders("issues")
        self._pending_folder_missing_owner = owner
        return True

    def _folder_component(self, key: str) -> Any:
        if self._library_scene_route != "folders":
            return None
        self._reconcile_folder_browser()
        return next(
            (
                item
                for item in (
                    *self._folder_browser.components[
                        : (self._folder_browser.page + 1) * PAGE_SIZE
                    ],
                    *self._folder_browser.locations,
                )
                if item.key == key
            ),
            None,
        )

    def _folder_versions(self, component: Any) -> list[dict[str, str]]:
        rows = self._folder_browser.records
        return [
            {
                "owner": history_archive_owner(rows[index]),
                "label": f"{position + 1}. {metadata_output_profile(dict(rows[index]))}",
            }
            for position, index in enumerate(component.indices)
            if rows[index].get("vodforge_output_dir")
        ]

    def _issue_job(self, run_id: str) -> Any:
        return next(
            (
                job
                for job in [
                    self._runtime.active_job,
                    *self._runtime.queued,
                    *self._runtime.recovered,
                ]
                if job is not None and job.run_id == run_id
            ),
            None,
        )

    def _retry_settings_for_job(
        self, job: Any, source: str, output_dir: str
    ) -> dict[str, Any]:
        return {
            "source": source,
            "source_editable": not bool(source),
            "output_dir": output_dir,
            "output_url": QUrl.fromLocalFile(output_dir).toString(),
            "output_type": job.output_type.value,
            "export_mode": job.export_mode.value,
            "quality": job.quality_label
            if job.quality_label in QUALITY_OPTIONS
            else "",
            "manual": {
                "manual_rate_control": (
                    "Quality" if job.manual_settings.video_crf is not None else "CBR"
                ),
                "manual_crf": str(job.manual_settings.video_crf or 21),
                "manual_video_bitrate": str(job.manual_settings.video_bitrate_kbps),
                "manual_audio_bitrate": str(job.manual_settings.audio_bitrate_kbps),
                "manual_audio_codec": job.manual_settings.audio_codec.value,
                "manual_sample_rate": job.manual_settings.audio_sample_rate,
                "manual_channels": (
                    "Mono" if job.manual_settings.audio_channels == "1" else "Stereo"
                ),
                "manual_preset": job.manual_settings.x264_preset,
            },
            "single_video_only": job.single_video_only,
            "use_nvenc": job.use_nvenc,
            "embed_thumbnail": job.embed_thumbnail,
            "write_thumbnail": job.write_thumbnail,
            "embed_metadata": job.embed_metadata,
            "write_info_json": job.write_info_json,
        }

    @Slot(str, str)
    def setIssueRetrySetting(self, key: str, value: str) -> None:
        if (
            not (self._issue_run_id or self._missing_issue_owner)
            or self._folder_browser.mode != "issues"
        ):
            return
        options = {
            "output_type": {item.value for item in OutputType},
            "export_mode": {item.value for item in ExportMode},
            "quality": set(QUALITY_OPTIONS),
        }
        if value not in options.get(key, set()):
            return
        self._issue_settings[key] = value
        self.historyChanged.emit()

    @Slot(str, str)
    def setIssueManualValue(self, key: str, value: str) -> None:
        if (
            not (self._issue_run_id or self._missing_issue_owner)
            or self._folder_browser.mode != "issues"
        ):
            return
        manual = self._issue_settings.get("manual")
        if not isinstance(manual, dict) or key not in manual or len(value) > 32:
            return
        self._issue_settings["manual"] = {**manual, key: value}
        self.historyChanged.emit()

    @Slot(str)
    def setIssueRetrySource(self, value: str) -> None:
        if (
            self._missing_issue_owner
            and self._folder_browser.mode == "issues"
            and self._missing_plan is not None
            and self._missing_plan.job is None
        ):
            self._issue_settings["source"] = value.strip()
            self.historyChanged.emit()
            return
        if self._missing_issue_owner and self._folder_browser.mode == "issues":
            return
        if not self._issue_run_id or self._folder_browser.mode != "issues":
            return
        try:
            self._runtime.terminal_retry_source(self._issue_run_id)
        except ValueError:
            self._issue_settings["source"] = value.strip()
            self.historyChanged.emit()

    @Slot(result=bool)
    def copyIssueSource(self) -> bool:
        if self._folder_browser.mode != "issues" or not (
            self._issue_run_id or self._missing_issue_owner
        ):
            return False
        source = str(self._issue_settings.get("source") or "").strip()
        clipboard = QGuiApplication.clipboard()
        if not source or clipboard is None:
            return False
        clipboard.setText(source)
        self._status = "Copied source URL."
        self.statusChanged.emit()
        return True

    @Slot(str, bool)
    def setIssueRetryFlag(self, key: str, value: bool) -> None:
        if (
            not (self._issue_run_id or self._missing_issue_owner)
            or self._folder_browser.mode != "issues"
        ):
            return
        if key not in {
            "single_video_only",
            "use_nvenc",
            "embed_thumbnail",
            "write_thumbnail",
            "embed_metadata",
            "write_info_json",
        } or (key == "use_nvenc" and value and not self._nvenc_available):
            return
        self._issue_settings[key] = value
        self.historyChanged.emit()

    @Slot(QUrl)
    def chooseIssueOutputUrl(self, value: QUrl) -> None:
        if (
            not (self._issue_run_id or self._missing_issue_owner)
            or not value.isLocalFile()
        ):
            return
        path = Path(value.toLocalFile())
        if not path.is_dir():
            self._set_status("Select an existing output folder.")
            return
        self._issue_settings["output_dir"] = str(path)
        self._issue_settings["output_url"] = QUrl.fromLocalFile(str(path)).toString()
        self.historyChanged.emit()

    @Slot(result=bool)
    def downloadSelectedIssue(self) -> bool:
        if (
            self._library_scene_route != "folders"
            or self._folder_browser.mode != "issues"
        ):
            return False
        if self._missing_issue_owner:
            return self._download_missing_issue()
        job = self._issue_job(self._issue_run_id)
        if job is None or job.terminal_status not in {
            "Failed",
            "Stopped",
            "Skipped",
            "Paused",
            "Partial",
        }:
            self._set_status("Select an interrupted run before downloading.")
            return False
        if job.terminal_status in {"Paused", "Partial"}:
            # Resume belongs to the durable run owner, never the editable draft.
            return self._admit_retry(job.run_id, stay_in_issues=True)
        config = self._issue_settings
        if not all(
            config.get(key)
            for key in ("source", "output_dir", "output_type", "export_mode", "quality")
        ):
            self._set_status("Choose the output folder and download settings first.")
            return False
        try:
            try:
                previous_source = self._runtime.terminal_retry_source(job.run_id)[1]
            except ValueError:
                previous_source = str(config["source"])
            if config["source"] != previous_source:
                raise ValueError("The source changed. Select this issue again.")
            selected_type = OutputType(config["output_type"])
            manual_settings = (
                manual_export_settings(config["manual"])
                if selected_type is OutputType.MP4
                and config["export_mode"] == ExportMode.MANUAL_OVERRIDE.value
                else job.manual_settings
            )
            access = (
                CookieSource.FILE
                if job.use_cookies and job.cookie_file is not None
                else CookieSource.BROWSER
                if job.use_cookies and job.cookie_browser
                else CookieSource.PUBLIC
            )
            prepared = self._runtime.prepare_job(
                previous_source,
                Path(config["output_dir"]),
                selected_type.value,
                config["export_mode"],
                config["quality"],
                DownloadPreferences(
                    **{
                        key: bool(config[key])
                        for key in (
                            "single_video_only",
                            "use_nvenc",
                            "embed_thumbnail",
                            "write_thumbnail",
                            "embed_metadata",
                            "write_info_json",
                        )
                    }
                ),
                manual_settings,
                job.mp3_settings,
                urls=[previous_source],
                batch_mode=False,
                cookie_source=access,
                translated_subtitle_language=job.translated_subtitle_language,
                cookie_file=job.cookie_file,
                cookie_browser=job.cookie_browser,
                tags=job.tags,
                nvenc_applicable=self.nvencAvailable,
            )
            prepared.preview_info = {"vodforge_issue_retry": True}
        except (OSError, RuntimeError, ValueError) as exc:
            self._set_status(str(exc))
            return False
        return self._admit_retry(job.run_id, current_job=prepared, stay_in_issues=True)

    def _download_missing_issue(self) -> bool:
        plan = self._missing_plan
        row = self._current_missing_record()
        existing = self._issue_job(self._missing_retry_run_id)
        if (
            existing is not None
            and existing.terminal_status
            in {"Failed", "Stopped", "Skipped", "Paused", "Partial"}
            and row is not None
        ):
            plan = self._media_recovery.plan(
                row, completed_jobs=self._runtime.recovered
            )
            self._missing_plan = plan
            self._missing_retry_run_id = ""
        if (
            plan is None
            or row is None
            or self._missing_retry_run_id
            or self._relink.active
            or self._file_action_busy
            or self._import_pending
        ):
            return False
        config = self._issue_settings
        job = plan.job
        if not all(
            config.get(key)
            for key in ("source", "output_dir", "output_type", "export_mode", "quality")
        ):
            self._set_status("Choose an output folder and download settings first.")
            return False
        if job is not None and (
            config.get("source") != job.url
            or config.get("output_type") != job.output_type.value
        ):
            self._set_status(
                "This recovery must keep the saved source and file format."
            )
            return False
        try:
            output_dir = Path(str(config["output_dir"]))
            if not output_dir.is_dir():
                raise ValueError("Choose an existing output folder.")
            selected_type = OutputType(str(config["output_type"]))
            manual = (
                manual_export_settings(config["manual"])
                if selected_type is OutputType.MP4
                and config["export_mode"] == ExportMode.MANUAL_OVERRIDE.value
                else job.manual_settings
                if job is not None
                else None
            )
            flags = {
                key: bool(config[key])
                for key in (
                    "single_video_only",
                    "use_nvenc",
                    "embed_thumbnail",
                    "write_thumbnail",
                    "embed_metadata",
                    "write_info_json",
                )
            }
            flags["single_video_only"] = True
            if job is not None:
                prepared = replace(
                    job,
                    output_dir=output_dir,
                    export_mode=ExportMode(str(config["export_mode"])),
                    quality_label=str(config["quality"]),
                    manual_settings=manual
                    if manual is not None
                    else job.manual_settings,
                    single_video_only=flags["single_video_only"],
                    use_nvenc=flags["use_nvenc"],
                    embed_thumbnail=flags["embed_thumbnail"],
                    write_thumbnail=flags["write_thumbnail"],
                    embed_metadata=flags["embed_metadata"],
                    write_info_json=flags["write_info_json"],
                    nvenc_applicable=self.nvencAvailable,
                )
            else:
                prepared = self._runtime.prepare_job(
                    str(config["source"]),
                    output_dir,
                    selected_type.value,
                    str(config["export_mode"]),
                    str(config["quality"]),
                    DownloadPreferences(**flags),
                    manual,
                    urls=[str(config["source"])],
                    batch_mode=False,
                    nvenc_applicable=self.nvencAvailable,
                )
            prepared.preview_info = annotate_job_metadata(
                prepared, dict(prepared.preview_info or {})
            )
            prepared.recovery_reason = "missing_media"
            prepared.annotation_source_owner = (
                plan.previous_annotation_owner or history_annotation_owner(row)
            )
            self._runtime.start_job(prepared)
        except (OSError, RuntimeError, RunStateError, ValueError) as exc:
            self._set_status(str(exc))
            return False
        self._missing_retry_run_id = prepared.run_id
        self._record_update_feature(
            "missing_media", "accepted", {"archive_mode": "issues"}
        )
        self._issue_live_phase = "Preparing"
        self._set_status(
            "Recovery queued."
            if prepared in self._runtime.queued
            else "Preparing recovery."
        )
        self.historyChanged.emit()
        self.runningChanged.emit()
        self.activityChanged.emit()
        return True

    @Slot()
    def requestMissingFileRelink(self) -> None:
        owner = self._missing_issue_owner
        if (
            self._library_scene_route == "folders"
            and self._folder_browser.mode == "issues"
            and owner
            and self._saved_item_for_owner(owner) is not None
        ):
            self.fileRelinkRequested.emit(owner)

    @Slot(str, result=bool)
    def selectLibraryFolderComponent(self, key: str) -> bool:
        component = self._folder_component(key)
        if (
            component is not None
            and component.kind == "file"
            and component.path is not None
            and self._folder_browser.mode == "folders"
        ):
            path = component.path
            parents = [
                row
                for row in self._runtime.history
                if archive_directory(row) == path.parent
            ]
            related = (
                parents[0]
                if len(parents) == 1
                and path.name
                in {
                    "metadata.json",
                    "thumbnail.jpg",
                    "thumbnail.jpeg",
                    "thumbnail.png",
                    "thumbnail.webp",
                }
                else None
            )
            self._folder_file_path = str(path)
            self._folder_file_detail_text = component.detail
            self._folder_file_owner = (
                history_archive_owner(related) if related is not None else ""
            )
            self._folder_inspector_key = key
            self._folder_inspector_owner = ""
            self._folder_inspector_versions = []
            self.historyChanged.emit()
            return True
        if (
            component is not None
            and component.kind == "missing"
            and self._folder_browser.mode == "issues"
            and component.indices
        ):
            owner = history_archive_owner(
                self._folder_browser.records[component.indices[0]]
            )
            row = self._saved_item_for_owner(owner)
            if row is None or self._missing_files.get(owner) != record_fingerprint(row):
                return False
            plan = self._media_recovery.plan(
                row, completed_jobs=self._runtime.recovered
            )
            if plan.kind in {"available", "unavailable", "ambiguous"}:
                self._missing_files.pop(owner, None)
                self.historyChanged.emit()
                return False
            self._missing_issue_owner = owner
            self._folder_file_path = ""
            self._missing_retry_run_id = ""
            self._issue_live_phase = ""
            self._missing_plan = plan
            self._missing_fingerprint = record_fingerprint(row)
            self._missing_media = {"owner": owner}
            self._record_update_feature(
                "missing_media", "offered", {"archive_mode": "issues"}
            )
            self._issue_run_id = ""
            self._folder_inspector_key = key
            self._folder_inspector_owner = ""
            self._folder_inspector_versions = []
            job = plan.job
            self._issue_settings = (
                self._retry_settings_for_job(
                    job,
                    job.url,
                    str(plan.destination)
                    if plan.destination is not None and plan.destination.is_dir()
                    else "",
                )
                if job is not None
                else {
                    "source": canonical_youtube_url(row) or "",
                    "source_editable": True,
                    "output_dir": "",
                    "output_type": metadata_output_type(row).value,
                    "export_mode": "",
                    "quality": "",
                    "manual": dict(self._manual_values),
                    "single_video_only": True,
                    "use_nvenc": False,
                    "embed_thumbnail": True,
                    "write_thumbnail": False,
                    "embed_metadata": True,
                    "write_info_json": False,
                }
            )
            self.historyChanged.emit()
            return True
        if (
            component is not None
            and component.kind == "activity"
            and self._folder_browser.mode == "issues"
            and component.indices
        ):
            row = self._folder_browser.records[component.indices[0]]
            run_id = str(
                row.get("vodforge_terminal_run_id")
                or row.get("vodforge_active_run_id")
                or row.get("vodforge_queued_run_id")
                or ""
            )
            job = self._issue_job(run_id)
            if job is None:
                self._set_status(
                    "Saved run settings are unavailable. Open the source in Forge."
                )
                return False
            try:
                _status, source = self._runtime.terminal_retry_source(run_id)
            except ValueError:
                source = ""
            self._issue_run_id = run_id
            self._folder_file_path = ""
            self._missing_issue_owner = ""
            self._issue_live_phase = (
                self._recovery_progress_label()
                if job is self._runtime.active_job
                else ""
            )
            self._folder_inspector_key = key
            self._folder_inspector_owner = ""
            self._folder_inspector_versions = []
            self._issue_settings = self._retry_settings_for_job(
                job, source, str(job.output_dir) if job.output_dir.is_dir() else ""
            )
            self.historyChanged.emit()
            return True
        if component is None or component.kind != "media":
            return False
        versions = self._folder_versions(component)
        if not versions:
            return False
        self._folder_inspector_owner = versions[0]["owner"]
        self._folder_file_path = ""
        self._folder_inspector_key = key
        self._folder_inspector_versions = versions
        self._issue_run_id = ""
        self._missing_issue_owner = ""
        self._issue_live_phase = ""
        self._issue_settings = {}
        self.historyChanged.emit()
        return True

    @Slot(str, result=bool)
    def chooseLibraryFolderInspectorVersion(self, owner: str) -> bool:
        if (
            self._library_scene_route != "folders"
            or owner not in {item["owner"] for item in self._folder_inspector_versions}
            or self._saved_item_for_owner(owner) is None
        ):
            return False
        self._folder_inspector_owner = owner
        self.historyChanged.emit()
        return True

    @Slot(result=bool)
    def openSelectedLibraryFolderDetail(self) -> bool:
        if self._library_scene_route != "folders" or not self._folder_inspector_owner:
            return False
        self._detail_versions = list(self._folder_inspector_versions)
        return self.openLibraryDetails(self._folder_inspector_owner)

    @Slot(result=bool)
    def attestQtLibraryVisibility(self) -> bool:
        if not quality_e2e_mode_enabled():
            return False
        window = self._window
        if window is None or self._library_scene_route != "folders":
            return False
        names = {
            "rail": "libraryFolderInspector",
            "details": "libraryFolderDetailsPanel",
            "table": "libraryFolderViewport",
            "heading": "libraryFolderDescriptionHeading",
            "scroll": "libraryFolderDescriptionScroll",
            "description": "libraryFolderDescriptionText",
            "title": "libraryFolderSelectedTitle",
            "location": "libraryInspectorExactLocation",
            "footer": "libraryInspectorActionFooter",
            "footer_action": "libraryFolderOpenDetails",
        }
        items = {key: window.findChild(QObject, name) for key, name in names.items()}
        if any(item is None for item in items.values()):
            return False
        if not items["location"].isVisible():
            items["location"] = window.findChild(
                QObject, "libraryFolderSelectedLocation"
            )
        if items["location"] is None:
            return False
        location_text = items["location"].findChild(QObject, "outputPathText")
        if location_text is None:
            return False
        rail = items["rail"]
        if rail.property("section") != "Description" or not rail.isVisible():
            return False
        detail = self.libraryFolderInspector
        selected_owner = self._folder_inspector_owner
        if not selected_owner or detail.get("owner") != selected_owner:
            return False
        if window.grabWindow().isNull():
            return False

        def bounds(item: Any) -> dict[str, int]:
            point = item.mapToScene(QPointF(0, 0))
            return {
                "x": round(window.x() + point.x()),
                "y": round(window.y() + point.y()),
                "width": round(item.width()),
                "height": round(item.height()),
            }

        scroll_content = items["scroll"].property("contentItem")
        if scroll_content is None:
            return False
        receipt = write_quality_e2e_qt_library_visibility_receipt(
            full_title=str(detail.get("title") or ""),
            description_text=str(items["description"].property("text") or ""),
            selected_owner=selected_owner,
            projected_owner=str(detail.get("owner") or ""),
            displayed_title_visible_lines=min(
                2, int(items["title"].property("lineCount") or 0)
            ),
            title_truncated=bool(items["title"].property("truncated")),
            location_truncated=bool(location_text.property("truncated")),
            location_visible=items["location"].isVisible()
            and location_text.isVisible(),
            footer_bounds=bounds(items["footer"]),
            footer_action_bounds=bounds(items["footer_action"]),
            footer_visible=items["footer"].isVisible(),
            footer_action_visible=items["footer_action"].isVisible(),
            details_footer_gap_px=round(float(rail.property("spacing") or 0)),
            rail_bounds=bounds(rail),
            details_bounds=bounds(items["details"]),
            library_table_bounds=bounds(items["table"]),
            description_heading_bounds=bounds(items["heading"]),
            description_viewport_bounds=bounds(items["scroll"]),
            description_text_bounds=bounds(items["description"]),
            rail_visible=rail.isVisible(),
            heading_visible=items["heading"].isVisible(),
            description_visible=items["description"].isVisible(),
            library_table_visible=items["table"].isVisible(),
            description_scroll_at_start=abs(
                float(scroll_content.property("contentY") or 0)
            )
            <= 0.5,
            library_invariant_receipt=self._library_projection.snapshot.receipt,
        )
        return receipt is not None

    @Slot(str, result=bool)
    def openLibraryFolderComponent(self, key: str) -> bool:
        component = self._folder_component(key)
        if component is None:
            return False
        if component.kind == "folder" and component.path is not None:
            self._folder_browser.navigate(component.path)
            self._queue_folder_listing()
            self._folder_inspector_owner = ""
            self._folder_file_path = ""
            self._folder_inspector_key = ""
            self._folder_inspector_versions = []
            self._issue_run_id = ""
            self._issue_settings = {}
            self.historyChanged.emit()
            self._record_update_feature(
                "archive", "folder_opened", {"archive_mode": "folders"}
            )
            return True
        if component.kind == "activity":
            if self._folder_browser.mode == "issues":
                return self.selectLibraryFolderComponent(key)
            rows = self._folder_browser.records
            if not component.indices:
                return False
            row = rows[component.indices[0]]
            if is_metadata_preview(row):
                return self.openPreviewOwner(str(row.get(PROJECTION_OWNER_KEY) or ""))
            if str(row.get("vodforge_terminal_status") or "") in {
                "Failed",
                "Stopped",
                "Skipped",
            } and not row.get("vodforge_output_dir"):
                self.navigateLibraryFolders("issues")
                return self.selectLibraryFolderComponent(key)
            self.select("Forge")
            return True
        if component.kind != "media":
            return False
        versions = self._folder_versions(component)
        if not versions:
            return False
        self._detail_versions = versions
        return self.openLibraryDetails(versions[0]["owner"])

    @Slot()
    def upLibraryFolder(self) -> None:
        if self._library_scene_route != "folders":
            return
        self._reconcile_folder_browser()
        model = self._folder_browser
        if model.parent_path is None and not (
            model.path is not None and len(model.locations) > 1
        ):
            return
        model.navigate(model.parent_path)
        self._queue_folder_listing()
        self._folder_inspector_owner = ""
        self._folder_file_path = ""
        self._folder_inspector_key = ""
        self._folder_inspector_versions = []
        self._issue_run_id = ""
        self._issue_settings = {}
        self.historyChanged.emit()
        self._record_update_feature(
            "archive", "scene_navigated", {"archive_mode": "folders"}
        )

    @Slot(str, result=bool)
    def openLibraryBreadcrumb(self, path: str) -> bool:
        if self._library_scene_route != "folders":
            return False
        self._reconcile_folder_browser()
        target = next(
            (item for item in self._folder_browser.breadcrumbs if str(item) == path),
            None,
        )
        if target is None:
            return False
        self._folder_browser.navigate(target)
        self._queue_folder_listing()
        self._folder_inspector_owner = ""
        self._folder_file_path = ""
        self._folder_inspector_key = ""
        self._folder_inspector_versions = []
        self._issue_run_id = ""
        self._missing_issue_owner = ""
        self._issue_settings = {}
        self.historyChanged.emit()
        self._record_update_feature(
            "archive", "scene_navigated", {"archive_mode": "folders"}
        )
        return True

    @Slot()
    def loadMoreLibraryFolder(self) -> None:
        if self._library_scene_route != "folders":
            return
        self._reconcile_folder_browser()
        model = self._folder_browser
        last_page = max(0, (len(model.components) - 1) // PAGE_SIZE)
        if model.page >= last_page:
            return
        model.page += 1
        self.historyChanged.emit()

    @Slot(str, result=bool)
    def chooseLibraryVersion(self, owner: str) -> bool:
        if self._library_scene_route != "detail" or owner not in {
            item["owner"] for item in self._detail_versions
        }:
            return False
        if self._saved_item_for_owner(owner) is None:
            return False
        self._library_detail_owner = owner
        self.historyChanged.emit()
        return True

    @Slot(str)
    def navigateWatch(self, route: str) -> None:
        if route not in {"home", "channels", "playlists", "collections", "videos"}:
            return
        if route == "home":
            self._watch_history.clear()
        elif (route, "", "", "") != (
            self._watch_scene_route,
            self._watch_group_kind,
            self._watch_group_key,
            self._watch_search,
        ):
            self._watch_history.append(
                (
                    self._watch_scene_route,
                    self._watch_group_kind,
                    self._watch_group_key,
                    self._watch_search,
                )
            )
            del self._watch_history[:-32]
        self._watch_scene_route = route
        self._watch_group_key = ""
        self._watch_group_kind = ""
        self._watch_search = ""
        self.historyChanged.emit()
        if route in {"channels", "playlists", "collections"}:
            self._record_update_feature("watch", route)

    @Slot(str, str)
    def navigateWatchGroup(self, kind: str, key: str) -> None:
        if kind not in {"channel", "playlist", "collection"} or not key:
            return
        self._watch_history.append(
            (
                self._watch_scene_route,
                self._watch_group_kind,
                self._watch_group_key,
                self._watch_search,
            )
        )
        del self._watch_history[:-32]
        self._watch_scene_route = "group"
        self._watch_group_kind = kind
        self._watch_group_key = key
        self._watch_search = ""
        self.historyChanged.emit()
        if kind == "channel":
            self._record_update_feature(
                "watch", "channel_opened", {"watch_mode": "channels"}
            )

    @Slot(str)
    def setWatchSearch(self, value: str) -> None:
        value = value[:200]
        if value == self._watch_search:
            return
        self._watch_search = value
        self.historyChanged.emit()
        if value.strip():
            self._record_update_feature("watch", "searched")

    @Property(str, notify=activeSearchChanged)
    def activeSearch(self) -> str:
        if self._selection == "Watch":
            return self._watch_search
        if self._selection == "Library":
            return self._library_search
        return ""

    @Slot(str)
    def setActiveSearch(self, value: str) -> None:
        if self._selection == "Watch":
            self.setWatchSearch(value)
        elif self._selection == "Library":
            self.setLibrarySearch(value)

    @Slot()
    def backWatch(self) -> None:
        if self._watch_history:
            (
                self._watch_scene_route,
                self._watch_group_kind,
                self._watch_group_key,
                self._watch_search,
            ) = self._watch_history.pop()
        else:
            self._watch_scene_route = "home"
            self._watch_group_kind = self._watch_group_key = self._watch_search = ""
        self.historyChanged.emit()

    @Slot(result=bool)
    def isPointerPressed(self) -> bool:
        return QGuiApplication.mouseButtons() != Qt.MouseButton.NoButton

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if isinstance(watched, QWindow):
            if event.type() in {
                QEvent.Type.MouseButtonPress,
                QEvent.Type.MouseButtonRelease,
                QEvent.Type.MouseMove,
                QEvent.Type.KeyPress,
                QEvent.Type.Wheel,
            }:
                self._social_idle_since = time.monotonic()
            if event.type() == QEvent.Type.MouseButtonPress:
                self._pointer_press = (watched, QPointF(cast(Any, event).position()))
            elif event.type() == QEvent.Type.MouseButtonRelease:
                self._pointer_press = None
                # Run after this release's MouseArea click handlers. Modal
                # dismissal can consume the click before the trigger sees it.
                QTimer.singleShot(0, self._notify_pointer_release)
        return False

    def _notify_pointer_release(self) -> None:
        if not self._closed and self._pointer_press is None:
            self.pointerGestureEnded.emit()

    @Slot(QObject, result=bool)
    def isPointerPressOnItem(self, item: QObject) -> bool:
        # Hover can remain stale under a modal overlay. Bind dismissal to the
        # actual press delivered to this window, without retaining input logs.
        if (
            not isinstance(item, QQuickItem)
            or self._pointer_press is None
            or not self.isPointerPressed()
        ):
            return False
        window, position = self._pointer_press
        return bool(
            item.window() == window and item.contains(item.mapFromScene(position))
        )

    @Slot(str, result=bool)
    def openSupport(self, kind: str) -> bool:
        if not self._support.open(
            kind, self._latest_failure if kind == "feedback" else None
        ):
            return False
        self.supportChanged.emit()
        self.supportRequested.emit()
        return True

    @Slot("QVariantMap", result=bool)
    def submitSupport(self, values: dict[str, Any]) -> bool:
        accepted = self._support.submit(values)
        self.supportChanged.emit()
        return accepted

    @Slot(result=bool)
    def closeSupport(self) -> bool:
        if not self._support.close():
            return False
        self.supportChanged.emit()
        return True

    @Slot(result=bool)
    def openWhatsNew(self) -> bool:
        if (
            not self.whatsNewAvailable
            or not self._analytics.settled
            or self._editorial_kind
            or self._support.kind
        ):
            return False
        self._editorial_kind = "whats-new"
        self._editorial_slides = HIGHLIGHTS
        self.editorialChanged.emit()
        self.editorialRequested.emit()
        self._record_update_feature("announcement", "shown")
        return True

    @Slot(result=bool)
    def openWelcomeTour(self) -> bool:
        return self._open_welcome(compact=False)

    @Slot(result=bool)
    def openWelcome(self) -> bool:
        return self._open_welcome(compact=True)

    def _open_welcome(self, *, compact: bool) -> bool:
        if self._editorial_kind or self._support.kind or self._social_invitation_open:
            return False
        self._editorial_kind = "welcome" if compact else "welcome-tour"
        self._editorial_slides = (
            (
                replace(
                    WELCOME_SLIDES[0],
                    title="Your videos. Ready when you are.",
                    description="Download, organize and watch in one place.",
                ),
            )
            if compact
            else WELCOME_SLIDES
        )
        try:
            self._engagement.presented_welcome()
        except (OSError, ValueError):
            pass
        self._settings["whats_new_seen"] = SHOWCASE_ID
        if compact:
            # This screen already includes the optional invitation.
            self._settings["social_invitation_dismissed"] = True
        self._schedule_preferences_save()
        self.editorialChanged.emit()
        self.editorialRequested.emit()
        return True

    @Slot(bool)
    def checkEditorial(self, ui_ready: bool) -> None:
        if (
            not ui_ready
            or not self._analytics.settled
            or self._editorial_kind
            or self._social_invitation_open
            or self._support.kind
            or self._runtime.active_job is not None
            or self._runtime.busy
            or self._runtime.queued
            or self._playback_binding is not None
        ):
            self._social_idle_since = time.monotonic()
            return
        try:
            if self._engagement.welcome_pending:
                self.openWelcome()
                return
            if self._engagement.rating_pending:
                if self.openSupport("review"):
                    self._engagement.presented_rating()
                return
        except (OSError, ValueError):
            return
        if (
            SHOWCASE_MODE in {"whats-new", "did-you-know"}
            and self._settings.get("whats_new_seen") != SHOWCASE_ID
        ):
            slides = (
                DID_YOU_KNOW_HIGHLIGHTS
                if SHOWCASE_MODE == "did-you-know"
                else HIGHLIGHTS
            )
            if slides:
                self._editorial_kind = SHOWCASE_MODE
                self._editorial_slides = slides
                self.editorialChanged.emit()
                self.editorialRequested.emit()
                self._record_update_feature("announcement", "shown")
                return
        if (
            self._settings.get("social_invitation_dismissed") is not True
            and time.monotonic() - self._social_idle_since >= 8
            and not self.isPointerPressed()
        ):
            self._social_invitation_open = True
            self.socialInvitationRequested.emit()

    @Slot(bool)
    def dismissSocialInvitation(self, follow: bool) -> None:
        if not self._social_invitation_open:
            return
        self._social_invitation_open = False
        self._settings["social_invitation_dismissed"] = True
        self._schedule_preferences_save()
        if follow:
            self.openSocialAccount()

    @Slot(bool)
    def dismissEditorial(self, try_it: bool) -> None:
        if not self._editorial_kind:
            return
        if self._editorial_kind in {"whats-new", "did-you-know"}:
            self._settings["whats_new_seen"] = SHOWCASE_ID
            self._schedule_preferences_save()
            if try_it:
                self._record_update_feature("announcement", "try_it")
        self._editorial_kind = ""
        self._editorial_slides = ()
        self.editorialChanged.emit()

    @Slot(str)
    def playWatchHero(self, owner: str) -> None:
        # Watch retains its visible hero as progress changes. A fresh ranking
        # may now feature another title; validate the requested saved owner,
        # rather than silently rejecting the still-visible Play control.
        if self._saved_item_for_owner(owner) is None:
            return
        self._record_update_feature(
            "watch", "hero_played", {"watch_mode": self._watch_mode()}
        )
        self.openLibraryOwner(owner)

    @Slot(str, result=bool)
    def openWatchDetails(self, owner: str) -> bool:
        if not self.openLibraryDetails(owner):
            return False
        self._library_detail_from_watch = True
        self._record_update_feature("watch", "details")
        self.select("Library")
        return True

    @Slot(str, "QVariantList", result=bool)
    def createCollection(self, name: str, owners: list[str]) -> bool:
        name = name.strip()
        available = {item["owner"] for item in self.collectionCandidates}
        chosen = set(owners)
        if (
            not name
            or len(name) > 120
            or not chosen
            or not chosen <= available
            or not self._annotations_writable
        ):
            self._status = "Name a collection and choose saved media."
            self.statusChanged.emit()
            return False
        try:
            self._annotations.replace_many(
                {
                    owner: replace(
                        self._annotations.annotation_for(owner), category=name
                    )
                    for owner in chosen
                }
            )
        except (LibraryAnnotationsError, OSError, ValueError) as error:
            self._status = str(error)
            self.statusChanged.emit()
            return False
        self._record_update_feature("organization", "category_saved")
        self.historyChanged.emit()
        self._status = f"Collection {name} saved."
        self.statusChanged.emit()
        return True

    @Slot(str, "QVariantList", result=bool)
    def addToCollection(self, name: str, owners: list[str]) -> bool:
        if name not in self.libraryCategories[1:]:
            self._status = "Choose an existing collection."
            self.statusChanged.emit()
            return False
        return self.createCollection(name, owners)

    @Slot(str, "QVariantList", result="QVariantList")
    def resolveScopedLibrarySelection(
        self, section: str, targets: list[dict[str, Any]]
    ) -> list[str]:
        """Reject cross-section or stale targets before opening any bulk action."""
        if section not in {"groups", "media"} or not targets:
            return []
        route = self.libraryScene["route"]
        group_route = route in {"channels", "playlists", "collections"}
        if (section == "groups" and route != "home" and not group_route) or (
            section == "media" and (group_route or route in {"detail", "folders"})
        ):
            return []
        if any(
            not isinstance(target, dict)
            or (target.get("kind") == "media") != (section == "media")
            for target in targets
        ):
            return []
        return self.resolveLibrarySelection(targets)

    @Slot("QVariantList", result="QVariantList")
    def resolveLibrarySelection(self, targets: list[dict[str, Any]]) -> list[str]:
        """Expand current screen entities only when an action is requested."""
        if self._selection != "Library" or not targets:
            return []
        # A bulk action must never combine collection/group members and files.
        if any(
            not isinstance(target, dict) or not isinstance(target.get("kind"), str)
            for target in targets
        ):
            return []
        kinds = {target["kind"] for target in targets}
        if "media" in kinds and len(kinds) > 1:
            return []
        scene = self.libraryScene
        groups = {
            (str(group["kind"]), str(group["key"])): group for group in scene["groups"]
        }
        media = {str(item["owner"]) for item in scene["media"]}
        seen: set[tuple[str, str]] = set()
        owners: list[str] = []
        for target in targets:
            if not isinstance(target, dict):
                return []
            kind = target.get("kind")
            key = target.get("owner") if kind == "media" else target.get("key")
            if not isinstance(kind, str) or not isinstance(key, str) or not key:
                return []
            identity = (kind, key)
            if identity in seen:
                return []
            seen.add(identity)
            if kind == "media":
                if key not in media:
                    return []
                owners.append(key)
            else:
                group = groups.get(identity)
                if group is None:
                    return []
                owners.extend(group["owners"])
        resolved = list(dict.fromkeys(owners))
        if any(self._saved_item_for_owner(owner) is None for owner in resolved):
            return []
        return resolved

    @Slot("QVariantList", result="QVariantList")
    def collectionOwnersForArchiveSelection(self, owners: list[str]) -> list[str]:
        """Resolve selected file owners to the stable annotation owners."""
        if not owners or len(owners) != len(set(owners)):
            return []
        items = [self._saved_item_for_owner(owner) for owner in owners]
        if any(item is None for item in items):
            self._status = "Selected Library items changed. Select them again."
            self.statusChanged.emit()
            return []
        return list(
            dict.fromkeys(
                history_annotation_owner(item) for item in items if item is not None
            )
        )

    @Slot(str, result=bool)
    def openAnnotationOwner(self, owner: str) -> bool:
        rows = self._projected_library()
        index = next(
            (
                index
                for index, row in enumerate(rows)
                if str(row.get(PROJECTION_OWNER_KEY) or "") == owner
            ),
            None,
        )
        return self.openAnnotation(index) if index is not None else False

    @Slot(str)
    def setLibrarySearch(self, query: str) -> None:
        query = query[:500]
        if query == self._library_search:
            return
        self._library_search = query
        if query and self._library_scene_route != "all":
            self._remember_library_route()
            self._library_scene_route = "all"
        self.librarySearchChanged.emit()
        self.historyChanged.emit()
        if query.strip():
            self._record_update_feature("library", "searched")

    @Slot(str)
    def setLibraryType(self, output_type: str) -> None:
        if output_type not in {
            LIBRARY_ALL_MEDIA,
            LIBRARY_VIDEO_MEDIA,
            LIBRARY_AUDIO_MEDIA,
            *(item.value for item in OutputType),
        }:
            return
        if output_type == self._library_type:
            return
        self._library_type = output_type
        self.libraryTypeChanged.emit()
        self.historyChanged.emit()
        self._record_update_feature("library", "filtered")

    @Slot(str)
    def setLibraryCategory(self, category: str) -> None:
        if category not in self.libraryCategories:
            return
        if category == self._library_category:
            return
        self._library_category = category
        self.libraryCategoryChanged.emit()
        self.historyChanged.emit()
        self._record_update_feature("library", "filtered")

    @Slot(str)
    def setLibrarySort(self, value: str) -> None:
        if value not in {"recent", "title"} or value == self._library_sort:
            return
        self._library_sort = value
        self.librarySortChanged.emit()
        self.historyChanged.emit()

    @Slot(int, result=bool)
    def openAnnotation(self, index: int) -> bool:
        rows = self._projected_library()
        if not 0 <= index < len(rows):
            return False
        self._annotation_owner = str(rows[index].get(ANNOTATION_OWNER_KEY) or "")
        if not self._annotation_owner:
            return False
        annotation = self._annotations.annotation_for(self._annotation_owner)
        self._annotation_values = {
            "note": annotation.note,
            "tags": ", ".join(annotation.tags),
            "category": annotation.category,
        }
        self.annotationChanged.emit()
        return True

    @Slot(str, str, str, result=bool)
    def saveAnnotation(self, note: str, tags: str, category: str) -> bool:
        if not self._annotation_owner or not self._annotations_writable:
            self._status = (
                "Library annotations need attention before changes can be saved."
            )
            self.statusChanged.emit()
            return False
        previous = self._annotations.annotation_for(self._annotation_owner)
        annotation = replace(
            previous,
            note=note,
            tags=tuple(item.strip() for item in tags.split(",") if item.strip()),
            category=category,
        )
        try:
            self._annotations.replace(self._annotation_owner, annotation)
        except LibraryAnnotationsError as exc:
            self._status = str(exc)
            self.statusChanged.emit()
            return False
        for before, after, action in (
            (previous.note, annotation.note, "notes_saved"),
            (previous.tags, annotation.tags, "tags_saved"),
            (previous.category, annotation.category, "category_saved"),
        ):
            if after != before:
                self._record_update_feature("organization", action)
        if self._library_category not in self.libraryCategories:
            self._library_category = LIBRARY_ALL_CATEGORIES
            self.libraryCategoryChanged.emit()
        self._status = "Library notes and organization saved."
        self.statusChanged.emit()
        self.historyChanged.emit()
        return True

    def _detail_annotation_owner(self, owner: str) -> str:
        if owner != self._library_detail_owner or not self._annotations_writable:
            return ""
        row = next(
            (
                item
                for item in self._projected_library()
                if history_archive_owner(item) == owner
            ),
            None,
        )
        if row is None or not row.get("vodforge_output_dir"):
            return ""
        return str(row.get(ANNOTATION_OWNER_KEY) or "")

    def _detail_fact(self, owner: str, section: str, label: str) -> str | None:
        if owner != self._library_detail_owner or self._library_scene_route != "detail":
            return None
        row = self._saved_item_for_owner(owner)
        if row is None:
            return None
        source, output = library_detail_facts(row)
        fields = {"source": source, "output": output}.get(section)
        if fields is None:
            return None
        return next((value for name, value, _icon in fields if name == label), None)

    @Slot(str, str, str, result=bool)
    def copyLibraryFact(self, owner: str, section: str, label: str) -> bool:
        value = self._detail_fact(owner, section, label)
        if value is None:
            return False
        clipboard = QGuiApplication.clipboard()
        if clipboard is None:
            return False
        clipboard.setText(value)
        self._status = "Copied Library detail."
        self.statusChanged.emit()
        return True

    @Slot(str, str, result=bool)
    @Slot(str, str, str, result=bool)
    def copyLibraryText(
        self, owner: str, field: str, displayed_note: str | None = None
    ) -> bool:
        if field not in {"description", "tags", "note"}:
            return False
        if displayed_note is not None and (
            field != "note" or len(displayed_note) > MAX_NOTE_CHARS
        ):
            return False
        playback_owner = (
            history_archive_owner(self._playback_record)
            if self._playback_record is not None
            else ""
        )
        if owner not in {
            self._library_detail_owner,
            self._folder_inspector_owner,
            playback_owner,
        }:
            return False
        rows = [
            row
            for row in self._projected_library()
            if history_archive_owner(row) == owner
        ]
        if len(rows) != 1:
            return False
        row = rows[0]
        if field == "description":
            value = str(
                row.get("vodforge_user_description", row.get("description")) or ""
            )
        elif field == "tags":
            value = ", ".join(str(tag) for tag in row.get("vodforge_user_tags") or ())
        else:
            value = (
                displayed_note
                if displayed_note is not None
                else str(row.get("vodforge_user_note") or "")
            )
        if not value:
            self._status = f"No {field} to copy."
            self.statusChanged.emit()
            return False
        clipboard = QGuiApplication.clipboard()
        if clipboard is None:
            return False
        clipboard.setText(value)
        self._status = f"Copied {field}."
        self.statusChanged.emit()
        self._record_update_feature(
            "library",
            {
                "description": "source_description_copied",
                "tags": "personal_tags_copied",
                "note": "personal_note_copied",
            }[field],
        )
        return True

    @Slot(str, result=bool)
    def openLibrarySource(self, owner: str) -> bool:
        value = self._detail_fact(owner, "source", "Source URL")
        if value is None or not value.startswith(("https://", "http://")):
            return False
        url = QUrl(value)
        if not url.isValid() or not url.host():
            return False
        return QDesktopServices.openUrl(url)

    @Slot(str, str, result=bool)
    def saveLibraryDescription(self, owner: str, value: str) -> bool:
        annotation_owner = self._detail_annotation_owner(owner)
        if not annotation_owner:
            return False
        if len(value) > MAX_NOTE_CHARS:
            self._status = (
                f"Use up to {MAX_NOTE_CHARS:,} characters for your description."
            )
            self.statusChanged.emit()
            return False
        try:
            self._annotations.replace(
                annotation_owner,
                replace(
                    self._annotations.annotation_for(annotation_owner),
                    description=value,
                ),
            )
        except LibraryAnnotationsError as exc:
            self._status = str(exc)
            self.statusChanged.emit()
            return False
        telemetry = self._analytics.telemetry
        if telemetry is not None:
            try:
                telemetry.record_feature("organization", "description_saved")
            except (OSError, ValueError):
                pass
        self._status = "Library description saved."
        self.statusChanged.emit()
        self.historyChanged.emit()
        return True

    @Slot(str, str, result=bool)
    def saveLibraryNote(self, owner: str, value: str) -> bool:
        annotation_owner = self._detail_annotation_owner(owner)
        if not annotation_owner:
            return False
        if len(value) > MAX_NOTE_CHARS:
            self._status = f"Use up to {MAX_NOTE_CHARS:,} characters for your note."
            self.statusChanged.emit()
            return False
        previous = self._annotations.annotation_for(annotation_owner)
        try:
            self._annotations.replace(
                annotation_owner,
                replace(previous, note=value),
            )
        except LibraryAnnotationsError as exc:
            self._status = str(exc)
            self.statusChanged.emit()
            return False
        if value != previous.note:
            self._record_update_feature("organization", "notes_saved")
        self._status = "Library note saved."
        self.statusChanged.emit()
        self.historyChanged.emit()
        return True

    @Slot(str, str, bool, result=bool)
    def editLibraryTag(self, owner: str, value: str, remove: bool) -> bool:
        annotation_owner = self._detail_annotation_owner(owner)
        if not annotation_owner:
            return False
        tag = value.strip()
        if not tag or len(tag) > MAX_TAG_CHARS:
            self._status = f"Use a tag of up to {MAX_TAG_CHARS} characters."
            self.statusChanged.emit()
            return False
        previous = self._annotations.annotation_for(annotation_owner)
        existing = {item.casefold() for item in previous.tags}
        if not remove and tag.casefold() in existing:
            return True
        if not remove and len(previous.tags) >= MAX_TAGS:
            self._status = "This item already has the maximum number of tags."
            self.statusChanged.emit()
            return False
        tags = (
            tuple(item for item in previous.tags if item.casefold() != tag.casefold())
            if remove
            else (*previous.tags, tag)
        )
        try:
            self._annotations.replace(annotation_owner, replace(previous, tags=tags))
        except LibraryAnnotationsError as exc:
            self._status = str(exc)
            self.statusChanged.emit()
            return False
        telemetry = self._analytics.telemetry
        if telemetry is not None:
            try:
                telemetry.record_feature("organization", "tags_saved")
            except (OSError, ValueError):
                pass
        self._status = "Library tags saved."
        self.statusChanged.emit()
        self.historyChanged.emit()
        return True

    @Slot(QUrl)
    def setLocalAudioUrl(self, url: QUrl) -> None:
        if url.isLocalFile():
            self._local_audio = url.toLocalFile()
            self.localChanged.emit()

    @Slot(QUrl)
    def setLocalImageUrl(self, url: QUrl) -> None:
        if url.isLocalFile():
            self._local_image = url.toLocalFile()
            self.localChanged.emit()

    @Slot(str)
    def setLocalProfile(self, profile: str) -> None:
        profile = local_video_profile_value(profile)
        if profile in LOCAL_VIDEO_PROFILE_OPTIONS:
            self._local_profile = profile
            self.localChanged.emit()

    @Slot(str, bool)
    def setDownloadOption(self, key: str, enabled: bool) -> None:
        if key not in self.downloadOptions:
            return
        if key == "use_nvenc" and enabled and not self._nvenc_available:
            return
        self._download_preferences = replace(
            self._download_preferences, **{key: enabled}
        )
        self.downloadOptionsChanged.emit()
        self._schedule_preferences_save()

    @Slot(str, str)
    def setManualValue(self, key: str, value: str) -> None:
        if key not in self._manual_values or len(value) > 32:
            return
        if self._manual_values[key] == value:
            return
        self._manual_values[key] = value
        self.exportSettingsChanged.emit()
        self._schedule_preferences_save()

    @Slot(str, str)
    def setMp3Value(self, key: str, value: str) -> None:
        allowed = {
            "mp3_quality": MP3_QUALITY_OPTIONS,
            "mp3_sample_rate": MP3_SAMPLE_RATE_OPTIONS,
            "mp3_channels": MP3_CHANNEL_OPTIONS,
            "mp3_cover_art_mode": MP3_COVER_ART_OPTIONS,
        }
        if key not in allowed or value not in cast(tuple[str, ...], allowed[key]):
            return
        if (
            key == "mp3_cover_art_mode"
            and value == "Custom art"
            and self._mp3_custom_cover is None
        ):
            return
        self._mp3_values[key] = value
        self.exportSettingsChanged.emit()
        self._schedule_preferences_save()

    @Slot(bool)
    def setMp3Metadata(self, enabled: bool) -> None:
        self._mp3_values["mp3_embed_metadata"] = enabled
        self.exportSettingsChanged.emit()
        self._schedule_preferences_save()

    @Slot(QUrl, result=bool)
    def setMp3CoverUrl(self, url: QUrl) -> bool:
        if not url.isLocalFile():
            return False
        try:
            cover_path = validate_custom_cover_art(Path(url.toLocalFile()))
        except ValueError as exc:
            self._set_status(str(exc))
            return False
        self._mp3_custom_cover = cover_path
        self._mp3_values["mp3_cover_art_mode"] = "Custom art"
        self.exportSettingsChanged.emit()
        self._schedule_preferences_save()
        return True

    @Slot()
    def clearMp3Cover(self) -> None:
        self._mp3_custom_cover = None
        if self._mp3_values["mp3_cover_art_mode"] == "Custom art":
            self._mp3_values["mp3_cover_art_mode"] = "No Art"
        self.exportSettingsChanged.emit()
        self._schedule_preferences_save()

    def _load_batch_path(self, path: Path) -> bool:
        self._batch_urls = []
        self._batch_name = ""
        self._batch_path = ""
        self._batch_snapshot_admitted = False
        try:
            # Bound composer-driven reads; no asynchronous parser can restore an
            # obsolete selection after an edit or toggle.
            if not path.is_file():
                raise ValueError("Choose an existing URL list file.")
            with path.open("rb") as source:
                payload = source.read(2 * 1024 * 1024 + 1)
            if len(payload) > 2 * 1024 * 1024:
                raise ValueError("Choose a URL list smaller than 2 MB.")
            urls = parse_url_list_text(payload.decode("utf-8-sig"))
            if not urls:
                raise ValueError("That text file contains no http or https URLs.")
        except (OSError, UnicodeError, ValueError) as exc:
            self._status = str(exc)
            self.batchListChanged.emit()
            self.statusChanged.emit()
            return False
        self._batch_urls = urls
        self._batch_path = str(path)
        self._batch_name = path.name
        self._status = f"Loaded {len(urls)} URL(s). They will run one at a time."
        self.batchListChanged.emit()
        self.statusChanged.emit()
        return True

    @Slot(QUrl)
    def loadBatchUrl(self, url: QUrl) -> None:
        if url.isLocalFile() and self._load_batch_path(Path(url.toLocalFile())):
            self.sourcePrepared.emit(self._batch_path)

    @staticmethod
    def _batch_file_available(value: str) -> bool:
        try:
            return Path(value).is_file()
        except OSError:
            return False

    def _clear_missing_batch_list(self) -> None:
        # Only detach the composer. Admitted runs own an immutable URL snapshot.
        self._reset_batch_composer()
        self._set_status(
            "Batch list missing. Choose the list again by clicking Load list."
        )

    def _check_batch_list_file(self) -> bool:
        if self._batch_snapshot_admitted:
            return True
        if self._batch_path and not self._batch_file_available(self._batch_path):
            self._clear_missing_batch_list()
            return False
        return True

    @Slot()
    def clearBatchList(self) -> None:
        self._reset_batch_composer()
        self._set_status("URL list cleared.")

    def _reset_batch_composer(self) -> None:
        """Detach the draft without issuing feedback for an admitted run."""
        self._composer_resume_run_id = ""
        self._batch_urls = []
        self._batch_name = ""
        self._batch_path = ""
        self._batch_snapshot_admitted = False
        self.batchListChanged.emit()
        self.sourcePrepared.emit("")

    @Slot(str)
    def setCookieSource(self, value: str) -> None:
        try:
            self._cookie_source = CookieSource(value)
        except ValueError:
            return
        self.cookieAccessChanged.emit()

    @Slot(str)
    def setCookieBrowser(self, value: str) -> None:
        if value not in COOKIE_BROWSER_OPTIONS[1:] or not browser_cookie_value(value):
            return
        self._cookie_browser = value
        self._cookie_source = CookieSource.BROWSER
        self.cookieAccessChanged.emit()

    @Slot(QUrl)
    def setCookieFileUrl(self, url: QUrl) -> None:
        if not url.isLocalFile():
            return
        path = Path(url.toLocalFile())
        if not path.is_file():
            self._status = "That cookies file does not exist."
            self.statusChanged.emit()
            return
        self._cookie_file = path
        self._cookie_source = CookieSource.FILE
        self.cookieAccessChanged.emit()

    @Slot()
    def startLocalConversion(self) -> None:
        try:
            if self._relink.active:
                raise RuntimeError(
                    "Finish the saved-location review before converting."
                )
            if self._import_pending:
                raise RuntimeError("Finish importing media before converting.")
            if self._file_action_busy:
                raise RuntimeError("Finish the Library file change before converting.")
            if not self._settings_writable:
                raise SettingsError(
                    "Settings need attention before a conversion can start."
                )
            self._local.start(
                Path(self._local_audio),
                Path(self._local_image),
                Path(self._output_path),
                self._local_profile,
            )
        except (
            LocalAudioVideoError,
            OSError,
            RuntimeError,
            SettingsError,
            ValueError,
        ) as exc:
            self._status = (
                download_error_message(exc)
                if isinstance(exc, (LocalAudioVideoError, OSError))
                else str(exc)
            )
            self._local_progress = self._status
            self.statusChanged.emit()
            self.localChanged.emit()
            return
        self._local_running = True
        self._local_progress = "Preparing local video…"
        self.localChanged.emit()

    @Slot()
    def cancelLocalConversion(self) -> None:
        self._local.cancel()
        self._local_progress = "Stopping local conversion…"
        self.localChanged.emit()

    @Slot(str)
    def sourceInputChanged(self, value: str) -> None:
        """A reviewed recovery draft expires as soon as its source is edited."""
        candidate = value.strip()
        paused = next(
            (
                job
                for job in self._runtime.recovered
                if job.run_id == self._composer_resume_run_id
            ),
            None,
        )
        if paused is not None and candidate != (paused.batch_list_path or paused.url):
            self._composer_resume_run_id = ""
            self.batchListChanged.emit()
        if (
            len(candidate) >= 2
            and candidate[0] == candidate[-1]
            and candidate[0] in {"'", '"'}
        ):
            candidate = candidate[1:-1]
        paused_source_unchanged = paused is not None and candidate == (
            paused.batch_list_path or paused.url
        )
        if (
            candidate != self._batch_path or not candidate
        ) and not paused_source_unchanged:
            if self._batch_urls:
                self._batch_urls = []
                self._batch_name = ""
                self._batch_path = ""
                self._batch_snapshot_admitted = False
                self.batchListChanged.emit()
            if candidate and not candidate.lower().startswith(("http://", "https://")):
                try:
                    path = Path(candidate).expanduser()
                    if path.is_absolute():
                        self._load_batch_path(path)
                except (OSError, ValueError, RuntimeError):
                    self._set_status("Choose an existing URL list file.")

        if self._recovery_source_url and value.strip() != self._recovery_source_url:
            self._media_recovery.clear_destination()
            self._recovery_source_url = ""
            self.outputPathChanged.emit()
            self.exportModeChanged.emit()

    @Slot(str)
    def setOutputPath(self, value: str) -> None:
        try:
            path = Path(value).expanduser()
            available = path.is_absolute() and path.is_dir()
        except OSError:
            self._status = (
                "Output folder is unavailable. Check access or choose another folder."
            )
            self.statusChanged.emit()
            self._record("output", "invalid")
            return
        except (ValueError, RuntimeError):
            available = False
        if not available:
            self._status = "Select an existing output folder."
            self.statusChanged.emit()
            self._record("output", "invalid")
            return
        if self._recovery_source_url:
            self._media_recovery.prepare_destination(
                self._recovery_source_url,
                path,
                export_mode=self._media_recovery.export_mode_for(
                    self._recovery_source_url
                ),
            )
            self.outputPathChanged.emit()
            return
        self._output_path = str(path)
        self.outputPathChanged.emit()
        self._schedule_preferences_save()
        self._record("output", "selected")

    @Slot(QUrl)
    def chooseOutputUrl(self, value: QUrl) -> None:
        if value.isLocalFile():
            self.setOutputPath(value.toLocalFile())

    @Slot(str)
    def setExportMode(self, value: str) -> None:
        if value not in {mode.value for mode in ExportMode}:
            return
        if self._recovery_source_url and self._media_recovery.update_export_mode(
            self._recovery_source_url, ExportMode(value)
        ):
            self.exportModeChanged.emit()
            return
        self._export_mode = value
        self.exportModeChanged.emit()
        self._schedule_preferences_save()

    @Slot(str)
    def setOutputFormat(self, value: str) -> None:
        if value not in {item.value for item in OutputType}:
            return
        self._output_format = value
        self.outputFormatChanged.emit()
        self._schedule_preferences_save()

    @Slot(str)
    def setQuality(self, value: str) -> None:
        if value not in QUALITY_OPTIONS:
            return
        self._quality = value
        self.qualityChanged.emit()
        self._schedule_preferences_save()

    def _schedule_preferences_save(self) -> None:
        if self._settings_writable:
            self._save_timer.start(250)

    def _save_preferences(self) -> None:
        updated = {
            **self._settings,
            "output_dir": self._output_path,
            "output_type": self._output_format,
            "quality": self._quality,
            "export_mode": self._export_mode,
            "appearance_theme": self._appearance_theme,
            "custom_accent": self._custom_accent,
            "translated_subtitle_language": self._translated_subtitle_language,
            **self.downloadOptions,
            **self._manual_values,
            **self._mp3_values,
            "mp3_cover_art_mode": "No Art"
            if self._mp3_custom_cover is not None
            else self._mp3_values["mp3_cover_art_mode"],
        }
        try:
            save_settings(self._settings_path, updated)
        except SettingsError:
            self._status = "Settings could not be saved. Check the app data folder."
            self.statusChanged.emit()
            return
        self._settings = updated
        self._record_settings_snapshot()

    def _record_settings_snapshot(self) -> None:
        telemetry = self._analytics.telemetry
        if telemetry is None or not telemetry.permitted():
            return
        values = {
            **self._settings,
            "output_type": self._output_format,
            "export_mode": self._export_mode,
            "quality": self._quality,
            **self.downloadOptions,
            **self._manual_values,
            **self._mp3_values,
        }
        dimensions = settings_dimensions(values)
        dimensions["cookie_access"] = {
            CookieSource.PUBLIC: "disabled",
            CookieSource.BROWSER: "browser",
            CookieSource.FILE: "file",
        }[self._cookie_source]
        try:
            telemetry.record_feature("settings", "snapshot", dimensions=dimensions)
        except (OSError, ValueError):
            pass

    @Slot(int, result=bool)
    def openLibraryItem(
        self, index: int, queue_token: QueueToken | None = None
    ) -> bool:
        if queue_token is None:
            self._watch_queue.cancel()
        if not 0 <= index < len(self._runtime.history):
            return False
        record = self._runtime.history[index]
        path = resolve_library_media_path(record)
        if path is None:
            plan = self._media_recovery.plan(record)
            prompt = library_media_recovery_prompt(plan)
            self._missing_plan = plan
            self._missing_fingerprint = record_fingerprint(record)
            self._missing_media = {
                "owner": history_archive_owner(record),
                "heading": prompt.heading,
                "message": prompt.message,
                "detail": prompt.detail,
                "kind": plan.kind,
                "primaryAction": prompt.primary_action,
                "primaryLabel": prompt.primary_label,
                "requiresFolder": "yes" if plan.requires_destination_choice else "no",
            }
            self.missingMediaChanged.emit()
            self.missingMediaRequested.emit()
            self._status = prompt.heading
            self.statusChanged.emit()
            self._record_update_feature(
                "missing_media", "offered", {"input_kind": "single"}
            )
            return False
        if self._playback_binding is not None:
            self._playback_binding.close()
            self._observe_playback_phase("closed")
        self._playback_path = path
        self._playback_record = dict(self._runtime.history[index])
        self._previews.load(
            path if watch_media_kind(self._runtime.history[index]) == "video" else None
        )
        self.playbackPreviewsChanged.emit()
        self._playback_position = 0.0
        self._playback_duration = 0.0
        self._playback_status = "Ready"
        self._playback_recorded = False
        self._playback_phases = set()
        self._playback_started_at = time.monotonic()
        self._playback_operation = bind_operation(
            self._analytics.telemetry,
            "playback_operation",
            operation_key=str(uuid.uuid4()),
        )
        self._observe_playback_phase("requested")
        self._playback_output_type = str(
            self._runtime.history[index].get("vodforge_output_type") or ""
        )
        self._playback_chapters = sanitize_chapters(
            self._runtime.history[index].get("chapters")
        )
        self._playback_heatmap = sanitize_heatmap(
            self._runtime.history[index].get("heatmap")
        )
        self._playback_binding = PlaybackProgressBinding(
            self._playback_progress,
            self._runtime.history[index],
            snapshot=self._playback_snapshot(),
            seek=self._request_playback_seek,
            observe=lambda action, key=self._playback_operation, **fields: operation(
                self._analytics.telemetry, "playback_operation", action, key, **fields
            ),
        )
        self._playback_url = QUrl.fromLocalFile(str(path))
        self._playback_origin_selection = self._selection
        self._playback_generation += 1
        self._playback_retained_frame = QVideoFrame()
        self._playback_frame_owner = ""
        self._playback_frame_generation = -1
        self._playback_frame_url = ""
        self._subtitles.load(
            path, self._playback_record.get("vodforge_caption_summary")
        )
        if queue_token is not None:
            self._watch_queue.attach(self, self._runtime.history[index], queue_token)
        self.playbackUrlChanged.emit()
        self.playerSceneChanged.emit()
        self.select("Watch")
        self.playbackRequested.emit(self._playback_generation)
        return True

    def _saved_item_for_owner(self, owner: str) -> dict[str, Any] | None:
        matches = [
            row for row in self._runtime.history if history_archive_owner(row) == owner
        ]
        return matches[0] if len(matches) == 1 else None

    @Slot(str)
    def openLibraryOwner(self, owner: str) -> None:
        item = self._saved_item_for_owner(owner)
        if item is None:
            self._status = "That Library item changed. Select it again."
            self.statusChanged.emit()
            return
        self.openLibraryItem(self._runtime.history.index(item))

    @Slot()
    def returnToPlaybackOrigin(self) -> None:
        """Return from the player without resetting the retained browse route."""
        self.select(self._playback_origin_selection)

    @Slot()
    @Slot(bool)
    def closePlayback(self, keep_selection: bool = False) -> None:
        self._watch_queue.cancel()
        had_playback = self._playback_binding is not None
        if self._playback_binding is not None:
            self._playback_binding.close()
            self._playback_binding = None
            self._observe_playback_phase("closed")
            self._playback_operation = None
        self._playback_path = None
        self._playback_record = None
        self._playback_retained_frame = QVideoFrame()
        self._playback_frame_owner = ""
        self._playback_frame_generation = -1
        self._playback_frame_url = ""
        self._subtitles.load(None)
        self._previews.load(None)
        self.playbackPreviewsChanged.emit()
        self._playback_url = QUrl()
        self.playbackUrlChanged.emit()
        self.playerSceneChanged.emit()
        if keep_selection and had_playback:
            # Mini-player close retires progress while retaining the browse route.
            # Rebuild Watch only now so the latest played owner becomes its hero.
            self.watchSceneChanged.emit()
        if not keep_selection:
            self.historyChanged.emit()
            self.returnToPlaybackOrigin()

    @Slot(str)
    def openLibraryFolder(self, owner: str) -> None:
        item = self._saved_item_for_owner(owner)
        path = history_output_path(item) if item is not None else None
        if path is None or not path.parent.is_dir():
            self._status = "The saved media folder is unavailable."
            self.statusChanged.emit()
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.parent)))

    @Slot(str, result=bool)
    def copySavedYoutubeUrl(self, owner: str) -> bool:
        item = self._saved_item_for_owner(owner)
        url = canonical_youtube_url(item) if item is not None else None
        if not url:
            self._status = "This item does not include a YouTube URL to copy."
            self.statusChanged.emit()
            return False
        clipboard = QGuiApplication.clipboard()
        if clipboard is None:
            return False
        clipboard.setText(url)
        self._status = "Copied YouTube URL to clipboard."
        self.statusChanged.emit()
        self._record_update_feature("library", "youtube_url_copied")
        return True

    @Slot(str, result=bool)
    def copyPlayerSourceUrl(self, owner: str) -> bool:
        record = self._playback_record
        if record is None or history_archive_owner(record) != owner:
            return False
        source, _output = library_detail_facts(record)
        value = next(
            (text for label, text, _icon in source if label == "Source URL"), ""
        )
        clipboard = QGuiApplication.clipboard()
        if not value or clipboard is None:
            return False
        clipboard.setText(value)
        self._status = "Copied source URL."
        self.statusChanged.emit()
        if canonical_youtube_url(record):
            self._record_update_feature("library", "youtube_url_copied")
        return True

    @Slot(str)
    def copyLibraryPath(self, owner: str) -> None:
        item = self._saved_item_for_owner(owner)
        path = history_output_path(item) if item is not None else None
        if path is None or not path.is_file():
            self._status = "The saved media file is unavailable."
            self.statusChanged.emit()
            return
        clipboard = QGuiApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(str(path))
            self._status = "Saved media path copied."
            self.statusChanged.emit()
            self._record_update_feature("archive", "location_copied")

    @Slot(str, result=bool)
    def prepareLibraryRemoval(self, owner: str) -> bool:
        """Bind confirmation to one exact saved record, not a changing row index."""
        self._pending_library_removal = None
        if (
            self._relink.active
            or self._file_action_busy
            or self._files.pending
            or self._import_pending
        ):
            self._status = "Review the Library file change first."
            self.statusChanged.emit()
            return False
        item = self._saved_item_for_owner(owner)
        if item is None:
            self._status = "That Library item changed. Select it again."
            self.statusChanged.emit()
            return False
        plan = resolve_library_removal_plan(
            item,
            active_job=self._runtime.active_job,
            pending_jobs=getattr(self._runtime, "queued", []),
        )
        if plan.history_identity is None or plan.execution_run_ids:
            self._status = "This item has an active or queued run. Finish it before removing its Library card."
            self.statusChanged.emit()
            return False
        self._pending_library_removal = owner, record_fingerprint(item)
        return True

    @Slot()
    def cancelLibraryRemoval(self) -> None:
        self._pending_library_removal = None

    @Slot(result=bool)
    def confirmLibraryRemoval(self) -> bool:
        if self._relink.active:
            return False
        pending = self._pending_library_removal
        self._pending_library_removal = None
        if pending is None:
            return False
        if self._file_action_busy or self._files.pending:
            self._status = "Review the Library file change first."
            self.statusChanged.emit()
            return False
        owner, fingerprint = pending
        item = self._saved_item_for_owner(owner)
        if item is None or record_fingerprint(item) != fingerprint:
            self._status = "That Library item changed. Select it again."
            self.statusChanged.emit()
            return False
        plan = resolve_library_removal_plan(
            item,
            active_job=self._runtime.active_job,
            pending_jobs=getattr(self._runtime, "queued", []),
        )
        if plan.history_identity is None or plan.execution_run_ids:
            self._status = "This item has an active or queued run. Finish it before removing its Library card."
            self.statusChanged.emit()
            return False
        matching = [
            row
            for row in self._runtime.history
            if history_identity(row) == plan.history_identity
        ]
        if len(matching) != 1:
            self._status = "That Library item is ambiguous. Select it again."
            self.statusChanged.emit()
            return False
        updated = [row for row in self._runtime.history if row is not item]
        try:
            save_history(self._runtime.history_path, updated)
        except HistoryError:
            self._status = "The Library card could not be removed safely."
            self.statusChanged.emit()
            return False
        self._runtime.history = updated
        try:
            self._annotations.remove(history_annotation_owner(item))
        except LibraryAnnotationsError:
            # The committed history is authoritative; an annotation cleanup
            # failure must not restore a card whose durable removal succeeded.
            pass
        if self._library_category not in self.libraryCategories:
            self._library_category = LIBRARY_ALL_CATEGORIES
            self.libraryCategoryChanged.emit()
        self._status = "Removed the Library card. Media files remain on your computer."
        self.statusChanged.emit()
        self.historyChanged.emit()
        self._record_update_feature("library", "removed")
        return True

    def _playback_snapshot(self) -> PlaybackSnapshot:
        return PlaybackSnapshot(
            path=self._playback_path,
            status=self._playback_status,
            position=self._playback_position,
            duration=self._playback_duration,
            volume=80,
        )

    def _request_playback_seek(self, position: float) -> PlaybackSnapshot:
        self.playbackSeekRequested.emit(position)
        return self._playback_snapshot()

    @Slot(float, float, str)
    @Slot(float, float, str, int)
    @Slot(float, float, str, int, int)
    def observePlayback(
        self,
        position: float,
        duration: float,
        status: str,
        generation: int = -1,
        native_error: int = 0,
    ) -> None:
        if generation >= 0 and generation != self._playback_generation:
            return
        if self._playback_binding is None or status not in {
            "Ready",
            "Playing",
            "Paused",
            "Ended",
            "Failed",
        }:
            return
        self._playback_position = position
        self._playback_duration = duration
        self._playback_status = cast(PlaybackStatus, status)
        if (
            duration > 0
            and status != "Failed"
            and "failed" not in self._playback_phases
        ):
            self._observe_playback_phase("ready")
        if status == "Playing":
            self._observe_playback_phase("started")
        elif status == "Failed":
            self._observe_playback_phase(
                "failed",
                failure_detail=FailureDiagnostic(
                    stage="playback",
                    reason={
                        1: "unknown",
                        2: "unsupported_format",
                        3: "network",
                        4: "permission_denied",
                    }.get(native_error, "unknown"),
                ),
                native_error=native_error,
            )
        elif status == "Ended" and "failed" not in self._playback_phases:
            self._observe_playback_phase("completed")
        if status == "Playing" and not self._playback_recorded:
            self._playback_recorded = True
            telemetry = self._analytics.telemetry
            if telemetry is not None:
                try:
                    telemetry.record(
                        "playback_started",
                        output_type=product_output_kind(self._playback_output_type),
                    )
                except (OSError, ValueError):
                    pass
        record = self._playback_record
        previous = self._playback_progress.for_record(record) if record else None
        self._playback_binding.present(self._playback_snapshot())
        if record and watch_progress(previous) != watch_progress(
            self._playback_progress.for_record(record)
        ):
            # Refresh only this retained hero's progress. Rebuilding Watch's
            # catalog can replace its hero and rail delegates during playback.
            self.watchProgressChanged.emit(history_archive_owner(record))
        if self._previews.request(duration):
            self.playbackPreviewsChanged.emit()
        self._watch_queue.present(self, status)

    def _observe_playback_phase(
        self,
        action: str,
        *,
        failure_detail: FailureDiagnostic | None = None,
        native_error: int = 0,
    ) -> None:
        if action in self._playback_phases:
            return
        self._playback_phases.add(action)
        if action in {"completed", "failed"}:
            # Preserve legacy engagement alongside correlated operation outcomes.
            self._record_player_feature(action)
        operation(
            self._analytics.telemetry,
            "playback_operation",
            action,
            self._playback_operation,
            {
                "playback_origin": "library"
                if self._playback_origin_selection == "Library"
                else "watch"
                if self._playback_origin_selection == "Watch"
                else "unknown",
                "player_surface": "embedded",
                "qt_media_error": {
                    0: "none",
                    1: "resource",
                    2: "format",
                    3: "network",
                    4: "access_denied",
                }.get(native_error, "unknown"),
                "processing_bucket": time_bucket(
                    max(0, time.monotonic() - self._playback_started_at)
                ),
            },
            failure_detail=failure_detail,
        )

    @Slot(float)
    def manualPlaybackSeek(self, position: float) -> None:
        if self._playback_binding is None:
            return
        self._playback_position = position
        self._playback_binding.manual_seek(self._playback_snapshot())
        self.playbackSeekRequested.emit(position)
        self._record_player_feature("seek")

    @Slot(float)
    def hoverPlaybackPreview(self, position: float) -> None:
        if self._previews.hover(position):
            self.playbackPreviewsChanged.emit()

    @Slot(int, result=bool)
    def seekPlaybackChapter(self, index: int) -> bool:
        if self._playback_binding is None or not 0 <= index < len(
            self._playback_chapters
        ):
            return False
        position = float(self._playback_chapters[index]["start_time"])
        self._playback_position = position
        self._playback_binding.manual_seek(self._playback_snapshot())
        self.playbackSeekRequested.emit(position)
        self._record_player_feature("chapter")
        return True

    def _record_player_feature(self, action: str) -> None:
        telemetry = self._analytics.telemetry
        if telemetry is not None:
            try:
                telemetry.record_feature("player", action)
            except (OSError, ValueError):
                pass

    @Slot(QObject, float, result=_QVARIANT_MAP)
    def initialPlayerGeometry(self, window: QObject, aspect: float) -> dict[str, Any]:
        from PySide6.QtGui import QWindow

        from yt_downloader.qt_quick.player_geometry import (
            clamp_player_origin,
            initial_player_client_size,
        )

        if (
            self._window is None
            or self._window.findChild(QObject, "watchPresentationWindow") is not window
        ):
            return {}
        if not isinstance(window, QWindow) or window.screen() is None:
            return {}
        available = window.screen().availableGeometry()
        margins = window.frameMargins()
        try:
            width, height, overflow = initial_player_client_size(
                window.width(),
                aspect,
                (available.width(), available.height()),
                (margins.left() + margins.right(), margins.top() + margins.bottom()),
                (window.minimumWidth(), window.minimumHeight()),
            )
        except ValueError:
            return {}
        x, y = clamp_player_origin(
            (window.x(), window.y()),
            (available.x(), available.y(), available.width(), available.height()),
            (margins.left(), margins.top(), margins.right(), margins.bottom()),
            (width, height),
        )
        return {"width": width, "height": height, "x": x, "y": y, "overflow": overflow}

    def _owned_playback_sink(self, surface: QObject, owner: str) -> QVideoSink | None:
        window = self._window
        if (
            self._closed
            or window is None
            or self._playback_record is None
            or history_archive_owner(self._playback_record) != owner
        ):
            return None
        if surface.objectName() not in {
            "watchVideoSurface",
            "watchPresentationVideoSurface",
            "miniVideoSurface",
        }:
            return None
        if window.findChild(QObject, surface.objectName()) is not surface:
            return None
        sink = surface.property("videoSink")
        player = window.findChild(QMediaPlayer, "watchMediaPlayer")
        if (
            not isinstance(sink, QVideoSink)
            or player is None
            or player.videoSink() is not sink
            or player.source() != self._playback_url
        ):
            return None
        return sink

    @Slot(QObject, str)
    def retainPlaybackFrame(self, surface: QObject, owner: str) -> None:
        sink = self._owned_playback_sink(surface, owner)
        if sink is None:
            return
        frame = sink.videoFrame()
        if frame.isValid():
            self._playback_retained_frame = QVideoFrame(frame)
            self._playback_frame_owner = owner
            self._playback_frame_generation = self._playback_generation
            self._playback_frame_url = self._playback_url.toString()

    @Slot(QObject, str)
    def restorePlaybackFrame(self, surface: QObject, owner: str) -> None:
        sink = self._owned_playback_sink(surface, owner)
        if (
            sink is None
            or self._playback_frame_owner != owner
            or self._playback_frame_generation != self._playback_generation
            or self._playback_frame_url != self._playback_url.toString()
            or not self._playback_retained_frame.isValid()
            or sink.videoFrame().isValid()
        ):
            return
        # Re-present one retained decoded frame, without advancing/restarting audio.
        sink.setVideoFrame(self._playback_retained_frame)

    @Slot(str)
    def recordPresentation(self, action: str) -> None:
        if (
            action
            in {
                "fit",
                "fill",
                "fullscreen",
                "floating",
                "returned",
                "captions_selected",
                "caption_fit_applied",
                "caption_fill_restored",
                "caption_fill_unavailable",
            }
            and self._playback_record is not None
            and watch_media_kind(self._playback_record) == "video"
        ):
            self._record_player_feature(action)

    @Slot()
    def beginShutdown(self) -> None:
        self._runtime.begin_shutdown()
        if self.running:
            self._status = "Pausing downloads…"
            self.statusChanged.emit()
        if self.localRunning:
            self.cancelLocalConversion()

    @Slot()
    def cancel(self) -> None:
        if self.running:
            self._runtime.cancel()
            self._status = "Stopping download…"
            self.statusChanged.emit()

    @Slot(str, str, result=bool)
    def admitRunMenu(self, run_id: str, execution_token: str) -> bool:
        active = self._runtime.active_job
        admitted = (
            active is not None
            and active is self._run_menu_identity_job
            and getattr(active, "run_id", None) == run_id
            and bool(execution_token)
            and execution_token == self._run_menu_identity_token
        )
        self._run_menu_admitted_job = active if admitted else None
        return admitted

    @Slot()
    def retireRunMenu(self) -> None:
        self._run_menu_admitted_job = None

    @Slot(str, str, result=bool)
    def controlRun(self, run_id: str, action: str) -> bool:
        if action not in {"cancel", "skip_item", "skip_source"}:
            return False
        active = self._runtime.active_job
        admitted = (
            active is not None
            and active is self._run_menu_admitted_job
            and getattr(active, "run_id", None) == run_id
        )
        operation(
            self._analytics.telemetry,
            "run_control_operation",
            "admitted" if admitted else "rejected",
            str(uuid.uuid4()),
            {
                "run_control_action": action,
                "run_control_origin": "run_menu",
                "run_control_owner": "current" if admitted else "retired",
            },
        )
        self._run_menu_admitted_job = None
        if not admitted:
            self._status = "That run changed. Open its actions again."
            self.statusChanged.emit()
            return False
        {
            "cancel": self.cancel,
            "skip_item": self.skipItem,
            "skip_source": self.skipSource,
        }[action]()
        return True

    @Slot()
    def skipItem(self) -> None:
        if self.running:
            self._runtime.skip_item()
            self._status = "Skipping this item after the current step stops…"
            self.statusChanged.emit()

    @Slot()
    def skipSource(self) -> None:
        if self.running:
            self._runtime.skip_source()
            self._status = "Skipping this source after the current step stops…"
            self.statusChanged.emit()

    @Slot(str, result=bool)
    def removeQueued(self, run_id: str) -> bool:
        try:
            removed = self._runtime.remove_queued(run_id)
        except RunStateError:
            self.operationFeedback.emit("The queued run could not be removed safely.")
            return False
        if removed:
            self.operationFeedback.emit("Queued run removed.")
            self.activityChanged.emit()
            self.historyChanged.emit()
        return removed

    @Slot(str, result=bool)
    def retryTerminal(self, run_id: str) -> bool:
        return self._admit_retry(run_id)

    @Slot()
    def cancelRunRemovalReview(self) -> None:
        if not self._files.busy and self._files.phase not in {"checking", "working"}:
            self._remove_run_request = None

    @Slot(str, result=bool)
    def openRunFolder(self, run_id: str) -> bool:
        # A configured output directory alone is not evidence of associated files.
        if self._issue_job(run_id) is None:
            return False
        for row in self._runtime.history:
            if row.get("vodforge_run_id") == run_id:
                path = history_output_path(row)
                try:
                    if path is not None and path.is_file():
                        return QDesktopServices.openUrl(
                            QUrl.fromLocalFile(str(path.parent))
                        )
                except OSError:
                    pass
        return False

    @Slot(str, result=bool)
    def runHasSavedFile(self, run_id: str) -> bool:
        for row in self._runtime.history:
            if row.get("vodforge_run_id") == run_id:
                path = history_output_path(row)
                try:
                    if path is not None and path.is_file():
                        return True
                except OSError:
                    pass
        return False

    @Slot(str, result=bool)
    def openRunIssues(self, run_id: str) -> bool:
        if self._issue_job(run_id) is None:
            return False
        self.select("Library")
        self.navigateLibraryFolders("issues")
        for component in self._folder_browser.components:
            if any(
                str(
                    self._folder_browser.records[index].get("vodforge_terminal_run_id")
                    or self._folder_browser.records[index].get("vodforge_active_run_id")
                    or self._folder_browser.records[index].get("vodforge_queued_run_id")
                    or ""
                )
                == run_id
                for index in component.indices
            ):
                return self.selectLibraryFolderComponent(component.key)
        return False

    @Slot(str, result=bool)
    def openRunRetrySettings(self, run_id: str) -> bool:
        if not self.openRunIssues(run_id):
            return False
        self.issueRetrySettingsRequested.emit()
        return True

    @Slot(str, result=bool)
    def requestRunRemoval(self, run_id: str) -> bool:
        job = self._issue_job(run_id)
        if (
            job is None
            or job not in self._runtime.recovered
            or job.terminal_status
            not in {"Failed", "Stopped", "Skipped", "Paused", "Partial"}
            or self._update_work_pending()
            or self._files.phase in {"checking", "working"}
        ):
            self.operationFeedback.emit(
                "Finish active work or recovery before removing this run."
            )
            return False
        owners = tuple(
            history_archive_owner(row)
            for row in self._runtime.history
            if row.get("vodforge_run_id") == run_id
        )
        if owners:
            if not self.startFileActions("delete", list(owners), QUrl()):
                return False
        else:
            self._files.plan = None
            self._files.action = "remove_run"
            self._files.phase = "preview"
            self._files.status = (
                "Remove this run? No owned Library files are recorded. "
                "Unindexed partial files cannot be verified and will be kept. "
                "The output folder and unrelated files will not be removed.\n\n"
                + str(job.output_dir)
            )
        self._remove_run_request = (job, owners)
        self.fileActionChanged.emit()
        self.fileActionRequested.emit()
        return True

    @Slot(str, result=bool)
    def dismissTerminal(self, run_id: str) -> bool:
        # Compatibility entry point: every UI path now requires confirmation.
        return self.requestRunRemoval(run_id)

    def _finish_run_removal(self) -> None:
        request = self._remove_run_request
        if request is None:
            return
        self._remove_run_request = None
        job, owners = request
        remaining = {history_archive_owner(row) for row in self._runtime.history}
        if self._files.phase != "done" or any(owner in remaining for owner in owners):
            self._files.status += " Run kept because cleanup was incomplete."
            return
        try:
            removed = self._issue_job(
                job.run_id
            ) is job and self._runtime.dismiss_terminal(job.run_id)
        except RunStateError:
            removed = False
        self._files.status = (
            "Run removed. Verified files moved to Trash; already-missing entries cleared."
            if removed and owners
            else "Run removed. No owned files were recorded; unverified files were kept."
            if removed
            else "File cleanup finished, but the run could not be removed. Retry Remove."
        )
        self.historyChanged.emit()
        self.activityChanged.emit()
        self.runDeckChanged.emit()

    def _admit_retry(
        self,
        run_id: str,
        *,
        current_job: Any = None,
        stay_in_issues: bool = False,
    ) -> bool:
        try:
            if self._relink.active:
                raise RuntimeError("Finish the saved-location review before retrying.")
            if self._import_pending:
                raise RuntimeError("Finish importing media before retrying.")
            if self._file_action_busy:
                raise RuntimeError("Finish the Library file change before retrying.")
            if current_job is None:
                status, url = self._runtime.terminal_retry_source(run_id)
            if current_job is None and status == "Failed":
                if not self._settings_writable:
                    raise SettingsError(
                        "Settings need attention before a retry can start."
                    )
                selected_type = OutputType(self._output_format)
                manual, mp3 = self._current_export_inputs(selected_type)
                current_job = self._runtime.prepare_job(
                    url,
                    Path(self._output_path),
                    selected_type.value,
                    self._export_mode,
                    self._quality,
                    self._download_preferences,
                    manual,
                    mp3,
                    urls=[url],
                    batch_mode=False,
                    cookie_source=self._cookie_source,
                    cookie_file=self._cookie_file,
                    cookie_browser=self._cookie_browser,
                    tags=self._current_extra_tags(),
                    translated_subtitle_language=self._translated_subtitle_language,
                    nvenc_applicable=self.nvencAvailable,
                )
            retry = self._runtime.retry_terminal(run_id, current_job=current_job)
        except (OSError, RuntimeError, ValueError) as exc:
            self._status = str(exc)
            self.statusChanged.emit()
            return False
        if self._composer_resume_run_id == run_id:
            self._reset_batch_composer()
            self.sourceAccepted.emit()
        if retry is self._runtime.active_job:
            self._status_text = "Retry started."
            self.statusChanged.emit()
        else:
            self.operationFeedback.emit("Added retry to the queue.")
        if stay_in_issues or self._issue_run_id == run_id:
            self._issue_run_id = retry.run_id
            self._folder_inspector_key = f"run:{retry.run_id}"
        self.activityChanged.emit()
        self.historyChanged.emit()
        self.runningChanged.emit()
        if stay_in_issues:
            self.historyChanged.emit()
            self._record_update_feature("guidance", "recovery_selected")
        else:
            self.select("Forge")
        return True

    def _pump(self) -> None:
        now = time.monotonic()
        if self._batch_path and now - self._batch_path_checked_at >= 2:
            self._batch_path_checked_at = now
            self._check_batch_list_file()
        if self._closed:
            return
        availability = self._availability_work.poll()
        if availability is not None and availability.kind == "folder_list":
            current_path = self._folder_browser.path
            if (
                self._folder_browser.mode == "folders"
                and current_path is not None
                and self._folder_listing_pending == str(current_path)
            ):
                self._folder_listing_pending = ""
                self._folder_listing_error = bool(availability.error)
                value = availability.value
                if isinstance(value, dict) and value.get("path") == str(current_path):
                    entries = []
                    for name, kind, size in value.get(
                        "entries", ()
                    ):  # bounded worker result
                        try:
                            path = current_path.join((name,))
                        except ValueError:
                            continue
                        entries.append(
                            ArchiveComponent(
                                str(path),
                                "folder" if kind == "folder" else "file",
                                name,
                                "Folder"
                                if kind == "folder"
                                else self._folder_file_detail(name, size),
                                (),
                                path,
                            )
                        )
                    self._folder_browser.set_folder_entries(current_path, entries)
                elif availability.error:
                    self._folder_browser.set_folder_entries(current_path, ())
                self.historyChanged.emit()
        elif availability is not None and availability.kind.startswith("availability_"):
            current = {
                history_archive_owner(row): record_fingerprint(row)
                for row in self._runtime.history
            }
            if self._folder_browser.mode == "issues" and availability.error:
                self._availability_checked = True
                self._availability_error = True
                self._pending_folder_missing_owner = ""
                self.historyChanged.emit()
            elif self._folder_browser.mode == "issues" and isinstance(
                availability.value, dict
            ):
                if availability.kind == "availability_full":
                    self._missing_files.clear()
                    self._availability_checked = True
                for owner, observation in availability.value.items():
                    if not isinstance(observation, tuple) or len(observation) != 2:
                        continue
                    fingerprint, state = observation
                    if current.get(owner) != fingerprint:
                        continue
                    if state == HISTORY_MEDIA_MISSING:
                        self._missing_files[owner] = fingerprint
                        if owner == self._missing_issue_owner:
                            retry = self._issue_job(self._missing_retry_run_id)
                            if retry is not None and retry.terminal_status in {
                                "Completed",
                                "Partial",
                            }:
                                self._missing_retry_run_id = ""
                    else:
                        self._missing_files.pop(owner, None)
                        if owner == self._missing_issue_owner:
                            self._missing_issue_owner = ""
                            self._folder_inspector_key = ""
                if (
                    availability.kind == "availability_full"
                    and self._pending_folder_missing_owner
                ):
                    owner = self._pending_folder_missing_owner
                    self._pending_folder_missing_owner = ""
                    if owner in self._missing_files:
                        self._reconcile_folder_browser()
                        for position, component in enumerate(
                            self._folder_browser.components
                        ):
                            if component.key == owner:
                                self._folder_browser.page = position // PAGE_SIZE
                                break
                        self.selectLibraryFolderComponent(owner)
                self.historyChanged.emit()
        self._start_availability_scan()
        cloud_result = self._cloud_work.poll()
        if cloud_result is not None and cloud_result.value is True:
            try:
                mark_cloud_seen_confirmed(
                    self._installation_path, self._cloud_seen_install_id
                )
            except (InstallationIdentityError, OSError, ValueError):
                pass
        if self._metadata.poll():
            metadata_record = self._metadata_preview_record
            pending_run_id = self._metadata_pending_run_id
            is_current_preview = metadata_record.get("runId") == pending_run_id
            self._metadata_pending_run_id = ""
            info = self._metadata.info
            if info is not None:
                items = [dict(item) for item in iter_video_infos(info)]
                if items:
                    self._library_projection.record_preview(pending_run_id, items)
                    if is_current_preview:
                        projected = self._projected_library()
                        self._metadata_preview_info = next(
                            (
                                item
                                for item in projected
                                if item.get("vodforge_preview_run_id") == pending_run_id
                            ),
                            None,
                        )
                if is_current_preview:
                    metadata_record["phase"] = (
                        "complete" if self._metadata_preview_info else "failed"
                    )
                    metadata_record["status"] = (
                        "Preview complete — no media downloaded"
                        if self._metadata_preview_info
                        else "No usable media in this preview"
                    )
            elif is_current_preview:
                metadata_record["phase"] = "failed"
                metadata_record["status"] = self._metadata.message
            if is_current_preview:
                self._set_status(str(metadata_record["status"]))
                self.forgePreviewChanged.emit()
            self.runDeckChanged.emit()
            self.historyChanged.emit()
        if self._relink.poll():
            phase = self._relink.phase
            preview = self._relink.preview
            if phase == "preview" and preview is not None:
                operation(
                    self._analytics.telemetry,
                    "archive_relink_operation",
                    "verified",
                    self._relink_operation,
                    relink_dimensions(preview),
                )
            elif phase in {"error", "stale", "timed_out", "cancelled"}:
                operation(
                    self._analytics.telemetry,
                    "archive_relink_operation",
                    "timed_out"
                    if phase == "timed_out"
                    else "cancelled"
                    if phase == "cancelled"
                    else "failed",
                    self._relink_operation,
                    {
                        "archive_result": "changed"
                        if phase == "stale"
                        else "unavailable"
                    },
                )
                self._relink_operation = None
            elif phase == "done" and preview is not None:
                operation(
                    self._analytics.telemetry,
                    "archive_relink_operation",
                    "committed",
                    self._relink_operation,
                    {
                        "committed_count": str(len(self._relink.ready_indices)),
                        **relink_dimensions(preview),
                    },
                )
                self._relink_operation = None
            actual = self._relink.updated_history
            if actual is not None:
                self._relink.updated_history = None
                previous_owner = self._relink.owner
                self._runtime.history = actual
                if 0 <= self._relink.index < len(actual):
                    next_owner = history_archive_owner(actual[self._relink.index])
                    if self._library_detail_owner == previous_owner:
                        self._library_detail_owner = next_owner
                    if previous_owner:
                        self._missing_files.pop(previous_owner, None)
                        if self._missing_issue_owner == previous_owner:
                            self._missing_issue_owner = ""
                            self._folder_inspector_key = ""
                        self._queue_availability_scan(
                            [dict(actual[self._relink.index])], full=False
                        )
                self.historyChanged.emit()
            self.relinkChanged.emit()
        if self._previews.poll():
            self.playbackPreviewsChanged.emit()
        if self._support.poll():
            self.supportChanged.emit()
        storage_snapshot = self._storage.poll()
        if storage_snapshot != self._storage_snapshot:
            self._storage_snapshot = storage_snapshot
            self.storageChanged.emit()
        import_result = self._import_work.poll()
        if import_result is not None:
            self._import_pending = False
            self.importBusyChanged.emit()
            completed, _failed = (
                import_result.value
                if not import_result.error and import_result.value is not None
                else ([], self._import_request_count)
            )
            saved = 0
            if (
                completed
                and not self._files.uncertain
                and not self._runtime.recovery_notice
            ):
                try:
                    prospective = commit_imports(
                        self._runtime.history,
                        completed,
                        self._runtime.history_path,
                    )
                except (HistoryError, OSError, ValueError):
                    pass
                else:
                    self._runtime.history = prospective
                    saved = len(completed)
                    self._library_scene_route = "home"
                    self.historyChanged.emit()
                    self.select("Library")
            self._status = (
                f"Added {saved} media {'file' if saved == 1 else 'files'} to Library."
                if saved == self._import_request_count
                else f"Added {saved} files. {self._import_request_count - saved} could not be added."
            )
            operation(
                self._analytics.telemetry,
                "library_import_operation",
                "completed" if saved == self._import_request_count else "failed",
                self._import_operation,
                {
                    "item_count": str(self._import_request_count),
                    "committed_count": str(saved),
                    "failed_count": str(self._import_request_count - saved),
                    "processing_bucket": time_bucket(
                        time.monotonic() - self._import_started_at
                    ),
                },
            )
            self._import_operation = None
            self.statusChanged.emit()
        if self._artwork.poll():
            self._artwork_revision += 1
            self.artworkChanged.emit()
            if self._selection == "Library" and self._library_scene_route in {
                "detail",
                "folders",
            }:
                self.historyChanged.emit()
            elif self._selection == "Watch" and not self._playback_url.isEmpty():
                self.playerSceneChanged.emit()
            elif self._selection == "Forge":
                self.runDeckChanged.emit()
        if self._files.poll():
            self._file_action_busy = self._files.uncertain
            actual = self._files.latest_history
            self._files.latest_history = None
            if actual is not None:
                previous = self._runtime.history
                self._runtime.history = actual
                current_owners = {history_archive_owner(row) for row in actual}
                for row in previous:
                    if history_archive_owner(row) not in current_owners:
                        try:
                            self._annotations.remove(history_annotation_owner(row))
                        except LibraryAnnotationsError:
                            pass
                if not self._files.pending and self._runtime.recovery_notice == (
                    "Library file recovery must finish before new downloads."
                ):
                    self._runtime.recovery_notice = None
                if self._library_category not in self.libraryCategories:
                    self._library_category = LIBRARY_ALL_CATEGORIES
                    self.libraryCategoryChanged.emit()
                self.historyChanged.emit()
                self.activityChanged.emit()
            if self._remove_run_request and self._files.phase in {
                "done",
                "error",
                "recovery",
            }:
                self._finish_run_removal()
            self.fileActionChanged.emit()
        if self._updates.poll():
            self.updateChanged.emit()
        for action, dimensions in self._updates.take_observations():
            self._record_update_feature("updater", action, dimensions)
        if not self._analytics.settled:
            if self._analytics.poll():
                self.analyticsPromptRequested.emit()
            if self._analytics.allowed != self._analytics_allowed:
                self._analytics_allowed = self._analytics.allowed
                self.analyticsChanged.emit()
                if self._analytics_allowed:
                    self._record_settings_snapshot()
                    self._analytics_snapshot_sent = True
        if (
            self._analytics.settled
            and self._analytics_allowed
            and not self._analytics_snapshot_sent
        ):
            self._record_settings_snapshot()
            self._analytics_snapshot_sent = True
        if self._analytics.settled and self._analytics.allowed:
            self._analytics.start_first_launch_delivery()
        self._analytics.poll_first_launch_delivery()
        poll_failure_notice = "Download state needs attention. Close and reopen VODForge before starting more work."
        active_job_before = self._runtime.active_job
        events = []
        if self._download_poll_failed and self._download_poll_can_resume():
            self._download_poll_failed = False
            if self._runtime.recovery_notice == poll_failure_notice:
                self._runtime.recovery_notice = None
        if not self._download_poll_failed:
            try:
                active_job_before = self._runtime.active_job
                if (
                    active_job_before is not None
                    and active_job_before.run_id != self._forge_run_id
                ):
                    self._forge_run_id = active_job_before.run_id
                    self._forge_technical = "\n".join(active_job_before.activity_lines)[
                        -50_000:
                    ]
                    self.activityChanged.emit()
                events = self._runtime.poll()
            except (HistoryError, OSError, RunStateError, ValueError):
                self._status = "Download state needs attention. See Technical details."
                self.statusChanged.emit()
                self._download_poll_failed = True
                if not self._runtime.recovery_notice:
                    self._runtime.recovery_notice = poll_failure_notice
        for kind, payload in self._run_control_events.take_context_events():
            self._run_controls.observe(active_job_before, kind, payload)
        for kind, payload in events:
            if (
                kind == "error"
                and getattr(payload, "action", "") == "choose_output_folder"
            ):
                self.outputFolderRecoveryRequested.emit(str(payload))
            if kind in {"progress", "progress_determinate"} and payload is not None:
                self._progress = max(0.0, min(100.0, float(payload)))
                self.progressChanged.emit()
            elif kind == "status":
                self._status_text = str(payload)
                self._forge_activity.observe(self._forge_run_id, self._status)
                self.statusChanged.emit()
                active = self._runtime.active_job
                if active is not None and active.run_id in {
                    self._issue_run_id,
                    self._missing_retry_run_id,
                }:
                    next_phase = self._recovery_progress_label()
                    if next_phase != self._issue_live_phase:
                        self._issue_live_phase = next_phase
                        self.historyChanged.emit()
                library_phase = library_phase_from_status(self._status)
                if (
                    active is not None
                    and library_phase is not None
                    and self._library_projection.observe_phase(
                        active.run_id, library_phase
                    )
                ):
                    self.historyChanged.emit()
            elif kind == "log":
                self._append_activity_line(str(payload))
                self._forge_technical = (
                    self._forge_technical
                    + ("\n" if self._forge_technical else "")
                    + str(payload)
                )[-50_000:]
            elif kind in {
                "history_record",
                "job_metadata",
                "item_terminal",
                "batch_item",
            }:
                self.historyChanged.emit()
            elif kind in {"done", "partial", "stopped", "error"}:
                if (
                    kind in {"done", "partial"}
                    and active_job_before is not None
                    and active_job_before.run_id == self._missing_retry_run_id
                ):
                    old_owner = self._missing_issue_owner
                    old_row = self._saved_item_for_owner(old_owner)
                    if old_row is None:
                        self._missing_files.pop(old_owner, None)
                        self._missing_issue_owner = ""
                        self._folder_inspector_key = ""
                    else:
                        self._queue_availability_scan([dict(old_row)], full=False)
                if kind in {"done", "partial"}:
                    self._selected_run_key = ""
                    self._recent_interrupted_run_id = ""
                    if (
                        active_job_before is not None
                        and self._issue_run_id == active_job_before.run_id
                        and self._folder_browser.mode == "issues"
                    ):
                        self._reconcile_folder_browser()
                        if self._folder_inspector_key not in {
                            item.key for item in self._folder_browser.components
                        }:
                            self._issue_run_id = ""
                            self._issue_settings = {}
                            self._folder_inspector_key = ""
                if kind in {"partial", "error"} and active_job_before is not None:
                    try:
                        self._latest_failure = failure_context(
                            active_job_before, str(payload)
                        )
                    except (OSError, ValueError):
                        self._latest_failure = None
                if kind in {"stopped", "error"} and active_job_before is not None:
                    self._recent_interrupted_run_id = active_job_before.run_id
                if kind == "done" and active_job_before is not None:
                    try:
                        self._engagement.completed_download(active_job_before.run_id)
                    except (OSError, ValueError):
                        pass
                self._status_text = str(payload)
                self._forge_activity.observe(
                    self._forge_run_id,
                    {
                        "done": "Completed",
                        "partial": "Partial",
                        "stopped": "Stopped",
                        "error": "Failed",
                    }[kind],
                    str(payload) if kind in {"partial", "error"} else "",
                )
                self.statusChanged.emit()
                self.runningChanged.emit()
                self.historyChanged.emit()
        if events:
            self.activityChanged.emit()
            self.runningChanged.emit()
            self.runDeckChanged.emit()
        for kind, payload in self._local.poll():
            if kind == "progress" and isinstance(payload, LocalAudioVideoProgress):
                self._local_progress = payload.label
            elif kind == "done" and isinstance(payload, LocalAudioVideoResult):
                try:
                    self._runtime.record_local_conversion(payload)
                except (HistoryError, OSError, ValueError):
                    self._local.observe_history_failed(payload)
                    self._status = "Video saved, but Library history needs attention."
                else:
                    self._local.observe_committed(payload)
                    self._status = f"Created {payload.output_path.name}"
                    self.historyChanged.emit()
                    self.select("Library")
                self._local_running = False
                self.statusChanged.emit()
            elif kind == "error":
                self._status = str(payload)
                self._local_progress = self._status
                self._local_running = False
                self.statusChanged.emit()
            self.localChanged.emit()
        if self._updates.pending_install and self._updates.ready is not None:
            if self._update_work_pending():
                status = (
                    "Update verified, but download state needs attention. Close and reopen VODForge, then check for updates again."
                    if self._download_poll_failed or self._runtime.recovery_notice
                    else "Update downloaded. Finish active and queued work; VODForge will restart when it is idle."
                )
                if self._updates.status != status:
                    self._updates.status = status
                    self.updateChanged.emit()
            elif not self._updates.busy:
                self.installUpdate()

    def close(self) -> None:
        if self._input_application is not None:
            self._input_application.removeEventFilter(self)
        self._pointer_press = None
        if self._closed:
            return
        self._closed = True
        if self._nvenc_probe is not None:
            probe = self._nvenc_probe
            self._nvenc_probe = None
            probe.kill()
            probe.deleteLater()
        if self._presentation_probe is not None:
            self._presentation_probe.close()
            self._presentation_probe = None
        self._timer.stop()
        if self._save_timer.isActive():
            self._save_timer.stop()
            self._save_preferences()
        self._watch_queue.cancel()
        self._subtitles.load(None)
        self._playback_retained_frame = QVideoFrame()
        self._playback_frame_owner = ""
        self._playback_frame_generation = -1
        self._playback_frame_url = ""
        self._previews.close()
        self._metadata.close()
        if self._import_pending:
            operation(
                self._analytics.telemetry,
                "library_import_operation",
                "cancelled",
                self._import_operation,
            )
        self._import_work.close()
        self._availability_work.close()
        self._cloud_work.close()
        self._relink.close()
        self._storage.close()
        self._artwork.close()
        self._files.close()
        if self._playback_binding is not None:
            self._playback_binding.close()
            self._playback_binding = None
            self._observe_playback_phase("closed")
            self._playback_operation = None
        self._local.close()
        self._runtime.close()
        self._analytics.close()
        if self._analytics.telemetry is not None:
            self._analytics.telemetry.shutdown(timeout_seconds=1.0)
        close_activity_log(self._activity_log_path)

    def _current_export_inputs(
        self, selected_type: OutputType
    ) -> tuple[ManualExportSettings | None, Mp3ExportSettings | None]:
        manual = (
            manual_export_settings(self._manual_values)
            if selected_type == OutputType.MP4
            and self.exportMode == ExportMode.MANUAL_OVERRIDE.value
            else None
        )
        mp3 = (
            mp3_export_settings(
                self._mp3_values,
                custom_cover_path=self._mp3_custom_cover,
                validate_cover=validate_custom_cover_art,
            )
            if selected_type == OutputType.MP3
            else None
        )
        return manual, mp3

    @Slot(str, str, result=bool)
    def previewMetadata(self, value: str, output_format: str) -> bool:
        try:
            selected_type = OutputType(output_format)
        except ValueError:
            self._set_status("Choose an output format first.")
            return False
        self._metadata.product_telemetry = self._analytics.telemetry
        if not self._metadata.begin(
            value,
            selected_type,
            ignore_playlists=self._download_preferences.single_video_only,
            cookie_source=self._cookie_source,
            cookie_file=self._cookie_file,
            cookie_browser=self._cookie_browser,
            ffmpeg=DownloaderApp._find_ffmpeg(),
            deno=DownloaderApp._find_deno(),
        ):
            self._set_status(self._metadata.message)
            return False
        run_id = f"preview:{uuid.uuid4().hex}"
        self._metadata_pending_run_id = run_id
        self._metadata_preview_info = None
        self._metadata_preview_record = {
            "runId": run_id,
            "source": value.strip(),
            "phase": "loading",
            "title": "Loading preview…",
            "status": "Fetching title, creator, and thumbnail",
            "type": selected_type.value,
        }
        self._set_status("Fetching metadata preview…")
        self.forgePreviewChanged.emit()
        self.runDeckChanged.emit()
        self.select("Forge")
        return True

    @Slot(str, result=bool)
    def openPreviewOwner(self, owner: str) -> bool:
        info = next(
            (
                row
                for row in self._projected_library()
                if row.get(PROJECTION_OWNER_KEY) == owner and is_metadata_preview(row)
            ),
            None,
        )
        if info is None:
            return False
        self._metadata_preview_info = info
        self._metadata_preview_record = {
            "runId": str(info.get("vodforge_preview_run_id") or ""),
            "source": str(info.get("webpage_url") or info.get("original_url") or ""),
            "phase": "complete",
            "title": str(info.get("title") or "Metadata preview"),
            "status": "Preview complete — no media downloaded",
            "type": metadata_output_type(info).value,
        }
        self.forgePreviewChanged.emit()
        self.select("Forge")
        return True

    @Slot(result=bool)
    def startPreviewDownload(self) -> bool:
        info = self._metadata_preview_info
        if info is None or not is_metadata_preview(info):
            self._set_status("Choose a completed metadata preview first.")
            return False
        fallback = str(self._metadata_preview_record.get("source") or "")
        source = retry_url_for_item(info, fallback)
        if not source:
            self._set_status("This preview has no source URL to download.")
            return False
        self._preview_download_info = info
        try:
            return self.submit(source, str(self._metadata_preview_record["type"]))
        finally:
            self._preview_download_info = None

    @Slot(str, str, result=bool)
    def submit(self, value: str, output_format: str) -> bool:
        if not self._check_batch_list_file():
            return False
        if self.composerResume:
            return self.retryTerminal(self._composer_resume_run_id)
        try:
            if self._recovery_source_url and (
                value.strip() != self._recovery_source_url or self._batch_urls
            ):
                self._media_recovery.clear_destination()
                self._recovery_source_url = ""
                self.outputPathChanged.emit()
                self.exportModeChanged.emit()
            if self._relink.active:
                raise RuntimeError(
                    "Finish the saved-location review before downloading."
                )
            if self._import_pending:
                raise RuntimeError("Finish importing media before starting a download.")
            if self._file_action_busy:
                raise RuntimeError("Finish the Library file change before downloading.")
            if not self._settings_writable:
                raise SettingsError(
                    "Settings need attention before a download can start."
                )
            selected_type = OutputType(output_format)
            manual, mp3 = self._current_export_inputs(selected_type)
            job_arguments = (
                value,
                Path(
                    self._media_recovery.destination_for(value, self._output_path)
                    if self._recovery_source_url
                    else self._output_path
                ),
                output_format,
                self.exportMode,
                self._quality,
                self._download_preferences,
                manual,
                mp3,
            )
            job_options: _SubmitJobOptions = {
                "urls": self._batch_urls if self._batch_urls else None,
                "batch_mode": bool(self._batch_urls),
                "batch_list_path": self._batch_path,
                "cookie_source": self._cookie_source,
                "cookie_file": self._cookie_file,
                "cookie_browser": self._cookie_browser,
                "tags": self._current_extra_tags(),
                "nvenc_applicable": self.nvencAvailable,
                "translated_subtitle_language": self._translated_subtitle_language,
            }
            preview = self._preview_download_info
            if (
                preview is None
                and not self._batch_urls
                and value.strip() == self._metadata_preview_record.get("source")
                and output_format == self._metadata_preview_record.get("type")
            ):
                preview = self._metadata_preview_info
            subject = None
            if preview is not None and is_metadata_preview(preview):
                job = self._runtime.prepare_job(*job_arguments, **job_options)
                subject = self._library_projection.preview_subject(preview)
                if subject is None:
                    raise RuntimeError(
                        "The preview changed. Fetch it again before downloading."
                    )
                job.preview_info = dict(preview)
                job.preview_info.pop("vodforge_preview_complete", None)
                job.preview_info.pop("vodforge_preview_run_id", None)
                job.preview_info = annotate_job_metadata(job, job.preview_info)
                if key := metadata_run_key(preview):
                    job.metadata_keys.add(key)
                job.preview_source_owner = subject
                job.batch_list_path = self._batch_path
                self._runtime.start_job(job)
            else:
                job = self._runtime.start(*job_arguments, **job_options)
            self._batch_snapshot_admitted = bool(self._batch_urls)
            if subject is not None:
                self._library_projection.consume_preview_subject(subject)
                self._metadata_preview_info = None
                self._metadata_preview_record = {}
                self.forgePreviewChanged.emit()
        except RunStateError as exc:
            self._status = run_admission_failure_message(exc)
            outcome = "rejected"
        except (OSError, RuntimeError, SettingsError, ValueError) as exc:
            self._status = str(exc)
            outcome = "rejected"
        else:
            if self._recovery_source_url:
                self._media_recovery.clear_destination()
                self._recovery_source_url = ""
                self.outputPathChanged.emit()
                self.exportModeChanged.emit()
            self._reset_batch_composer()
            self.sourceAccepted.emit()
            self.historyChanged.emit()
            self._progress = 0.0
            self.progressChanged.emit()
            self.runningChanged.emit()
            queued = job is not self._runtime.active_job
            # Accepted execution is presented by the owner-bound run status.
            # Queue admission remains action feedback; preparing is not a toast.
            if queued:
                self._status = "Added to download queue."
            else:
                self._status_text = "Preparing download…"
            outcome = "queued" if queued else "started"
            self.activityChanged.emit()
        self.statusChanged.emit()
        self._record("submit", outcome)
        return outcome in {"queued", "started"}

    def _current_extra_tags(self) -> list[str]:
        return [item.strip() for item in self._extra_tags.split(",") if item.strip()]


def create_engine(bridge: Bridge) -> QQmlApplicationEngine:
    # VODForge's custom actions participate in Tab navigation on every platform,
    # even when the platform defaults to text fields only. This is process-local.
    QGuiApplication.styleHints().setTabFocusBehavior(
        Qt.TabFocusBehavior.TabFocusAllControls
    )
    register_window_model()
    engine = QQmlApplicationEngine()
    materials = Materials()
    engine.addImageProvider("vodforge", materials)
    engine.addImageProvider("vodforge-thumbnails", ThumbnailReductionProvider())
    bridge._theme_engine = engine
    bridge._theme_materials = materials
    engine.addImageProvider("vodforge-previews", bridge._previews.images)
    engine.rootContext().setContextProperty("bridge", bridge)
    engine.rootContext().setContextProperty("theme", dict(THEME))
    engine.rootContext().setContextProperty("buttonFontFamily", FONT_UI_FAMILY)
    engine.rootContext().setContextProperty("monoFontFamily", FONT_MONO_FAMILY)
    engine.rootContext().setContextProperty("qualityOptions", list(QUALITY_OPTIONS))
    engine.rootContext().setContextProperty(
        "localVideoProfiles",
        [local_video_profile_label(value) for value in LOCAL_VIDEO_PROFILE_OPTIONS],
    )
    engine.rootContext().setContextProperty(
        "buttonMetrics",
        {
            name: {
                "height": metrics.height,
                "fontPixels": metrics.font_pixels,
                "horizontalPadding": metrics.horizontal_padding,
                "iconPixels": metrics.icon_pixels,
            }
            for name, metrics in BUTTON_METRICS.items()
        },
    )
    assets = SOURCE / "assets"
    engine.rootContext().setContextProperty(
        "assetUrl", QUrl.fromLocalFile(str(assets) + "/").toString()
    )
    engine.load(QUrl.fromLocalFile(str(Path(__file__).with_name("Main.qml"))))
    return engine


class QtQualityE2EApp:
    """Expose Qt's real launch identity to the existing isolation attestor."""

    def __init__(self, bridge: Bridge, window: Any) -> None:
        self.history_path = bridge._runtime.history_path
        self.output_var = self
        self._bridge = bridge
        self._window = window

    def get(self) -> str:
        return self._bridge._output_path

    @overload
    def title(self, value: None = None) -> str: ...

    @overload
    def title(self, value: str) -> None: ...

    def title(self, value: str | None = None) -> str | None:
        if value is not None:
            self._window.setTitle(value)
            return None
        return str(self._window.title())


def attest_qt_launch(bridge: Bridge, window: Any) -> Path | None:
    return write_quality_e2e_startup_attestation(
        QtQualityE2EApp(bridge, window),
        app_version=__version__,
        renderer="qt",
        application_data_path=application_data_dir(),
        diagnostics_path=DIAGNOSTICS_LOG_PATH,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--event-log", type=Path)
    parser.add_argument("--ready-file", type=Path)
    parser.add_argument("--runtime-smoke", action="store_true")
    args = parser.parse_args()
    smoke_home = (
        tempfile.TemporaryDirectory(prefix="vodforge-qt-smoke-")
        if args.runtime_smoke
        else None
    )
    if smoke_home is not None:
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
        os.environ["HOME"] = smoke_home.name
        os.environ["LOCALAPPDATA"] = smoke_home.name
        os.environ["VODFORGE_DISABLE_TELEMETRY"] = "1"
        if runtime_smoke(require_libvlc=False) != 0:
            smoke_home.cleanup()
            return 1
    QQuickStyle.setStyle("Basic")
    application = QGuiApplication(sys.argv[:1])
    application.setApplicationName("VODForge Qt Quick")
    application.setFont(QFont(FONT_UI_FAMILY))
    bridge = Bridge(args.event_log)
    application.aboutToQuit.connect(bridge.close)
    engine = create_engine(bridge)
    if not engine.rootObjects():
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, cast(Any, QEvent).DeferredDelete)
        bridge.close()
        if smoke_home is not None:
            smoke_home.cleanup()
        return 2
    bridge._window = engine.rootObjects()[0]
    native_header_integrated = integrate_qt_main_window(bridge._window)
    try:
        attest_qt_launch(bridge, bridge._window)
    except QualityE2EAttestationError as exc:
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, cast(Any, QEvent).DeferredDelete)
        bridge.close()
        if smoke_home is not None:
            smoke_home.cleanup()
        raise SystemExit(f"VODForge Qt quality-E2E startup rejected: {exc}") from exc
    bridge.startSession()
    if bridge._analytics.telemetry is not None and not args.runtime_smoke:
        bridge._presentation_probe = QtPresentationProbe(
            bridge, bridge._window, bridge._analytics.telemetry
        )
    QTimer.singleShot(6000, bridge._record_update_telemetry_receipt)
    if bridge._files.pending and not args.runtime_smoke:
        QTimer.singleShot(0, bridge.fileActionRequested.emit)
    if bool(getattr(sys, "frozen", False)) and not args.runtime_smoke:
        QTimer.singleShot(0, bridge._auto_check_updates)
    if args.runtime_smoke:
        application.processEvents()
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, cast(Any, QEvent).DeferredDelete)
        application.processEvents()
        bridge.close()
        if smoke_home is None:
            raise RuntimeError("Runtime smoke home was not initialized")
        smoke_home.cleanup()
        return 0
    if args.ready_file:
        window = engine.rootObjects()[0]

        def record_ready() -> None:
            args.ready_file.write_text(
                json.dumps(
                    {
                        "pid": os.getpid(),
                        "platform": QGuiApplication.platformName(),
                        "window_id": int(window.winId()),
                        "visible": window.isVisible(),
                        "native_header_integrated": native_header_integrated,
                        "frame_top_px": window.frameMargins().top(),
                        "geometry": [
                            window.x(),
                            window.y(),
                            window.width(),
                            window.height(),
                        ],
                    }
                )
            )

        QTimer.singleShot(300, record_ready)
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
