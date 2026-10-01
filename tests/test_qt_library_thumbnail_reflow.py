"""Painted-pixel continuity and bounded admission during Library column reflow."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize("count,scroll", [(72, 1900), (2000, 1900), (2000, 90000)])
def test_library_column_reflow_keeps_painted_owners_bounded(tmp_path, count, scroll):
    result = subprocess.run(
        [sys.executable, __file__, "--probe", str(tmp_path), str(count), str(scroll)],
        env={
            **os.environ,
            "QT_QPA_PLATFORM": "offscreen",
            "QT_QUICK_BACKEND": "software",
            "QT_QUICK_CONTROLS_STYLE": "Basic",
            "VODFORGE_DISABLE_TELEMETRY": "1",
            "HOME": str(tmp_path),
            "LOCALAPPDATA": str(tmp_path),
            "PYTHONPATH": str(Path(__file__).resolve().parents[1]),
        },
        capture_output=True,
        text=True,
        # Measured Intel software CI needs up to91s for fixture creation,
        # scene setup, 153 pixel captures and detail/return assertions. This
        # whole-process guard is not a native resize-latency qualification.
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, result.stdout[-3000:] + result.stderr[-3000:]
    proof = json.loads((tmp_path / "proof.json").read_text())
    assert not proof["blank_faces"], proof["blank_faces"]
    assert proof["max_delegates"] <= proof["max_cap"] < count
    assert proof["selection_retained"]
    assert proof["scroll_return_error"] < 1
    assert proof["scroll_cycle_error"] < 1
    assert proof["survivor_replacements"] == 0
    assert proof["hidden_scene_scroll_error"] < 1


def probe(output: Path, count: int, scroll: int) -> None:
    import math
    import shutil
    import statistics
    import time
    from collections import Counter

    started = time.monotonic()

    def phase(name):
        evidence = {
            "phase": name,
            "elapsed_seconds": time.monotonic() - started,
            "count": count,
            "scroll": scroll,
        }
        with (output / "phases.jsonl").open("a") as stream:
            stream.write(json.dumps(evidence) + "\n")
        print(json.dumps(evidence), flush=True)

    phase("imports_started")
    from PySide6.QtCore import QCoreApplication, QEvent, QObject, QPointF, QUrl, Slot
    from PySide6.QtGui import QColor, QGuiApplication, QImage
    from PySide6.QtQml import QQmlApplicationEngine
    from PySide6.QtTest import QTest
    from shiboken6 import getCppPointer

    from yt_downloader.qt_quick import main

    try:
        import resource
    except ImportError:  # Windows does not expose process rusage.
        resource = None

    def descendants(item):
        yield item
        for child in item.childItems():
            yield from descendants(child)

    phase("imports_ready")
    # Instrument a disposable QML copy, never product source.
    qml = output / "qml"
    shutil.copytree(Path(main.__file__).parent, qml)

    class PaintCounter(QObject):
        def __init__(self):
            super().__init__()
            self.counts = Counter()

        @Slot(str)
        def hit(self, kind):
            self.counts[kind] += 1

    phase("qml_copy_ready")
    counter = PaintCounter()
    artwork = qml / "ArtworkImage.qml"
    artwork.write_text(
        artwork.read_text()
        .replace("onPaint: {", 'onPaint: { reflowCounter.hit("paint");')
        .replace(
            "id: artwork",
            'id: artwork\n Component.onCompleted: reflowCounter.hit("created")',
            1,
        )
    )

    class Engine(QQmlApplicationEngine):
        def __init__(self):
            super().__init__()
            self.rootContext().setContextProperty("reflowCounter", counter)

        def load(self, _url):
            super().load(QUrl.fromLocalFile(str(qml / "Main.qml")))

    main.QQmlApplicationEngine = Engine
    app = QGuiApplication([])
    bridge = main.Bridge(None)
    phase("bridge_created")
    bridge._engagement.presented_welcome()
    bridge._settings["whats_new_seen"] = main.SHOWCASE_ID
    bridge._runtime.history = [
        {
            "id": str(i),
            "title": f"Video {i:04d}",
            "channel": "One channel",
            "vodforge_output_dir": str(output),
            "vodforge_output_path": str(output / f"{i}.mp4"),
            "vodforge_output_type": "MP4",
        }
        for i in range(count)
    ]
    phase("records_ready")
    urls, expected = {}, {}
    for i in range(count):
        color = QColor(40 + i % 80, 110 + i % 60, 180 + i % 60)
        image = QImage(320, 180, QImage.Format_RGB32)
        image.fill(color)
        path = output / f"art-{i}.png"
        image.save(str(path))
        url = QUrl.fromLocalFile(str(path)).toString()
        urls[str(i)], expected[url] = url, color.name()
    bridge._artwork.request = lambda record, *_a, **_k: urls[str(record["id"])]
    bridge._artwork.state = lambda *_a: "ready"
    phase("fixture_images_ready")
    engine = main.create_engine(bridge)
    window = engine.rootObjects()[0]
    try:
        window.resize(1100, 740)
        window.show()
        bridge.select("Library")
        bridge.navigateLibrary("videos")
        QTest.qWait(300)
        flow = window.findChild(QObject, "libraryMediaFlow")
        viewport = window.findChild(QObject, "libraryViewport")
        flickable = viewport.property("contentItem")
        scene = flow.parentItem()
        while scene.property("selectedOwners") is None:
            scene = scene.parentItem()
        owner = bridge.libraryScene["media"][0]["owner"]
        scene.setProperty("selectedOwners", [owner])
        scene.setProperty("selectionMode", True)
        QTest.qWait(100)
        flickable.setProperty("contentY", scroll)
        QTest.qWait(500)
        phase("viewport_warmed")
        initial_scroll = flickable.property("contentY")
        counter.counts.clear()
        max_delegates = max_cap = replaced = 0
        blank_faces, timings, frames = [], [], []
        cpu_start = time.process_time()
        before_cards = {}
        widths = (
            [1100] * 3
            + list(range(1100, 919, -12))
            + [920] * 8
            + list(range(920, 1101, 12))
            + [1100] * 8
        ) * 3
        for step, width in enumerate(widths):
            start = time.perf_counter()
            window.resize(width, 740)
            app.processEvents()
            timings.append((time.perf_counter() - start) * 1000)
            QTest.qWait(1)
            frame = window.grabWindow()
            delegates = window.findChild(QObject, "libraryMediaRepeater").property(
                "count"
            )
            cap = (
                math.ceil(viewport.height() / flow.property("rowStride")) + 5
            ) * flow.property("columns")
            assert delegates <= cap
            max_delegates, max_cap = max(max_delegates, delegates), max(max_cap, cap)
            current_cards, frame_bad = {}, []
            for item in descendants(window.contentItem()):
                if (
                    item.objectName() != "libraryMediaArtworkImage"
                    or not item.isVisible()
                ):
                    continue
                source = item.property("source").toString()
                current_cards[source] = getCppPointer(item.parentItem())[0]
                point = item.mapToScene(QPointF(item.width() / 2, item.height() / 2))
                if not 64 < point.y() < window.height() - 20:
                    continue
                pixel = frame.pixelColor(
                    round(point.x() * frame.width() / window.width()),
                    round(point.y() * frame.height() / window.height()),
                ).name()
                if pixel != expected[source]:
                    frame_bad.append([step, width, source.rsplit("/", 1)[-1], pixel])
            for source in set(before_cards) & set(current_cards):
                replaced += before_cards[source] != current_cards[source]
            before_cards = current_cards
            blank_faces.extend(frame_bad)
            frames.append([step, width, delegates, cap, len(frame_bad)])
            if frame_bad and not (output / "before-failure.png").exists():
                frame.save(str(output / "before-failure.png"))
            if step in (0, 6, 40, 142):
                frame.save(str(output / f"frame-{step:03d}.png"))
            QTest.qWait(15)
            if (step + 1) % (len(widths) // 3) == 0:
                phase("resize_cycle_completed")
        phase("resize_cycles_captured")
        cpu_ms = (time.process_time() - cpu_start) * 1000
        final_scroll = flickable.property("contentY")
        detail_owner = bridge.libraryScene["media"][min(count - 1, 30)]["owner"]
        retained = scene.property("selectedOwners")
        retained = retained.toVariant() if hasattr(retained, "toVariant") else retained
        selection_retained = retained == [owner] and scene.property("selectionMode")
        bridge.openLibraryDetails(detail_owner)
        app.processEvents()
        bridge.returnLibraryDetails()
        QTest.qWait(50)
        return_error = abs(flickable.property("contentY") - final_scroll)
        retained = scene.property("selectedOwners")
        retained = retained.toVariant() if hasattr(retained, "toVariant") else retained
        bridge.select("Forge")
        window.resize(1080, 740)
        app.processEvents()
        proof = {
            "count": count,
            "scroll": scroll,
            "frames": frames,
            "blank_faces": blank_faces,
            "max_delegates": max_delegates,
            "max_cap": max_cap,
            "selection_retained": selection_retained,
            "scroll_return_error": return_error,
            "scroll_cycle_error": abs(final_scroll - initial_scroll),
            "initial_scroll": initial_scroll,
            "final_scroll": final_scroll,
            "survivor_replacements": replaced,
            "hidden_scene_scroll_error": abs(
                flickable.property("contentY") - final_scroll
            ),
            "paint_counts": dict(counter.counts),
            "resize_process_p50_ms": statistics.median(timings),
            "resize_process_max_ms": max(timings),
            "cpu_ms_including_grabs": cpu_ms,
            "max_rss_bytes": (
                resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
                * (1 if sys.platform == "darwin" else 1024)
                if resource is not None
                else None
            ),
        }
        (output / "proof.json").write_text(json.dumps(proof, indent=2))
    finally:
        phase("teardown_started")
        window.close()
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        bridge.close()
        phase("teardown_completed")


if __name__ == "__main__":
    probe(Path(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]))
