"""Actual format-specific Options geometry survives live format transitions."""

import json
import os
from copy import deepcopy
from pathlib import Path

import pytest
from PySide6.QtCore import QObject, QPointF, Qt
from PySide6.QtTest import QTest

from tests.test_qt_interaction_invariants import _close, _launch
from tests.test_qt_scene_port import polish_scene, visual_item


@pytest.mark.parametrize("audio_format", ["MP3", "Original audio"])
@pytest.mark.parametrize("size", [(1100, 740), (820, 560)])
def test_options_supported_controls_survive_live_format_round_trip(
    tmp_path, monkeypatch, audio_format, size
):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    output = (
        Path(__file__).resolve().parents[1]
        / "build/options-rendered-regression-20261018/transitions"
    )
    if root := os.environ.get("VODFORGE_OPTIONS_ARTIFACT_ROOT"):
        output = Path(root) / "transitions"
    output.mkdir(parents=True, exist_ok=True)
    stem = f"{audio_format.replace(' ', '-')}-{size[0]}"
    app, bridge, engine, window = _launch(tmp_path, monkeypatch, [])
    observations = []
    from tests.test_run_identity import make_job

    active_job = make_job(tmp_path)
    bridge._runtime.active_job = active_job
    active_before = deepcopy(active_job)

    def settle():
        QTest.qWait(90)
        for _ in range(3):
            app.processEvents()
            polish_scene(window.contentItem())

    def rect(item, parent):
        point = item.mapToItem(parent, QPointF(0, 0))
        return [point.x(), point.y(), item.width(), item.height()]

    try:
        window.resize(*size)
        settle()
        trigger = window.findChild(QObject, "forgeOptionsButton")
        QTest.mouseClick(
            window,
            Qt.LeftButton,
            pos=trigger.mapToScene(
                QPointF(trigger.width() / 2, trigger.height() / 2)
            ).toPoint(),
        )
        popup = window.findChild(QObject, "optionsMenu")
        settle()
        assert popup.property("visible")
        settings = window.findChild(QObject, "downloadSettingsPopup")
        first_mp4 = None
        for phase, format_name in enumerate(("MP4", audio_format, "MP4")):
            bridge.setOutputFormat(format_name)
            settle()
            assert popup.property("visible") and not settings.property("visible")
            mp4 = format_name == "MP4"
            assert popup.property("sideBySideExtras")
            controls = {}
            viewport = window.findChild(QObject, "composerExtrasScroll").property(
                "contentItem"
            )
            viewport.setProperty("contentY", 0)
            settle()
            record = {"format": format_name, "side_by_side": True, "controls": controls}
            observations.append(record)
            content = popup.property("contentItem")
            groups = {
                name: visual_item(window.contentItem(), name)
                for name in (
                    "composerOutputModes",
                    "composerQualities",
                    "composerQuickExtras",
                )
            }
            assert groups["composerOutputModes"].isVisible() == mp4
            assert groups["composerQualities"].isVisible() == mp4
            assert groups["composerQuickExtras"].isVisible()
            if mp4:
                mode, quality, extras = [
                    groups[name]
                    for name in (
                        "composerOutputModes",
                        "composerQualities",
                        "composerQuickExtras",
                    )
                ]
                positions = [rect(item, content) for item in (mode, quality, extras)]
                assert positions[1][0] >= positions[0][0] + positions[0][2] + 15
                assert positions[2][0] >= positions[1][0] + positions[1][2] + 15
                assert max(p[1] for p in positions) - min(p[1] for p in positions) < 1
                if first_mp4 is None:
                    first_mp4 = positions
                else:
                    assert positions == first_mp4
                record["columns"] = positions
            expected = [
                "composerYouTubeAccessButton",
                "composerDownloadOption_single_video_only",
                "composerExtraTagsInput",
                "composerAllSettingsButton",
            ]
            if mp4:
                expected += [
                    "composerDownloadOption_embed_thumbnail",
                    "composerDownloadOption_embed_metadata",
                    "composerDownloadOption_write_thumbnail",
                    "composerDownloadOption_write_info_json",
                    "composerTranslatedSubtitleButton",
                ]
            elif format_name == "MP3":
                expected += [
                    "composerMp3Option_" + key
                    for key in (
                        "mp3_quality",
                        "mp3_sample_rate",
                        "mp3_channels",
                        "mp3_cover_art_mode",
                    )
                ]
                expected += ["composerMp3Metadata"]
            for name in expected:
                item = visual_item(window.contentItem(), name)
                assert item is not None and item.isVisible(), name
                scroll_name = (
                    "composerOptionsScroll"
                    if (
                        name.startswith("composerMp3")
                        or (
                            format_name == "Original audio"
                            and name
                            in (
                                "composerYouTubeAccessButton",
                                "composerDownloadOption_single_video_only",
                            )
                        )
                    )
                    else "composerExtrasScroll"
                )
                viewport = window.findChild(QObject, scroll_name).property(
                    "contentItem"
                )
                point = item.mapToItem(viewport, QPointF(0, item.height() / 2))
                viewport.setProperty(
                    "contentY",
                    min(
                        max(0, viewport.property("contentHeight") - viewport.height()),
                        max(
                            0,
                            viewport.property("contentY")
                            + point.y()
                            - viewport.height() / 2,
                        ),
                    ),
                )
                settle()
                bounds = rect(item, viewport)
                controls[name] = bounds
                assert bounds[2] > 0 and bounds[3] > 0, name
                assert 0 <= bounds[0] + bounds[2] / 2 < viewport.width(), (name, bounds)
                assert 0 <= bounds[1] + bounds[3] / 2 < viewport.height(), (
                    name,
                    bounds,
                )
            quick = visual_item(
                window.contentItem(), "composerDownloadOption_single_video_only"
            )
            viewport = window.findChild(
                QObject,
                "composerOptionsScroll"
                if format_name == "Original audio"
                else "composerExtrasScroll",
            ).property("contentItem")
            viewport.setProperty("contentY", 0)
            settle()
            previous = bridge.downloadOptions["single_video_only"]
            QTest.mouseClick(
                window,
                Qt.LeftButton,
                pos=quick.mapToScene(
                    QPointF(quick.width() / 2, quick.height() / 2)
                ).toPoint(),
            )
            assert bridge.downloadOptions["single_video_only"] != previous
            assert (
                bridge._runtime.active_job is active_job and active_job == active_before
            )
            assert len(window.findChildren(QObject, "composerYouTubeAccessButton")) == 1
            assert (
                len(
                    window.findChildren(
                        QObject, "composerDownloadOption_single_video_only"
                    )
                )
                == 1
            )
            assert window.grabWindow().save(str(output / f"{stem}-{phase}.png"))
            assert len(window.findChildren(QObject, "composerQuickExtras")) == 1
            assert len(window.findChildren(QObject, "composerExtraTagsInput")) == 1
    finally:
        (output / (stem + ".json")).write_text(
            json.dumps(observations, indent=2) + "\n"
        )
        _close(bridge, engine, window)


