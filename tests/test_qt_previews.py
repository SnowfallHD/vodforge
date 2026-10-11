"""Qt handoff keeps preview images tied to the current saved media."""

from __future__ import annotations

import io
import threading
import time
from pathlib import Path

import pytest
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


@pytest.mark.usefixtures("production_telemetry_contract")
@pytest.mark.parametrize(
    "context",
    [
        "granted",
        "unavailable",
        "denied",
        "regranted",
        "replaced",
        "not_presented",
        "sink_failed",
    ],
)
def test_preview_observation_requires_current_visible_result_and_original_consent(
    tmp_path, context
):
    from tests.test_presentation_diagnostics import real_owner
    from tests.test_qt_telemetry_coverage import rows
    from yt_downloader.analytics_consent import AnalyticsConsentOwner

    owner = PreviewOwner()
    telemetry = real_owner(tmp_path / "telemetry", permitted=context != "denied")
    session = QtPreviewSession("ffmpeg", owner=owner)
    session.product_telemetry = telemetry
    if context == "sink_failed":

        class Broken:
            def bind_feature(self, *_args):
                raise OSError("PRIVATE sink")

        session.product_telemetry = Broken()
    if context == "unavailable":
        owner.preview_png = lambda *_args, **_kwargs: None
    try:
        session.load(tmp_path / "first.mp4")
        assert session.request(100)
        assert session.hover(42)
        if context != "unavailable":
            assert owner.first_started.wait(1)
        assert not session.presented("PRIVATE stale image", True)
        if context in {"denied", "regranted"}:
            consent = AnalyticsConsentOwner(tmp_path / "telemetry")
            if context == "regranted":
                consent.choose(False)
                telemetry.set_enabled(False)
            consent.choose(True)
            telemetry.set_enabled(True)
        if context == "replaced":
            session.load(tmp_path / "second.mp4")
        owner.release_first.set()
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            if session.poll() or not session._work.busy:
                break
            time.sleep(0.005)
        assert not rows_without_shutdown(telemetry, tmp_path)
        if context not in {"replaced", "not_presented"}:
            image = session.records[0]["image"]
            session.presented(image, bool(image))
            session.presented(image, bool(image))
        actual = rows(telemetry, tmp_path, "player")
        assert [row["action"] for row in actual] == (
            ["hover_preview_shown"]
            if context == "granted"
            else ["hover_preview_unavailable"]
            if context == "unavailable"
            else []
        )
    finally:
        session.close()
        telemetry.shutdown(2)


def rows_without_shutdown(telemetry, tmp_path):
    from yt_downloader.product_telemetry import _load_outbox

    return [
        row
        for row in _load_outbox(tmp_path / "telemetry/events.json")
        if row.feature == "player"
    ]
