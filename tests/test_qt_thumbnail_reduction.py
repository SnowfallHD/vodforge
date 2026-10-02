"""Target-sized image filtering preserves owners and bounds derived memory."""

import hashlib
from pathlib import Path
from urllib.parse import urlencode

import pytest
from PIL import Image, ImageDraw
from PySide6.QtCore import QSize, QUrl

from yt_downloader.qt_quick.artwork import ThumbnailReductionProvider


def request(provider, path, width, height, cover=False):
    return provider.requestImage(
        urlencode(
            {
                "source": QUrl.fromLocalFile(str(path)).toString(),
                "w": width,
                "h": height,
                "cover": int(cover),
            }
        ),
        QSize(),
        QSize(),
    )


@pytest.mark.parametrize("dpr", [1, 2])
@pytest.mark.parametrize("dimensions", [(152, 86), (61, 48)])
def test_reduction_removes_aliasing_preserves_original(tmp_path, dpr, dimensions):
    source = tmp_path / "original.png"
    image = Image.new("RGB", (1280, 720))
    draw = ImageDraw.Draw(image)
    for x in range(1280):
        draw.line((x, 0, x, 720), fill="white" if x % 4 < 2 else "black")
    image.save(source)
    before = hashlib.sha256(source.read_bytes()).digest()
    w, h = (n * dpr for n in dimensions)
    result = request(ThumbnailReductionProvider(), source, w, h)
    assert not result.isNull()
    assert result.width() <= w and result.height() <= h
    assert abs(result.width() / result.height() - 1280 / 720) < 0.04
    values = [result.pixelColor(x, 10).red() for x in range(8, result.width() - 8)]
    assert max(values) - min(values) <= 4
    assert hashlib.sha256(source.read_bytes()).digest() == before


def test_cover_geometry_and_source_revision(tmp_path):
    source = tmp_path / "original.png"
    Image.new("RGB", (1280, 720), "red").save(source)
    provider = ThumbnailReductionProvider()
    fit = request(provider, source, 61, 48)
    cover = request(provider, source, 61, 48, True)
    assert (fit.width(), fit.height()) == (61, 34)
    assert (cover.width(), cover.height()) == (85, 48)
    Image.new("RGB", (1280, 720), "blue").save(source)
    changed = request(provider, source, 61, 48)
    assert changed.pixelColor(30, 20).blue() == 255
    assert fit.pixelColor(30, 20).red() == 255


def test_cache_is_bounded_and_nonlocal_requests_rejected(tmp_path):
    provider = ThumbnailReductionProvider()
    source = tmp_path / "original.png"
    Image.new("RGB", (1280, 720), "red").save(source)
    for width in range(50, 150):
        request(provider, source, width, 80)
    assert len(provider._reductions) <= 64
    assert provider._reduction_bytes <= 32 * 1024 * 1024
    assert provider.requestImage(
        "source=https%3A%2F%2Fexample.invalid%2Fimage&w=40&h=40", QSize(), QSize()
    ).isNull()
    assert request(provider, tmp_path / "missing.png", 40, 40).isNull()


@pytest.mark.parametrize("dpr", [1, 2])
def test_qml_uses_physical_size_and_retains_ready_reduction_during_resize(
    tmp_path, dpr
):
    import os
    import subprocess
    import sys

    source = tmp_path / "stripes.png"
    image = Image.new("RGB", (1280, 720))
    draw = ImageDraw.Draw(image)
    for x in range(1280):
        draw.line((x, 0, x, 720), fill="white" if x % 4 < 2 else "black")
    image.save(source)
    script = """
import sys,time,threading
from pathlib import Path
from PySide6.QtCore import QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQuick import QQuickView
from yt_downloader.qt_quick.artwork import ThumbnailReductionProvider
app=QGuiApplication([]);view=QQuickView()
class TrackingProvider(ThumbnailReductionProvider):
 def __init__(self):
  super().__init__();self.threads=[]
 def requestImage(self,*args):
  self.threads.append(threading.get_ident());return super().requestImage(*args)
provider=TrackingProvider()
view.engine().addImageProvider('vodforge-thumbnails',provider)
view.setSource(QUrl.fromLocalFile(str(Path('yt_downloader/qt_quick/ArtworkImage.qml').resolve())))
assert not view.errors()
item=view.rootObject();item.setProperty('inset',0)
item.setWidth(152);item.setHeight(86);view.resize(152,86)
item.setProperty('source',QUrl.fromLocalFile(sys.argv[1]));view.show()
def settle():
 for _ in range(100):app.processEvents();time.sleep(.01)
settle()
assert provider.threads and threading.get_ident() not in provider.threads
url=item.property('adoptedSource').toString()
assert 'w='+str(152*int(sys.argv[2])) in url,url
capture=view.grabWindow()
values=[capture.pixelColor(x,10*int(sys.argv[2])).red() for x in range(20,capture.width()-20)]
assert max(values)-min(values)<=4, (min(values),max(values))
item.setWidth(61);item.setHeight(48);view.resize(61,48)
assert item.property('adoptedSource').toString()==url
settle()
url=item.property('adoptedSource').toString()
assert 'w='+str(61*int(sys.argv[2]))+'&h='+str(48*int(sys.argv[2])) in url,url
item.setProperty('circular',True)
assert item.property('presentedSource')==item.property('source')
view.close()
"""
    result = subprocess.run(
        [sys.executable, "-c", script, str(source), str(dpr)],
        cwd=Path(__file__).resolve().parents[1],
        env={
            **os.environ,
            "QT_QPA_PLATFORM": "offscreen",
            "QT_QUICK_BACKEND": "software",
            "QT_SCALE_FACTOR": str(dpr),
        },
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