@pytest.mark.parametrize("output_format", ["MP3", "Original audio"])
@pytest.mark.parametrize("size", [(1100, 740), (820, 560)])
def test_audio_options_has_two_meaningful_columns(
    tmp_path, monkeypatch, output_format, size
):
    output = (
        Path(__file__).resolve().parents[1] / "build/options-audio-columns-20261018"
    )
    output.mkdir(parents=True, exist_ok=True)
    _app, bridge, engine, window = _launch(tmp_path, monkeypatch, [])
    record = {"format": output_format, "size": size}
    stem = f"{output_format.replace(' ', '-')}-{size[0]}"
    try:
        window.resize(*size)
        bridge.setOutputFormat(output_format)
        QTest.qWait(100)
        button = window.findChild(QObject, "forgeOptionsButton")
        QTest.mouseClick(
            window,
            Qt.LeftButton,
            pos=button.mapToScene(
                QPointF(button.width() / 2, button.height() / 2)
            ).toPoint(),
        )
        QTest.qWait(120)
        polish_scene(window.contentItem())
        QTest.qWait(200)
        popup = window.findChild(QObject, "optionsMenu")
        left = visual_item(window.contentItem(), "composerAudioOptions")
        right = visual_item(window.contentItem(), "composerQuickExtras")
        record.update(
            side_by_side=popup.property("sideBySideExtras"),
            left_exists=left is not None,
            right_visible=right.isVisible(),
        )
        assert window.grabWindow().save(str(output / (stem + ".png")))
        assert popup.property("sideBySideExtras"), record
        assert left is not None and left.isVisible()
        point = right.mapToScene(QPointF(0, 0))
        left_point = left.mapToScene(QPointF(0, 0))
        record.update(
            left=[left_point.x(), left_point.y(), left.width(), left.height()],
            right=[point.x(), point.y(), right.width(), right.height()],
        )
        assert point.x() >= left_point.x() + left.width() + 15
        assert abs(point.y() - left_point.y()) < 1
        assert left.width() >= 200 and right.width() >= 200
        assert not visual_item(window.contentItem(), "composerOutputModes").isVisible()
        assert not visual_item(window.contentItem(), "composerQualities").isVisible()
        record["shared"] = {}
        for name in (
            "composerYouTubeAccessButton",
            "composerDownloadOption_single_video_only",
            "composerExtraTagsInput",
            "composerAllSettingsButton",
        ):
            item = visual_item(window.contentItem(), name)
            ancestors = []
            ancestor = item
            while ancestor is not None:
                ancestors.append(
                    {
                        "name": ancestor.objectName(),
                        "visible": ancestor.isVisible(),
                        "opacity": ancestor.opacity(),
                        "clip": ancestor.clip(),
                        "x": ancestor.x(),
                        "y": ancestor.y(),
                        "width": ancestor.width(),
                        "height": ancestor.height(),
                    }
                )
                ancestor = ancestor.parentItem()
            record["shared"][name] = ancestors
            assert item.isVisible(), (name, ancestors)
            target = window.findChild(
                QObject,
                "composerOptionsScroll"
                if output_format == "Original audio"
                and name
                in (
                    "composerYouTubeAccessButton",
                    "composerDownloadOption_single_video_only",
                )
                else "composerExtrasScroll",
            ).property("contentItem")
            position = item.mapToItem(
                target, QPointF(item.width() / 2, item.height() / 2)
            )
            assert (
                0 <= position.x() < target.width()
                and 0 <= position.y() < target.height()
            ), (name, position, ancestors)
        frame = window.grabWindow()
        record["control_paint"] = {}
        for name in ("composerYouTubeAccessButton", "composerAllSettingsButton"):
            item = visual_item(window.contentItem(), name)
            origin = item.mapToScene(QPointF(0, 0))
            bright = sum(
                frame.pixelColor(x, y).lightness() > 170
                for x in range(int(origin.x()) + 8, int(origin.x() + item.width()) - 8)
                for y in range(int(origin.y()) + 8, int(origin.y() + item.height()) - 8)
            )
            record["control_paint"][name] = bright
            record.setdefault("caption", {})[name] = [
                {
                    "text": child.property("text"),
                    "visible": child.property("visible"),
                    "opacity": child.property("opacity"),
                    "width": child.property("width"),
                    "height": child.property("height"),
                    "color": str(child.property("color")),
                }
                for child in item.findChildren(QObject)
                if child.objectName() == "stoneButtonCaption"
            ]
            assert bright > 10, (name, bright, record)
        if output_format == "Original audio":
            access = visual_item(window.contentItem(), "composerYouTubeAccessButton")
            assert access.mapToScene(QPointF(0, 0)).x() < point.x()
            assert not any(
                item.property("text")
                == "Keep the source audio without extra compression."
                for item in window.findChildren(QObject)
            )
    finally:
        (output / (stem + ".json")).write_text(json.dumps(record, indent=2) + "\n")
        _close(bridge, engine, window)


