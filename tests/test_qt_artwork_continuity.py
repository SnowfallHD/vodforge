"""Delayed provider responses cannot clear a surviving owner's painted face."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image


@pytest.mark.parametrize("change_owner", [False, True])
@pytest.mark.parametrize("resize", [False, True])
def test_pending_artwork_retains_only_the_same_owner(tmp_path, change_owner, resize):
    Image.new("RGB", (320, 180), (200, 50, 50)).save(tmp_path / "red.png")
    Image.new("RGB", (320, 180), (50, 50, 200)).save(tmp_path / "blue.png")
    result = subprocess.run(
        [
            sys.executable,
            __file__,
            "--probe",
            str(tmp_path),
            str(int(change_owner)),
            str(int(resize)),
        ],
        env={
            **os.environ,
            "HOME": str(tmp_path),
            "LOCALAPPDATA": str(tmp_path),
            "QT_QPA_PLATFORM": "offscreen",
            "QT_QUICK_BACKEND": "software",
            "QT_QUICK_CONTROLS_STYLE": "Basic",
            "PYTHONPATH": str(Path(__file__).resolve().parents[1]),
        },
        capture_output=True,
        text=True,
        check=False,
        timeout=12,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def probe(root: Path, change_owner: bool, resize: bool):
    import time
    from urllib.parse import parse_qs, urlencode

    from PySide6.QtCore import QEventLoop, QMetaObject, QTimer, QUrl
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQuick import QQuickView

    from yt_downloader.qt_quick.artwork import ThumbnailReductionProvider

    class DelayedProvider(ThumbnailReductionProvider):
        def requestImage(self, identifier, size, requested_size):
            # The fixture deliberately uses a provider URL as an owner source.
            # Resize reduction can wrap that synthetic URL; production owner
            # sources are local files. Resolve fixture wrappers while retaining
            # the outer requested geometry and the delayed-load condition.
            params = parse_qs(identifier)
            delayed_request = params.get("delay") == ["1"]
            source = params["source"][0]
            prefix = "image://vodforge-thumbnails/"
            while source.startswith(prefix):
                nested = parse_qs(source[len(prefix) :])
                delayed_request |= nested.get("delay") == ["1"]
                source = nested["source"][0]
            params["source"] = [source]
            if delayed_request:
                time.sleep(0.35)
            return super().requestImage(
                urlencode(params, doseq=True), size, requested_size
            )

    app = QGuiApplication([])
    view = QQuickView()
    view.engine().addImageProvider("vodforge-thumbnails", DelayedProvider())

    def settle(ms):
        loop = QEventLoop()
        QTimer.singleShot(ms, loop.quit)
        loop.exec()

    red = QUrl.fromLocalFile(str(root / "red.png")).toString()
    target = QUrl.fromLocalFile(
        str(root / ("blue.png" if change_owner else "red.png"))
    ).toString()
    delayed = "image://vodforge-thumbnails/" + urlencode(
        {"source": target, "w": 120, "h": 72, "delay": 1}
    )
    component = Path(__file__).resolve().parents[1] / "yt_downloader/qt_quick"
    if os.environ.get("VODFORGE_TEST_CLEAR_PENDING") == "1":
        # Negative control edits only a disposable component, restoring the
        # clear-before-ready fault while retaining all provider/owner behavior.
        copied = root / "fault-component"
        copied.mkdir()
        code = (component / "ArtworkImage.qml").read_text()
        marker = "const drawSource = fresh ? artwork.presentedSource : paintedSource"
        assert marker in code
        (copied / "ArtworkImage.qml").write_text(
            code.replace(
                marker, 'const drawSource = fresh ? artwork.presentedSource : ""'
            )
        )
        component = copied

    qml = root / "probe.qml"
    qml.write_text(f'''import QtQuick
import "{component.as_uri()}"
Rectangle {{ id:frame; width:120;height:72;color:"#202020"
 ArtworkImage {{ id:art; anchors.fill:parent; inset:0; source:"{red}" }}
 Timer {{ id:trigger; interval:0; onTriggered: {{ {"frame.width=140; frame.height=84;" if resize else ""} art.{"source" if change_owner else "adoptedSource"}="{delayed}" }} }}
 function startPending() {{ trigger.start() }}
}}''')
    view.setSource(QUrl.fromLocalFile(str(qml)))
    assert not view.errors()
    view.show()
    settle(600)
    before = view.grabWindow()
    assert before.pixelColor(60, 36).red() == 200
    QMetaObject.invokeMethod(view.rootObject(), "startPending")
    settle(50)
    pending = view.grabWindow()
    pending.save(str(root / "pending.png"))
    pixel = pending.pixelColor(pending.width() // 2, pending.height() // 2)
    if change_owner:
        assert pixel.red() != 200, "old owner remains visible during replacement load"
    else:
        assert pixel.red() == 200 and pixel.blue() == 50, (
            "same-owner artwork cleared while derivative pending"
        )
    # Asynchronous consumers can queue behind the delayed provider. Await the
    # asserted result with a bound; the pending-frame check stays at 50 ms.
    expected_blue = 200 if change_owner else 50
    deadline = time.monotonic() + 4
    while True:
        settle(50)
        final = view.grabWindow()
        if (
            final.pixelColor(final.width() // 2, final.height() // 2).blue()
            == expected_blue
        ):
            break
        if time.monotonic() >= deadline:
            break
    final.save(str(root / "final.png"))
    assert (
        final.pixelColor(final.width() // 2, final.height() // 2).blue()
        == expected_blue
    )
    view.close()
    app.quit()


if __name__ == "__main__":
    probe(Path(sys.argv[2]), bool(int(sys.argv[3])), bool(int(sys.argv[4])))
