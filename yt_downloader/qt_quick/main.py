"""Qt Quick application under port; release entrypoint remains the Tk app."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
import uuid
from dataclasses import asdict, fields, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SOURCE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SOURCE))

from PIL import Image
from PySide6.QtCore import (
    Property,
    QCoreApplication,
    QEvent,
    QObject,
    QSize,
    QTimer,
    QUrl,
    Signal,
    Slot,
)
from PySide6.QtGui import QDesktopServices, QFont, QGuiApplication, QImage
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickImageProvider
from PySide6.QtQuickControls2 import QQuickStyle

from yt_downloader.app import (
    DownloaderApp,
    append_activity_log,
    load_activity_log_tail,
    prepare_activity_log,
)
from yt_downloader.archive_observations import bind_operation, operation
from yt_downloader.archive_relink import record_fingerprint
from yt_downloader.archive_work import ArchiveWorkOwner
from yt_downloader.cloud_funnel import installation_state_path
from yt_downloader.cookie_inputs import browser_cookie_value
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
from yt_downloader.export_planning import QUALITY_OPTIONS
from yt_downloader.forge_activity import ForgeActivityProjection
from yt_downloader.history import (
    HistoryError,
    application_data_dir,
    history_annotation_owner,
    history_archive_owner,
    history_identity,
    history_output_path,
    sanitize_chapters,
    sanitize_heatmap,
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
from yt_downloader.library_scene_facts import library_detail_facts
from yt_downloader.library_search import (
    LIBRARY_ALL_CATEGORIES,
    LIBRARY_ALL_MEDIA,
    library_categories,
    library_visible_indices,
)
from yt_downloader.library_state import (
    ANNOTATION_OWNER_KEY,
    PROJECTION_OWNER_KEY,
    RUN_STATUS_KEY,
    LibraryProjectionOwner,
    persisted_run_deck_records,
    resolve_library_removal_plan,
)
from yt_downloader.local_audio_video import (
    LOCAL_VIDEO_PROFILE_OPTIONS,
    LocalAudioVideoError,
    LocalAudioVideoProgress,
    LocalAudioVideoResult,
)
from yt_downloader.models import (
    CookieSource,
    ExportMode,
    ManualExportSettings,
    Mp3ExportSettings,
    OutputType,
)
from yt_downloader.platform_services import diagnostics_dir
from yt_downloader.playback_backend import PlaybackSnapshot
from yt_downloader.playback_progress import PlaybackProgressOwner
from yt_downloader.playback_progress_binding import PlaybackProgressBinding
from yt_downloader.player_related import player_related_plan
from yt_downloader.product_telemetry import product_output_kind
from yt_downloader.qt_quick.analytics import QtAnalyticsSession
from yt_downloader.qt_quick.artwork import QtArtwork
from yt_downloader.qt_quick.library_files import QtLibraryFiles
from yt_downloader.qt_quick.local_conversion import LocalConversionRuntime
from yt_downloader.qt_quick.previews import QtPreviewSession
from yt_downloader.qt_quick.runtime import DownloadPreferences, DownloadRuntime
from yt_downloader.qt_quick.scene_projection import library_scene, watch_scene
from yt_downloader.qt_quick.support import QtSupportSession
from yt_downloader.qt_quick.update_session import QtUpdateSession
from yt_downloader.run_state import RunStateError
from yt_downloader.settings_store import (
    SettingsError,
    load_settings,
    save_settings,
    settings_file_path,
)
from yt_downloader.support_diagnostics import FailureContext, failure_context
from yt_downloader.telemetry_features import settings_dimensions, time_bucket
from yt_downloader.telemetry_policy import telemetry_site_origin
from yt_downloader.ui_button_contract import button_metrics
from yt_downloader.ui_chrome import action_button_image, field_border_image
from yt_downloader.ui_materials import backdrop_pixels
from yt_downloader.ui_theme import FONT_MONO_FAMILY, FONT_UI_FAMILY, THEME, theme_motif
from yt_downloader.updates import RELEASES_PAGE, record_update_telemetry_receipts
from yt_downloader.url_list_inputs import read_url_list_file
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
            if parts[0] == "backdrop" and len(parts) == 1:
                source = backdrop_pixels(
                    theme_motif(), THEME["bg"], THEME["accent"], (1920, 1200)
                )
            elif parts[0] == "button" and len(parts) == 5:
                width, height = int(parts[1]), int(parts[2])
                if not (1 <= width <= 4096 and 1 <= height <= 512):
                    raise ValueError("button image dimensions out of bounds")
                source = action_button_image(
                    width, height, accent=parts[4] == "1", state=parts[3]
                )
            elif parts[0] == "field" and len(parts) == 4:
                width, height = int(parts[1]), int(parts[2])
                if not (1 <= width <= 4096 and 1 <= height <= 2048):
                    raise ValueError("field image dimensions out of bounds")
                source = field_border_image(width, height, focused=parts[3] == "focus")
            elif parts[0] == "icon" and len(parts) == 2:
                if parts[1] not in {
                    "download-20.png",
                    "folder-20.png",
                    "play.png",
                    "activity-20.png",
                }:
                    raise ValueError("unknown icon")
                with Image.open(
                    SOURCE / "assets" / "icons" / "lucide" / parts[1]
                ) as original:
                    source = Image.new("RGBA", original.size, THEME["icon"])
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


class Bridge(QObject):
    statusChanged = Signal()
    outputPathChanged = Signal()
    selectionChanged = Signal()
    progressChanged = Signal()
    runningChanged = Signal()
    historyChanged = Signal()
    activityChanged = Signal()
    runDeckChanged = Signal()
    exportModeChanged = Signal()
    outputFormatChanged = Signal()
    qualityChanged = Signal()
    playbackUrlChanged = Signal()
    playerSceneChanged = Signal()
    playbackPreviewsChanged = Signal()
    playbackRequested = Signal(int)
    playbackSeekRequested = Signal(float)
    librarySearchChanged = Signal()
    libraryTypeChanged = Signal()
    localChanged = Signal()
    downloadOptionsChanged = Signal()
    exportSettingsChanged = Signal()
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

    def __init__(self, event_log: Path | None) -> None:
        super().__init__()
        self._runtime = DownloadRuntime()
        self.historyChanged.connect(self.playerSceneChanged.emit)
        self.historyChanged.connect(self.runDeckChanged.emit)
        self._support = QtSupportSession(self._runtime.history_path.parent)
        self._latest_failure: FailureContext | None = None
        self._engagement = EngagementState(
            installation_state_path(data_dir=self._runtime.history_path.parent)
        )
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
        self._import_pending = False
        self._import_request_count = 0
        self._import_started_at = 0.0
        self._import_operation: Any | None = None
        self._storage = StorageCapacityOwner()
        self._storage_snapshot = self._storage.snapshot
        self._artwork = QtArtwork(self._runtime.history_path.parent / "artwork")
        self._files.refresh_recovery()
        self._file_action_busy = self._files.uncertain
        if self._files.uncertain and self._runtime.recovery_notice is None:
            self._runtime.recovery_notice = (
                "Library file recovery must finish before new downloads."
            )
        self._runtime.resume_queued()
        self._window: Any | None = None
        self._annotations_writable = True
        self._annotations = LibraryAnnotationsOwner(
            self._runtime.history_path.parent / "library-annotations.json",
            diagnostic=lambda _message: setattr(self, "_annotations_writable", False),
        )
        self._annotations.load()
        self._library_projection = LibraryProjectionOwner()
        self._annotation_owner = ""
        self._library_detail_owner = ""
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
        self._playback_position = 0.0
        self._playback_duration = 0.0
        self._playback_status = "Ready"
        self._playback_recorded = False
        self._playback_output_type = ""
        self._playback_chapters: list[dict[str, Any]] = []
        self._playback_heatmap: list[dict[str, float]] = []
        self._playback_generation = 0
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
            self._settings = load_settings(self._settings_path)
            self._settings_writable = True
        except SettingsError:
            self._settings = {}
            self._settings_writable = False
        defaults = DownloadPreferences()
        self._download_preferences = DownloadPreferences(
            **{
                field.name: value
                if isinstance((value := self._settings.get(field.name)), bool)
                else getattr(defaults, field.name)
                for field in fields(DownloadPreferences)
            }
        )
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
        self._output_path = (
            saved_output
            if saved_output and Path(saved_output).is_dir()
            else str(Path.home() / "Downloads")
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
        self._library_sort = "recent"
        self._library_group_key = ""
        self._library_group_kind = ""
        self._watch_scene_route = "home"
        self._watch_group_key = ""
        self._watch_group_kind = ""
        self._watch_search = ""
        self._watch_history: list[tuple[str, str, str, str]] = []
        self._watch_hero_seen_key = ""
        self._local_audio = ""
        self._local_image = ""
        self._local_profile = LOCAL_VIDEO_PROFILE_OPTIONS[0]
        self._local_progress = ""
        self._local_running = False
        self._batch_urls: list[str] = []
        self._batch_name = ""
        self._cookie_source = CookieSource.PUBLIC
        self._cookie_browser = ""
        self._cookie_file: Path | None = None
        self._event_log = event_log
        self._closed = False
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._pump)
        self._timer.start(50)
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.timeout.connect(self._save_preferences)

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
        return self._files.status

    @Property(str, notify=fileActionChanged)
    def fileActionName(self) -> str:
        return self._files.action

    @Property(bool, notify=fileActionChanged)
    def fileActionBusy(self) -> bool:
        return self._files.phase in {"checking", "working"}

    @Property(bool, notify=fileActionChanged)
    def fileActionEligible(self) -> bool:
        return self._files.phase == "preview" and self._files.eligible

    @Property(bool, notify=fileActionChanged)
    def fileActionRecovery(self) -> bool:
        return self._files.phase == "recovery"

    @Property(bool, notify=fileActionChanged)
    def fileActionCanFinish(self) -> bool:
        return self._files.can_finish

    @Slot(str, str, QUrl, result=bool)
    def startFileAction(self, action: str, owner: str, destination: QUrl) -> bool:
        pending = self._files.refresh_recovery()
        self._file_action_busy = self._files.uncertain
        if pending:
            self.fileActionChanged.emit()
            return True
        item = self._saved_item_for_owner(owner)
        if item is None:
            self._status = "That Library item changed. Select it again."
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
        elif (
            self._playback_path is not None
            and history_output_path(item) == self._playback_path
        ):
            self._status = "Close Watch playback before changing this media."
        else:
            folder = Path(destination.toLocalFile()) if action == "move" else None
            if self._files.begin(
                action, owner, self._runtime.history, destination=folder
            ):
                self.fileActionChanged.emit()
                return True
            self._status = self._files.status or "This file action could not start."
        self.statusChanged.emit()
        return False

    @Slot(result=bool)
    def confirmFileAction(self) -> bool:
        if (
            self._runtime.active_job is not None
            or self._runtime.busy
            or self._runtime.queued
            or self._local_running
            or self._import_pending
            or self._file_action_busy
        ):
            return False
        started = self._files.confirm(self._runtime.history)
        if started:
            self._file_action_busy = True
        self.fileActionChanged.emit()
        return started

    @Slot(bool, result=bool)
    def recoverFileAction(self, finish: bool) -> bool:
        started = self._files.recover(finish=finish)
        if started:
            self._file_action_busy = True
            self.fileActionChanged.emit()
        return started

    @Slot()
    def checkForUpdates(self) -> None:
        if self._updates.check():
            self.updateChanged.emit()

    @Slot()
    def downloadUpdate(self) -> None:
        if self._updates.download():
            self._record_update_feature("updater", "download_started")
            self.updateChanged.emit()

    @Slot()
    def repairUpdate(self) -> None:
        if self._updates.download(repair=True):
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
        except (OSError, ValueError):
            pass

    def _auto_check_updates(self) -> None:
        if (
            self._updates.busy
            or self._runtime.busy
            or self._runtime.active_job is not None
        ):
            QTimer.singleShot(10 * 60 * 1000, self._auto_check_updates)
            return
        self.checkForUpdates()
        QTimer.singleShot(6 * 60 * 60 * 1000, self._auto_check_updates)

    @Slot()
    def openDownloadPage(self) -> None:
        QDesktopServices.openUrl(QUrl(RELEASES_PAGE))

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
            downloads_busy=(
                self._runtime.active_job is not None
                or self._runtime.busy
                or bool(getattr(self._runtime, "queued", []))
                or self._local_running
            ),
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

    @Property(str, notify=outputPathChanged)
    def outputPath(self) -> str:
        return self._output_path

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
        return self._export_mode

    @Property(str, notify=outputFormatChanged)
    def outputFormat(self) -> str:
        return self._output_format

    @Property(str, notify=qualityChanged)
    def quality(self) -> str:
        return self._quality

    @Property(QUrl, notify=playbackUrlChanged)
    def playbackUrl(self) -> QUrl:
        return self._playback_url

    @Property("QVariantList", notify=playbackUrlChanged)
    def playbackChapters(self) -> list[dict[str, Any]]:
        return list(self._playback_chapters)

    @Property("QVariantList", notify=playbackUrlChanged)
    def playbackHeatmap(self) -> list[dict[str, float]]:
        return list(self._playback_heatmap)

    @Property("QVariantList", notify=playbackPreviewsChanged)
    def playbackPreviews(self) -> list[dict[str, Any]]:
        return self._previews.records

    @Property("QVariantMap", notify=playerSceneChanged)
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
            "creator": str(
                current.get("channel") or current.get("uploader") or "Unknown creator"
            ),
            "category": str(current.get("vodforge_user_category") or ""),
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

    @Property("QVariantList", notify=historyChanged)
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

    @Property("QVariantMap", notify=historyChanged)
    def libraryScene(self) -> dict[str, Any]:
        return library_scene(
            self._projected_library(),
            self._library_scene_route,
            self._library_group_key,
            self._library_group_kind,
            self._artwork.request,
            self._library_search,
            ""
            if self._library_category == LIBRARY_ALL_CATEGORIES
            else self._library_category,
            self._library_sort,
        )

    @Property("QVariantMap", notify=historyChanged)
    def watchScene(self) -> dict[str, Any]:
        scene = watch_scene(
            self._projected_library(),
            self._watch_scene_route,
            self._artwork.request,
            self._watch_group_key,
            self._watch_group_kind,
            self._watch_search,
            self._playback_progress.for_record,
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

    @Property("QVariantMap", notify=supportChanged)
    def supportContext(self) -> dict[str, str]:
        context = self._support.context
        return {
            "diagnostics": context.diagnostics if context is not None else "",
            "videoUrl": context.video_url if context is not None else "",
        }

    @Property(str, notify=editorialChanged)
    def editorialHeading(self) -> str:
        return {
            "welcome": "Welcome to VODForge",
            "whats-new": "What’s new",
            "did-you-know": "Did you know?",
        }.get(self._editorial_kind, "")

    @Property(str, notify=editorialChanged)
    def editorialFinishLabel(self) -> str:
        if self._editorial_kind == "welcome":
            return "Start using VODForge"
        if self._editorial_kind == "did-you-know" or (
            len(self._editorial_slides) == 1
            and self._editorial_slides[0].key == "output-settings"
        ):
            return "Try it"
        return "Done"

    @Property("QVariantList", notify=editorialChanged)
    def editorialSlides(self) -> list[dict[str, str]]:
        return [
            {
                "key": slide.key,
                "title": slide.title,
                "description": slide.description,
                "preview": slide.preview.value,
            }
            for slide in self._editorial_slides
        ]

    @Property("QVariantMap", notify=historyChanged)
    def libraryDetail(self) -> dict[str, Any]:
        row = next(
            (
                row
                for row in self._projected_library()
                if history_archive_owner(row) == self._library_detail_owner
                and row.get("vodforge_output_dir")
            ),
            None,
        )
        if row is None:
            return {}
        source, output = library_detail_facts(row)
        return {
            "owner": self._library_detail_owner,
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
            "tags": [str(tag) for tag in row.get("vodforge_user_tags") or ()],
            "artwork": self._artwork.request(row),
            "source": [{"label": label, "value": value} for label, value, _ in source],
            "output": [{"label": label, "value": value} for label, value, _ in output],
        }

    @Property("QVariantList", notify=historyChanged)
    def collectionCandidates(self) -> list[dict[str, str]]:
        return [
            {
                "owner": history_annotation_owner(row),
                "title": str(row.get("title") or "Saved media"),
            }
            for row in self._runtime.history
            if row.get("vodforge_output_dir")
        ]

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

    @Property("QVariantMap", notify=storageChanged)
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

    @Property("QVariantList", notify=storageChanged)
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
                            subprocess.SubprocessError,
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

    @Property("QVariantList", notify=historyChanged)
    def libraryCategories(self) -> list[str]:
        return [LIBRARY_ALL_CATEGORIES, *library_categories(self._projected_library())]

    @Property("QVariantMap", notify=annotationChanged)
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
        return self._local_profile

    @Property(str, notify=localChanged)
    def localProgress(self) -> str:
        return self._local_progress

    @Property(bool, notify=localChanged)
    def localRunning(self) -> bool:
        return self._local_running

    @Property("QVariantMap", notify=downloadOptionsChanged)
    def downloadOptions(self) -> dict[str, bool]:
        return asdict(self._download_preferences)

    @Property("QVariantMap", notify=exportSettingsChanged)
    def manualValues(self) -> dict[str, str]:
        return dict(self._manual_values)

    @Property("QVariantMap", notify=exportSettingsChanged)
    def mp3Values(self) -> dict[str, str | bool]:
        return dict(self._mp3_values)

    @Property("QVariantList", constant=True)
    def mp3QualityOptions(self) -> list[str]:
        return list(MP3_QUALITY_OPTIONS)

    @Property("QVariantList", constant=True)
    def mp3SampleRateOptions(self) -> list[str]:
        return list(MP3_SAMPLE_RATE_OPTIONS)

    @Property("QVariantList", constant=True)
    def mp3ChannelOptions(self) -> list[str]:
        return list(MP3_CHANNEL_OPTIONS)

    @Property("QVariantList", constant=True)
    def mp3CoverOptions(self) -> list[str]:
        return list(MP3_COVER_ART_OPTIONS)

    @Property(str, notify=exportSettingsChanged)
    def mp3CoverName(self) -> str:
        return self._mp3_custom_cover.name if self._mp3_custom_cover else "Choose image"

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

    @Property("QVariantList", constant=True)
    def cookieBrowserOptions(self) -> list[str]:
        return list(COOKIE_BROWSER_OPTIONS[1:])

    @Property("QVariantList", notify=activityChanged)
    def activity(self) -> list[dict[str, str]]:
        return self._runtime.activity

    @Property(str, notify=activityChanged)
    def activityLog(self) -> str:
        return self._activity_log_text

    @Property("QVariantMap", notify=activityChanged)
    def forgeActivity(self) -> dict[str, str]:
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

    @Property("QVariantMap", notify=runDeckChanged)
    def runDeck(self) -> dict[str, Any]:
        records: list[dict[str, Any]] = []
        active = self._runtime.active_job
        if active is not None:
            preview = active.preview_info or {}
            records.append(
                {
                    "runId": active.run_id,
                    "kind": "active",
                    "title": str(
                        preview.get("title") or f"{active.output_type.value} download"
                    ),
                    "status": self._status,
                    "type": active.output_type.value,
                    "progress": self._progress,
                    "artwork": self._artwork.request(preview) if preview else "",
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
                        "kind": kind,
                        "title": str(
                            preview.get("title") or f"{job.output_type.value} download"
                        ),
                        "status": job.terminal_status or "Queued",
                        "type": job.output_type.value,
                        "progress": 0,
                        "artwork": self._artwork.request(preview) if preview else "",
                    }
                )
        for record in persisted_run_deck_records(
            self._runtime.history, completed_jobs=()
        ):
            index = record.get("metadata_index")
            if not isinstance(index, int):
                continue
            item = self._runtime.history[index]
            records.append(
                {
                    "runId": str(record["run_id"]),
                    "owner": history_archive_owner(item),
                    "kind": str(record["kind"]),
                    "title": str(record["title"]),
                    "status": str(record["status"]),
                    "type": str(record["output_type"]),
                    "progress": 100,
                    "artwork": self._artwork.request(item),
                }
            )
        counts: dict[str, int] = {}
        for record in records:
            kind = record["kind"]
            counts[kind] = counts.get(kind, 0) + 1
        summary = (
            "No runs yet"
            if not records
            else f"{len(records)} run{'s' if len(records) != 1 else ''}"
        )
        for kind in ("active", "queued", "completed", "terminal"):
            if count := counts.get(kind, 0):
                summary += f"  •  {count} {kind}"
        return {
            "records": records,
            "visible": records[:4],
            "count": len(records),
            "summary": summary,
        }

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
        self._selection = name
        self.selectionChanged.emit()
        self._record("select", name)

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
        operation_key: str,
        dimensions: dict[str, str],
        *,
        failure_detail: Any = None,
    ) -> None:
        telemetry = self._analytics.telemetry
        if action == "requested":
            self._watch_queue_observations[operation_key] = (
                telemetry.bind_operation(
                    "watch_queue_operation", operation_key=operation_key
                )
                if telemetry is not None
                else None
            )
        observation = self._watch_queue_observations.get(operation_key)
        try:
            if observation is not None:
                observation.record(action, dimensions, failure_detail=failure_detail)
        finally:
            if action in {"completed", "cancelled", "failed"}:
                self._watch_queue_observations.pop(operation_key, None)

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
        }:
            return
        self._library_scene_route = route
        self._library_group_key = ""
        self._library_group_kind = ""
        self._library_detail_owner = ""
        self._library_detail_origin = None
        self.historyChanged.emit()

    @Slot(str, str)
    def navigateLibraryGroup(self, kind: str, key: str) -> None:
        if kind not in {"channel", "playlist", "collection"} or not key:
            return
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
            self._library_detail_origin = (
                self._library_scene_route,
                self._library_group_kind,
                self._library_group_key,
            )
        self._library_detail_owner = owner
        self._library_scene_route = "detail"
        self.historyChanged.emit()
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
        self._library_detail_origin = None
        self.historyChanged.emit()

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
    def openWelcomeTour(self) -> bool:
        if self._editorial_kind or self._support.kind:
            return False
        self._editorial_kind = "welcome"
        self._editorial_slides = WELCOME_SLIDES
        try:
            self._engagement.presented_welcome()
        except (OSError, ValueError):
            pass
        self._settings["whats_new_seen"] = SHOWCASE_ID
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
            or self._support.kind
            or self._runtime.active_job is not None
            or self._runtime.busy
            or self._runtime.queued
            or self._playback_binding is not None
        ):
            return
        try:
            if self._engagement.welcome_pending:
                self.openWelcomeTour()
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
        if owner != str(self.watchScene["hero"].get("owner") or ""):
            return
        self._record_update_feature(
            "watch", "hero_played", {"watch_mode": self._watch_mode()}
        )
        self.openLibraryOwner(owner)

    @Slot(str, result=bool)
    def openWatchDetails(self, owner: str) -> bool:
        if not self.openLibraryDetails(owner):
            return False
        self._record_update_feature("watch", "details")
        self.select("Library")
        return True

    @Slot(str, "QVariantList", result=bool)
    def createCollection(self, name: str, owners: list[str]) -> bool:
        name = name.strip()
        available = {item["owner"] for item in self.collectionCandidates}
        chosen = set(owners)
        if not name or not chosen or not chosen <= available:
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
        self.historyChanged.emit()
        self._status = f"Collection {name} saved."
        self.statusChanged.emit()
        return True

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
        if query and self._library_scene_route == "home":
            self._library_scene_route = "all"
        self.librarySearchChanged.emit()
        self.historyChanged.emit()

    @Slot(str)
    def setLibraryType(self, output_type: str) -> None:
        if output_type not in {LIBRARY_ALL_MEDIA, *(item.value for item in OutputType)}:
            return
        if output_type == self._library_type:
            return
        self._library_type = output_type
        self.libraryTypeChanged.emit()
        self.historyChanged.emit()

    @Slot(str)
    def setLibraryCategory(self, category: str) -> None:
        if category not in self.libraryCategories:
            return
        self._library_category = category
        self.libraryCategoryChanged.emit()
        self.historyChanged.emit()

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
        if profile in LOCAL_VIDEO_PROFILE_OPTIONS:
            self._local_profile = profile
            self.localChanged.emit()

    @Slot(str, bool)
    def setDownloadOption(self, key: str, enabled: bool) -> None:
        if key not in self.downloadOptions:
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
        if key not in allowed or value not in allowed[key]:
            return
        self._mp3_values[key] = value
        if key == "mp3_cover_art_mode" and value != "Custom art":
            self._mp3_custom_cover = None
        self.exportSettingsChanged.emit()
        self._schedule_preferences_save()

    @Slot(bool)
    def setMp3Metadata(self, enabled: bool) -> None:
        self._mp3_values["mp3_embed_metadata"] = enabled
        self.exportSettingsChanged.emit()
        self._schedule_preferences_save()

    @Slot(QUrl)
    def setMp3CoverUrl(self, url: QUrl) -> None:
        if not url.isLocalFile():
            return
        self._mp3_custom_cover = Path(url.toLocalFile())
        self._mp3_values["mp3_cover_art_mode"] = "Custom art"
        self.exportSettingsChanged.emit()

    @Slot(QUrl)
    def loadBatchUrl(self, url: QUrl) -> None:
        if not url.isLocalFile():
            return
        path = Path(url.toLocalFile())
        try:
            urls = read_url_list_file(path)
            if not urls:
                raise ValueError("That text file contains no http or https URLs.")
        except (OSError, UnicodeError, ValueError) as exc:
            self._status = str(exc)
            self.statusChanged.emit()
            return
        self._batch_urls = urls
        self._batch_name = path.name
        self._status = f"Loaded {len(urls)} URL(s). They will run one at a time."
        self.batchListChanged.emit()
        self.statusChanged.emit()

    @Slot()
    def clearBatchList(self) -> None:
        self._batch_urls = []
        self._batch_name = ""
        self.batchListChanged.emit()

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
            self._status = str(exc)
            self.statusChanged.emit()
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
    def setOutputPath(self, value: str) -> None:
        path = Path(value).expanduser()
        if not path.is_dir():
            self._status = "Select an existing output folder."
            self.statusChanged.emit()
            self._record("output", "invalid")
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
        path = history_output_path(self._runtime.history[index])
        if path is None or not path.is_file():
            self._status = "The saved media file is missing."
            self.statusChanged.emit()
            return False
        if self._playback_binding is not None:
            self._playback_binding.close()
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
        )
        self._playback_url = QUrl.fromLocalFile(str(path))
        self._playback_generation += 1
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
    def closePlayback(self) -> None:
        self._watch_queue.cancel()
        if self._playback_binding is not None:
            self._playback_binding.close()
            self._playback_binding = None
        self._playback_path = None
        self._playback_record = None
        self._previews.load(None)
        self.playbackPreviewsChanged.emit()
        self._playback_url = QUrl()
        self.playbackUrlChanged.emit()
        self.playerSceneChanged.emit()
        self.historyChanged.emit()

    @Slot(str)
    def openLibraryFolder(self, owner: str) -> None:
        item = self._saved_item_for_owner(owner)
        path = history_output_path(item) if item is not None else None
        if path is None or not path.parent.is_dir():
            self._status = "The saved media folder is unavailable."
            self.statusChanged.emit()
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.parent)))

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

    @Slot(str, result=bool)
    def prepareLibraryRemoval(self, owner: str) -> bool:
        """Bind confirmation to one exact saved record, not a changing row index."""
        self._pending_library_removal = None
        if self._file_action_busy or self._files.pending or self._import_pending:
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
    def observePlayback(
        self, position: float, duration: float, status: str, generation: int = -1
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
        self._playback_status = status
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
        self._playback_binding.present(self._playback_snapshot())
        if self._previews.request(duration):
            self.playbackPreviewsChanged.emit()
        self._watch_queue.present(self, status)

    @Slot(float)
    def manualPlaybackSeek(self, position: float) -> None:
        if self._playback_binding is None:
            return
        self._playback_position = position
        self._playback_binding.manual_seek(self._playback_snapshot())
        self.playbackSeekRequested.emit(position)
        self._record_player_feature("seek")

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

    @Slot()
    def cancel(self) -> None:
        if self.running:
            self._runtime.cancel()
            self._status = "Stopping download…"
            self.statusChanged.emit()

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
            self._status = "The queued run could not be removed safely."
            self.statusChanged.emit()
            return False
        if removed:
            self._status = "Queued run removed."
            self.statusChanged.emit()
            self.activityChanged.emit()
            self.historyChanged.emit()
        return removed

    @Slot(str, result=bool)
    def retryTerminal(self, run_id: str) -> bool:
        try:
            if self._import_pending:
                raise RuntimeError("Finish importing media before retrying.")
            if self._file_action_busy:
                raise RuntimeError("Finish the Library file change before retrying.")
            status, url = self._runtime.terminal_retry_source(run_id)
            current_job = None
            if status == "Failed":
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
                )
            retry = self._runtime.retry_terminal(run_id, current_job=current_job)
        except (OSError, RuntimeError, ValueError) as exc:
            self._status = str(exc)
            self.statusChanged.emit()
            return False
        self._status = (
            "Added retry to the queue."
            if retry is not self._runtime.active_job
            else "Retry started."
        )
        self.statusChanged.emit()
        self.activityChanged.emit()
        self.historyChanged.emit()
        self.runningChanged.emit()
        self.select("Forge")
        return True

    def _pump(self) -> None:
        if self._closed:
            return
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
            self.historyChanged.emit()
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
            self._timer.stop()
            return
        for kind, payload in events:
            if kind in {"progress", "progress_determinate"} and payload is not None:
                self._progress = max(0.0, min(100.0, float(payload)))
                self.progressChanged.emit()
            elif kind == "status":
                self._status = str(payload)
                self._forge_activity.observe(self._forge_run_id, self._status)
                self.statusChanged.emit()
            elif kind == "log":
                self._append_activity_line(str(payload))
                self._forge_technical = (
                    self._forge_technical
                    + ("\n" if self._forge_technical else "")
                    + str(payload)
                )[-50_000:]
            elif kind in {"history_record", "job_metadata"}:
                self.historyChanged.emit()
            elif kind in {"done", "partial", "stopped", "error"}:
                if kind in {"partial", "error"} and active_job_before is not None:
                    try:
                        self._latest_failure = failure_context(
                            active_job_before, str(payload)
                        )
                    except (OSError, ValueError):
                        self._latest_failure = None
                if kind == "done" and active_job_before is not None:
                    try:
                        self._engagement.completed_download(active_job_before.run_id)
                    except (OSError, ValueError):
                        pass
                self._status = str(payload)
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
                self._local_running = False
                self.statusChanged.emit()
            self.localChanged.emit()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._timer.stop()
        if self._save_timer.isActive():
            self._save_timer.stop()
            self._save_preferences()
        self._watch_queue.cancel()
        self._previews.close()
        if self._import_pending:
            operation(
                self._analytics.telemetry,
                "library_import_operation",
                "cancelled",
                self._import_operation,
            )
        self._import_work.close()
        self._storage.close()
        self._artwork.close()
        self._files.close()
        if self._playback_binding is not None:
            self._playback_binding.close()
            self._playback_binding = None
        self._local.close()
        self._runtime.close()
        if self._analytics.telemetry is not None:
            self._analytics.telemetry.shutdown(timeout_seconds=1.0)

    def _current_export_inputs(
        self, selected_type: OutputType
    ) -> tuple[ManualExportSettings | None, Mp3ExportSettings | None]:
        manual = (
            manual_export_settings(self._manual_values)
            if selected_type == OutputType.MP4
            and self._export_mode == ExportMode.MANUAL_OVERRIDE.value
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

    @Slot(str, str)
    def submit(self, value: str, output_format: str) -> None:
        try:
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
            job = self._runtime.start(
                value,
                Path(self._output_path),
                output_format,
                self._export_mode,
                self._quality,
                self._download_preferences,
                manual,
                mp3,
                urls=self._batch_urls if self._batch_urls else None,
                batch_mode=bool(self._batch_urls),
                cookie_source=self._cookie_source,
                cookie_file=self._cookie_file,
                cookie_browser=self._cookie_browser,
            )
        except (OSError, RuntimeError, SettingsError, ValueError) as exc:
            self._status = str(exc)
            outcome = "rejected"
        else:
            self.clearBatchList()
            self.sourceAccepted.emit()
            self.historyChanged.emit()
            self._progress = 0.0
            self.progressChanged.emit()
            self.runningChanged.emit()
            queued = job is not self._runtime.active_job
            self._status = (
                "Added to download queue." if queued else "Preparing download…"
            )
            outcome = "queued" if queued else "started"
            self.activityChanged.emit()
        self.statusChanged.emit()
        self._record("submit", outcome)


def create_engine(bridge: Bridge) -> QQmlApplicationEngine:
    engine = QQmlApplicationEngine()
    engine.addImageProvider("vodforge", Materials())
    engine.addImageProvider("vodforge-previews", bridge._previews.images)
    engine.rootContext().setContextProperty("bridge", bridge)
    engine.rootContext().setContextProperty("theme", dict(THEME))
    engine.rootContext().setContextProperty("buttonFontFamily", FONT_UI_FAMILY)
    engine.rootContext().setContextProperty("monoFontFamily", FONT_MONO_FAMILY)
    engine.rootContext().setContextProperty("qualityOptions", list(QUALITY_OPTIONS))
    engine.rootContext().setContextProperty(
        "localVideoProfiles", list(LOCAL_VIDEO_PROFILE_OPTIONS)
    )
    engine.rootContext().setContextProperty(
        "buttonMetrics",
        {
            name: {
                "height": button_metrics(name).height,
                "fontPixels": button_metrics(name).font_pixels,
                "horizontalPadding": button_metrics(name).horizontal_padding,
                "iconPixels": button_metrics(name).icon_pixels,
            }
            for name in ("default", "compact", "inline")
        },
    )
    assets = SOURCE / "assets"
    engine.rootContext().setContextProperty(
        "assetUrl", QUrl.fromLocalFile(str(assets) + "/").toString()
    )
    engine.load(QUrl.fromLocalFile(str(Path(__file__).with_name("Main.qml"))))
    return engine


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
    QQuickStyle.setStyle("Basic")
    application = QGuiApplication(sys.argv[:1])
    application.setApplicationName("VODForge Qt Quick")
    application.setFont(QFont(FONT_UI_FAMILY))
    bridge = Bridge(args.event_log)
    application.aboutToQuit.connect(bridge.close)
    engine = create_engine(bridge)
    if not engine.rootObjects():
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        bridge.close()
        if smoke_home is not None:
            smoke_home.cleanup()
        return 2
    bridge.startSession()
    bridge._window = engine.rootObjects()[0]
    QTimer.singleShot(6000, bridge._record_update_telemetry_receipt)
    if bridge._files.pending and not args.runtime_smoke:
        QTimer.singleShot(0, bridge.fileActionRequested.emit)
    if bool(getattr(sys, "frozen", False)) and not args.runtime_smoke:
        QTimer.singleShot(0, bridge._auto_check_updates)
    if args.runtime_smoke:
        application.processEvents()
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        application.processEvents()
        bridge.close()
        assert smoke_home is not None
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