@pytest.mark.parametrize("width", [1100, 820])
def test_mp3_format_entry_reuses_the_canonical_options_owner(
    tmp_path, monkeypatch, width
):
    _app, bridge, engine, window = _launch(tmp_path, monkeypatch, [])
    try:
        from tests.test_run_identity import make_job

        job = make_job(tmp_path)
        bridge._runtime.active_job = job
        before = deepcopy(job)
        window.resize(width, 740)
        QTest.qWait(80)
        field = visual_item(window.contentItem(), "forgeUrlField")

        def descendants(item):
            for child in item.childItems():
                yield child
                yield from descendants(child)

        trigger = next(
            item for item in descendants(field) if item.property("label") == "MP4  ▾"
        )
        QTest.mouseClick(
            window,
            Qt.LeftButton,
            pos=trigger.mapToScene(
                QPointF(trigger.width() / 2, trigger.height() / 2)
            ).toPoint(),
        )
        QTest.qWait(80)
        menu = window.findChild(QObject, "forgeFormatPopup")
        choice = next(
            item
            for item in descendants(menu.property("contentItem"))
            if item.property("label") == "MP3"
        )
        QTest.mouseClick(
            window,
            Qt.LeftButton,
            pos=choice.mapToScene(
                QPointF(choice.width() / 2, choice.height() / 2)
            ).toPoint(),
        )
        QTest.qWait(120)
        assert bridge.outputFormat == "MP3"
        assert window.findChild(QObject, "optionsMenu").property("visible")
        assert not window.property("menuNavigationAllowed")
        assert window.findChild(QObject, "mp3OptionsPopup") is None
        assert visual_item(
            window.contentItem(), "composerMp3Option_mp3_quality"
        ).isVisible()
        assert bridge._runtime.active_job is job and job == before
        output = Path(os.environ.get("VODFORGE_OPTIONS_ARTIFACT_ROOT", str(tmp_path)))
        output.mkdir(parents=True, exist_ok=True)
        assert window.grabWindow().save(str(output / f"canonical-mp3-{width}.png"))
    finally:
        _close(bridge, engine, window)


