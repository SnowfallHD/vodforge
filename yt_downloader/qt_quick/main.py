"""Qt Quick application under port; release entrypoint remains the Tk app."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from dataclasses import asdict, fields, replace
from pathlib import Path

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
from PySide6.QtGui import QFont, QGuiApplication, QImage
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickImageProvider
from PySide6.QtQuickControls2 import QQuickStyle

from yt_downloader.app import validate_custom_cover_art
from yt_downloader.export_inputs import (
    MP3_CHANNEL_OPTIONS,
    MP3_COVER_ART_OPTIONS,
    MP3_QUALITY_OPTIONS,
    MP3_SAMPLE_RATE_OPTIONS,
    manual_export_settings,
    mp3_export_settings,
)
from yt_downloader.export_planning import QUALITY_OPTIONS
from yt_downloader.history import HistoryError, history_output_path
from yt_downloader.library_search import LIBRARY_ALL_MEDIA, library_visible_indices
from yt_downloader.local_audio_video import (
    LOCAL_VIDEO_PROFILE_OPTIONS,
    LocalAudioVideoError,
    LocalAudioVideoProgress,
    LocalAudioVideoResult,
)
from yt_downloader.models import ExportMode, OutputType
from yt_downloader.playback_backend import PlaybackSnapshot
from yt_downloader.playback_progress import PlaybackProgressOwner
from yt_downloader.playback_progress_binding import PlaybackProgressBinding
from yt_downloader.qt_quick.local_conversion import LocalConversionRuntime
from yt_downloader.qt_quick.runtime import DownloadPreferences, DownloadRuntime
from yt_downloader.run_state import RunStateError
from yt_downloader.settings_store import (
    SettingsError,
    load_settings,
    save_settings,
    settings_file_path,
)
from yt_downloader.ui_button_contract import button_metrics
from yt_downloader.ui_chrome import action_button_image, field_border_image
from yt_downloader.ui_materials import backdrop_pixels
from yt_downloader.ui_theme import FONT_UI_FAMILY, THEME, theme_motif


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
                if not (1 <= width <= 4096 and 1 <= height <= 512):
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
    exportModeChanged = Signal()
    outputFormatChanged = Signal()
    qualityChanged = Signal()
    playbackUrlChanged = Signal()
    playbackRequested = Signal()
    playbackSeekRequested = Signal(float)
    librarySearchChanged = Signal()
    libraryTypeChanged = Signal()
    localChanged = Signal()
    downloadOptionsChanged = Signal()
    exportSettingsChanged = Signal()

    def __init__(self, event_log: Path | None) -> None:
        super().__init__()
        self._runtime = DownloadRuntime()
        self._local = LocalConversionRuntime()
        self._playback_progress = PlaybackProgressOwner(
            self._runtime.history_path.parent / "watch-progress.json"
        )
        self._playback_progress.load()
        self._playback_binding: PlaybackProgressBinding | None = None
        self._playback_path: Path | None = None
        self._playback_position = 0.0
        self._playback_duration = 0.0
        self._playback_status = "Ready"
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
        self._local_audio = ""
        self._local_image = ""
        self._local_profile = LOCAL_VIDEO_PROFILE_OPTIONS[0]
        self._local_progress = ""
        self._local_running = False
        self._event_log = event_log
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._pump)
        self._timer.start(50)
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.timeout.connect(self._save_preferences)

    @Property(str, notify=statusChanged)
    def status(self) -> str:
        return self._status

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

    @Property("QVariantList", notify=historyChanged)
    def history(self) -> list[dict[str, str]]:
        return [
            {
                "sourceIndex": index,
                "title": str(item.get("title") or "Untitled media"),
                "type": str(item.get("vodforge_output_type") or "MP4"),
                "path": str(item.get("vodforge_output_path") or ""),
            }
            for index in library_visible_indices(
                self._runtime.history, self._library_type, self._library_search
            )
            for item in [self._runtime.history[index]]
        ]

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

    @Property("QVariantList", notify=activityChanged)
    def activity(self) -> list[dict[str, str]]:
        return self._runtime.activity

    def _record(self, action: str, outcome: str) -> None:
        if self._event_log is not None:
            with self._event_log.open("a", encoding="utf-8") as file:
                file.write(json.dumps({"action": action, "outcome": outcome}) + "\n")

    @Slot(str)
    def select(self, name: str) -> None:
        if name not in {"Forge", "Library", "Watch", "Activity"}:
            return
        self._selection = name
        self.selectionChanged.emit()
        self._record("select", name)

    @Slot(str)
    def setLibrarySearch(self, query: str) -> None:
        query = query[:500]
        if query == self._library_search:
            return
        self._library_search = query
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

    @Slot()
    def startLocalConversion(self) -> None:
        try:
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
        except (LocalAudioVideoError, OSError, SettingsError, ValueError) as exc:
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

    @Slot(int)
    def openLibraryItem(self, index: int) -> None:
        if not 0 <= index < len(self._runtime.history):
            return
        path = history_output_path(self._runtime.history[index])
        if path is None or not path.is_file():
            self._status = "The saved media file is missing."
            self.statusChanged.emit()
            return
        if self._playback_binding is not None:
            self._playback_binding.close()
        self._playback_path = path
        self._playback_position = 0.0
        self._playback_duration = 0.0
        self._playback_status = "Ready"
        self._playback_binding = PlaybackProgressBinding(
            self._playback_progress,
            self._runtime.history[index],
            snapshot=self._playback_snapshot(),
            seek=self._request_playback_seek,
        )
        self._playback_url = QUrl.fromLocalFile(str(path))
        self.playbackUrlChanged.emit()
        self.select("Watch")
        self.playbackRequested.emit()

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
    def observePlayback(self, position: float, duration: float, status: str) -> None:
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
        self._playback_binding.present(self._playback_snapshot())

    @Slot(float)
    def manualPlaybackSeek(self, position: float) -> None:
        if self._playback_binding is None:
            return
        self._playback_position = position
        self._playback_binding.manual_seek(self._playback_snapshot())

    @Slot()
    def cancel(self) -> None:
        if self.running:
            self._runtime.cancel()
            self._status = "Stopping download…"
            self.statusChanged.emit()

    def _pump(self) -> None:
        try:
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
                self.statusChanged.emit()
            elif kind == "history_record":
                self.historyChanged.emit()
            elif kind in {"done", "partial", "stopped", "error"}:
                self._status = str(payload)
                self.statusChanged.emit()
                self.runningChanged.emit()
        if events:
            self.activityChanged.emit()
            self.runningChanged.emit()
        for kind, payload in self._local.poll():
            if kind == "progress" and isinstance(payload, LocalAudioVideoProgress):
                self._local_progress = payload.label
            elif kind == "done" and isinstance(payload, LocalAudioVideoResult):
                try:
                    self._runtime.record_local_conversion(payload)
                except (HistoryError, OSError, ValueError):
                    self._status = "Video saved, but Library history needs attention."
                else:
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
        if self._playback_binding is not None:
            self._playback_binding.close()
            self._playback_binding = None
        self._local.close()
        self._runtime.close()

    @Slot(str, str)
    def submit(self, value: str, output_format: str) -> None:
        try:
            if not self._settings_writable:
                raise SettingsError(
                    "Settings need attention before a download can start."
                )
            selected_type = OutputType(output_format)
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
            job = self._runtime.start(
                value,
                Path(self._output_path),
                output_format,
                self._export_mode,
                self._quality,
                self._download_preferences,
                manual,
                mp3,
            )
        except (OSError, RuntimeError, SettingsError, ValueError) as exc:
            self._status = str(exc)
            outcome = "rejected"
        else:
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
    engine.rootContext().setContextProperty("bridge", bridge)
    engine.rootContext().setContextProperty("theme", dict(THEME))
    engine.rootContext().setContextProperty("buttonFontFamily", FONT_UI_FAMILY)
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
