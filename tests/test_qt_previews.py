"""Qt handoff keeps preview images tied to the current saved media."""

from __future__ import annotations

import io
import threading
import time
from pathlib import Path

from PIL import Image
from PySide6.QtCore import QSize

from yt_downloader.qt_quick.previews import PreviewImages, QtPreviewSession


def _png() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (16, 9), "#5684a7").save(output, format="PNG")
    return output.getvalue()


class PreviewOwner:
    def __init__(self) -> None:
        self.path: Path | None = None
        self.positions: list[tuple[Path | None, float]] = []
        self.first_started = threading.Event()
        self.release_first = threading.Event()
        self.closed = False

    def load(self, path: Path) -> None:
        self.path = path

    def preview_png(self, position, *, cancel, expected_path):
        self.positions.append((expected_path, position))
        if expected_path.name == "first.mp4":
            self.first_started.set()
            self.release_first.wait(2)
        return _png()

    def shutdown(self) -> None:
        self.closed = True
        self.release_first.set()


def test_qt_preview_session_retires_replaced_media_and_publishes_exact_hover_frame(
    tmp_path,
):
    owner = PreviewOwner()
    session = QtPreviewSession("ffmpeg", owner=owner)
    first, second = tmp_path / "first.mp4", tmp_path / "second.mp4"
    try:
        session.load(first)
        assert session.request(100)
        assert session.records == []
        assert session.hover(42.4)
        assert owner.first_started.wait(2)
        session.load(second)
        assert session.records == []
        assert session.request(200)
        assert session.hover(151.2)
        owner.release_first.set()
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            session.poll()
            if session.records and session.records[0]["image"]:
                break
            time.sleep(0.005)
        assert [row["position"] for row in session.records] == [151.2]
        assert [position for path, position in owner.positions if path == second] == [
            151.2
        ]
        assert all(
            row["image"].startswith("image://vodforge-previews/")
            for row in session.records
        )
        image_id = session.records[0]["image"].split("vodforge-previews/", 1)[1]
        size = QSize()
        image = session.images.requestImage(image_id, size, QSize())
        assert not image.isNull() and (size.width(), size.height()) == (16, 9)
        assert not session.request(200)
        assert not session.hover(151.3)
        assert session.hover(180)
        previous_image = session.records[0]["image"]
        assert previous_image
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            session.poll()
            if session.records and session.records[0]["position"] == 180:
                break
            assert session.records[0]["image"] == previous_image
            time.sleep(0.005)
        assert session.records[0]["position"] == 180
        assert session.records[0]["image"]
    finally:
        session.close()
    assert owner.closed


def test_qt_preview_fast_hover_keeps_last_frame_and_coalesces_latest_position(tmp_path):
    owner = PreviewOwner()
    session = QtPreviewSession("ffmpeg", owner=owner)
    path = tmp_path / "second.mp4"
    try:
        session.load(path)
        assert session.request(100)
        assert session.hover(5)
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline and not session.records[0]["image"]:
            session.poll()
            time.sleep(0.005)
        first_image = session.records[0]["image"]
        assert first_image
        assert session.hover(20)
        assert session.hover(30)
        assert session.records[0]["image"] == first_image
        while time.monotonic() < deadline and session.records[0]["position"] != 30:
            session.poll()
            time.sleep(0.005)
        assert session.records[0]["position"] == 30
        assert session.records[0]["image"]
        assert owner.positions[-1] == (path, 30)
    finally:
        session.close()


def test_qt_preview_images_reject_oversized_or_invalid_data():
    images = PreviewImages()
    assert not images.put("bad", b"not png")
    output = io.BytesIO()
    Image.new("RGB", (513, 9)).save(output, format="PNG")
    assert not images.put("large", output.getvalue())
    missing = images.requestImage("missing", QSize(), QSize())
    assert not missing.isNull()
    assert missing.pixelColor(0, 0).alpha() == 0