@pytest.mark.parametrize("width", [1100, 820])
def test_original_audio_format_is_identifiable_before_and_inside_options(
    tmp_path, monkeypatch, width
):
    _app, bridge, engine, window = _launch(tmp_path, monkeypatch, [])
    try:
        window.resize(width, 740)
        bridge.setOutputFormat("Original audio")
        QTest.qWait(100)
        polish_scene(window.contentItem())
        field = visual_item(window.contentItem(), "forgeUrlField")

        def descendants(item):
            for child in item.childItems():
                yield child
                yield from descendants(child)

        trigger = next(
            item
            for item in descendants(field)
            if item.property("label") == "Original audio  ▾"
        )
        caption = trigger.findChild(QObject, "stoneButtonCaption")
        assert caption is not None and not caption.property("truncated")
        button = window.findChild(QObject, "forgeOptionsButton")
        QTest.mouseClick(
            window,
            Qt.LeftButton,
            pos=button.mapToScene(
                QPointF(button.width() / 2, button.height() / 2)
            ).toPoint(),
        )
        QTest.qWait(120)
        heading = visual_item(window.contentItem(), "composerAudioFormatHeading")
        assert heading is not None and heading.property("text") == "ORIGINAL AUDIO"
        assert heading.isVisible()
        assert not visual_item(window.contentItem(), "composerOutputModes").isVisible()
        assert not visual_item(window.contentItem(), "composerQualities").isVisible()
        assert bridge.outputFormat == "Original audio"
        output = Path(os.environ.get("VODFORGE_OPTIONS_ARTIFACT_ROOT", str(tmp_path)))
        output.mkdir(parents=True, exist_ok=True)
        assert window.grabWindow().save(
            str(output / f"original-format-context-{width}.png")
        )
    finally:
        _close(bridge, engine, window)
