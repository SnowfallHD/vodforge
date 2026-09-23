"""Isolated Qt Quick Forge presentation proof; never a release build."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

SOURCE = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(SOURCE))

from PIL import Image
from PySide6.QtCore import Property, QObject, QSize, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QGuiApplication, QImage
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickImageProvider
from PySide6.QtQuickControls2 import QQuickStyle

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

    def __init__(self, event_log: Path | None) -> None:
        super().__init__()
        self._status = "Ready"
        self._output_path = str(Path.home() / "Downloads")
        self._selection = "Forge"
        self._event_log = event_log

    @Property(str, notify=statusChanged)
    def status(self) -> str:
        return self._status

    @Property(str, notify=outputPathChanged)
    def outputPath(self) -> str:
        return self._output_path

    @Property(str, notify=selectionChanged)
    def selection(self) -> str:
        return self._selection

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
    def setOutputPath(self, value: str) -> None:
        path = Path(value).expanduser()
        if not path.is_dir():
            self._status = "Select an existing output folder."
            self.statusChanged.emit()
            self._record("output", "invalid")
            return
        self._output_path = str(path)
        self.outputPathChanged.emit()
        self._record("output", "selected")

    @Slot(str, str)
    def submit(self, value: str, output_format: str) -> None:
        parsed = urlparse(value.strip())
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            self._status = "Enter a complete video URL."
            outcome = "invalid"
        elif output_format not in {"MP4", "MP3", "M4A"}:
            self._status = "Choose a supported output format."
            outcome = "invalid-format"
        else:
            self._status = (
                "URL accepted by prototype; download engine is not connected."
            )
            outcome = "validated-only"
        self.statusChanged.emit()
        self._record("submit", outcome)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--event-log", type=Path)
    parser.add_argument("--ready-file", type=Path)
    args = parser.parse_args()
    QQuickStyle.setStyle("Basic")
    application = QGuiApplication(sys.argv[:1])
    application.setApplicationName("VODForge Qt Quick prototype")
    engine = QQmlApplicationEngine()
    engine.addImageProvider("vodforge", Materials())
    bridge = Bridge(args.event_log)
    engine.rootContext().setContextProperty("bridge", bridge)
    engine.rootContext().setContextProperty("theme", dict(THEME))
    engine.rootContext().setContextProperty("buttonFontFamily", FONT_UI_FAMILY)
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
    if not engine.rootObjects():
        return 2
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
